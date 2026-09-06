# -*- coding:utf-8 -*-
"""
NotificationConfigService - 通知渠道通用配置服务

设计原则（2026-09-03 落地，详见 ``memory/misc.md`` 「通知渠道通用表设计原则」）：

- 所有新渠道（飞书 / 钉钉 / 企微 / Slack）共用 ``notification_channels`` +
  ``notification_targets`` 两张通用表，通过 ``channel_type`` / ``target_type`` 字段区分
- 凭证差异一律进 ``config`` JSONB，service 层按 ``channel_type`` 分发
- 邮件老表（``email_server_configs`` / ``email_policies`` / ``email_policy_recipients``）
  完全不动；本服务不替代 ``EmailConfigService``

凭证加解密：复用 ``DEVOPS_CREDENTIAL_KEY``，与邮件同款约定（Fernet 加密 →
ascii 解码为 str 写入 TEXT 列；asyncpg 不接受 bytes 入 TEXT 列）。
"""
from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Dict, List, Optional, Tuple

from cryptography.fernet import Fernet, InvalidToken

from app.shared.utils.auth.ownership_scope import OwnershipScope


logger = logging.getLogger(__name__)


# =============================================================================
# Exceptions
# =============================================================================


class NotificationConfigError(Exception):
    """通知渠道配置相关错误基类。"""


class NotificationConfigNotFoundError(NotificationConfigError):
    """渠道或目标不存在时抛出。"""


class NotificationConfigValidationError(NotificationConfigError):
    """配置参数校验失败时抛出。"""


# =============================================================================
# Constants（白名单，未来扩展 ALTER 约束）
# =============================================================================

# channel_type 白名单（本期仅注册 feishu）
SUPPORTED_CHANNEL_TYPES: Tuple[str, ...] = ("feishu",)

# target_type 白名单（本期仅注册 feishu.chat + feishu.user）
SUPPORTED_TARGET_TYPES: Tuple[str, ...] = (
    "feishu.chat",
    "feishu.user",
)

# 飞书 config 必填字段（写入 DB 前 fail-fast 校验）
FEISHU_REQUIRED_CONFIG_KEYS: Tuple[str, ...] = (
    "app_id_encrypted",      # Fernet 加密后的 app_id
    "app_secret_encrypted",  # Fernet 加密后的 app_secret
    "default_receive_id",    # 默认接收方 ID（群 chat_id 或 open_id）
    "default_receive_id_type",  # chat_id / open_id / user_id / email
    "log_level",             # SDK 日志级别 DEBUG / INFO / WARNING / ERROR
    "agent_name",            # WS 实例绑定的目标 agent 名（如 "project"）
    "receiver_username",     # 该应用 session 归属系统用户名
)

# 飞书 target config 必填字段
FEISHU_TARGET_REQUIRED_CONFIG_KEYS: Tuple[str, ...] = (
    "chat_id",     # 群 ID / 用户 open_id 等
    "chat_type",   # chat_id / open_id / user_id / email
)

# 接收方类型白名单
FEISHU_RECEIVE_ID_TYPES: Tuple[str, ...] = ("chat_id", "open_id", "user_id", "email")


# =============================================================================
# Service
# =============================================================================


class NotificationConfigService:
    """通知渠道通用配置服务。

    参数:
        db: asyncpg 连接池；支持 ``fetch`` / ``fetchrow`` / ``execute`` / ``fetchval``
            异步方法。测试可传 ``None``，但所有 DB 方法将无法调用。
        credential_key: Fernet 对称密钥（base64 字符串）；空字符串代表未配置，
            ``_ensure_fernet`` 在首次解密时抛 ``NotificationConfigError``。
    """

    def __init__(self, db: Any, credential_key: str) -> None:
        """初始化服务。

        参数:
            db: asyncpg 连接池。
            credential_key: Fernet 密钥。

        异常:
            NotificationConfigError: ``credential_key`` 非空但非法时抛出。
        """
        self._db = db
        self._credential_key = credential_key or ""
        self._fernet: Optional[Fernet] = None
        self._write_lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Fernet helper（与 EmailConfigService 同款）
    # ------------------------------------------------------------------

    def _ensure_fernet(self) -> Fernet:
        """惰性构造 Fernet 实例。

        异常:
            NotificationConfigError: ``credential_key`` 为空或非法时抛出。
        """
        if self._fernet is not None:
            return self._fernet
        if not self._credential_key:
            raise NotificationConfigError(
                "credential_key 未配置（请在 .env 中设置 DEVOPS_CREDENTIAL_KEY）"
            )
        try:
            self._fernet = Fernet(self._credential_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise NotificationConfigError(
                f"credential_key 不是合法 Fernet base64 密钥: {exc}"
            ) from exc
        return self._fernet

    @staticmethod
    def _to_db_str(value: Any) -> str:
        """将 Fernet 密文规范化为可写入 ``TEXT`` 列的字符串。

        asyncpg 对 ``TEXT`` 列不接受 ``bytes``，必须转 str（Fernet token
        仅含 url-safe base64 ASCII 字符）。

        异常:
            NotificationConfigError: 输入不是合法 Fernet token（解码失败）。
        """
        if isinstance(value, str):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                return bytes(value).decode("ascii")
            except UnicodeDecodeError as exc:
                raise NotificationConfigError(
                    "Fernet 密文包含非 ASCII 字符，无法存入 TEXT 列"
                ) from exc
        raise NotificationConfigError(
            f"Fernet 密文类型非法，期望 bytes/str，实际 {type(value).__name__}"
        )

    # ------------------------------------------------------------------
    # Preload（保留入口占位；未来加缓存时启用）
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """启动时预加载（本期无内存缓存；保留接口与 EmailConfigService 对齐）。"""
        # 未来可在 _cache 缓存 default channel；本期不实现
        logger.info(
            "[notification_config_service] preload_all called (db=%s)",
            "available" if self._db is not None else "unavailable",
        )

    # ------------------------------------------------------------------
    # Channel CRUD（凭证通用表）
    # ------------------------------------------------------------------

    async def list_channels(
        self,
        channel_type: Optional[str] = None,
        enabled_only: bool = False,
    ) -> List[Dict[str, Any]]:
        """列出渠道。

        参数:
            channel_type: 仅返回该渠道类型；None 返回全部。
            enabled_only: True 时仅返回 ``enabled=TRUE`` 的行。

        返回:
            List[Dict[str, Any]]: 每项含 ``id`` / ``name`` / ``display_name`` /
            ``channel_type`` / ``config``（加密字段已脱敏为空串）/ ``enabled`` /
            ``is_default`` / ``created_at`` / ``updated_at``。
        """
        if self._db is None:
            return []
        conditions: List[str] = []
        params: List[Any] = []
        if channel_type is not None:
            params.append(channel_type)
            conditions.append(f"channel_type = ${len(params)}")
        if enabled_only:
            conditions.append("enabled = TRUE")
        where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""
        rows = await self._db.fetch(
            f"""
            SELECT id, name, display_name, channel_type, config, enabled,
                   is_default, created_by_user_id, created_at, updated_at
            FROM notification_channels
            {where_sql}
            ORDER BY id ASC
            """,
            *params,
        )
        return [self._channel_to_public(row) for row in rows]

    async def get_channel(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """读取单个渠道（密码脱敏）。

        返回:
            Optional[Dict[str, Any]]: 渠道详情；不存在返回 None。
        """
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, name, display_name, channel_type, config, enabled,
                   is_default, created_by_user_id, created_at, updated_at
            FROM notification_channels
            WHERE id = $1
            """,
            channel_id,
        )
        if row is None:
            return None
        return self._channel_to_public(row)

    async def _get_channel_internal(self, channel_id: int) -> Optional[Dict[str, Any]]:
        """读取单个渠道（config 含加密字段原文），仅 service 内部使用。"""
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, name, display_name, channel_type, config, enabled,
                   is_default, created_by_user_id, created_at, updated_at
            FROM notification_channels
            WHERE id = $1
            """,
            channel_id,
        )
        if row is None:
            return None
        return self._channel_to_internal(row)

    async def get_channel_by_name(
        self,
        name: str,
        channel_type: str = "feishu",
    ) -> Optional[Dict[str, Any]]:
        """按名称读取渠道（密码脱敏）。"""
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, name, display_name, channel_type, config, enabled,
                   is_default, created_by_user_id, created_at, updated_at
            FROM notification_channels
            WHERE name = $1 AND channel_type = $2
            """,
            name,
            channel_type,
        )
        if row is None:
            return None
        return self._channel_to_public(row)

    async def upsert_channel(
        self,
        channel_type: str,
        name: str,
        display_name: str,
        config: Dict[str, Any],
        enabled: bool,
        is_default: bool,
        created_by_user_id: Optional[int],
        keep_existing_secret: bool = False,
    ) -> Dict[str, Any]:
        """新建或更新渠道（按 name + channel_type 唯一约束）。

        参数:
            channel_type: 渠道类型（白名单）。
            name: 渠道名（按 channel_type 唯一）。
            display_name: 显示名。
            config: 渠道配置 dict（含加密字段明文，必填 ``app_id_encrypted`` /
                ``app_secret_encrypted`` 等，service 会 Fernet 加密写入）。
            enabled: 是否启用。
            is_default: 是否默认渠道（部分唯一索引约束每 channel_type 仅 1 行）。
            created_by_user_id: 创建者用户 ID；首次创建必填。
            keep_existing_secret: True 时保留原 config 中加密字段
                （用于前端「密钥留空表示不修改」场景）。

        返回:
            Dict[str, Any]: 含 ``id`` / ``updated_at`` / ``created`` 字段。

        异常:
            NotificationConfigValidationError: channel_type 不在白名单、
                config 缺必填字段、name 已存在但 channel_type 不同等。
            NotificationConfigError: Fernet 加密失败。
        """
        # channel_type 白名单校验提前(在 db 检查前),保证输入校验总在 IO 前
        if channel_type not in SUPPORTED_CHANNEL_TYPES:
            raise NotificationConfigValidationError(
                f"channel_type 不在白名单 {SUPPORTED_CHANNEL_TYPES}，"
                f"实际为: {channel_type!r}"
            )
        if self._db is None:
            raise NotificationConfigError("数据库未初始化")
        if not name or not name.strip():
            raise NotificationConfigValidationError("name 不能为空")

        # config JSONB 守卫（防止非 object 类型入 JSONB 列）
        if not isinstance(config, dict):
            raise NotificationConfigValidationError("config 必须是 dict 类型")
        # 校验 config 必填字段
        self._validate_config(channel_type, config)

        # 处理加密字段
        config_db = dict(config)
        fernet = self._ensure_fernet()
        if channel_type == "feishu":
            if not keep_existing_secret:
                # 必填：app_id_encrypted / app_secret_encrypted
                # 调用方传明文 app_id / app_secret 时由 router 加密；这里假设已加密
                # （router 层负责「明文 → 加密」转换，service 层接收密文）
                for k in ("app_id_encrypted", "app_secret_encrypted"):
                    v = config_db.get(k)
                    if not v:
                        raise NotificationConfigValidationError(
                            f"config.{k} 不能为空"
                        )
            else:
                # 保留原密钥：调用方需在传 config 前先把空字段填充为已存在的密文
                # （router 层处理）
                pass
            # log_level 默认值
            config_db.setdefault("log_level", "INFO")
            # 校验 receive_id_type
            recv_type = config_db.get("default_receive_id_type", "chat_id")
            if recv_type not in FEISHU_RECEIVE_ID_TYPES:
                raise NotificationConfigValidationError(
                    f"default_receive_id_type 必须是 {FEISHU_RECEIVE_ID_TYPES} 之一，"
                    f"实际为: {recv_type!r}"
                )

        config_json = json.dumps(config_db, ensure_ascii=False)

        # 检查是否已存在（同 channel_type + name）
        existing = await self._db.fetchrow(
            """
            SELECT id FROM notification_channels
            WHERE name = $1 AND channel_type = $2
            """,
            name, channel_type,
        )

        async with self._write_lock:
            # 若 is_default=True，先把同 channel_type 的其他行 is_default 置 False
            if is_default:
                await self._db.execute(
                    """
                    UPDATE notification_channels
                    SET is_default = FALSE
                    WHERE channel_type = $1 AND (is_default = TRUE)
                    """,
                    channel_type,
                )

            if existing is not None:
                row = await self._db.fetchrow(
                    """
                    UPDATE notification_channels
                    SET display_name = $1, config = $2::jsonb, enabled = $3,
                        is_default = $4, updated_at = CURRENT_TIMESTAMP
                    WHERE id = $5
                    RETURNING id, updated_at
                    """,
                    display_name, config_json, enabled, is_default, existing["id"],
                )
                return {"id": row["id"], "updated_at": row["updated_at"], "created": False}
            else:
                row = await self._db.fetchrow(
                    """
                    INSERT INTO notification_channels
                        (name, display_name, channel_type, config, enabled,
                         is_default, created_by_user_id)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7)
                    RETURNING id, updated_at
                    """,
                    name, display_name, channel_type, config_json, enabled,
                    is_default, created_by_user_id,
                )
                return {"id": row["id"], "updated_at": row["updated_at"], "created": True}

    async def delete_channel(self, channel_id: int) -> bool:
        """删除渠道（级联清理 targets）。

        返回:
            bool: 删除成功返回 True；渠道不存在返回 False。
        """
        if self._db is None:
            return False
        result = await self._db.execute(
            "DELETE FROM notification_channels WHERE id = $1",
            channel_id,
        )
        return "DELETE 1" in str(result)

    async def set_default_channel(
        self,
        channel_id: int,
        channel_type: str,
    ) -> bool:
        """把指定渠道设为该 channel_type 的默认渠道。

        实现方式：先 UPDATE 同 channel_type 所有行 is_default=FALSE，
        再 UPDATE 目标行 is_default=TRUE。两次操作在 write_lock 内执行。

        返回:
            bool: 渠道存在并成功设为默认返回 True；不存在返回 False。
        """
        if self._db is None:
            return False
        exists = await self._db.fetchval(
            "SELECT id FROM notification_channels WHERE id = $1 AND channel_type = $2",
            channel_id, channel_type,
        )
        if exists is None:
            return False
        async with self._write_lock:
            await self._db.execute(
                """
                UPDATE notification_channels
                SET is_default = FALSE
                WHERE channel_type = $1 AND is_default = TRUE
                """,
                channel_type,
            )
            await self._db.execute(
                """
                UPDATE notification_channels
                SET is_default = TRUE, updated_at = CURRENT_TIMESTAMP
                WHERE id = $1
                """,
                channel_id,
            )
        return True

    async def resolve_default_channel(
        self,
        channel_type: str = "feishu",
    ) -> Optional[Dict[str, Any]]:
        """解析默认渠道（内部使用，含加密字段原文）。

        顺序：``is_default=TRUE`` → 第一行 ``enabled=TRUE`` → None。

        返回:
            Optional[Dict[str, Any]]: 含 ``config.app_id_encrypted`` /
            ``config.app_secret_encrypted`` 等密文 + ``id`` 等;无默认返回 None。
        """
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, name, display_name, channel_type, config, enabled,
                   is_default, created_by_user_id, created_at, updated_at
            FROM notification_channels
            WHERE channel_type = $1 AND is_default = TRUE
            ORDER BY id ASC
            LIMIT 1
            """,
            channel_type,
        )
        if row is None:
            row = await self._db.fetchrow(
                """
                SELECT id, name, display_name, channel_type, config, enabled,
                       is_default, created_by_user_id, created_at, updated_at
                FROM notification_channels
                WHERE channel_type = $1 AND enabled = TRUE
                ORDER BY id ASC
                LIMIT 1
                """,
                channel_type,
            )
        if row is None:
            return None
        return self._channel_to_internal(row)

    # ------------------------------------------------------------------
    # Target CRUD（目标 + 绑智能体 + 模板）
    # ------------------------------------------------------------------

    async def list_targets(
        self,
        channel_id: Optional[int] = None,
        channel_type: Optional[str] = None,
        scope: Optional[OwnershipScope] = None,
    ) -> List[Dict[str, Any]]:
        """列出目标。

        参数:
            channel_id: 仅返回该 channel 下的目标。
            channel_type: 仅返回该 channel_type 的目标（与 channel_id 互斥时以 channel_id 优先）。
            scope: 归属过滤；admin/system 见全部，普通用户按 created_by_user_id。

        返回:
            List[Dict[str, Any]]: 每项含 ``id`` / ``channel_id`` / ``target_type`` /
            ``name`` / ``config`` / ``agent_name`` / ``subject_template`` /
            ``body_template`` / ``enabled`` / ``created_at`` / ``updated_at`` /
            ``created_by_user_id``。
        """
        if self._db is None:
            return []
        conditions: List[str] = []
        params: List[Any] = []
        if channel_id is not None:
            params.append(channel_id)
            conditions.append(f"t.channel_id = ${len(params)}")
        elif channel_type is not None:
            params.append(channel_type)
            conditions.append(f"c.channel_type = ${len(params)}")
        if scope is not None and not (scope.system or scope.is_admin):
            if scope.user_id is None:
                return []
            params.append(scope.user_id)
            conditions.append(f"t.created_by_user_id = ${len(params)}")
        where_sql = ("WHERE " + " AND ".join(conditions)) if conditions else ""

        sql = f"""
            SELECT t.id, t.channel_id, t.target_type, t.name, t.config,
                   t.agent_name, t.subject_template, t.body_template,
                   t.enabled, t.created_by_user_id, t.created_at, t.updated_at,
                   c.channel_type, c.name AS channel_name
            FROM notification_targets t
            JOIN notification_channels c ON c.id = t.channel_id
            {where_sql}
            ORDER BY t.id ASC
        """
        rows = await self._db.fetch(sql, *params)
        return [self._target_to_public(row) for row in rows]

    async def get_target(self, target_id: int) -> Optional[Dict[str, Any]]:
        """读取单个目标。"""
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT t.id, t.channel_id, t.target_type, t.name, t.config,
                   t.agent_name, t.subject_template, t.body_template,
                   t.enabled, t.created_by_user_id, t.created_at, t.updated_at,
                   c.channel_type, c.name AS channel_name
            FROM notification_targets t
            JOIN notification_channels c ON c.id = t.channel_id
            WHERE t.id = $1
            """,
            target_id,
        )
        if row is None:
            return None
        return self._target_to_public(row)

    async def upsert_target(
        self,
        channel_id: int,
        target_type: str,
        name: str,
        config: Dict[str, Any],
        agent_name: str,
        subject_template: str,
        body_template: str,
        enabled: bool,
        created_by_user_id: Optional[int],
        target_id: Optional[int] = None,
    ) -> Dict[str, Any]:
        """新建或更新目标。

        参数:
            channel_id: 关联渠道 ID。
            target_type: 目标类型（白名单）。
            name: 目标名。
            config: 目标配置 dict（含 chat_id / chat_type 等）。
            agent_name: 绑定的智能体名（必填）。
            subject_template: 主题模板。
            body_template: 正文模板。
            enabled: 是否启用。
            created_by_user_id: 创建者用户 ID。
            target_id: 更新时传；None 表示新建。

        返回:
            Dict[str, Any]: 含 ``id`` / ``updated_at`` / ``created`` 字段。
        """
        # target_type 白名单校验提前(在 db 检查前)
        if target_type not in SUPPORTED_TARGET_TYPES:
            raise NotificationConfigValidationError(
                f"target_type 不在白名单 {SUPPORTED_TARGET_TYPES}，"
                f"实际为: {target_type!r}"
            )
        if self._db is None:
            raise NotificationConfigError("数据库未初始化")
        if not name or not name.strip():
            raise NotificationConfigValidationError("name 不能为空")
        if not agent_name or not agent_name.strip():
            raise NotificationConfigValidationError("agent_name 不能为空")
        if not isinstance(config, dict):
            raise NotificationConfigValidationError("config 必须是 dict 类型")

        # 校验 channel 存在 + channel_type 与 target_type 对应
        ch_row = await self._db.fetchrow(
            "SELECT channel_type FROM notification_channels WHERE id = $1",
            channel_id,
        )
        if ch_row is None:
            raise NotificationConfigNotFoundError(
                f"channel_id={channel_id} 不存在"
            )
        channel_type = ch_row["channel_type"]
        # target_type 必须以 channel_type 开头（feishu.* / dingtalk.* ...）
        if not target_type.startswith(channel_type + "."):
            raise NotificationConfigValidationError(
                f"target_type={target_type!r} 必须以 channel_type={channel_type!r} 开头"
            )
        # 飞书 target config 校验
        if channel_type == "feishu":
            for k in FEISHU_TARGET_REQUIRED_CONFIG_KEYS:
                if not config.get(k):
                    raise NotificationConfigValidationError(
                        f"飞书 target config.{k} 必填"
                    )

        config_json = json.dumps(config, ensure_ascii=False)

        async with self._write_lock:
            if target_id is not None:
                # 更新（先校验存在 + 归属）
                existing = await self._db.fetchrow(
                    """
                    SELECT created_by_user_id FROM notification_targets WHERE id = $1
                    """,
                    target_id,
                )
                if existing is None:
                    raise NotificationConfigNotFoundError(
                        f"target_id={target_id} 不存在"
                    )
                row = await self._db.fetchrow(
                    """
                    UPDATE notification_targets
                    SET target_type = $1, name = $2, config = $3::jsonb,
                        agent_name = $4, subject_template = $5,
                        body_template = $6, enabled = $7,
                        updated_at = CURRENT_TIMESTAMP
                    WHERE id = $8
                    RETURNING id, updated_at
                    """,
                    target_type, name, config_json, agent_name,
                    subject_template, body_template, enabled, target_id,
                )
                return {"id": row["id"], "updated_at": row["updated_at"], "created": False}
            else:
                row = await self._db.fetchrow(
                    """
                    INSERT INTO notification_targets
                        (channel_id, target_type, name, config, agent_name,
                         subject_template, body_template, enabled,
                         created_by_user_id)
                    VALUES ($1, $2, $3, $4::jsonb, $5, $6, $7, $8, $9)
                    RETURNING id, updated_at
                    """,
                    channel_id, target_type, name, config_json, agent_name,
                    subject_template, body_template, enabled, created_by_user_id,
                )
                return {"id": row["id"], "updated_at": row["updated_at"], "created": True}

    async def delete_target(self, target_id: int) -> bool:
        """删除目标。"""
        if self._db is None:
            return False
        result = await self._db.execute(
            "DELETE FROM notification_targets WHERE id = $1",
            target_id,
        )
        return "DELETE 1" in str(result)

    # ------------------------------------------------------------------
    # 加密工具（暴露给 router 层：明文 → Fernet 密文）
    # ------------------------------------------------------------------

    def encrypt_field(self, plaintext: str) -> str:
        """将明文字符串 Fernet 加密为可入库的 str（调用 ``_to_db_str``）。

        异常:
            NotificationConfigError: Fernet 未配置或加密失败。
        """
        if not plaintext:
            return plaintext
        fernet = self._ensure_fernet()
        encrypted = fernet.encrypt(plaintext.encode("utf-8"))
        return self._to_db_str(encrypted)

    def decrypt_field(self, ciphertext: str) -> str:
        """解密单个 config 字段（str → str 明文）。

        异常:
            NotificationConfigError: 解密失败。
        """
        if not ciphertext:
            return ""
        fernet = self._ensure_fernet()
        if isinstance(ciphertext, str):
            ciphertext_bytes = ciphertext.encode("ascii")
        else:
            ciphertext_bytes = bytes(ciphertext)
        try:
            return fernet.decrypt(ciphertext_bytes).decode("utf-8")
        except InvalidToken as exc:
            raise NotificationConfigError(
                f"config 字段解密失败（Fernet key 不一致？）: {exc}"
            ) from exc

    def decrypt_feishu_config(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """解密飞书 config 中加密字段，返回含明文 app_id / app_secret 的新 dict。

        调用方应只把返回值用于内存（不写库），写库前需重新加密。
        """
        out = dict(config)
        for key in ("app_id_encrypted", "app_secret_encrypted"):
            if out.get(key):
                out[key + "_plain"] = self.decrypt_field(out[key])
        return out

    # ------------------------------------------------------------------
    # 智能体列表（target 下拉数据源）
    # ------------------------------------------------------------------

    async def list_enabled_agents(self) -> List[Dict[str, Any]]:
        """列出所有 enabled=True 的智能体（target agent_name 下拉用）。

        返回:
            List[Dict[str, Any]]: 每项含 ``name`` / ``display_name``。
        """
        if self._db is None:
            return []
        rows = await self._db.fetch(
            """
            SELECT name, display_name
            FROM agents
            WHERE enabled = TRUE
            ORDER BY sort_order ASC, name ASC
            """
        )
        return [
            {
                "name": row["name"],
                "display_name": row.get("display_name") or row["name"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Connection test（按 channel_type 分发）
    # ------------------------------------------------------------------

    async def test_channel_connection(self, channel_id: int) -> Dict[str, Any]:
        """测试渠道凭证（不发消息）。

        本期仅支持飞书：解密 config 中 app_id/app_secret → 构造 lark.Client
        → 不调用任何 SDK API（仅构造成功即视为凭证有效；连接真实可达性
        由后续 send-test 验证）。
        """
        if self._db is None:
            return {"success": False, "message": "数据库未初始化"}
        ch = await self._get_channel_internal(channel_id)
        if ch is None:
            return {"success": False, "message": f"channel_id={channel_id} 不存在"}
        if ch["channel_type"] == "feishu":
            return await self._test_feishu_connection(ch)
        return {
            "success": False,
            "message": f"channel_type={ch['channel_type']!r} 暂不支持 test-connection",
        }

    async def _test_feishu_connection(self, ch: Dict[str, Any]) -> Dict[str, Any]:
        """测试飞书凭证：解密 + 构造 lark.Client（不调 SDK）。"""
        try:
            cfg = self.decrypt_feishu_config(ch["config"])
            app_id = cfg.get("app_id_encrypted_plain")
            app_secret = cfg.get("app_secret_encrypted_plain")
            if not app_id or not app_secret:
                return {
                    "success": False,
                    "message": "config 中 app_id 或 app_secret 为空",
                }
            try:
                import lark_oapi as lark  # 延迟导入：测试环境可能未安装
            except ImportError as exc:
                return {
                    "success": False,
                    "message": f"lark_oapi 未安装: {exc}",
                }
            log_level_str = ch["config"].get("log_level", "INFO")
            log_level = self._resolve_lark_log_level(log_level_str)
            lark.Client.builder().app_id(app_id).app_secret(app_secret).log_level(log_level).build()
            return {"success": True, "message": "飞书凭证构造成功"}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[notification_config_service] test_feishu_connection failed: %s",
                exc, exc_info=True,
            )
            return {"success": False, "message": f"飞书连接测试失败: {exc}"}

    @staticmethod
    def _resolve_lark_log_level(level_str: str) -> int:
        """把字符串日志级别映射为 lark.LogLevel 枚举值；未识别默认 INFO。"""
        try:
            import lark_oapi as lark

            mapping = {
                "DEBUG": lark.LogLevel.DEBUG,
                "INFO": lark.LogLevel.INFO,
                "WARNING": lark.LogLevel.WARNING,
                "ERROR": lark.LogLevel.ERROR,
            }
            return mapping.get((level_str or "").upper(), lark.LogLevel.INFO)
        except Exception:  # noqa: BLE001
            # 测试环境无 lark 时返回 0 占位（实际不会调用到这里）
            return 0

    # ------------------------------------------------------------------
    # 发送测试（按 channel_type 分发；飞书路径用临时 lark.Client）
    # ------------------------------------------------------------------

    async def send_test_message(
        self,
        target_id: int,
        channel_type: str,
        content: str,
    ) -> Dict[str, Any]:
        """发送测试消息。

        参数:
            target_id: 目标 ID。
            channel_type: 渠道类型（与 target.channel.channel_type 一致，冗余校验）。
            content: 消息正文（Markdown 自动检测 → 卡片）。

        返回:
            Dict[str, Any]: ``{"success": bool, "message_id"?: str, "error"?: str}``。
        """
        if self._db is None:
            return {"success": False, "error": "数据库未初始化"}
        target = await self.get_target(target_id)
        if target is None:
            return {"success": False, "error": f"target_id={target_id} 不存在"}
        ch = await self._get_channel_internal(target["channel_id"])
        if ch is None:
            return {"success": False, "error": f"target.channel_id={target['channel_id']} 不存在"}
        if ch["channel_type"] != channel_type:
            return {
                "success": False,
                "error": (
                    f"channel_type 参数={channel_type!r} 与目标所属渠道 "
                    f"{ch['channel_type']!r} 不一致"
                ),
            }
        if not ch.get("enabled"):
            return {"success": False, "error": "该渠道已禁用，请先在应用设置中启用"}
        if channel_type == "feishu":
            return await self._send_feishu_test(ch, target, content)
        return {
            "success": False,
            "error": f"channel_type={channel_type!r} 暂不支持 send-test",
        }

    async def _send_feishu_test(
        self,
        ch: Dict[str, Any],
        target: Dict[str, Any],
        content: str,
    ) -> Dict[str, Any]:
        """飞书路径发送测试：解密凭证 + 临时 lark.Client + message.create。"""
        try:
            cfg = self.decrypt_feishu_config(ch["config"])
            app_id = cfg.get("app_id_encrypted_plain")
            app_secret = cfg.get("app_secret_encrypted_plain")
            if not app_id or not app_secret:
                return {"success": False, "error": "config 中 app_id 或 app_secret 为空"}

            try:
                import lark_oapi as lark
                from lark_oapi.api.im.v1 import (
                    CreateMessageRequest,
                    CreateMessageRequestBody,
                )
            except ImportError as exc:
                return {"success": False, "error": f"lark_oapi 未安装: {exc}"}

            chat_id = target["config"].get("chat_id")
            chat_type = target["config"].get("chat_type", "chat_id")
            if not chat_id:
                return {"success": False, "error": "target.config.chat_id 为空"}

            log_level_str = ch["config"].get("log_level", "INFO")
            log_level = self._resolve_lark_log_level(log_level_str)
            client = (
                lark.Client.builder()
                .app_id(app_id)
                .app_secret(app_secret)
                .log_level(log_level)
                .build()
            )

            # Markdown 自动检测（与 send_feishu_message 一致）
            from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
                MarkdownToCardConverter,
            )
            if MarkdownToCardConverter.looks_like_markdown(content or ""):
                card = MarkdownToCardConverter.to_card_json(content or "")
                msg_type = "interactive"
                content_str = json.dumps(card, ensure_ascii=False)
            else:
                msg_type = "text"
                content_str = json.dumps({"text": content or ""}, ensure_ascii=False)

            request = (
                CreateMessageRequest.builder()
                .receive_id_type(chat_type)
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type(msg_type)
                    .content(content_str)
                    .uuid(str(__import__("uuid").uuid4()))
                    .build()
                )
                .build()
            )
            response = client.im.v1.message.create(request)
            if not response.success():
                return {
                    "success": False,
                    "error": f"飞书返回失败: code={response.code} msg={response.msg}",
                }
            msg_id = getattr(response.data, "message_id", None) if response.data else None
            return {"success": True, "message_id": msg_id}
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[notification_config_service] send_feishu_test failed: %s",
                exc, exc_info=True,
            )
            return {"success": False, "error": f"发送失败: {exc}"}

    # ------------------------------------------------------------------
    # Validation helper（按 channel_type 分发 config 校验）
    # ------------------------------------------------------------------

    def _validate_config(self, channel_type: str, config: Dict[str, Any]) -> None:
        """按 channel_type 校验 config 必填字段。

        异常:
            NotificationConfigValidationError: 缺必填字段时抛出。
        """
        if channel_type == "feishu":
            for k in FEISHU_REQUIRED_CONFIG_KEYS:
                v = config.get(k)
                if v is None or v == "":
                    raise NotificationConfigValidationError(
                        f"飞书 config.{k} 必填"
                    )

    # ------------------------------------------------------------------
    # Row → dict（public + internal）
    # ------------------------------------------------------------------

    @staticmethod
    def _channel_to_public(row: Any) -> Dict[str, Any]:
        """channel 行转对外 dict：config 中加密字段脱敏为空串。"""
        config = row["config"]
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        if not isinstance(config, dict):
            config = {}
        # 加密字段脱敏
        config_public = dict(config)
        for k in ("app_id_encrypted", "app_secret_encrypted"):
            if k in config_public:
                config_public[k] = ""
        return {
            "id": row["id"],
            "name": row["name"],
            "display_name": row.get("display_name") or "",
            "channel_type": row["channel_type"],
            "config": config_public,
            "enabled": row["enabled"],
            "is_default": row["is_default"],
            "created_by_user_id": row.get("created_by_user_id"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }

    @staticmethod
    def _channel_to_internal(row: Any) -> Dict[str, Any]:
        """channel 行转内部 dict：config 含加密字段原文（service 内部使用）。"""
        config = row["config"]
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        if not isinstance(config, dict):
            config = {}
        return {
            "id": row["id"],
            "name": row["name"],
            "display_name": row.get("display_name") or "",
            "channel_type": row["channel_type"],
            "config": config,
            "enabled": row["enabled"],
            "is_default": row["is_default"],
            "created_by_user_id": row.get("created_by_user_id"),
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    @staticmethod
    def _target_to_public(row: Any) -> Dict[str, Any]:
        """target 行转对外 dict。"""
        config = row["config"]
        if isinstance(config, str):
            try:
                config = json.loads(config)
            except json.JSONDecodeError:
                config = {}
        if not isinstance(config, dict):
            config = {}
        return {
            "id": row["id"],
            "channel_id": row["channel_id"],
            "channel_type": row.get("channel_type"),
            "channel_name": row.get("channel_name"),
            "target_type": row["target_type"],
            "name": row["name"],
            "config": config,
            "agent_name": row["agent_name"],
            "subject_template": row.get("subject_template") or "",
            "body_template": row.get("body_template") or "",
            "enabled": row["enabled"],
            "created_by_user_id": row.get("created_by_user_id"),
            "created_at": row["created_at"].isoformat() if row.get("created_at") else None,
            "updated_at": row["updated_at"].isoformat() if row.get("updated_at") else None,
        }
