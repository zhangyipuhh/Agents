#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SSHTools - SSH 远程命令执行工具集（2026-07-15 重写）

职责：
    - 通过 ``DevOpsServerService`` 单例获取目标服务器的配置（IP/端口/用户名/密码/类型/名单）
    - 使用 Paramiko 在目标机器执行 SSH 命令
    - 平台派生：Linux → ``/bin/bash -c '...'``；Windows → ``powershell.exe -NoProfile
      -NonInteractive -ExecutionPolicy Bypass -EncodedCommand <Base64>``(UTF-16 LE),
      与 ``app.shared.utils.ssh.executor.execute_script`` 共享同一 ``wrap_script_for_platform``
      实现,避免双份 naive 包装漂移
    - 决策顺序：黑名单优先（拒绝执行）→ 白名单 allowlist（仅当服务显式配置时启用）
    - 命令批量：任一条命中黑名单 → 整批拒绝（不调用 paramiko）
    - 工具结果不含连接配置（password / ip / username 永不出现在 ToolMessage）

工具清单：
    - execute_command       单条命令执行（Linux/bash 或 Windows/powershell）
    - execute_batch_commands 批量命令执行（任一黑名单命中即整批拒绝）
    - get_system_logs       获取指定类型日志（tail -n <lines> <path>）

注入与发现：
    - 仅使用 ``@tool(description=...)`` 装饰，**不调用** ``register_tool(agent=...)``
    - 工具元数据（module_path / file_path）由 ToolRegistryService 通过源码扫描发现
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from typing import Any, Dict, List, Optional

import paramiko
from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

try:
    # 生产环境：使用真实 ToolMessage
    from langchain_core.messages import ToolMessage as _RealToolMessage
except Exception:  # noqa: BLE001 - 测试环境被 conftest mock 时降级
    _RealToolMessage = None


def _is_real_tool_message_class(cls) -> bool:
    """判断 ``_RealToolMessage`` 是真实类还是 conftest 注入的 ``Mock``。

    测试环境下 ``conftest.py`` 把 ``langchain_core.messages.ToolMessage = Mock()``
    替换为 Mock，导致 ``from langchain_core.messages import ToolMessage`` 拿到 Mock。
    Mock 对象的 ``.mro``、``__bases__`` 等内省属性都不存在或返回 Mock，
    与真实 ``pydantic.BaseModel`` 子类差异巨大。

    Args:
        cls: 候选类对象

    Returns:
        bool: ``cls`` 是否为真正的 pydantic 类
    """
    if cls is None:
        return False
    try:
        from unittest.mock import Mock as _Mock  # noqa: WPS433 - 局部 import 避免循环

        if isinstance(cls, _Mock):
            return False
    except Exception:  # noqa: BLE001
        pass
    return True


_REAL_TOOL_MESSAGE_OK: bool = _is_real_tool_message_class(_RealToolMessage)

from app.shared.tools.skills.devops.CommandInterceptor import (
    CommandBlockedError,
    CommandInterceptor,
)
from app.shared.utils.devops_server_service import DevOpsServerService
from app.shared.utils.log_service import (
    LogEvent,
    LogLevel,
    LogResult,
    LogType,
    get_log_service,
    hash_command,
    redact_command,
)
from app.shared.utils.ssh.platform_shell import wrap_script_for_platform

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 统一审计日志（2026-07-29 落地）
# ---------------------------------------------------------------------------


def _runtime_context(runtime: Any) -> Dict[str, Any]:
    """从 LangChain ``ToolRuntime`` 安全取出 ``context`` 字典（非 dict 时返回 ``{}``）。

    Args:
        runtime: LangChain ``ToolRuntime`` 实例（可能为 ``None``）。

    Returns:
        Dict[str, Any]: ``runtime.context`` 字典副本（可能为空）。
    """
    if runtime is None:
        return {}
    ctx = getattr(runtime, "context", None)
    if isinstance(ctx, dict):
        return ctx
    return {}


def _runtime_tool_call_id(runtime: Any) -> str:
    """从 ``runtime`` 取 ``tool_call_id``，缺失或非 str 时退回 ``"unknown"``。

    Args:
        runtime: LangChain ``ToolRuntime`` 实例（可能为 ``None``）。

    Returns:
        str: 工具调用 ID（永不空）。
    """
    if runtime is None:
        return "unknown"
    raw = getattr(runtime, "tool_call_id", None)
    if isinstance(raw, str) and raw:
        return raw
    return "unknown"


def _runtime_identity(runtime: Any) -> tuple[Optional[int], Optional[str]]:
    """从 ``runtime.context`` 取 ``log_user_id`` / ``log_username``。

    Args:
        runtime: LangChain ``ToolRuntime`` 实例。

    Returns:
        Tuple[Optional[int], Optional[str]]: (user_id, username)，缺失时为 ``None``。
    """
    ctx = _runtime_context(runtime)
    raw_uid = ctx.get("log_user_id")
    raw_name = ctx.get("log_username")
    user_id = raw_uid if isinstance(raw_uid, int) else None
    username = raw_name if isinstance(raw_name, str) and raw_name else None
    return user_id, username


def _runtime_session_id(runtime: Any) -> Optional[str]:
    """从 ``runtime.context`` 取 ``session_id``，非 str 时返回 ``None``。

    Args:
        runtime: LangChain ``ToolRuntime`` 实例。

    Returns:
        Optional[str]: 会话 ID，未识别时 ``None``。
    """
    ctx = _runtime_context(runtime)
    raw = ctx.get("session_id")
    if isinstance(raw, str) and raw:
        return raw
    return None


def _runtime_ip(runtime: Any) -> Optional[str]:
    """从 ``runtime.context`` 取 ``log_ip``，非 str 或全空白时返回 ``None``。

    业务语义（2026-07-30 新增）：与 ``_runtime_identity`` / ``_runtime_session_id``
    同款，从 ``AgentContext.log_ip`` 读取客户端 IP 写入 ``LogEvent.ip_address``。
    来源：``agent_router.chat`` 用 ``request.client.host`` 强制覆盖后的真值，
    禁止信任客户端 context_overrides 提供的 log_ip（已由 router 兜底）。

    Args:
        runtime: LangChain ToolRuntime 实例。

    Returns:
        Optional[str]: 客户端 IP（v4 / v6 文本，已 strip），缺失或非法时为 ``None``。
    """
    ctx = _runtime_context(runtime)
    raw = ctx.get("log_ip")
    if isinstance(raw, str) and raw.strip():
        return raw.strip()
    return None


def _intercept_category(error: CommandBlockedError) -> str:
    """把策略异常归一化为固定拦截类别代码。

    Args:
        error: 命令策略拦截异常。

    Returns:
        str: ``command_blacklisted`` 或 ``command_not_whitelisted``。
    """
    reason = str(error)
    if "不在白名单" in reason:
        return "command_not_whitelisted"
    return "command_blacklisted"


def _redact_intercept_reason(reason: Optional[str]) -> Optional[str]:
    """对 ``intercept_reason`` 做脱敏 + 截断 1000 字符。

    SSHTools 把 ``CommandBlockedError`` 的原始 message 写入 metadata 时,
    其中可能包含原始命令片段(例如 ``子命令[1]='rm -rf /tmp' 不在白名单中``)。
    在写入 metadata 前必须走 ``redact_command`` 避免泄漏原始命令。

    Args:
        reason: 拦截原因文本(可空)。

    Returns:
        Optional[str]: 脱敏并截断到 1000 字符的原因;空输入返回 None。
    """
    if not reason:
        return reason
    sanitized = redact_command(reason)
    if len(sanitized) > 1000:
        sanitized = sanitized[:1000]
    return sanitized


def _emit_batch_failure_with_members(
    *,
    runtime: Any,
    business_name: Optional[str],
    commands: List[str],
    batch_cid: str,
    duration_ms: int,
    stage: str,
    error_code: str,
    intercept_reason: str,
    server_type: Optional[str],
    decision: str = "allowed",
) -> None:
    """批量失败场景统一 emit:1 条汇总 + N 条明细(共享 batch_cid)。

    用于 ``config_unresolved`` / ``auth_failed`` / ``ssh_error`` / ``execution_failed``
    阶段。每个子项 ``result=failure`` / ``decision=allowed`` 或 ``config_failed`` /
    ``error_code=<同阶段>``。

    Args:
        runtime: LangChain ToolRuntime。
        business_name: 业务名(写入 target_name)。
        commands: 子命令列表(用于明细);可空 list 时只发汇总。
        batch_cid: 共享 correlation_id(UUID 字符串)。
        duration_ms: 耗时(毫秒)。
        stage: 阶段标签,如 ``auth_failed`` / ``config_unresolved``;用于汇总决策描述。
        error_code: 错误码,如 ``auth_failed``;汇总 + 明细同步。
        intercept_reason: 失败原因(汇总/明细共享同一原因)。
        server_type: 平台类型(写入 metadata)。
        decision: 明细决策标签;默认 ``allowed``(允许但执行失败),
            config_unresolved 阶段传 ``config_failed``。

    Returns:
        None
    """
    # 1. 先发 N 条明细
    for cmd in commands:
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_batch_member",
                "server_type": server_type,
                "command_redacted": redact_command(cmd),
                "command_hash": hash_command(cmd),
                "decision": decision,
                "intercept_reason": intercept_reason,
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": error_code,
                "stage": stage,
            },
            correlation_id=batch_cid,
        )
    # 2. 再发 1 条汇总
    _emit_log(
        action="ssh_execute_batch",
        result="failure",
        runtime=runtime,
        business_name=business_name,
        metadata={
            "event_type": "execute_batch",
            "server_type": server_type,
            "command_redacted": None,
            "command_hash": None,
            "decision": decision,
            "intercept_reason": intercept_reason,
            "exit_code": None,
            "duration_ms": duration_ms,
            "stdout_size": 0,
            "stderr_size": 0,
            "error_code": error_code,
            "total": len(commands),
            "stage": stage,
        },
        correlation_id=batch_cid,
    )


def _emit_log(
    *,
    action: str,
    result: str,
    runtime: Any,
    business_name: Optional[str],
    metadata: Dict[str, Any],
    correlation_id: Optional[str] = None,
) -> None:
    """通过 ``LogService.emit`` 写入一条 ``log_type='ssh'`` 的审计日志（fail-soft）。

    该函数被 ``execute_command`` / ``execute_batch_commands`` / ``get_system_logs``
    所有终态调用，作为统一的「结构化审计写入口」。内部捕获一切异常并降级为
    ``logger.warning``，避免日志失败污染工具业务响应。

    Args:
        action: 业务动作名（如 ``ssh_execute_command``）。
        result: ``LogResult`` 枚举值字符串（success / failure / blocked / skipped）。
        runtime: LangChain ``ToolRuntime``（用于读 ``tool_call_id`` / ``session_id`` / ``log_user_id`` / ``log_username``）。
        business_name: 业务名（写入 ``target_name``）。
        metadata: 元数据字典，调用方应在传入前填充完约定的固定键集合；
            ``LogService.emit`` 内部会再次做 ``redact_metadata`` 递归脱敏（防止 ``password`` /
            ``stdout`` 等敏感键漏网）。
        correlation_id: 关联批次 ID（批量场景使用）；``None`` 时**不自动生成 UUID**（单命令
            不挂关联 ID，避免污染 ``get_correlated_logs`` 查询语义；批量场景由调用方显式
            传入共享 UUID）。

    Returns:
        None：失败不影响调用方。

    Raises:
        不抛出异常：所有错误均降级为 warning 日志。
    """
    try:
        service = get_log_service()
        if service is None:
            return
        # metadata.intercept_reason 必须经过 redact_command,杜绝原命令残留
        if isinstance(metadata, dict) and "intercept_reason" in metadata:
            metadata["intercept_reason"] = _redact_intercept_reason(
                metadata.get("intercept_reason")
            )
        tool_call_id = _runtime_tool_call_id(runtime)
        user_id, username = _runtime_identity(runtime)
        session_id = _runtime_session_id(runtime)
        # 2026-07-30 新增：审计日志 IP 字段（与 log_user_id / log_username 同款，
        # 由 agent_router 用 request.client.host 强制覆盖）。
        client_ip = _runtime_ip(runtime)
        evt = LogEvent(
            action=action,
            log_type=LogType.SSH,
            result=LogResult(result),
            level=LogLevel.WARNING if result in {"failure", "blocked"} else LogLevel.INFO,
            source="ssh_executor",
            message=action,
            tool_call_id=tool_call_id,
            session_id=session_id,
            correlation_id=correlation_id,
            target_type="devops_server",
            target_name=business_name,
            user_id=user_id,
            username=username,
            ip_address=client_ip,
            metadata=metadata,
        )
        # service.emit 内部已含 redact_metadata 递归脱敏；本函数不重复。
        service.emit(evt)
    except Exception as exc:  # noqa: BLE001 - fail-soft：日志失败不阻断业务
        logger.warning(
            "[SSHTools] emit log failed (action=%s, result=%s): %s",
            action,
            result,
            type(exc).__name__,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_server_config(
    runtime: ToolRuntime, business_name: Optional[str]
) -> Dict[str, Any]:
    """从 ``DevOpsServerService`` 单例解析指定业务的 SSH 连接配置。

    业务名解析容错：
      - 优先使用函数入参 ``business_name``
      - 兜底从 ``runtime.context["business_name"]`` 读取
      - 兜底时要求 ``isinstance(name, str) and name.strip()``,
        防止 MagicMock / None 等异常类型逃过空值检查导致下游 KeyError

    Args:
        runtime: 工具运行时（用于读取 ``context.business_name`` 兜底）
        business_name: 业务名（优先于 ``runtime.context["business_name"]``）

    Returns:
        Dict[str, Any]: ``ip`` / ``port`` / ``username`` / ``password`` /
        ``server_type`` / ``blacklist`` / ``whitelist``

    Raises:
        RuntimeError: 单例未初始化时抛出
        KeyError: 业务名不存在时抛出
        ValueError: Fernet 解密失败时抛出（密钥错配）
    """
    svc = DevOpsServerService.get_instance()
    name = business_name
    # Bug-4 修复:non-str（如 MagicMock / None）一律视为缺失
    if not isinstance(name, str) or not name.strip():
        ctx = getattr(runtime, "context", {}) or {}
        cand = ctx.get("business_name") if isinstance(ctx, dict) else None
        name = cand if isinstance(cand, str) and cand.strip() else None
    if not name:
        # 给一个清晰错误：业务名缺失时不让工具失败得莫名其妙
        raise RuntimeError("business_name 缺失（请通过 tool context 注入）")
    return svc.get_connection_config(name)


def _validate_business_name(business_name: str) -> Optional[str]:
    """校验 ``business_name`` 非空且非纯空白。

    Args:
        business_name: 待校验的业务名

    Returns:
        Optional[str]: 校验失败时返回错误消息；通过时返回 None
    """
    if not business_name or not business_name.strip():
        return "business_name 不能为空"
    return None


def _make_interceptor(config: Dict[str, Any]) -> CommandInterceptor:
    """根据服务器配置构造 ``CommandInterceptor``。

    Args:
        config: ``_resolve_server_config`` 的返回值

    Returns:
        CommandInterceptor: 已配好黑/白名单的拦截器
    """
    blacklist = config.get("blacklist") or []
    whitelist = config.get("whitelist")  # 可能是 None / [] / list
    return CommandInterceptor(blacklist=blacklist, whitelist=whitelist)


def _wrap_for_platform(server_type: str, command: str) -> str:
    """按平台派生真正的 shell 调用命令前缀。

    - ``server_type.lower() == "windows"`` →
      ``powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass
      -EncodedCommand <Base64>``(UTF-16 LE),由 ``app.shared.utils.ssh.platform_shell
      .wrap_script_for_platform`` 统一派生
    - 其他（含 ``linux``） → ``/bin/bash -c '<escaped>'``

    Args:
        server_type: 服务端的 ``server_type`` 字段（来自 service）
        command: 原始用户命令

    Returns:
        str: 已包裹的 shell 调用
    """
    return wrap_script_for_platform(server_type, command)


def _clamp_timeout(timeout: Any, default: int = 30, lo: int = 1, hi: int = 120) -> int:
    """把 LLM 端传入的 timeout 钳制到 ``[lo, hi]`` 区间。

    设计意图:
      - 防止 LLM 误传 ``timeout=999999`` 或负数 / 0 导致工具卡死
      - 非 int 输入（None / str）退回到 ``default``

    Args:
        timeout: 原始 timeout 值
        default: 非整数或越界时的兜底值
        lo: 最小允许值（含）
        hi: 最大允许值（含）

    Returns:
        int: 钳制后的合法 timeout
    """
    try:
        v = int(timeout)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _open_client(config: Dict[str, Any]) -> paramiko.SSHClient:
    """打开一个 Paramiko SSHClient 并返回。

    Args:
        config: SSH 连接配置（含明文 password / 可选 ``ssh_connect_timeout``）

    Returns:
        paramiko.SSHClient: 已建立连接的客户端
    """
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    # Bug-5 修复:连接期显式 timeout,默认 10s；防止对端不可达时工具 hang 死
    connect_timeout = _clamp_timeout(
        config.get("ssh_connect_timeout"), default=10, lo=1, hi=60
    )
    client.connect(
        hostname=config["ip"],
        port=int(config.get("port") or 22),
        username=config["username"],
        password=config["password"],
        timeout=connect_timeout,
        auth_timeout=connect_timeout,
        banner_timeout=connect_timeout,
    )
    return client


def _make_tool_message(
    tool_call_id: str, content: Any
):
    """构造一个消息对象（生产环境用真实的 ``ToolMessage``，测试环境用 duck-typed）。

    Args:
        tool_call_id: 工具调用 ID
        content: ``dict`` 或 ``str`` 内容

    Returns:
        一个带 ``.content`` 与 ``.tool_call_id`` 属性的对象
    """
    if isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    if _REAL_TOOL_MESSAGE_OK:
        return _RealToolMessage(content=text, tool_call_id=tool_call_id)  # type: ignore[misc]  # noqa: ERA001 - 真实类已确认

    # 降级：测试环境 conftest 把 ``ToolMessage`` mock 为 MagicMock，
    # 实际构造出来的对象 ``.content`` 也是 Mock。为此提供 duck-typed 实现：
    class _DuckMessage:
        """简易消息载体，提供 ``content`` 与 ``tool_call_id`` 属性。"""

        def __init__(self, content: str, tool_call_id: str) -> None:
            self.content = content
            self.tool_call_id = tool_call_id

        def __repr__(self) -> str:
            return f"<_DuckMessage tool_call_id={self.tool_call_id!r} content={self.content[:80]!r}>"

    return _DuckMessage(text, tool_call_id)


# ---------------------------------------------------------------------------
# Tool: execute_command
# ---------------------------------------------------------------------------


@tool(description="在已配置的远程服务器上执行单条命令（Linux/bash 或 Windows/powershell）。")
def execute_command(
    command: str,
    business_name: str,
    timeout: int = 30,
    runtime: ToolRuntime = None,
) -> Command:
    """在远程服务器执行单条命令。

    步骤：
      1) 通过 ``DevOpsServerService`` 取连接配置（**忽略调用方传入的 server_type**）
      2) ``CommandInterceptor`` 黑名单优先 → 白名单 allowlist
      3) 平台派生（Linux/bash 或 Windows/powershell）
      4) **2026-08-03 新增**：根据 ``runtime.context["use_third_party_executor"]``
         决定走第三方 HTTPS 调用（请求体加密，RSA-OAEP + AES-256-GCM），
         还是走本地 paramiko.exec_command
      5) 把执行结果（无敏感字段）封装为 ``ToolMessage`` 返回 Command

    Args:
        command: 待执行的命令字符串
        business_name: 业务名（必填，不可为空）
        timeout: 命令执行超时（秒）
        runtime: LangChain ToolRuntime（langchain runtime 自动注入）。
            context 中支持：
              - ``use_third_party_executor`` (bool): True → 走第三方 HTTPS 调用
              - ``third_party_endpoint_name`` (str): 第三方端点名；缺省取
                ``settings.third_party_executor.default_endpoint``

    Returns:
        Command: 包含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    err = _validate_business_name(business_name)
    if err:
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": None,
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "rejected",
                "intercept_reason": err,
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "invalid_business_name",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id, {"success": False, "error": err}
                    )
                ]
            }
        )
    try:
        config = _resolve_server_config(runtime, business_name)
    except Exception:  # noqa: BLE001 - Bug-3 修复:覆盖 ValueError（Fernet 密钥错配）等所有异常,统一返回通用错误避免密钥错配细节泄漏
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": None,
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "rejected",
                "intercept_reason": "无法解析服务器配置",
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "config_unresolved",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    interceptor = _make_interceptor(config)
    try:
        interceptor.check_and_raise(command)
    except CommandBlockedError as e:
        _emit_log(
            action="ssh_execute_command",
            result="blocked",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "blocked",
                "intercept_reason": _intercept_category(e),
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "blocked",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": f"命令被拦截: {e}",
                            "blocked": True,
                        },
                    )
                ]
            }
        )

    # 平台派生（service 决定 platform）
    wrapped = _wrap_for_platform(config["server_type"], command)
    # Bug-5 修复:LLM 端 timeout 钳制到 [1, 120]
    safe_timeout = _clamp_timeout(timeout, default=30, lo=1, hi=120)
    # 2026-08-03 新增：通过 runtime.context 控制是否走第三方执行器（加密 body 调用 HTTPS）。
    # 默认 False → 走本地 Paramiko（保持向后兼容）；True → 跳过本地 SSH，由第三方执行。
    ctx = _runtime_context(runtime)
    use_third_party = bool(ctx.get("use_third_party_executor"))

    if use_third_party:
        # ===== 第三方分支（2026-08-03 新增）=====
        endpoint_name = ctx.get("third_party_endpoint_name")
        if not isinstance(endpoint_name, str) or not endpoint_name.strip():
            from app.core.config.settings import settings as _settings

            endpoint_name = _settings.third_party_executor.default_endpoint
        started = time.monotonic()
        try:
            import asyncio as _asyncio
            from app.shared.utils.executor.third_party_executor import (
                dispatch as _tp_dispatch,
                normalize_response as _tp_normalize,
            )

            # execute_command 是同步函数,通过 asyncio.run 包装异步 dispatch。
            # 若当前已处于事件循环（agent runtime 内），则改用 run_until_complete 走现有 loop
            # （避免 RuntimeError: asyncio.run() cannot be called from a running event loop）。
            try:
                _loop = _asyncio.get_running_loop()
                _in_loop = True
            except RuntimeError:
                _in_loop = False

            if _in_loop:
                # 当前已在一个 event loop 内,直接 await coro（LangChain agent runtime 同步
                # 调用工具函数的场景不进入此分支；此处为 future-proof）
                resp_coro = _tp_dispatch(
                    endpoint_name=endpoint_name,
                    command=command,
                    wrapped_command=wrapped,
                    business_name=business_name,
                    timeout=safe_timeout,
                    server_type=config.get("server_type"),
                )
                resp = _asyncio.run_coroutine_threadsafe(
                    _asyncio.ensure_future(resp_coro), _loop
                ).result()
            else:
                resp = _asyncio.run(
                    _tp_dispatch(
                        endpoint_name=endpoint_name,
                        command=command,
                        wrapped_command=wrapped,
                        business_name=business_name,
                        timeout=safe_timeout,
                        server_type=config.get("server_type"),
                    )
                )
            payload = _tp_normalize(resp)
            duration_ms = int((time.monotonic() - started) * 1000)
            success = bool(payload.get("success"))
            output_text = payload.get("output") or ""
            err_text = payload.get("error") or ""
            stdout_size = len(output_text.encode("utf-8")) if output_text else 0
            stderr_size = len(err_text.encode("utf-8")) if err_text else 0
            _emit_log(
                action="ssh_execute_command",
                result="success" if success else "failure",
                runtime=runtime,
                business_name=business_name,
                metadata={
                    "event_type": "execute_command",
                    "server_type": config.get("server_type"),
                    "command_redacted": redact_command(command),
                    "command_hash": hash_command(command),
                    "decision": "executed",
                    "intercept_reason": None,
                    "exit_code": payload.get("exit_code"),
                    "duration_ms": duration_ms,
                    "stdout_size": stdout_size,
                    "stderr_size": stderr_size,
                    "error_code": None if success else "non_zero_exit",
                    "executor_type": "third_party",
                    "third_party_endpoint": endpoint_name,
                },
            )
            return Command(
                update={
                    "messages": [
                        _make_tool_message(tool_call_id, payload)
                    ]
                }
            )
        except Exception as tp_exc:  # noqa: BLE001 - 第三方调用失败统一降级
            from app.shared.utils.executor.errors import (
                ThirdPartyExecutorError,
            )

            duration_ms = int((time.monotonic() - started) * 1000)
            if isinstance(tp_exc, ThirdPartyExecutorError):
                error_code = tp_exc.error_code
                intercept_reason = tp_exc.reason
                user_message = tp_exc.user_message
            else:
                error_code = "third_party_unexpected_error"
                intercept_reason = (
                    f"{type(tp_exc).__name__}: {tp_exc}"
                )
                user_message = "第三方调用异常"
            _emit_log(
                action="ssh_execute_command",
                result="failure",
                runtime=runtime,
                business_name=business_name,
                metadata={
                    "event_type": "execute_command",
                    "server_type": config.get("server_type"),
                    "command_redacted": redact_command(command),
                    "command_hash": hash_command(command),
                    "decision": "executed",
                    "intercept_reason": intercept_reason,
                    "exit_code": None,
                    "duration_ms": duration_ms,
                    "stdout_size": 0,
                    "stderr_size": 0,
                    "error_code": error_code,
                    "executor_type": "third_party",
                    "third_party_endpoint": endpoint_name,
                },
            )
            return Command(
                update={
                    "messages": [
                        _make_tool_message(
                            tool_call_id,
                            {"success": False, "error": user_message},
                        )
                    ]
                }
            )

    # ===== 本地 Paramiko SSH 分支（原行为完全保留）=====
    client = None
    started = time.monotonic()
    try:
        client = _open_client(config)
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
        # Windows OpenSSH 非 PTY 通道下远端 shell 会等待 stdin EOF 才退出,
        # 不关闭写端 read() 将阻塞至超时;命令不读 stdin,关闭写端无副作用。
        stdin.close()
        output = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        duration_ms = int((time.monotonic() - started) * 1000)
        # 2026-07-29 统一语义:成功 = exit_code == 0,stderr 不改变成功语义
        # (Linux /root/.bashrc 注释噪声或 cron stderr 警告都不应让 exit 0 命令被视为失败)。
        success = exit_code == 0
        stdout_size = len(output.encode("utf-8")) if output else 0
        stderr_size = len(err.encode("utf-8")) if err else 0
        payload: Dict[str, Any] = {
            "success": success,
            "output": output,
            "exit_code": exit_code,
        }
        if err:
            payload["error"] = err
        _emit_log(
            action="ssh_execute_command",
            result="success" if success else "failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "executed",
                "intercept_reason": None,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "stdout_size": stdout_size,
                "stderr_size": stderr_size,
                # 仅当 exit_code != 0 时 error_code = non_zero_exit;stderr 有噪音但 exit 0 时仍 success
                "error_code": None if success else "non_zero_exit",
            },
        )
        return Command(
            update={"messages": [_make_tool_message(tool_call_id, payload)]}
        )
    except paramiko.AuthenticationException:
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "executed",
                "intercept_reason": "SSH 认证失败",
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "auth_failed",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 认证失败"},
                    )
                ]
            }
        )
    except paramiko.SSHException:
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "executed",
                "intercept_reason": "SSH 连接错误",
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "ssh_error",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 连接错误"},
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 捕获所有并以通用错误返回，避免泄漏 IP/凭据
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_log(
            action="ssh_execute_command",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_command",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(command),
                "command_hash": hash_command(command),
                "decision": "executed",
                "intercept_reason": "远程命令执行失败",
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "execution_failed",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "远程命令执行失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool: execute_batch_commands
# ---------------------------------------------------------------------------


@tool(description="在已配置的远程服务器上批量执行多条命令；任何一条被策略拦截即整批拒绝。")
def execute_batch_commands(
    commands: List[str],
    business_name: str,
    timeout: int = 30,
    runtime: ToolRuntime = None,
) -> Command:
    """批量执行多条 SSH 命令。

    策略：
      - 任一命令被黑名单拦截 → 整个 batch 拒绝（不调 paramiko）
      - 全部通过 → 按顺序执行

    Args:
        commands: 命令字符串列表
        business_name: 业务名（必填，不可为空）
        timeout: 单条命令超时（秒）
        runtime: LangChain ToolRuntime

    Returns:
        Command: 含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    err = _validate_business_name(business_name)
    batch_cid = str(uuid.uuid4())
    if err:
        _emit_log(
            action="ssh_execute_batch",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_batch",
                "server_type": None,
                "command_redacted": None,
                "command_hash": None,
                "decision": "rejected",
                "intercept_reason": err,
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "invalid_business_name",
                "total": 0,
            },
            correlation_id=batch_cid,
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id, {"success": False, "error": err}
                    )
                ]
            }
        )
    # Bug-7 修复:显式校验 commands 非空 list，防止 LLM 误传 None / []
    if not isinstance(commands, list) or not commands:
        _emit_log(
            action="ssh_execute_batch",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_batch",
                "server_type": None,
                "command_redacted": None,
                "command_hash": None,
                "decision": "rejected",
                "intercept_reason": "commands 不能为空",
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "invalid_commands",
                "total": 0,
            },
            correlation_id=batch_cid,
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "commands 不能为空"},
                    )
                ]
            }
        )
    try:
        config = _resolve_server_config(runtime, business_name)
    except Exception:  # noqa: BLE001 - Bug-3 修复:统一吞掉异常,避免泄漏密钥错配等内部细节
        _emit_batch_failure_with_members(
            runtime=runtime,
            business_name=business_name,
            commands=commands,
            batch_cid=batch_cid,
            duration_ms=0,
            stage="config_unresolved",
            error_code="config_unresolved",
            intercept_reason="无法解析服务器配置",
            server_type=None,
            decision="config_failed",
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    interceptor = _make_interceptor(config)

    # 先做拦截；任一被拦 → 整批拒绝
    blocked: List[Dict[str, Any]] = []
    allowed_cmds: List[str] = []
    for idx, cmd in enumerate(commands):
        is_allowed, reason = interceptor.is_allowed(cmd)
        if not is_allowed:
            blocked.append({"index": idx, "command": cmd, "reason": reason})
        else:
            allowed_cmds.append(cmd)
    if blocked:
        # 整批拒绝：先写 batch 汇总（blocked），然后逐子命令 emit blocked / skipped
        for idx, cmd in enumerate(commands):
            blocked_entry = next((b for b in blocked if b["index"] == idx), None)
            if blocked_entry is not None:
                _emit_log(
                    action="ssh_execute_command",
                    result="blocked",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "execute_batch_member",
                        "server_type": config.get("server_type"),
                        "command_redacted": redact_command(cmd),
                        "command_hash": hash_command(cmd),
                        "decision": "blocked",
                        "intercept_reason": (
                            "command_not_whitelisted"
                            if "不在白名单" in str(blocked_entry["reason"])
                            else "command_blacklisted"
                        ),
                        "exit_code": None,
                        "duration_ms": 0,
                        "stdout_size": 0,
                        "stderr_size": 0,
                        "error_code": "blocked",
                    },
                    correlation_id=batch_cid,
                )
            else:
                _emit_log(
                    action="ssh_execute_command",
                    result="skipped",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "execute_batch_member",
                        "server_type": config.get("server_type"),
                        "command_redacted": redact_command(cmd),
                        "command_hash": hash_command(cmd),
                        "decision": "skipped",
                        "intercept_reason": "同批次其他命令被拦截，整批拒绝",
                        "exit_code": None,
                        "duration_ms": 0,
                        "stdout_size": 0,
                        "stderr_size": 0,
                        "error_code": "batch_rejected",
                    },
                    correlation_id=batch_cid,
                )
        _emit_log(
            action="ssh_execute_batch",
            result="blocked",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_batch",
                "server_type": config.get("server_type"),
                "command_redacted": None,
                "command_hash": None,
                "decision": "blocked",
                "intercept_reason": "部分命令被拦截",
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "blocked",
                "total": len(commands),
            },
            correlation_id=batch_cid,
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": "部分命令被拦截",
                            "blocked_commands": blocked,
                        },
                    )
                ]
            }
        )

    # 全部通过；按顺序执行
    results: List[Dict[str, Any]] = []
    # Bug-5 修复:批量同样钳制 timeout
    safe_timeout = _clamp_timeout(timeout, default=30, lo=1, hi=120)
    client = None
    started = time.monotonic()
    try:
        client = _open_client(config)
        for cmd in allowed_cmds:
            wrapped = _wrap_for_platform(config["server_type"], cmd)
            member_started = time.monotonic()
            try:
                stdin, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
                # Windows OpenSSH 非 PTY 通道下需关闭 stdin 写端(发送 EOF),
                # 否则远端 shell 等待输入导致 read() 阻塞至超时。
                stdin.close()
                output = stdout.read().decode("utf-8", errors="replace").strip()
                err = stderr.read().decode("utf-8", errors="replace").strip()
                exit_code = stdout.channel.recv_exit_status()
                # 2026-07-29 统一语义:success = exit_code == 0,stderr 不改变成功语义
                success = exit_code == 0
                item: Dict[str, Any] = {
                    "command": cmd,
                    "success": success,
                    "output": output,
                    "exit_code": exit_code,
                }
                if err:
                    item["error"] = err
                results.append(item)
                duration_ms = int((time.monotonic() - member_started) * 1000)
                stdout_size = len(output.encode("utf-8")) if output else 0
                stderr_size = len(err.encode("utf-8")) if err else 0
                _emit_log(
                    action="ssh_execute_command",
                    result="success" if success else "failure",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "execute_batch_member",
                        "server_type": config.get("server_type"),
                        "command_redacted": redact_command(cmd),
                        "command_hash": hash_command(cmd),
                        "decision": "executed",
                        "intercept_reason": None,
                        "exit_code": exit_code,
                        "duration_ms": duration_ms,
                        "stdout_size": stdout_size,
                        "stderr_size": stderr_size,
                        "error_code": None if success else "non_zero_exit",
                    },
                    correlation_id=batch_cid,
                )
            except Exception:  # noqa: BLE001 - 单条出错不影响其他条；不携带异常字符串避免凭据泄漏
                results.append(
                    {"command": cmd, "success": False, "error": "执行失败"}
                )
                duration_ms = int((time.monotonic() - member_started) * 1000)
                _emit_log(
                    action="ssh_execute_command",
                    result="failure",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "execute_batch_member",
                        "server_type": config.get("server_type"),
                        "command_redacted": redact_command(cmd),
                        "command_hash": hash_command(cmd),
                        "decision": "executed",
                        "intercept_reason": "执行失败",
                        "exit_code": None,
                        "duration_ms": duration_ms,
                        "stdout_size": 0,
                        "stderr_size": 0,
                        "error_code": "execution_failed",
                    },
                    correlation_id=batch_cid,
                )

        duration_ms = int((time.monotonic() - started) * 1000)
        all_success = all(r.get("success") for r in results)
        _emit_log(
            action="ssh_execute_batch",
            result="success" if all_success else "failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "execute_batch",
                "server_type": config.get("server_type"),
                "command_redacted": None,
                "command_hash": None,
                "decision": "executed",
                "intercept_reason": None,
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": None if all_success else "non_zero_exit",
                "total": len(results),
                "succeeded": sum(1 for r in results if r.get("success")),
            },
            correlation_id=batch_cid,
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": all_success,
                            "results": results,
                            "total": len(results),
                            "succeeded": sum(1 for r in results if r.get("success")),
                        },
                    )
                ]
            }
        )
    except paramiko.AuthenticationException:
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_batch_failure_with_members(
            runtime=runtime,
            business_name=business_name,
            commands=allowed_cmds,
            batch_cid=batch_cid,
            duration_ms=duration_ms,
            stage="auth_failed",
            error_code="auth_failed",
            intercept_reason="SSH 认证失败",
            server_type=config.get("server_type"),
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 认证失败"},
                    )
                ]
            }
        )
    except paramiko.SSHException:
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_batch_failure_with_members(
            runtime=runtime,
            business_name=business_name,
            commands=allowed_cmds,
            batch_cid=batch_cid,
            duration_ms=duration_ms,
            stage="ssh_error",
            error_code="ssh_error",
            intercept_reason="SSH 连接错误",
            server_type=config.get("server_type"),
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "SSH 连接错误"},
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 通用错误，避免泄漏 IP/凭据
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_batch_failure_with_members(
            runtime=runtime,
            business_name=business_name,
            commands=allowed_cmds,
            batch_cid=batch_cid,
            duration_ms=duration_ms,
            stage="execution_failed",
            error_code="execution_failed",
            intercept_reason="批量远程命令执行失败",
            server_type=config.get("server_type"),
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "批量远程命令执行失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass


# ---------------------------------------------------------------------------
# Tool: get_system_logs
# ---------------------------------------------------------------------------


@tool(description="获取远程服务器系统日志（tail）。返回成功摘要，不含连接配置。")
def get_system_logs(
    business_name: str,
    log_type: str = "syslog",
    lines: int = 100,
    runtime: ToolRuntime = None,
) -> Command:
    """获取服务器系统日志。

    内部命令 ``tail -n <lines> <path>`` 同样走 ``CommandInterceptor`` 检查。

    Args:
        business_name: 业务名（必填，不可为空）
        log_type: 日志类型（syslog / auth / kern / 其他）
        lines: 行数
        runtime: LangChain ToolRuntime

    Returns:
        Command: 含 messages 的 LangChain 命令对象
    """
    tool_call_id = getattr(runtime, "tool_call_id", "unknown") if runtime else "unknown"
    err = _validate_business_name(business_name)
    if err:
        _emit_log(
            action="ssh_get_system_logs",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "get_system_logs",
                "server_type": None,
                "command_redacted": None,
                "command_hash": None,
                "decision": "rejected",
                "intercept_reason": err,
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "invalid_business_name",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id, {"success": False, "error": err}
                    )
                ]
            }
        )
    try:
        config = _resolve_server_config(runtime, business_name)
    except Exception:  # noqa: BLE001 - Bug-3 修复:统一吞掉异常,避免泄漏密钥错配等内部细节
        _emit_log(
            action="ssh_get_system_logs",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "get_system_logs",
                "server_type": None,
                "command_redacted": None,
                "command_hash": None,
                "decision": "rejected",
                "intercept_reason": "无法解析服务器配置",
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "config_unresolved",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "无法解析服务器配置"},
                    )
                ]
            }
        )

    # 派生内部命令：Linux 走 tail，Windows 走 PowerShell Get-WinEvent
    server_type = (config.get("server_type") or "linux").lower()
    if server_type == "windows":
        # Windows：PowerShell Get-WinEvent；常见日志名 LogName 映射
        win_log_map = {
            "system": "System",
            "application": "Application",
            "security": "Security",
            "setup": "Setup",
        }
        log_name = win_log_map.get(log_type.lower(), log_type)
        # PowerShell 内部命令（不含外层 powershell.exe 包裹，由 _wrap_for_platform 注入）
        # Bug-1 提示:该命令会被 CommandInterceptor 拆成多段（管道 / 函数调用），
        # 白名单需覆盖 ``Get-WinEvent`` / ``Select-Object`` / ``Format-Table`` /
        # ``Out-String`` 等每个子段关键词（含尾空格前缀模式）。
        inner_cmd = (
            f"Get-WinEvent -LogName {log_name} -MaxEvents {int(lines)} "
            f"| Select-Object TimeCreated,Message | Format-Table -AutoSize | Out-String"
        )
    else:
        if log_type == "syslog":
            path = "/var/log/syslog"
        elif log_type == "auth":
            path = "/var/log/auth.log"
        elif log_type == "kern":
            path = "/var/log/kern.log"
        else:
            path = f"/var/log/{log_type}"
        inner_cmd = f"tail -n {int(lines)} {path}"

    interceptor = _make_interceptor(config)
    try:
        interceptor.check_and_raise(inner_cmd)
    except CommandBlockedError as e:
        _emit_log(
            action="ssh_get_system_logs",
            result="blocked",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "get_system_logs",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(inner_cmd),
                "command_hash": hash_command(inner_cmd),
                "decision": "blocked",
                "intercept_reason": str(e),
                "exit_code": None,
                "duration_ms": 0,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "blocked",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": f"内部命令被拦截: {e}",
                            "blocked": True,
                        },
                    )
                ]
            }
        )

    client = None
    started = time.monotonic()
    try:
        client = _open_client(config)
        wrapped = _wrap_for_platform(config["server_type"], inner_cmd)
        # Bug-5 修复:get_system_logs 内部命令固定 30s,这里用钳制函数统一约束
        safe_timeout = _clamp_timeout(30, default=30, lo=1, hi=120)
        stdin, stdout, stderr = client.exec_command(wrapped, timeout=safe_timeout)
        # Windows OpenSSH 非 PTY 通道下需关闭 stdin 写端(发送 EOF),
        # 否则远端 shell 等待输入导致 read() 阻塞至超时。
        stdin.close()
        output = stdout.read().decode("utf-8", errors="replace").strip()
        err = stderr.read().decode("utf-8", errors="replace").strip()
        exit_code = stdout.channel.recv_exit_status()
        duration_ms = int((time.monotonic() - started) * 1000)
        stdout_size = len(output.encode("utf-8")) if output else 0
        stderr_size = len(err.encode("utf-8")) if err else 0
        success = exit_code == 0
        if not success:
            _emit_log(
                action="ssh_get_system_logs",
                result="failure",
                runtime=runtime,
                business_name=business_name,
                metadata={
                    "event_type": "get_system_logs",
                    "server_type": config.get("server_type"),
                    "command_redacted": redact_command(inner_cmd),
                    "command_hash": hash_command(inner_cmd),
                    "decision": "executed",
                    "intercept_reason": err or "日志获取失败",
                    "exit_code": exit_code,
                    "duration_ms": duration_ms,
                    "stdout_size": stdout_size,
                    "stderr_size": stderr_size,
                    "error_code": "non_zero_exit",
                },
            )
            return Command(
                update={
                    "messages": [
                        _make_tool_message(
                            tool_call_id,
                            {
                                "success": False,
                                "error": err or "日志获取失败",
                            },
                        )
                    ]
                }
            )
        # 统计行数 & 返回摘要；不外泄连接配置
        log_lines = output.split("\n") if output else []
        total = len(log_lines)
        _emit_log(
            action="ssh_get_system_logs",
            result="success" if success else "failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "get_system_logs",
                "server_type": config.get("server_type"),
                "command_redacted": redact_command(inner_cmd),
                "command_hash": hash_command(inner_cmd),
                "decision": "executed",
                "intercept_reason": None,
                "exit_code": exit_code,
                "duration_ms": duration_ms,
                "stdout_size": stdout_size,
                "stderr_size": stderr_size,
                "error_code": None,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": success,
                            "log_type": log_type,
                            "total_lines": total,
                            "lines_requested": int(lines),
                            "summary": f"成功获取 {total} 行 {log_type} 日志",
                        },
                    )
                ]
            }
        )
    except Exception:  # noqa: BLE001 - 通用错误，避免泄漏 IP/凭据
        duration_ms = int((time.monotonic() - started) * 1000)
        _emit_log(
            action="ssh_get_system_logs",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "get_system_logs",
                "server_type": config.get("server_type") if "config" in locals() else None,
                "command_redacted": redact_command(inner_cmd) if "inner_cmd" in locals() else None,
                "command_hash": hash_command(inner_cmd) if "inner_cmd" in locals() else None,
                "decision": "executed",
                "intercept_reason": "获取日志失败",
                "exit_code": None,
                "duration_ms": duration_ms,
                "stdout_size": 0,
                "stderr_size": 0,
                "error_code": "execution_failed",
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "获取日志失败"},
                    )
                ]
            }
        )
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
