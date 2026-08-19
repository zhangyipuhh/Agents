# -*- coding:utf-8 -*-
"""第三方 SSH 同步执行器薄壳（脚本系统专用，2026-08-16 新增）。

背景:
    脚本系统（``app.scripts.server_ops``）以 ``asyncio.to_thread`` 调用同步阻塞
    SSH 执行器；既有 ``app.shared.utils.ssh.executor.execute_script``（paramiko
    本地 SSH）已满足该契约，但走第三方 HTTPS 端点的能力只在 ``SSHTools.execute_command``
    第三方分支中存在且与 LangChain ``ToolRuntime`` / ``LogService._emit_log`` 强
    耦合，不可直接 import 到脚本系统。

    本模块作为「薄壳」复用以下既有单元:
        * :func:`app.shared.utils.executor.third_party_executor.dispatch` ——
          负责端点选取、RSA-OAEP + AES-256-GCM 加解密、HTTPS 调用、响应归一。
        * :func:`app.shared.utils.executor.third_party_executor.normalize_response` ——
          把第三方响应归一为 ``{success, output, exit_code, error?}`` 形态。

薄壳职责:
    * 把 ``async dispatch`` 包装为同步阻塞函数（在 worker 线程中通过 ``asyncio.run``
      驱动,避开 SSHTools 在 LangGraph in-flight loop 中的 ``RuntimeError`` 陷阱）；
    * 把响应归一为与 ``ssh.executor.execute_script`` **同形**的
      :class:`app.shared.utils.ssh.executor.SSHExecResult`,让
      ``server_ops._run_one`` 在两条路径上复用同一套 dataclass 与失败判定逻辑；
    * 显式**不抛出**异常,所有 ``ThirdPartyExecutorError`` 全部封进
      ``SSHExecResult(success=False, exit_code=1, stderr=...)``,使
      ``server_ops._run_one`` 既有「退出码非 0 → crit」判定路径无需再分支
      区分"异常 vs 非零退出"两种语义——非降级策略的稳定基础。
"""
from __future__ import annotations

import asyncio
from typing import Any, Mapping, Optional

# 2026-08-16 修正: 仅 ``import module`` 而不直接导入 ``dispatch`` / ``normalize_response``
# 名称 —— 后者在每次调用时从 ``third_party_executor`` 模块属性读取,便于测试用
# ``monkeypatch.setattr(tp_module, 'dispatch', AsyncMock(...))`` 注入,避免 in-test
# 与生产模块引用不一致(``from X import dispatch`` 会把名称绑定到首次解析的函数对象,
# 后续 monkeypatch 模块属性对它不生效)。``ThirdPartyExecutorError`` 是类引用,
# 直接 import 即可(测试通过构造实例即可,无需 patch 类本身)。
import app.shared.utils.executor.third_party_executor as tp_module
from app.shared.utils.executor.third_party_executor import ThirdPartyExecutorError
from app.shared.utils.ssh.executor import SSHExecResult


def execute_third_party_script(
    config: Mapping[str, Any],
    script: str,
    timeout: Any = None,             # 2026-08-19：参数被忽略，统一走 config["ssh_timeout"]
    *,
    endpoint_name: Optional[str] = None,
) -> SSHExecResult:
    """通过第三方 HTTPS 端点执行巡检脚本,返回与 ``execute_script`` 同形结果。

    参数:
        config: 与 ``execute_script`` 同形;至少含 ``ip`` / ``port`` / ``username``
            / ``password`` / ``server_type`` / ``ssh_timeout``(其中 ``password``
            已在 ``DevOpsServerService.get_connection_config`` 内由 Fernet 解密；
            ``ssh_timeout`` 已由 service 内 ``resolve_ssh_timeout`` 钳制到 ``[1, 120]``,
            缺省 30)。
            允许携带额外键(如 ``business_name`` / 黑/白名单)被忽略。
        script: 远端执行的脚本原文(由 ``inspection_scripts`` 表透传)。
        timeout: **已废弃**(2026-08-19),保留仅为向后兼容签名；运行时从
            ``config["ssh_timeout"]`` 读取。LLM / 脚本层无法覆盖节点配置。
        endpoint_name: 第三方端点名;缺省或空字符串时使用
            ``settings.third_party_executor.default_endpoint``。

    返回:
        SSHExecResult: 与 :func:`app.shared.utils.ssh.executor.execute_script`
        字段完全一致:
            * ``success`` —— ``bool(payload["success"])``
            * ``stdout`` —— ``payload["output"]``(字符串)
            * ``stderr`` —— ``payload["error"]``(可空字符串)
            * ``exit_code`` —— ``int(payload["exit_code"])``

        异常场景下返回 ``SSHExecResult(success=False, stdout="",
        stderr="third_party:<reason>", exit_code=1)``,
        与 ``execute_script`` 在 paramiko 异常路径下的字段约定对齐。

    异常:
        不抛出。``ThirdPartyExecutorError``、``RuntimeError``、``OSError``
        等全部异常封装为 ``SSHExecResult(success=False, exit_code=1)``
        并写入 ``stderr``;调用方无需 ``try/except`` 即可判定。
    """
    # 端点名解析顺序: 入参 → settings 默认。
    # 局部 import settings 避免 third_party_ssh → settings → endpoints → third_party_ssh 循环。
    if not endpoint_name or not str(endpoint_name).strip():
        from app.core.config.settings import settings as _settings
        endpoint_name = _settings.third_party_executor.default_endpoint

    # 2026-08-19 高内聚：直接取 service 给的已钳制值；删手写的 max(1, min(...))
    # 缺省回退 30 / 越界钳制 [1, 120] 已由 ``DevOpsServerService.resolve_ssh_timeout``
    # 统一完成；本函数禁止二次 clamp。
    # ``.get(..., 30)`` 兜底是给测试 fixture 容错（生产 service 必给此字段）。
    safe_timeout = config.get("ssh_timeout") or 30
    business_name = str(config.get("business_name") or "")
    ssh_config = {
        "ip": config.get("ip"),
        "port": config.get("port"),
        "username": config.get("username"),
        "password": config.get("password"),
    }

    async def _call() -> Any:
        """驱动异步 dispatch 完成一次端点请求。"""
        return await tp_module.dispatch(
            endpoint_name=str(endpoint_name),
            command=str(script),
            # 巡检脚本原文已自包含(由 inspection_scripts 表存入),不再二次 wrap
            wrapped_command=str(script),
            business_name=business_name,
            timeout=safe_timeout,
            server_type=config.get("server_type"),
            ssh_config=ssh_config,
        )

    try:
        # asyncio.run 在 worker 线程中执行（server_ops._run_one 通过
        # asyncio.to_thread 切线程池），与 LangGraph in-flight loop 不同场景，
        # 与 SSHTools.execute_command 规避的 RuntimeError 触发条件不同；
        # 此处 asyncio.run 安全。
        resp = asyncio.run(_call())
    except ThirdPartyExecutorError as exc:
        # 不抛异常 —— 把第三方错误封进 SSHExecResult，与 execute_script 在
        # paramiko 异常路径下的行为一致，避免 server_ops._run_one 引入"区分
        # 异常 vs 非零退出"的分支（保持非降级契约的稳定性）。
        return SSHExecResult(
            success=False,
            stdout="",
            stderr=f"third_party:{exc.reason}",
            exit_code=1,
        )
    except Exception as exc:  # noqa: BLE001 - 兜底：所有未预期异常也封进结果，不外抛
        return SSHExecResult(
            success=False,
            stdout="",
            stderr=f"third_party:unexpected:{type(exc).__name__}:{exc}",
            exit_code=1,
        )

    payload = tp_module.normalize_response(resp)
    return SSHExecResult(
        success=bool(payload.get("success")),
        stdout=str(payload.get("output") or ""),
        stderr=str(payload.get("error") or ""),
        exit_code=int(payload.get("exit_code") or 0),
    )
