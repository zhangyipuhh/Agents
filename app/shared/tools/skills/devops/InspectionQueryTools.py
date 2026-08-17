#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InspectionQueryTools - 服务器巡检记录查询工具（2026-08-17 新增）

职责：
    - 通过 ``ServerInspectionRecordService.list_records`` 查询
      ``server_inspection_records`` 表的历史巡检记录
    - 查询条件：时间范围（start/end）+ 业务名（business_name）
    - 输出字段白名单严格不含服务器 IP；并对 JSONB 字段做 IP 残留兜底剔除
    - 纯 DB 查询工具，**不**连 SSH / paramiko / 不读连接凭据 / 不触碰 whitelist

工具清单：
    - query_inspection_records    按时间 + business_name 查询巡检记录（不含 IP，默认仅返回最新一条）

注入与发现：
    - 仅使用 ``@tool(description=...)`` 装饰，**不调用** ``register_tool(agent=...)``
    - 工具元数据（module_path / file_path）由 ToolRegistryService 通过源码扫描发现
    - 服务实例 ``ServerInspectionRecordService`` 由 lifespan 在
      ``app/core/server.py`` 通过 ``ServerInspectionRecordService.set_instance(...)``
      注册类级单例；工具通过 ``ServerInspectionRecordService.get_instance()``
      获取（与 ``DevOpsServerService.get_instance()`` 同款契约）。
      **不**依赖 ``runtime.context`` 注入（避免污染 ``agent_router.chat``
      通用通道）。
    - 数据归属上下文 ``OwnershipScope`` 由 ``agent_router.chat`` 通过
      ``context_overrides["ownership_scope"]`` 注入字典形态
      （``{user_id, is_admin, system}``），工具侧 ``_resolve_scope``
      还原为 ``OwnershipScope`` 实例；缺失兜底为 ``OwnershipScope.system_scope()``。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, Optional

from langchain.tools import tool, ToolRuntime
from langgraph.types import Command

try:
    # 生产环境：使用真实 ToolMessage
    from langchain_core.messages import ToolMessage as _RealToolMessage
except Exception:  # noqa: BLE001 - 测试环境被 conftest mock 时降级
    _RealToolMessage = None


def _is_real_tool_message_class(cls) -> bool:
    """判断 ``_RealToolMessage`` 是真实类还是 conftest 注入的 ``Mock``。

    与 SSHTools.py 同款判定逻辑：测试环境下 ``conftest.py`` 把
    ``langchain_core.messages.ToolMessage = Mock()`` 替换为 Mock，
    Mock 对象的内省属性与真实 ``pydantic.BaseModel`` 子类差异巨大。

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


from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.log_service import (
    LogEvent,
    LogLevel,
    LogResult,
    LogType,
    get_log_service,
)
from app.shared.utils.server_inspection_record_service import (
    ServerInspectionRecordService,
)


logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# 严格白名单：payload 输出键（不含 ip / port / password 等敏感字段）
# ---------------------------------------------------------------------------
# 来自 ``server_inspection_records`` 表 + ``_row_to_history_record`` 的输出。
# 服务层 / 表 schema 都不存 IP，但保留白名单作为契约防御（防止后续演进意外
# 把敏感字段加入视图 dict）。
_RECORD_OUTPUT_KEYS: tuple = (
    "id",
    "server_id",
    "business_name",
    "collected_at",
    "success",
    "skipped",
    "exit_code",
    "duration_ms",
    "inspection_status",
    "error_message",
    "inspection_error",
    "parsed_values",
    "field_results",
    "created_at",
    "schedule_id",
    "run_id",
    "inspection_script_id",
    "created_by_user_id",
)

# JSONB 内可能存在 IP 残留的键名（大小写不敏感）；递归剔除
_IP_LIKE_KEYS: frozenset = frozenset({
    "ip",
    "ip_address",
    "host",
    "hostname",
    "address",
    "ssh_ip",
    "server_ip",
    "source_ip",
})


# ---------------------------------------------------------------------------
# 统一审计日志（与 SSHTools.py 风格一致）
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

    与 SSHTools.py 同款语义：从 ``AgentContext.log_ip`` 读取客户端 IP
    写入 ``LogEvent.ip_address``。来源：``agent_router.chat`` 用
    ``request.client.host`` 强制覆盖后的真值，禁止信任客户端
    context_overrides 提供的 log_ip。

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


async def _emit_log(
    *,
    action: str,
    result: str,
    runtime: Any,
    business_name: Optional[str],
    metadata: Dict[str, Any],
    target_id: Optional[int] = None,
    correlation_id: Optional[str] = None,
) -> None:
    """通过 ``LogService.emit`` 写入一条 ``log_type='system'`` 的审计日志（fail-soft）。

    与 SSHTools.py ``_emit_log`` 同款契约：所有异常降级为 warning 日志，
    避免日志失败污染工具业务响应。

    Args:
        action: 业务动作名（本工具固定 ``inspection_query_records``）。
        result: ``LogResult`` 枚举值字符串（success / failure）。
        runtime: LangChain ``ToolRuntime``。
        business_name: 业务名（写入 ``target_name``）。
        metadata: 元数据字典，调用方应在传入前填充完约定的固定键集合；
            ``LogService.emit`` 内部会再次做 ``redact_metadata`` 递归脱敏。
        target_id: ``devops_servers.id``（写入 ``target_id``）。
        correlation_id: 关联批次 ID（保留接口，本工具未使用）。

    Returns:
        None：失败不影响调用方。

    Raises:
        不抛出异常：所有错误均降级为 warning 日志。
    """
    try:
        service = get_log_service()
        if service is None:
            return
        tool_call_id = _runtime_tool_call_id(runtime)
        user_id, username = _runtime_identity(runtime)
        session_id = _runtime_session_id(runtime)
        client_ip = _runtime_ip(runtime)
        evt = LogEvent(
            action=action,
            log_type=LogType.SYSTEM,
            result=LogResult(result),
            level=LogLevel.WARNING if result == "failure" else LogLevel.INFO,
            source="inspection_query_tools",
            message=action,
            tool_call_id=tool_call_id,
            session_id=session_id,
            correlation_id=correlation_id,
            target_type="devops_server",
            target_name=business_name,
            target_id=str(target_id) if target_id is not None else None,
            user_id=user_id,
            username=username,
            ip_address=client_ip,
            metadata=metadata,
        )
        await service.emit(evt)
    except Exception as exc:  # noqa: BLE001 - fail-soft：日志失败不阻断业务
        logger.warning(
            "[InspectionQueryTools] emit log failed (action=%s, result=%s): %s",
            action,
            result,
            type(exc).__name__,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_tool_message(tool_call_id: str, content: Any):
    """构造一个消息对象（生产环境用真实的 ``ToolMessage``，测试环境用 duck-typed）。

    与 SSHTools.py ``_make_tool_message`` 同款：production 走
    ``_RealToolMessage(content=text, tool_call_id=tool_call_id)``；
    测试环境 conftest 把 ``ToolMessage`` mock 为 MagicMock，提供 duck-typed
    fallback 避免 ``.content`` 也变成 Mock。

    Args:
        tool_call_id: 工具调用 ID。
        content: ``dict`` 或 ``str`` 内容。

    Returns:
        一个带 ``.content`` 与 ``.tool_call_id`` 属性的对象。
    """
    if isinstance(content, dict):
        text = json.dumps(content, ensure_ascii=False)
    else:
        text = str(content)
    if _REAL_TOOL_MESSAGE_OK:
        return _RealToolMessage(content=text, tool_call_id=tool_call_id)  # type: ignore[misc]

    class _DuckMessage:
        """简易消息载体，提供 ``content`` 与 ``tool_call_id`` 属性。"""

        def __init__(self, content: str, tool_call_id: str) -> None:
            self.content = content
            self.tool_call_id = tool_call_id

        def __repr__(self) -> str:
            return f"<_DuckMessage tool_call_id={self.tool_call_id!r} content={self.content[:80]!r}>"

    return _DuckMessage(text, tool_call_id)


def _validate_business_name(business_name: str) -> Optional[str]:
    """校验 ``business_name`` 非空且非纯空白。

    Args:
        business_name: 待校验的业务名。

    Returns:
        Optional[str]: 校验失败时返回错误消息；通过时返回 ``None``。
    """
    if not isinstance(business_name, str) or not business_name.strip():
        return "business_name 不能为空"
    return None


def _parse_iso_datetime(raw: str, *, field_name: str) -> Optional[datetime]:
    """解析 LLM 端传入的时间字符串为 ``datetime``。

    接受 ISO8601 形态：
        - ``2026-08-01T00:00:00`` / ``2026-08-01T00:00:00+08:00``
        - ``2026-08-01 00:00:00``（空格等价 ``T``）
        - ``2026-08-01``（日期；落到本地 00:00:00）

    失败时返回 ``None``，由调用方负责转换成工具错误响应。

    Args:
        raw: 原始字符串。
        field_name: 字段名（start / end），用于错误日志与可读消息。

    Returns:
        Optional[datetime]: 解析成功返回 ``datetime``；失败返回 ``None``。
    """
    if not isinstance(raw, str) or not raw.strip():
        return None
    candidate = raw.strip()
    # 容错：把空格当 T（LLM 偶发）
    if " " in candidate and "T" not in candidate:
        candidate = candidate.replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(candidate)
    except (TypeError, ValueError):
        return None


def _clamp_limit(limit: Any, default: int = 100, lo: int = 1, hi: int = 1000) -> int:
    """把 LLM 端传入的 ``limit`` 钳制到 ``[lo, hi]`` 区间。

    与 ``ServerInspectionRecordService.list_records`` 现有契约对齐：
    1~1000。非法值（``None`` / 字符串 / 负数 / 0 / 超大）兜底为 ``default``。

    Args:
        limit: 原始 limit 值。
        default: 非整数时的兜底值。
        lo: 最小允许值（含）。
        hi: 最大允许值（含）。

    Returns:
        int: 钳制后的合法 limit。
    """
    try:
        v = int(limit)
    except (TypeError, ValueError):
        return default
    if v < lo:
        return lo
    if v > hi:
        return hi
    return v


def _resolve_scope(runtime: Any) -> OwnershipScope:
    """从 ``runtime.context["ownership_scope"]`` 还原 ``OwnershipScope`` 实例。

    ``agent_router.chat`` 注入的 ``ownership_scope`` 是字典形态
    （``{user_id, is_admin, system}``），由本函数还原为 ``OwnershipScope``。
    兼容三种形态：
      - ``OwnershipScope`` 实例 → 直接返回
      - dict（agent_router.chat 注入）→ 还原
      - 缺失 / 非法 → 兜底为 ``OwnershipScope.system_scope()``

    兜底语义：
      - tool 调用链正常情况下由 router 注入；缺失是异常路径
      - system_scope 兜底比拒绝所有查询更友好（system=True → 全量放行）
      - 对应当前 InspectionQueryTools 设计的「运维控制台查询」语义，
        默认 system 全量可接受；如未来有强隔离需求再收紧

    Args:
        runtime: LangChain ``ToolRuntime`` 实例。

    Returns:
        OwnershipScope: 永远非 ``None``。
    """
    ctx = _runtime_context(runtime)
    scope = ctx.get("ownership_scope")
    if isinstance(scope, OwnershipScope):
        return scope
    if isinstance(scope, dict):
        # 2026-08-17 新增:agent_router.chat 注入的字典形态（含 user_id /
        # is_admin / system 三键）。缺失键走 .get() 容错;非法 user_id
        # 退化为 None（系统内部调用），不让 IntegrityError 污染业务响应。
        try:
            return OwnershipScope(
                user_id=scope.get("user_id") if isinstance(scope.get("user_id"), int) else None,
                is_admin=bool(scope.get("is_admin", False)),
                system=bool(scope.get("system", False)),
            )
        except Exception:
            return OwnershipScope.system_scope()
    return OwnershipScope.system_scope()


def _resolve_record_service() -> Optional[ServerInspectionRecordService]:
    """从类级单例取 ``ServerInspectionRecordService``。

    **不**通过 ``runtime.context`` 注入——因为：
      1) ``agent_router.chat`` 是通用通道，注入服务实例会让所有 agent
         context payload 携带数据库实例，污染通用接口
      2) lifespan 在 ``app/core/server.py`` 已经通过
         ``ServerInspectionRecordService.set_instance(...)`` 注册单例
      3) 测试可通过 ``ServerInspectionRecordService.set_instance(...)``
         注入 stub（与 ``DevOpsServerService`` 同款契约）

    Returns:
        Optional[ServerInspectionRecordService]: 实例；DB 未启用 / lifespan
        异常时返回 ``None``。
    """
    try:
        return ServerInspectionRecordService.get_instance()
    except RuntimeError:
        # 单例未初始化：DB 未启用 / lifespan 异常 / 内存降级模式
        return None


def _resolve_server_id_by_name(business_name: str) -> Optional[int]:
    """通过 ``DevOpsServerService.list_public_servers()`` 内存缓存做反查。

    ``DevOpsServerService.list_public_servers()`` 返回严格白名单
    （id / business_name / server_type / updated_at / inspection_script_*），
    不含 ip / port / password，符合工具「不出现 IP」契约。

    Args:
        business_name: 业务名（精确匹配）。

    Returns:
        Optional[int]: ``server_id``；找不到 / service 未注入 / 异常时返回 ``None``。
    """
    try:
        from app.shared.utils.devops_server_service import DevOpsServerService

        svc = DevOpsServerService.get_instance()
        if svc is None:
            return None
        for row in svc.list_public_servers() or []:
            if row.get("business_name") == business_name:
                sid = row.get("id")
                if sid is not None:
                    return int(sid)
        return None
    except Exception as exc:  # noqa: BLE001 - fail-soft：service 异常降级为 None
        logger.warning(
            "[InspectionQueryTools] DevOpsServerService.list_public_servers 失败: %s",
            type(exc).__name__,
        )
        return None


def _scrub_ip(value: Any) -> Any:
    """递归剔除 dict / list 中可能的 IP 残留键。

    仅对 ``_IP_LIKE_KEYS`` 集合中的键（大小写不敏感）做 ``del``；
    其它字段原样保留。**不**修改原对象，返回新对象。

    Args:
        value: 任意 JSONB 兼容值。

    Returns:
        Any: 清洗后的副本。
    """
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and k.lower() in _IP_LIKE_KEYS:
                continue
            out[k] = _scrub_ip(v)
        return out
    if isinstance(value, list):
        return [_scrub_ip(item) for item in value]
    return value


def _filter_record_keys(row: Dict[str, Any]) -> Dict[str, Any]:
    """把 ``_row_to_history_record`` 输出 dict 收敛到 ``_RECORD_OUTPUT_KEYS`` 白名单。

    同时对 ``parsed_values`` / ``field_results`` 做 IP 剔除兜底。

    Args:
        row: 单行历史记录 dict（来自 ``_row_to_history_record``）。

    Returns:
        Dict[str, Any]: 收敛后的新 dict；不在白名单的键被剔除。
    """
    if not isinstance(row, dict):
        return {}
    out: Dict[str, Any] = {}
    for k in _RECORD_OUTPUT_KEYS:
        if k in row:
            v = row[k]
            # JSONB 字段走 IP 剔除
            if k in ("parsed_values", "field_results"):
                v = _scrub_ip(v)
            out[k] = v
    return out


# ---------------------------------------------------------------------------
# Tool: query_inspection_records
# ---------------------------------------------------------------------------


@tool(description=(
    "查询服务器巡检历史记录。"
    "支持按服务器业务名（business_name）过滤；返回结果不含服务器 IP。"
    "默认仅返回最新一条记录（latest_only=True），无需传时间范围。"
    "如需历史区间，置 latest_only=False；start / end 均为可选过滤（ISO8601，如 '2026-08-01T00:00:00'），"
    "可单独或同时传入；缺省视为不限界，返回最近 limit 条（默认 100）。"
    "如需精确区间（如「最近2天」），建议先调用 get_current_time 获取当前时间再构造绝对区间；"
    "若 LLM 仅传 latest_only=False 而不传 start/end，工具将返回最近 limit 条而非报错，避免死循环。"
))
async def query_inspection_records(
    business_name: str,
    start: Optional[str] = None,
    end: Optional[str] = None,
    latest_only: bool = True,
    limit: int = 100,
    runtime: ToolRuntime = None,
) -> Command:
    """按业务名查询服务器巡检历史记录（不含 IP）。

    步骤：
      1) 校验 ``business_name`` 非空
      2) latest_only 模式分支：
         - True → ``start`` / ``end`` 强制 ``None``；limit 强制为 1
         - False → 解析显式传入的 ``start`` / ``end`` 为 ``datetime``；
           缺省侧保持 ``None``（不限界）；仅当显式传入但 ISO8601 解析失败时报
           ``invalid_time``；limit 钳制到 [1, 1000]
      4) 从 ``runtime.context["ownership_scope"]`` 取 ``OwnershipScope``
         （dict / 实例 / 缺失 → 三层兜底；缺失 → system_scope）
      5) 从类级单例 ``ServerInspectionRecordService.get_instance()`` 取服务实例
      6) 通过 ``DevOpsServerService.list_public_servers`` 内存缓存做
         ``business_name → server_id`` 反查
      7) 调用 ``service.list_records(server_id, scope, start=..., end=..., limit=...)``
      8) 对每行做 IP 剔除 + 字段白名单收敛
      9) emit 一条审计日志（action=``inspection_query_records``）
     10) 返回 ``Command``（messages 列表含单个 ``ToolMessage``）

    **数据归属隔离**：admin / system 全量；普通用户仅可见
    ``user_server_nodes`` 中归属自己的服务器（service 层按
    ``OwnershipScope`` 过滤）。越权 / 不可见时返回通用错误，不回显
    server_id。

    **latest_only 语义**（2026-08-17 新增 / 同日收紧为可选）：
      - True（默认）→ ``limit=1``，**忽略** ``start`` / ``end``；返回
        ``server_inspection_records`` 中该服务器 ``collected_at`` 最新的
        一条。适合"查询最近一次巡检记录"自然语言问题，避免 LLM 必须
        先调 ``get_current_time`` 才能算时间范围。
      - False → ``start`` / ``end`` 改为**可选过滤**：缺省侧视为不限界
        （透传 ``None`` 给 ``list_records``，服务层 ``None``=不限界），
        双缺返回最近 ``limit`` 条（默认 100）。仅当显式传入但 ISO8601
        解析失败时报 ``invalid_time``，**不引入 silent 兜底**。
        审计 metadata 与 payload 同步输出 ``time_range_defaulted``
        字段（双缺为 ``True``；latest_only=True 或已传 start/end 时
        为 ``False``）。修复 2026-08-17 ops-detect 智能检测窗口死循环
        （详见顶部 description 与本函数注释）。

    Args:
        business_name: 业务名（必填，不可为空）。
        start: 起始时间（含），ISO8601 字符串；``latest_only=False`` 时可选，
            缺省透传 ``None``（不限下界）。
        end: 截止时间（含），ISO8601 字符串；``latest_only=False`` 时可选，
            缺省透传 ``None``（不限上界）。
        latest_only: 是否仅返回最新一条记录（默认 True）。
        limit: 最大返回条数（1~1000，默认 100；``latest_only=True`` 时强制 1）。
        runtime: LangChain ``ToolRuntime``（langchain runtime 自动注入）。
            context 中支持：
              - ``ownership_scope`` (dict / OwnershipScope): 数据归属隔离上下文；
                缺失时兜底为 ``OwnershipScope.system_scope()``
              - ``log_user_id`` / ``log_username`` / ``log_ip`` /
                ``session_id``：审计日志上下文

    Returns:
        Command: 包含 messages 的 LangChain 命令对象。
    """
    tool_call_id = _runtime_tool_call_id(runtime)
    started = time.monotonic()

    # 1) 业务名校验
    err = _validate_business_name(business_name)
    if err:
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "invalid_business_name",
                "duration_ms": 0,
                "row_count": 0,
                "latest_only": latest_only,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(tool_call_id, {"success": False, "error": err})
                ]
            }
        )

    # 2) latest_only 模式：start / end 可空；limit 强制为 1
    if latest_only:
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        safe_limit = 1
        time_range_defaulted = False
    else:
        # 区间模式（latest_only=False）：start / end 改为**可选过滤**。
        # 2026-08-17 根因修复（ops-detect 智能检测窗口死循环）：
        #   原契约要求 start/end 必填，LLM 在「最近N天」相对时间面前常不传绝对区间，
        #   收到死胡同错误「latest_only=False 时 start 与 end 必填」后原地重试，
        #   直到 recursion_limit=100 才终止，表现为 agent 死循环。
        #   新契约：缺省侧视为不限界（list_records 服务层 None=不限界），
        #   返回最近 limit 条（默认 100）；仅当显式传入但 ISO8601 解析失败时报 invalid_time，
        #   不引入 silent 兜底（避免 LLM 错传 ISO 字符串时静默通过）。
        start_dt: Optional[datetime] = None
        end_dt: Optional[datetime] = None
        if start:
            start_dt = _parse_iso_datetime(start, field_name="start")
            if start_dt is None:
                await _emit_log(
                    action="inspection_query_records",
                    result="failure",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "query_inspection_records",
                        "error_code": "invalid_time",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "row_count": 0,
                        "time_range_start_raw": str(start),
                        "time_range_end_raw": str(end) if end else None,
                        "latest_only": False,
                    },
                )
                return Command(
                    update={
                        "messages": [
                            _make_tool_message(
                                tool_call_id,
                                {
                                    "success": False,
                                    "error": "起始时间格式错误，请使用 ISO8601（如 '2026-08-01T00:00:00'）",
                                },
                            )
                        ]
                    }
                )
        if end:
            end_dt = _parse_iso_datetime(end, field_name="end")
            if end_dt is None:
                await _emit_log(
                    action="inspection_query_records",
                    result="failure",
                    runtime=runtime,
                    business_name=business_name,
                    metadata={
                        "event_type": "query_inspection_records",
                        "error_code": "invalid_time",
                        "duration_ms": int((time.monotonic() - started) * 1000),
                        "row_count": 0,
                        "time_range_start_raw": str(start) if start else None,
                        "time_range_end_raw": str(end),
                        "latest_only": False,
                    },
                )
                return Command(
                    update={
                        "messages": [
                            _make_tool_message(
                                tool_call_id,
                                {
                                    "success": False,
                                    "error": "截止时间格式错误，请使用 ISO8601（如 '2026-08-02T00:00:00'）",
                                },
                            )
                        ]
                    }
                )
        # 区间模式 limit 钳制到 [1, 1000]
        safe_limit = _clamp_limit(limit, default=100, lo=1, hi=1000)
        # 双侧均为 None 时视为「不限界」默认，按设计加 defaulted 标记；
        # 单侧缺失虽不是 defaulted 场景，但 payload 端走「仅双侧都有 time_range」约定，
        # 故此处统一 False（defaulted 严格表示「区间被默认放宽」）。
        time_range_defaulted = (start_dt is None and end_dt is None)

    # 3) 取 OwnershipScope（dict / 实例 / 缺失 → 三层兜底）
    scope = _resolve_scope(runtime)

    # 4) 取服务实例（类级单例，不依赖 runtime.context）
    service = _resolve_record_service()
    if service is None:
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "service_unavailable",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "row_count": 0,
                "latest_only": latest_only,
                "limit": safe_limit,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "巡检记录服务不可用"},
                    )
                ]
            }
        )

    # 5) business_name → server_id 反查
    server_id = _resolve_server_id_by_name(business_name)
    if server_id is None:
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "server_not_found",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "row_count": 0,
                "latest_only": latest_only,
                "limit": safe_limit,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {
                            "success": False,
                            "error": "未找到业务名对应的服务器",
                        },
                    )
                ]
            }
        )

    # 6) 查询（latest_only 时 start/end 传 None → list_records 走全表 ORDER BY DESC LIMIT 1）
    try:
        # service.list_records 是 async（asyncpg.Pool），必须在 in-flight loop 内 await
        records = await service.list_records(
            server_id, scope, start=start_dt, end=end_dt, limit=safe_limit,
        )
    except ValueError as exc:
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            target_id=server_id,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "invalid_limit",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "row_count": 0,
                "latest_only": latest_only,
                "limit": safe_limit,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": f"参数错误: {exc}"},
                    )
                ]
            }
        )
    except Exception as exc:  # noqa: BLE001 - 通用兜底，不泄漏 DB 内部细节
        logger.warning(
            "[InspectionQueryTools] list_records 异常: %s", type(exc).__name__,
        )
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            target_id=server_id,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "db_error",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "row_count": 0,
                "latest_only": latest_only,
                "limit": safe_limit,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "查询巡检记录失败"},
                    )
                ]
            }
        )

    # 7) 越权 / 不可见
    if records is None:
        await _emit_log(
            action="inspection_query_records",
            result="failure",
            runtime=runtime,
            business_name=business_name,
            target_id=server_id,
            metadata={
                "event_type": "query_inspection_records",
                "error_code": "not_visible",
                "duration_ms": int((time.monotonic() - started) * 1000),
                "row_count": 0,
                "latest_only": latest_only,
                "limit": safe_limit,
            },
        )
        return Command(
            update={
                "messages": [
                    _make_tool_message(
                        tool_call_id,
                        {"success": False, "error": "服务器不存在或不可见"},
                    )
                ]
            }
        )

    # 8) 字段白名单收敛 + IP 剔除
    cleaned_items = [_filter_record_keys(r) for r in records]
    duration_ms = int((time.monotonic() - started) * 1000)

    # 9) 审计日志（成功）
    metadata_success: Dict[str, Any] = {
        "event_type": "query_inspection_records",
        "error_code": None,
        "duration_ms": duration_ms,
        "row_count": len(cleaned_items),
        "latest_only": latest_only,
        "limit": safe_limit,
        "time_range_defaulted": time_range_defaulted,
    }
    if start_dt is not None:
        metadata_success["time_range_start"] = start_dt.isoformat()
    if end_dt is not None:
        metadata_success["time_range_end"] = end_dt.isoformat()
    await _emit_log(
        action="inspection_query_records",
        result="success",
        runtime=runtime,
        business_name=business_name,
        target_id=server_id,
        metadata=metadata_success,
    )

    payload: Dict[str, Any] = {
        "success": True,
        "business_name": business_name,
        "server_id": server_id,
        "count": len(cleaned_items),
        "latest_only": latest_only,
        "time_range_defaulted": time_range_defaulted,
        "items": cleaned_items,
    }
    if start_dt is not None and end_dt is not None:
        payload["time_range"] = {
            "start": start_dt.isoformat(),
            "end": end_dt.isoformat(),
        }
    return Command(
        update={"messages": [_make_tool_message(tool_call_id, payload)]}
    )
