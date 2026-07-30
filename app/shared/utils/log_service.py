# -*- coding:utf-8 -*-
"""
统一日志服务模块（2026-07-29 落地，Phase 1 基础层）。

提供全项目唯一的「结构化审计 / 操作日志」写入口，避免业务模块各自实现
散落的 INSERT / 内存列表导致的契约漂移。

设计原则（与项目 ``AGENTS.md`` "高内聚低耦合、统一入口/出口" 一致）：

- **唯一写入口**：业务模块统一调用 ``LogService.emit(event)``；模块内任何
  字段缺失 / 非法均会被 ``LogEvent`` 校验拦截或 ``fail-soft`` 降级；
- **线程安全**：其它线程通过 ``loop.call_soon_threadsafe`` 投递事件，
  避免跨线程直接操作 ``asyncio.Queue`` 引发 ``RuntimeError``；
- **背压保护**：asyncio.Queue 容量 10000；达到上限后 ``emit`` 返回 False
  而非无限堆叠内存；
- **批量写入**：后台消费者每攒满 100 条或 500ms 即触发一次
  ``executemany`` 写入 PostgreSQL；DB 异常 ``fail-soft`` 仅记 warning，
  不影响调用方返回 True（事件已被消费者接收）；
- **memory 模式兼容**：当 ``AUTH_STORAGE_MODE=memory`` 或注入 ``memory_only=True``
  时启用进程内列表存储，便于单测 / 演示 / 故障降级；
- **schema 单一入口**：``audit_logs`` 表结构由 ``app/migrations/init_all_tables.sql``
  与本模块 ``init_audit_log_schema``（``@register_schema``）共同维护，
  schema 入口归属于 ``LogService``（替代旧 ``auth/audit_log.py``），保证
  业务模块与 schema 注册单一真相源。

字段语义参考 ``memory/agents-skills.md`` 的「审计日志」与「运维日志聚合」章节。
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import re
import threading
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Iterable, List, Optional, Set

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.core.database import DatabasePool, register_schema

logger = logging.getLogger(__name__)


# =============================================================================
# 审计日志表 schema 初始化（迁移自旧 audit_log.py，2026-07-29）
# =============================================================================


@register_schema
async def init_audit_log_schema():
    """``audit_logs`` 表结构与扩展字段初始化。

    表结构由 ``app/migrations/init_all_tables.sql`` 为单一一手源；本函数
    用于兼容旧部署（init SQL 尚未执行）和测试环境幂等建表。

    与 ``init_all_tables.sql`` 同步的关键字段：

    - 2026-07-29 扩展：log_type / result / level / source / message / session_id /
      request_id / tool_call_id / correlation_id / target_type / target_id /
      target_name / metadata；
    - ``action`` 扩到 ``VARCHAR(100)``；
    - 添加 CHECK 约束 ``chk_audit_logs_log_type`` / ``chk_audit_logs_result`` /
      ``chk_audit_logs_level``，保证枚举层合法性。

    参数:
        无。

    返回:
        None。

    异常:
        asyncpg.PostgresError: 单条语句失败时向上传播。
    """
    statements = (
        """
        CREATE TABLE IF NOT EXISTS audit_logs (
            id SERIAL PRIMARY KEY, user_id INTEGER, username VARCHAR(100),
            action VARCHAR(100) NOT NULL, detail TEXT, ip_address VARCHAR(50),
            log_type VARCHAR(32) NOT NULL DEFAULT 'system',
            result VARCHAR(32) NOT NULL DEFAULT 'success',
            level VARCHAR(16) NOT NULL DEFAULT 'info',
            source VARCHAR(64) NOT NULL DEFAULT 'app',
            message TEXT NOT NULL DEFAULT '', session_id VARCHAR(100),
            request_id VARCHAR(100), tool_call_id VARCHAR(100), correlation_id VARCHAR(100),
            target_type VARCHAR(64), target_id VARCHAR(100), target_name VARCHAR(200),
            metadata JSONB DEFAULT '{}'::jsonb, created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS log_type VARCHAR(32) DEFAULT 'system'",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS result VARCHAR(32) DEFAULT 'success'",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS level VARCHAR(16) DEFAULT 'info'",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS source VARCHAR(64) DEFAULT 'app'",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS message TEXT DEFAULT ''",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS session_id VARCHAR(100)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS request_id VARCHAR(100)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS tool_call_id VARCHAR(100)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS correlation_id VARCHAR(100)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_type VARCHAR(64)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_id VARCHAR(100)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS target_name VARCHAR(200)",
        "ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS metadata JSONB DEFAULT '{}'::jsonb",
        """
        UPDATE audit_logs SET
            log_type = CASE
                WHEN action IN ('login_success', 'login_failure', 'logout') THEN 'auth'
                WHEN action IN ('admin_update_user', 'admin_kick_user') THEN 'user'
                WHEN action = 'admin_delete_session' THEN 'session'
                ELSE 'system'
            END,
            result = CASE WHEN action = 'login_failure' THEN 'failure' ELSE 'success' END,
            level = CASE WHEN action IN ('login_failure', 'admin_kick_user', 'admin_delete_session') THEN 'warning' ELSE 'info' END,
            source = 'audit_log',
            message = COALESCE(NULLIF(message, ''), detail, action)
        WHERE message IS NULL OR message = ''
        """,
        "ALTER TABLE audit_logs ALTER COLUMN log_type SET DEFAULT 'system'",
        "ALTER TABLE audit_logs ALTER COLUMN result SET DEFAULT 'success'",
        "ALTER TABLE audit_logs ALTER COLUMN level SET DEFAULT 'info'",
        "ALTER TABLE audit_logs ALTER COLUMN source SET DEFAULT 'app'",
        "ALTER TABLE audit_logs ALTER COLUMN message SET DEFAULT ''",
        "ALTER TABLE audit_logs ALTER COLUMN log_type SET NOT NULL",
        "ALTER TABLE audit_logs ALTER COLUMN result SET NOT NULL",
        "ALTER TABLE audit_logs ALTER COLUMN level SET NOT NULL",
        "ALTER TABLE audit_logs ALTER COLUMN source SET NOT NULL",
        "ALTER TABLE audit_logs ALTER COLUMN message SET NOT NULL",
        "ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS chk_audit_logs_log_type",
        "ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_logs_log_type CHECK (log_type IN ('auth', 'user', 'session', 'ssh', 'system'))",
        "ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS chk_audit_logs_result",
        "ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_logs_result CHECK (result IN ('success', 'failure', 'blocked', 'pending', 'skipped'))",
        "ALTER TABLE audit_logs DROP CONSTRAINT IF EXISTS chk_audit_logs_level",
        "ALTER TABLE audit_logs ADD CONSTRAINT chk_audit_logs_level CHECK (level IN ('info', 'warning', 'error'))",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_username ON audit_logs(username)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_action ON audit_logs(action)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_created_at ON audit_logs(created_at DESC)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_session_id ON audit_logs(session_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_correlation_id ON audit_logs(correlation_id)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_log_type ON audit_logs(log_type)",
        "CREATE INDEX IF NOT EXISTS idx_audit_logs_level ON audit_logs(level)",
    )
    for statement in statements:
        await DatabasePool.execute(statement)


# =============================================================================


# =============================================================================
# 枚举：与 init_all_tables.sql CHECK 约束 / 索引对齐
# =============================================================================


class LogType(str, Enum):
    """日志类型。"""

    AUTH = "auth"
    USER = "user"
    SESSION = "session"
    SSH = "ssh"
    SYSTEM = "system"


class LogLevel(str, Enum):
    """日志级别。"""

    INFO = "info"
    WARNING = "warning"
    ERROR = "error"


class LogResult(str, Enum):
    """执行结果。"""

    SUCCESS = "success"
    FAILURE = "failure"
    BLOCKED = "blocked"
    PENDING = "pending"
    SKIPPED = "skipped"


# =============================================================================
# LogEvent
# =============================================================================


class LogEvent(BaseModel):
    """统一日志事件。

    Attributes:
        action: 业务动作名（必填）。历史 ``audit_logs.action`` 已存在的取值
            有 ``admin_delete_session`` / ``login_success`` / ``logout`` /
            ``login_failure`` / ``admin_kick_user`` / ``admin_update_user``。
        log_type: 日志类型，详见 :class:`LogType`。
        result: 执行结果，详见 :class:`LogResult`。
        level: 日志级别，详见 :class:`LogLevel`。
        source: 模块来源标识，例如 ``"auth_router"`` / ``"ssh_executor"``。
        message: 人类可读描述（可空）。
        session_id / request_id / tool_call_id / correlation_id:
            关联维度 ID，便于跨模块追踪同一业务事件。
        target_type / target_id / target_name:
            操作目标（类型 / ID / 名称），与 ownership_scope 解耦。
        user_id / username: 触发用户标识。
        ip_address: 触发源 IP（v4 / v6 文本）。
        metadata: 任意附加结构（会被 :func:`redact_metadata` 脱敏后再写入）。
        timestamp: 事件 UTC naive 时间。默认 ``datetime.utcnow()``，序列化
            时按 ``TIMESTAMP WITHOUT TIME ZONE`` 入库；API 输出明确追加 UTC 标记。
    """

    model_config = ConfigDict(extra="forbid", use_enum_values=True)

    action: str = Field(min_length=1, max_length=100)
    log_type: LogType = LogType.SYSTEM
    result: LogResult = LogResult.SUCCESS
    level: LogLevel = LogLevel.INFO
    source: str = "app"
    message: Optional[str] = None
    session_id: Optional[str] = None
    request_id: Optional[str] = None
    tool_call_id: Optional[str] = None
    correlation_id: Optional[str] = None
    target_type: Optional[str] = None
    target_id: Optional[str] = None
    target_name: Optional[str] = None
    user_id: Optional[int] = None
    username: Optional[str] = None
    ip_address: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=lambda: datetime.utcnow())

    @field_validator("timestamp", mode="before")
    @classmethod
    def _ensure_naive_utc(cls, value: Any) -> Any:
        """将带 tzinfo 的 datetime 转换为 UTC naive。

        Args:
            value: 候选 timestamp。

        Returns:
            Any: UTC naive datetime 或原始值。
        """
        if isinstance(value, datetime) and value.tzinfo is not None:
            return value.astimezone(timezone.utc).replace(tzinfo=None)
        return value

    def to_record(self) -> Dict[str, Any]:
        """渲染为数据库 INSERT 行字典（metadata 序列化为 JSON 字符串）。

        Returns:
            Dict[str, Any]: 与 ``audit_logs`` 列一一对应的字典。
        """
        return {
            "log_type": str(self.log_type),
            "result": str(self.result),
            "level": str(self.level),
            "source": self.source,
            "action": self.action,
            "message": self.message,
            "session_id": self.session_id,
            "request_id": self.request_id,
            "tool_call_id": self.tool_call_id,
            "correlation_id": self.correlation_id,
            "target_type": self.target_type,
            "target_id": self.target_id,
            "target_name": self.target_name,
            "user_id": self.user_id,
            "username": self.username,
            "ip_address": self.ip_address,
            "metadata": json.dumps(self.metadata, ensure_ascii=False, default=str),
            "timestamp": self.timestamp,
        }


# =============================================================================
# 敏感字段脱敏（递归）
# =============================================================================

# 大小写不敏感的敏感键集合。增删时与 ``audit_logs.metadata`` 实际写入字段对齐。
def _normalize_key(key: str) -> str:
    """大小写不敏感 + 去除 ``-`` / ``_`` 后的归一化键。"""
    return key.lower().replace("-", "").replace("_", "")


_SENSITIVE_KEYS: Set[str] = {
    "password",
    "passwd",
    "pwd",
    "secret",
    "sectoken",
    "token",
    "accesstoken",
    "refreshtoken",
    "authorization",
    "auth",
    "apikey",
    "api_key",
    "api-key",
    "access_key",
    "privatekey",
    "private_key",
    "mysql_pwd",
    "redis_pwd",
    "cookie",
    "credential",
    "credentials",
}
# 归一化（去 - / _）后的敏感键集合
_NORMALIZED_SENSITIVE_KEYS: Set[str] = {_normalize_key(k) for k in _SENSITIVE_KEYS}
_REDACTED = "***REDACTED***"


def redact_metadata(value: Any) -> Any:
    """递归遍历 dict / list，将键名（大小写不敏感、忽略 ``-``/``_``）
    匹配敏感词的字段脱敏。

    Args:
        value: 待脱敏对象。

    Returns:
        Any: 脱敏后的副本（不会修改原对象）。
    """
    if isinstance(value, dict):
        out: Dict[str, Any] = {}
        for k, v in value.items():
            normalized_key = _normalize_key(k) if isinstance(k, str) else ""
            if normalized_key in _NORMALIZED_SENSITIVE_KEYS:
                out[k] = _REDACTED
            elif normalized_key in {
                "command",
                "sshcommand",
                "interceptreason",
                "decision",
                "interceptcode",
            } and isinstance(v, str):
                out[k] = redact_command(v)
            else:
                out[k] = redact_metadata(v)
        return out
    if isinstance(value, list):
        return [redact_metadata(v) for v in value]
    if isinstance(value, tuple):
        return tuple(redact_metadata(v) for v in value)
    return value


# =============================================================================
# SSH 命令 redact / hash
# =============================================================================

# 敏感键（脱敏白名单）——大小写不敏感、忽略 `-` / `_`。
# 与 redact_metadata 的 _NORMALIZED_SENSITIVE_KEYS 保持一致,避免命令文本与 metadata 字典走两套规则。
# 敏感键(脱敏白名单)——大小写不敏感、忽略 `-` / `_`。
# 与 redact_metadata 的 _NORMALIZED_SENSITIVE_KEYS 保持一致,避免命令文本与 metadata 字典走两套规则。
# 顺序敏感:Python 正则 alternation 从左到右匹配,所以 ``authorization`` 必须排在 ``auth`` 之前,防止 ``auth`` 抢占。
_REDACT_APPROVED_KEYS = (
    "password",
    "passwd",
    "pwd",
    "secret",
    "sectoken",
    "token",
    "accesstoken",
    "refreshtoken",
    "authorization",
    "auth",
    "apikey",
    "api[-_]?key",
    "private[-_]?key",
    "credential",
    "credentials",
)

# 不带 ``--`` 前缀的「裸键」(KEY=value / KEY: value)可识别的 key 集合。
# 注意:``auth`` 是 ``authorization`` 的子串,如单独放进去会被长 key 抢匹配,故从裸键中移除;
# 仅在带 ``--`` 前缀时 ``auth`` 才作为合法 key。
_BARE_APPROVED_KEYS = tuple(k for k in _REDACT_APPROVED_KEYS if k != "authorization")

# 形如 ``--password=xxx`` / ``--password xxx`` / ``--password "xxx"`` / ``--password 'xxx'`` 等。
# 命名组:
# - lead_ws: 前导空白(用于保留原文中段首/管道前的空格)
# - flag: 命中标志(如 ``--password=`` 或 ``--password ``)
# - quote: 值起始引号(单/双,可选)
_SSH_PWD_LONG_PATTERN = re.compile(
    r"(?P<lead_ws>^|[\s;|&])(?P<flag>--(?:" + "|".join(_REDACT_APPROVED_KEYS) + r")(?:\s*=\s*|\s+))(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^\s;|&]+))",
    re.IGNORECASE,
)
# ``-kvalue`` / ``-k value`` 短选项，值支持单引号、双引号与无引号；
# 仅匹配已知敏感短键（password / token / key），避免吞下 ``-u`` / ``-h`` 等无关选项。
_SHORT_PWD_KEYS = (
    "p",
    "password",
    "passwd",
    "pwd",
    "token",
    "key",
    "apikey",
    "secret",
    "auth",
)
_SSH_SHORT_PWD_PATTERN = re.compile(
    r"(?P<lead>^|[\s;|&])-(?P<flag>(?:" + "|".join(_SHORT_PWD_KEYS) + r"))(?:(?P<spacing>\s+)(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^\s'\";|&]+))|(?P<tightquote>['\"])(?P<tq_val>.*?)(?P=tightquote)|(?P<tight>[^\s'\";|&]+))"
)

# ``KEY=value`` 无 ``--`` 前缀的形式(逐个 key 匹配,单词边界避免吞下 ``mypassword`` / ``tokenizer`` 等)。
_SSH_BARE_KEY_PATTERN = re.compile(
    r"(?P<lead_ws>^|[\s;|&])(?P<key>(?:" + "|".join(_BARE_APPROVED_KEYS) + r"))\s*=\s*(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^\s;|&]+))",
    re.IGNORECASE,
)
# ``KEY: value`` 冒号分隔形式，值支持单引号、双引号与无引号。
_SSH_KEY_COLON_PATTERN = re.compile(
    r"(?P<lead_ws>^|[\s|&])(?P<key>(?:" + "|".join(_BARE_APPROVED_KEYS) + r"))\s*:\s*(?:(?P<quote>['\"])(?P<quoted>.*?)(?P=quote)|(?P<plain>[^\s;|&]+))",
    re.IGNORECASE,
)

# Bearer token 形式: ``Authorization: Bearer <token>`` / ``Authorization=Bearer <token>``
_BEARER_TOKEN_PATTERN = re.compile(
    r"(?P<head>Authorization\s*[:=]\s*Bearer\s+)(?P<val>[^\s'\";|&]+)",
    re.IGNORECASE,
)
# URL userinfo: ``scheme://user:password@host``
_URL_USERINFO_PATTERN = re.compile(
    r"(?P<scheme>[a-zA-Z][a-zA-Z0-9+\-.]*://)(?P<user>[^/\s:@]+):(?P<pwd>[^/\s@]+)@"
)

# 控制字符:0x00 - 0x1F(含 \t \n \r)与 0x7F
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f]")

# 截断阈值(2026-07-29 锁定:防止恶意超长命令撑爆审计日志)
_REDACT_MAX_LENGTH = 2000
_REDACT_TRUNCATION_MARKER = "...<truncated>"


def _redact_segment(segment: str) -> str:
    """对单段子串进行口令 / token / URL userinfo / Bearer token 替换。

    Args:
        segment: 单段子串。

    Returns:
        str: 替换后的子串。
    """
    # 1. URL userinfo
    segment = _URL_USERINFO_PATTERN.sub(
        lambda m: f"{m.group('scheme')}{_REDACTED}@", segment
    )
    # 2. Bearer token(必须在 KEY=value / KEY: value 之前,避免 Authorization 被后者吃光)
    segment = _BEARER_TOKEN_PATTERN.sub(
        lambda m: f"{m.group('head')}{_REDACTED}", segment
    )
    # 3. --key=value / --key value(覆盖 =/空格 + 单/双/无引号)
    segment = _SSH_PWD_LONG_PATTERN.sub(
        lambda m: f"{m.group('lead_ws')}{m.group('flag')}{_REDACTED}", segment
    )
    # 4. KEY: value(冒号分隔)
    segment = _SSH_KEY_COLON_PATTERN.sub(
        lambda m: f"{m.group('lead_ws')}{m.group('key')}: {_REDACTED}", segment
    )
    # 5. KEY=value(裸键)
    segment = _SSH_BARE_KEY_PATTERN.sub(
        lambda m: f"{m.group('lead_ws')}{m.group('key')}={_REDACTED}", segment
    )
    # 6. 短选项 -kvalue / -k value
    def _short_repl(m: "re.Match[str]") -> str:
        lead = m.group("lead") or ""
        flag = m.group("flag")
        if m.group("spacing"):
            return f"{lead}-{flag}{m.group('spacing')}{_REDACTED}"
        return f"{lead}-{flag}{_REDACTED}"

    segment = _SSH_SHORT_PWD_PATTERN.sub(_short_repl, segment)
    # 7. 控制字符清除
    segment = _CONTROL_CHARS_PATTERN.sub("", segment)
    return segment


def _truncate_redacted(value: str) -> str:
    """截断 redact 结果,避免超长日志撑爆存储。

    Args:
        value: redact 后的命令。

    Returns:
        str: 截断后的字符串(超过 ``_REDACT_MAX_LENGTH`` 时追加 ``...<truncated>`` 标记)。
    """
    if len(value) <= _REDACT_MAX_LENGTH:
        return value
    keep = _REDACT_MAX_LENGTH - len(_REDACT_TRUNCATION_MARKER)
    if keep < 0:
        keep = 0
    return value[:keep] + _REDACT_TRUNCATION_MARKER


def redact_command(command: Optional[str]) -> str:
    """SSH 命令 redact:管道 / 逻辑与或 / 分号分段独立替换敏感口令 / Bearer / URL userinfo。

    覆盖模式:
    - ``--password=value`` / ``--password value`` / ``--password "value"`` / ``--password 'value'``
    - ``--token=value`` / ``--api-key=value`` / ``--authorization=value`` 等同族
    - ``KEY=value`` / ``export KEY=value``(无 ``--`` 前缀)
    - ``KEY: value``(冒号分隔)
    - ``-pvalue``(短选项)
    - ``Authorization: Bearer <token>``
    - ``scheme://user:password@host``(URL userinfo)
    - 控制字符(``\\r`` ``\\n`` ``\\t`` ``\\x00`` 等)全部清除
    - 截断 2000 字符上限,追加 ``...<truncated>`` 标记

    Args:
        command: 原始命令文本(可空)。

    Returns:
        str: redact 后的命令(结构与原命令一致,仅敏感位置被替换并截断)。
    """
    if not command:
        return command or ""
    pieces: List[str] = []
    for sep_full, seg in _split_command_segments(command):
        redacted = _redact_segment(seg)
        if sep_full:
            if redacted and redacted[0] == " " and sep_full.endswith(" "):
                pieces.append(sep_full[:-1])
            else:
                pieces.append(sep_full)
        pieces.append(redacted)
    return _truncate_redacted("".join(pieces))


def _split_command_segments(command: str) -> List[tuple]:
    """按 shell 操作符拆分（用于 SSH 命令独立 redact）。

    返回 ``(separator_with_padding, segment)`` 列表；separator_with_padding
    包含操作符及其前后空白（取原始命令中的样子）。首段 separator 为 ``""``。

    Args:
        command: 原始命令字符串。

    Returns:
        List[tuple]: ``[(sep_full, seg), ...]``，至少 1 项。
    """

    segments: List[tuple] = []
    buf: List[str] = []
    sep_full = ""
    in_single = False
    in_double = False
    i = 0
    n = len(command)
    while i < n:
        ch = command[i]
        if in_single:
            buf.append(ch)
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            buf.append(ch)
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            buf.append(ch)
            i += 1
            continue
        if ch == '"':
            in_double = True
            buf.append(ch)
            i += 1
            continue
        if ch == "\\" and i + 1 < n:
            buf.append(ch)
            buf.append(command[i + 1])
            i += 2
            continue
        if ch == "|" or ch == ";":
            seg = "".join(buf)
            # 仅去前导空白,保留段尾空白(段尾空白 = separator 前的空格)
            head_stripped = seg.lstrip(" \t")
            if head_stripped:
                segments.append((sep_full, head_stripped))
            # 收集 separator + 后续空白作为下一个 separator
            sep_full = ch
            j = i + 1
            while j < n and command[j] in (" ", "\t"):
                sep_full += command[j]
                j += 1
            buf = []
            i = j
            continue
        if ch == "&" and i + 1 < n and command[i + 1] == "&":
            seg = "".join(buf)
            head_stripped = seg.lstrip(" \t")
            if head_stripped:
                segments.append((sep_full, head_stripped))
            sep_full = "&&"
            j = i + 2
            while j < n and command[j] in (" ", "\t"):
                sep_full += command[j]
                j += 1
            buf = []
            i = j
            continue
        buf.append(ch)
        i += 1
    seg = "".join(buf)
    head_stripped = seg.strip(" \t")
    if head_stripped:
        segments.append((sep_full, head_stripped))
    if not segments:
        segments.append(("", command))
    return segments


def hash_command(command: str) -> str:
    """对命令做 SHA-256 哈希（hex,小写,64 字符）。

    Args:
        command: 原始或 redact 后的命令文本。

    Returns:
        str: 64 字符 SHA-256 hex digest。
    """
    return hashlib.sha256((command or "").encode("utf-8")).hexdigest()


# =============================================================================
# LogService
# =============================================================================


_INSERT_SQL = (
    "INSERT INTO audit_logs ("
    "log_type, result, level, source, action, message, "
    "session_id, request_id, tool_call_id, correlation_id, "
    "target_type, target_id, target_name, "
    "user_id, username, ip_address, metadata, created_at"
    ") VALUES ("
    "$1, $2, $3, $4, $5, $6, "
    "$7, $8, $9, $10, "
    "$11, $12, $13, "
    "$14, $15, $16, $17::jsonb, $18"
    ")"
)

_QUERY_SELECT = (
    "SELECT id, log_type, result, level, source, action, message, "
    "session_id, request_id, tool_call_id, correlation_id, "
    "target_type, target_id, target_name, "
    "user_id, username, ip_address, metadata, created_at "
    "FROM audit_logs"
)


class LogService:
    """统一日志服务（单例 + 后台消费协程）。

    Attributes:
        _db_pool: 可选 asyncpg Pool 引用；``None`` 时仅走内存模式。
        _memory_only: 强制走内存模式（即使 db_pool 注入）。
        _queue: asyncio.Queue 背压 10000。
        _batch_size: 批量写入阈值（默认 100）。
        _flush_interval_seconds: flush 周期（默认 0.5s）。
        _consumer_task: 后台消费协程。
        _memory_lock: 内存模式读写锁。
        _memory_records: 内存模式行列表（dict）。
    """

    QUEUE_MAX_SIZE = 10000
    DEFAULT_BATCH_SIZE = 100
    DEFAULT_FLUSH_INTERVAL_SECONDS = 0.5

    def __init__(
        self,
        *,
        db_pool: Any = None,
        memory_only: bool = False,
        batch_size: int = DEFAULT_BATCH_SIZE,
        flush_interval_seconds: float = DEFAULT_FLUSH_INTERVAL_SECONDS,
    ) -> None:
        """构造 LogService（不启动后台协程，需显式调用 ``start``）。

        Args:
            db_pool: asyncpg 连接池（生产从 ``DatabasePool._pool`` 取）。
            memory_only: 强制内存模式（``AUTH_STORAGE_MODE=memory`` / 单测）。
            batch_size: 批量写入阈值。
            flush_interval_seconds: flush 周期（秒）。
        """
        self._db_pool = db_pool
        self._memory_only = bool(memory_only or os.getenv("AUTH_STORAGE_MODE", "memory") != "postgres")
        self._batch_size = int(batch_size)
        self._flush_interval_seconds = float(flush_interval_seconds)
        self._queue: asyncio.Queue = asyncio.Queue(maxsize=self.QUEUE_MAX_SIZE)
        self._consumer_task: Optional[asyncio.Task] = None
        self._consumer_started = False
        self._accepting = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._stop_event = asyncio.Event()
        self._memory_lock = threading.RLock()
        self._memory_records: List[Dict[str, Any]] = []
        self._memory_next_id = 1
        # 2026-07-29 线程安全容量预留:
        # ``emit`` 在 worker 线程被频繁调用,直接 ``qsize()`` 检查存在「检查后到 put_nowait
        # 之间被调度回调消费一空」→ 「put_nowait 永不超容」的竞态;通过 ``_reserve_lock`` +
        # ``_reserved_count`` 在调度前预留名额,事件循环线程入队后释放预留。
        self._reserve_lock = threading.Lock()
        self._reserved_count = 0

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """启动后台消费协程（幂等）。

        Returns:
            None
        """
        if self._consumer_started:
            return
        self._stop_event.clear()
        self._loop = asyncio.get_running_loop()
        self._consumer_task = self._loop.create_task(self._consume_loop())
        self._consumer_started = True
        self._accepting = True

    async def stop(self) -> None:
        """停止后台消费协程并 flush 残留事件。

        Returns:
            None
        """
        if not self._consumer_started:
            return
        self._accepting = False
        await asyncio.sleep(0)
        self._stop_event.set()
        task = self._consumer_task
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=5.0)
            except asyncio.TimeoutError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            except asyncio.CancelledError:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
        await self._flush_remaining()
        self._consumer_task = None
        self._consumer_started = False
        self._loop = None

    def emit(self, event: LogEvent) -> bool:
        """统一同步入口，通过启动时保存的事件循环线程安全调度入队。

        实现要点:
            1. 服务可接收校验(必须 started / accepting / loop alive)
            2. **线程安全容量预留** (2026-07-29 锁定):``_reserve_lock`` 保护下检查
               ``qsize + reserved >= QUEUE_MAX_SIZE``,若超容直接 ``return False``
               (不调度,避免消费者无暇 flush 时继续堆积)
            3. 通过 ``loop.call_soon_threadsafe`` 调度 ``_enqueue_sync`` 入队;
               调度失败时回滚 ``_reserved_count`` 并 ``return False``
            4. ``_enqueue_sync`` 在事件循环线程同步执行,入队成功 / ``QueueFull``
               均释放预留,保证 ``_reserved_count`` 不泄漏

        Args:
            event: 已通过 ``LogEvent`` 校验的日志事件。

        Returns:
            bool: 服务可接收且调度成功时为 True，否则为 False。
        """
        loop = self._loop
        if not self._consumer_started or not self._accepting or loop is None or loop.is_closed():
            return False
        # 1. 容量检查 + 预留(线程安全)
        with self._reserve_lock:
            current_size = self._queue.qsize()
            if current_size + self._reserved_count >= self.QUEUE_MAX_SIZE:
                # 已达上限:直接拒绝,不再调度
                return False
            self._reserved_count += 1
        snapshot = event.model_copy(deep=True)
        snapshot.metadata = redact_metadata(snapshot.metadata)
        # 2. 调度入队(失败回滚预留)
        try:
            loop.call_soon_threadsafe(self._enqueue_sync, snapshot)
            return True
        except RuntimeError:
            with self._reserve_lock:
                self._reserved_count -= 1
            return False

    # ------------------------------------------------------------------
    # 内部：后台消费循环
    # ------------------------------------------------------------------

    def _enqueue_sync(self, event: LogEvent) -> None:
        """线程安全 enqueue（仅被 call_soon_threadsafe 调用）。

        无论入队成功 / 失败,均释放 ``_reserved_count``(由 emit 预留),
        避免预留名额泄漏导致后续 emit 永远返回 False。

        Args:
            event: 待写入事件。
        """
        try:
            self._queue.put_nowait(event)
        except asyncio.QueueFull:
            logger.error("[LogService] queue full in scheduled enqueue action=%s", event.action)
        finally:
            with self._reserve_lock:
                if self._reserved_count > 0:
                    self._reserved_count -= 1

    async def _consume_loop(self) -> None:
        """后台消费协程：攒批 + flush + 收尾。"""
        batch: List[LogEvent] = []
        try:
            while not self._stop_event.is_set():
                try:
                    first = await asyncio.wait_for(
                        self._queue.get(), timeout=self._flush_interval_seconds
                    )
                    batch.append(first)
                except asyncio.TimeoutError:
                    continue
                deadline = asyncio.get_running_loop().time() + self._flush_interval_seconds
                while len(batch) < self._batch_size and not self._stop_event.is_set():
                    remaining = deadline - asyncio.get_running_loop().time()
                    if remaining <= 0:
                        break
                    try:
                        batch.append(await asyncio.wait_for(self._queue.get(), timeout=remaining))
                    except asyncio.TimeoutError:
                        break
                await self._flush_batch(batch)
                batch = []
        except asyncio.CancelledError:
            if batch:
                await self._flush_batch(batch)
            raise
        except Exception as exc:  # pragma: no cover - 防御性兜底
            logger.exception("[LogService] consume loop crashed: %s", exc)

    async def _flush_batch(self, batch: Iterable[LogEvent]) -> None:
        """flush 一批事件到内存 / DB（fail-soft）。

        Args:
            batch: 一批事件。
        """
        events = list(batch)
        if not events:
            return
        if self._memory_only or self._db_pool is None:
            with self._memory_lock:
                for evt in events:
                    self._store_memory(evt)
            return
        rows = [self._materialize_row(evt) for evt in events]
        try:
            async with self._db_pool.acquire() as conn:  # type: ignore[attr-defined]
                await conn.executemany(_INSERT_SQL, rows)
        except Exception as exc:
            logger.warning(
                "[LogService] batch insert failed (%d rows): %s",
                len(rows),
                type(exc).__name__,
            )
            # fail-soft:DB 失败时回退内存,避免调用方感知
            with self._memory_lock:
                for evt in events:
                    self._store_memory(evt)

    async def _flush_remaining(self) -> None:
        """停止时排空队列中残留事件。

        Returns:
            None
        """
        leftover: List[LogEvent] = []
        while True:
            try:
                leftover.append(self._queue.get_nowait())
            except asyncio.QueueEmpty:
                break
        if leftover:
            await self._flush_batch(leftover)

    def _materialize_row(self, event: LogEvent) -> tuple:
        """把 LogEvent 物化为 executemany 行元组（顺序与 ``_INSERT_SQL`` 占位符对齐）。

        Args:
            event: 待写入事件。

        Returns:
            tuple: 与 SQL 占位符 $1..$18 一一对应的元组。
        """
        redacted_meta = redact_metadata(event.metadata)
        metadata_json = json.dumps(redacted_meta, ensure_ascii=False, default=str)
        return (
            str(event.log_type),
            str(event.result),
            str(event.level),
            event.source,
            event.action,
            event.message or event.action,
            event.session_id,
            event.request_id,
            event.tool_call_id,
            event.correlation_id,
            event.target_type,
            event.target_id,
            event.target_name,
            event.user_id,
            event.username,
            event.ip_address,
            metadata_json,
            event.timestamp,
        )

    # ------------------------------------------------------------------
    # 内部：内存存储
    # ------------------------------------------------------------------

    def _store_memory(self, event: LogEvent) -> None:
        """把事件写入内存表。

        Args:
            event: 待写入事件。
        """
        redacted_meta = redact_metadata(event.metadata)
        row = {
            "id": self._memory_next_id,
            "log_type": str(event.log_type),
            "result": str(event.result),
            "level": str(event.level),
            "source": event.source,
            "action": event.action,
            "message": event.message or event.action,
            "session_id": event.session_id,
            "request_id": event.request_id,
            "tool_call_id": event.tool_call_id,
            "correlation_id": event.correlation_id,
            "target_type": event.target_type,
            "target_id": event.target_id,
            "target_name": event.target_name,
            "user_id": event.user_id,
            "username": event.username,
            "ip_address": event.ip_address,
            "metadata": redacted_meta,
            "created_at": event.timestamp,
        }
        self._memory_records.append(row)
        self._memory_next_id += 1

    # ------------------------------------------------------------------
    # 公共查询（memory / PostgreSQL 同契约）
    # ------------------------------------------------------------------

    @staticmethod
    def _query_filters(
        *, log_type: Optional[str] = None, action: Optional[str] = None,
        result: Optional[str] = None, level: Optional[str] = None,
        source: Optional[str] = None, user_id: Optional[int] = None,
        username: Optional[str] = None, session_id: Optional[str] = None,
        request_id: Optional[str] = None, tool_call_id: Optional[str] = None,
        correlation_id: Optional[str] = None, target_type: Optional[str] = None,
        target_id: Optional[str] = None, target_name: Optional[str] = None,
        created_from: Optional[datetime] = None, created_to: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """整理固定白名单过滤器。

        Returns:
            Dict[str, Any]: 非空过滤器。
        """
        values = locals()
        return {key: value for key, value in values.items() if value is not None}

    @staticmethod
    def _build_where(filters: Dict[str, Any]) -> tuple[str, List[Any]]:
        """构造参数化 WHERE 子句。

        Args:
            filters: 固定白名单过滤器。
        Returns:
            tuple[str, List[Any]]: WHERE SQL 与参数。
        """
        operators = {"created_from": ("created_at", ">="), "created_to": ("created_at", "<=")}
        clauses: List[str] = []
        params: List[Any] = []
        for key, value in filters.items():
            column, operator = operators.get(key, (key, "="))
            params.append(value)
            clauses.append(f"{column} {operator} ${len(params)}")
        return (" WHERE " + " AND ".join(clauses) if clauses else "", params)

    def _memory_filtered(self, filters: Dict[str, Any]) -> List[Dict[str, Any]]:
        """按统一契约过滤内存记录。

        Args:
            filters: 固定白名单过滤器。
        Returns:
            List[Dict[str, Any]]: 深复制前的命中记录。
        """
        with self._memory_lock:
            rows = list(self._memory_records)
        for key, value in filters.items():
            if key == "created_from":
                rows = [row for row in rows if row["created_at"] >= value]
            elif key == "created_to":
                rows = [row for row in rows if row["created_at"] <= value]
            else:
                rows = [row for row in rows if row.get(key) == value]
        return rows

    async def query_logs(
        self, *, log_type: Optional[str] = None, action: Optional[str] = None,
        result: Optional[str] = None, level: Optional[str] = None,
        source: Optional[str] = None, user_id: Optional[int] = None,
        username: Optional[str] = None, session_id: Optional[str] = None,
        request_id: Optional[str] = None, tool_call_id: Optional[str] = None,
        correlation_id: Optional[str] = None, target_type: Optional[str] = None,
        target_id: Optional[str] = None, target_name: Optional[str] = None,
        created_from: Optional[datetime] = None, created_to: Optional[datetime] = None,
        limit: int = 100, offset: int = 0,
    ) -> List[Dict[str, Any]]:
        """按固定字段查询日志。

        Returns:
            List[Dict[str, Any]]: 按 created_at 倒序的日志。
        """
        filters = self._query_filters(**{key: value for key, value in locals().items() if key not in {"self", "limit", "offset"}})
        if self._memory_only or self._db_pool is None:
            rows = self._memory_filtered(filters)
            rows.sort(key=lambda row: row["created_at"], reverse=True)
            return [dict(row) for row in rows[offset:offset + limit]]
        where, params = self._build_where(filters)
        params.extend([limit, offset])
        sql = f"{_QUERY_SELECT}{where} ORDER BY created_at DESC LIMIT ${len(params)-1} OFFSET ${len(params)}"
        async with self._db_pool.acquire() as conn:
            return [dict(row) for row in await conn.fetch(sql, *params)]

    async def count_logs(
        self, *, log_type: Optional[str] = None, action: Optional[str] = None,
        result: Optional[str] = None, level: Optional[str] = None,
        source: Optional[str] = None, user_id: Optional[int] = None,
        username: Optional[str] = None, session_id: Optional[str] = None,
        request_id: Optional[str] = None, tool_call_id: Optional[str] = None,
        correlation_id: Optional[str] = None, target_type: Optional[str] = None,
        target_id: Optional[str] = None, target_name: Optional[str] = None,
        created_from: Optional[datetime] = None, created_to: Optional[datetime] = None,
    ) -> int:
        """按固定字段统计日志。

        Returns:
            int: 命中数量。
        """
        filters = self._query_filters(**{key: value for key, value in locals().items() if key != "self"})
        if self._memory_only or self._db_pool is None:
            return len(self._memory_filtered(filters))
        where, params = self._build_where(filters)
        async with self._db_pool.acquire() as conn:
            return int(await conn.fetchval(f"SELECT COUNT(*) FROM audit_logs{where}", *params))

    async def get_log(self, log_id: int) -> Optional[Dict[str, Any]]:
        """按 ID 查询单条日志。

        Args:
            log_id: 日志 ID。
        Returns:
            Optional[Dict[str, Any]]: 日志或 None。
        """
        if self._memory_only or self._db_pool is None:
            with self._memory_lock:
                row = next((item for item in self._memory_records if item["id"] == log_id), None)
            return dict(row) if row else None
        async with self._db_pool.acquire() as conn:
            row = await conn.fetchrow(f"{_QUERY_SELECT} WHERE id = $1", log_id)
            return dict(row) if row else None

    async def get_correlated_logs(self, correlation_id: str) -> List[Dict[str, Any]]:
        """按 correlation_id 查询关联日志。

        Args:
            correlation_id: 关联 ID。
        Returns:
            List[Dict[str, Any]]: 按 created_at 正序的日志。
        """
        if self._memory_only or self._db_pool is None:
            rows = self._memory_filtered({"correlation_id": correlation_id})
            rows.sort(key=lambda row: row["created_at"])
            return [dict(row) for row in rows]
        async with self._db_pool.acquire() as conn:
            rows = await conn.fetch(f"{_QUERY_SELECT} WHERE correlation_id = $1 ORDER BY created_at ASC", correlation_id)
            return [dict(row) for row in rows]

    def reset_for_test(self) -> None:
        """清空内存表 + 重置 id 计数（仅供测试使用）。"""
        with self._memory_lock:
            self._memory_records.clear()
            self._memory_next_id = 1


# =============================================================================
# 单例管理
# =============================================================================


_log_service_singleton: Optional[LogService] = None
_log_service_lock = threading.Lock()


def set_log_service(service: LogService) -> None:
    """设置全局单例。

    Args:
        service: LogService 实例。
    """
    global _log_service_singleton
    with _log_service_lock:
        _log_service_singleton = service


def get_log_service() -> Optional[LogService]:
    """获取全局单例。

    Returns:
        Optional[LogService]: 已注册实例或 None。
    """
    with _log_service_lock:
        return _log_service_singleton


def reset_log_service() -> None:
    """重置全局单例。"""
    global _log_service_singleton
    with _log_service_lock:
        _log_service_singleton = None