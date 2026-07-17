# -*- coding:utf-8 -*-
"""
邮件配置服务模块。

``EmailConfigService`` 负责：
- SMTP 服务器配置的读取 / 写入 / 连接测试（密码字段使用 Fernet 加密）。
- 邮件发送策略的 CRUD（策略名 + 描述 + 收件人用户 ID 列表）。
- 列出已注册且邮箱非空的用户（供前端挑选收件人）。

与 ``EmailService`` 一样，本服务与 FastAPI 解耦：构造时仅需 ``db`` 与
``credential_key``，所有方法均为纯异步方法，可被脚本或 HTTP 路由层调用。
"""
import asyncio
import logging
import smtplib
import ssl
from typing import Any, Dict, List, Optional

from cryptography.fernet import Fernet, InvalidToken

from app.shared.utils.email.email_models import EmailServerConfig


logger = logging.getLogger(__name__)


class EmailConfigError(Exception):
    """邮件配置相关错误基类。"""


class EmailConfigNotFoundError(Exception):
    """邮件服务器配置或策略不存在时抛出。"""


class EmailConfigValidationError(Exception):
    """邮件配置参数校验失败时抛出。"""


class EmailConfigService:
    """邮件配置服务。

    参数:
        db: asyncpg 连接池；需支持 ``fetch`` / ``fetchrow`` / ``execute`` 异步方法。
            测试可传 ``None``，但所有 DB 方法将无法调用。
        credential_key: Fernet 对称密钥（base64 字符串）；空字符串代表未配置，
            ``_ensure_fernet`` 会在首次使用时抛 ``EmailConfigError``。
    """

    def __init__(self, db: Any, credential_key: str) -> None:
        """初始化邮件配置服务。

        参数:
            db: asyncpg 连接池。
            credential_key: Fernet 密钥（base64 字符串）。

        异常:
            EmailConfigError: ``credential_key`` 非空但非法时抛出。
        """
        self._db = db
        self._credential_key = credential_key or ""
        self._fernet: Optional[Fernet] = None
        self._cache: Dict[str, EmailServerConfig] = {}
        self._write_lock = asyncio.Lock()

    def _ensure_fernet(self) -> Fernet:
        """惰性构造 Fernet 实例。

        返回:
            Fernet: 实例。

        异常:
            EmailConfigError: ``credential_key`` 为空或非法时抛出。
        """
        if self._fernet is not None:
            return self._fernet
        if not self._credential_key:
            raise EmailConfigError(
                "credential_key 未配置（请在 .env 中设置 DEVOPS_CREDENTIAL_KEY）"
            )
        try:
            self._fernet = Fernet(self._credential_key.encode("ascii"))
        except (ValueError, TypeError) as exc:
            raise EmailConfigError(
                f"credential_key 不是合法 Fernet base64 密钥: {exc}"
            ) from exc
        return self._fernet

    @staticmethod
    def _to_db_str(value: Any) -> str:
        """将 Fernet 密文规范化为可写入 ``TEXT`` 列的字符串。

        ``email_server_configs.password_encrypted`` 列类型为 ``TEXT``，
        asyncpg 对 ``TEXT`` 列不接受 ``bytes``（会抛
        ``DataError: expected str, got bytes``）。Fernet 加密结果天然
        是 ``bytes``，因此在写入前统一规范化为 ``str``（Fernet token
        仅含 url-safe base64 ASCII 字符，可用 ``ascii`` 解码）。

        参数:
            value: 密文（``bytes`` 或 ``str``）。

        返回:
            str: 规范化后的密文字符串。

        异常:
            EmailConfigError: 输入不是合法的 Fernet token（解码失败）时抛出。
        """
        if isinstance(value, str):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                return bytes(value).decode("ascii")
            except UnicodeDecodeError as exc:
                raise EmailConfigError(
                    "Fernet 密文包含非 ASCII 字符，无法存入 TEXT 列"
                ) from exc
        raise EmailConfigError(
            f"password_encrypted 类型非法，期望 bytes/str，实际 {type(value).__name__}"
        )

    # ------------------------------------------------------------------
    # Preload
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """启动时预加载启用的 SMTP 配置到内存缓存。

        返回:
            None。
        """
        if self._db is None:
            return
        try:
            config = await self.get_active_server_config()
            if config is not None:
                async with self._write_lock:
                    self._cache["active"] = config
                logger.info("[email_config_service] preloaded active SMTP config")
        except Exception as exc:
            logger.warning(
                "[email_config_service] preload failed: %s", exc, exc_info=True
            )

    # ------------------------------------------------------------------
    # SMTP server config
    # ------------------------------------------------------------------

    async def get_active_server_config(self) -> Optional[EmailServerConfig]:
        """读取启用的 SMTP 配置（解密密码）。

        返回:
            Optional[EmailServerConfig]: 启用的配置；不存在返回 None。

        异常:
            EmailConfigError: 解密失败时抛出。
        """
        if self._db is None:
            return None
        row = await self._db.fetchrow(
            """
            SELECT id, host, port, use_ssl, username, password_encrypted,
                   sender_name, enabled, created_at, updated_at
            FROM email_server_configs
            WHERE enabled = TRUE
            ORDER BY id ASC
            LIMIT 1
            """
        )
        if row is None:
            return None
        encrypted = row["password_encrypted"]
        if isinstance(encrypted, str):
            encrypted = encrypted.encode("ascii")
        fernet = self._ensure_fernet()
        try:
            password = fernet.decrypt(encrypted).decode("utf-8") if encrypted else ""
        except InvalidToken as exc:
            raise EmailConfigError("SMTP 密码解密失败（Fernet key 不一致？）") from exc
        return EmailServerConfig(
            host=row["host"],
            port=row["port"],
            use_ssl=row["use_ssl"],
            username=row["username"],
            password=password,
            sender_name=row["sender_name"] or "",
            enabled=row["enabled"],
        )

    async def get_server_config_public(self) -> Optional[Dict[str, Any]]:
        """读取启用的 SMTP 配置（密码字段返回空字符串，不外泄）。

        返回:
            Optional[Dict[str, Any]]: 公开字段配置；不存在返回 None。
        """
        config = await self.get_active_server_config()
        if config is None:
            return None
        return {
            "host": config.host,
            "port": config.port,
            "use_ssl": config.use_ssl,
            "username": config.username,
            "password": "",  # 永远不外泄
            "sender_name": config.sender_name,
            "enabled": config.enabled,
        }

    async def upsert_server_config(
        self,
        config: EmailServerConfig,
        keep_existing_password: bool = False,
    ) -> Dict[str, Any]:
        """插入或更新 SMTP 配置（单行模式，启用配置全局唯一）。

        参数:
            config: SMTP 配置实例。
            keep_existing_password: True 时保留原密码（``config.password`` 为空），
                用于前端"密码留空表示不修改"场景。

        返回:
            Dict[str, Any]: 含 ``id`` / ``updated_at`` 字段。

        异常:
            EmailConfigError: ``keep_existing_password=True`` 但数据库无记录时抛出。
        """
        if self._db is None:
            raise EmailConfigError("数据库未初始化")

        fernet = self._ensure_fernet()

        # 查询是否已有启用配置
        existing = await self._db.fetchrow(
            "SELECT id, password_encrypted FROM email_server_configs "
            "WHERE enabled = TRUE ORDER BY id ASC LIMIT 1"
        )

        if keep_existing_password:
            if existing is None:
                raise EmailConfigError(
                    "keep_existing_password=True 但数据库无记录"
                )
            encrypted_existing = existing["password_encrypted"]
            if isinstance(encrypted_existing, str):
                encrypted_existing = encrypted_existing.encode("ascii")
            # 归一化为 str 后再写库（TEXT 列不接受 bytes）
            encrypted = self._to_db_str(encrypted_existing)
        else:
            encrypted = self._to_db_str(
                fernet.encrypt(config.password.encode("utf-8"))
            )

        if existing is not None:
            row = await self._db.fetchrow(
                """
                UPDATE email_server_configs
                SET host = $1, port = $2, use_ssl = $3, username = $4,
                    password_encrypted = $5, sender_name = $6, enabled = $7,
                    updated_at = CURRENT_TIMESTAMP
                WHERE id = $8
                RETURNING id, updated_at
                """,
                config.host, config.port, config.use_ssl, config.username,
                encrypted, config.sender_name, config.enabled,
                existing["id"],
            )
        else:
            row = await self._db.fetchrow(
                """
                INSERT INTO email_server_configs
                    (host, port, use_ssl, username, password_encrypted,
                     sender_name, enabled)
                VALUES ($1, $2, $3, $4, $5, $6, $7)
                RETURNING id, updated_at
                """,
                config.host, config.port, config.use_ssl, config.username,
                encrypted, config.sender_name, config.enabled,
            )

        # 更新内存缓存
        async with self._write_lock:
            if config.enabled:
                self._cache["active"] = config
            else:
                self._cache.pop("active", None)

        return {"id": row["id"], "updated_at": row["updated_at"]}

    async def test_connection(self, config: EmailServerConfig) -> Dict[str, Any]:
        """测试 SMTP 连接（不发送邮件）。

        异常分类（便于前端展示与服务器日志定位）：
        - ``smtplib.SMTPAuthenticationError`` → 535 等授权错误（账号/授权码错）
        - ``ssl.SSLError`` → SSL 握手失败（证书校验 / 协议版本 / 端口被 RST）
        - ``smtplib.SMTPServerDisconnected`` → 服务器主动关闭连接
          （常见原因：账号域名不被该 SMTP 服务器识别，如企业邮用 smtp.qq.com）
        - ``OSError`` / ``socket.gaierror`` → 网络层失败（DNS / 防火墙阻断）
        - 其他异常 → 兜底返回

        参数:
            config: 待测试的 SMTP 配置。

        返回:
            Dict[str, Any]: ``{"success": True, "message": "..."}`` 或
            ``{"success": False, "message": "..."}``。
        """
        try:
            if config.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(config.host, config.port, context=context, timeout=15) as smtp:
                    if config.password:
                        smtp.login(config.username, config.password)
            else:
                with smtplib.SMTP(config.host, config.port, timeout=15) as smtp:
                    smtp.starttls(context=ssl.create_default_context())
                    if config.password:
                        smtp.login(config.username, config.password)
            return {"success": True, "message": "SMTP 连接成功"}
        except smtplib.SMTPAuthenticationError as exc:
            logger.warning(
                "[email_config_service] test_connection auth failed: %s", exc, exc_info=True
            )
            return {"success": False, "message": f"SMTP 认证失败: {exc}"}
        except smtplib.SMTPServerDisconnected as exc:
            logger.warning(
                "[email_config_service] test_connection server disconnected: %s",
                exc, exc_info=True,
            )
            return {
                "success": False,
                "message": (
                    f"服务器主动断开连接: {exc}。"
                    "可能原因：账号域名（如 foxmail.com.cn / 企业邮）不被该 SMTP 服务器识别；"
                    "可尝试切换主机（如 smtp.qq.com → smtp.exmail.qq.com）。"
                ),
            }
        except smtplib.SMTPConnectError as exc:
            logger.warning(
                "[email_config_service] test_connection connect failed: %s",
                exc, exc_info=True,
            )
            hint = (
                "若正在使用 SSL(465)，请取消勾选改用 STARTTLS(587) 后重试。"
                if config.use_ssl
                else "请检查端口与主机是否正确，或确认网络环境未对该端口做 RST 阻断。"
            )
            return {"success": False, "message": f"SMTP 连接失败: {exc}。{hint}"}
        except ssl.SSLError as exc:
            logger.warning(
                "[email_config_service] test_connection SSL failed: %s",
                exc, exc_info=True,
            )
            return {
                "success": False,
                "message": (
                    f"SSL 握手失败: {exc}。"
                    "可能原因：证书校验失败 / 端口被防火墙 RST / 协议版本不兼容；"
                    "可尝试取消勾选 SMTP_SSL 改用 587（STARTTLS）。"
                ),
            }
        except OSError as exc:
            logger.warning(
                "[email_config_service] test_connection network failed: %s",
                exc, exc_info=True,
            )
            return {
                "success": False,
                "message": (
                    f"网络层失败: {exc}。"
                    "可能原因：DNS 无法解析 / 主机不可达 / 防火墙阻断 / 端口被运营商拦截。"
                ),
            }
        except Exception as exc:
            logger.warning(
                "[email_config_service] test_connection unexpected failure: %s",
                exc, exc_info=True,
            )
            return {"success": False, "message": f"SMTP 测试失败: {exc}"}

    # ------------------------------------------------------------------
    # Emailable users
    # ------------------------------------------------------------------

    async def list_emailable_users(self) -> List[Dict[str, Any]]:
        """列出已注册且邮箱非空的用户。

        返回:
            List[Dict[str, Any]]: 每项含 ``id`` / ``username`` / ``real_name`` / ``email``。
        """
        if self._db is None:
            return []
        rows = await self._db.fetch(
            """
            SELECT id, username, real_name, email
            FROM users
            WHERE email IS NOT NULL AND email <> ''
            ORDER BY id ASC
            """
        )
        return [
            {
                "id": row["id"],
                "username": row["username"],
                "real_name": row.get("real_name", ""),
                "email": row["email"],
            }
            for row in rows
        ]

    # ------------------------------------------------------------------
    # Policy CRUD
    # ------------------------------------------------------------------

    async def list_policies(self) -> List[Dict[str, Any]]:
        """列出所有邮件发送策略（含收件人列表与模板字段）。

        返回:
            List[Dict[str, Any]]: 策略列表，每项含
            ``id`` / ``name`` / ``description`` / ``recipient_user_ids`` /
            ``recipients`` (含 email) / ``subject_template`` / ``body_template`` /
            ``created_at`` / ``updated_at``。
        """
        if self._db is None:
            return []
        rows = await self._db.fetch(
            """
            SELECT p.id, p.name, p.description, p.subject_template,
                   p.body_template, p.created_at, p.updated_at,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'user_id', r.user_id,
                               'username', u.username,
                               'email', u.email
                           )
                       ) FILTER (WHERE r.user_id IS NOT NULL),
                       '[]'
                   ) AS recipients
            FROM email_policies p
            LEFT JOIN email_policy_recipients r ON r.policy_id = p.id
            LEFT JOIN users u ON u.id = r.user_id
            GROUP BY p.id, p.name, p.description, p.subject_template,
                     p.body_template, p.created_at, p.updated_at
            ORDER BY p.id DESC
            """
        )
        result: List[Dict[str, Any]] = []
        for row in rows:
            recipients = row.get("recipients") or []
            if isinstance(recipients, str):
                import json
                recipients = json.loads(recipients)
            result.append({
                "id": row["id"],
                "name": row["name"],
                "description": row.get("description", ""),
                "recipient_user_ids": [r["user_id"] for r in recipients],
                "recipients": recipients,
                "subject_template": row.get("subject_template", "") or "",
                "body_template": row.get("body_template", "") or "",
                "created_at": row["created_at"],
                "updated_at": row["updated_at"],
            })
        return result

    async def get_policy(self, policy_id: int) -> Dict[str, Any]:
        """获取单个策略详情。

        参数:
            policy_id: 策略 ID。

        返回:
            Dict[str, Any]: 策略详情。

        异常:
            EmailConfigNotFoundError: 策略不存在时抛出。
        """
        if self._db is None:
            raise EmailConfigNotFoundError("数据库未初始化")
        row = await self._db.fetchrow(
            """
            SELECT p.id, p.name, p.description, p.subject_template,
                   p.body_template, p.created_at, p.updated_at,
                   COALESCE(
                       json_agg(
                           json_build_object(
                               'user_id', r.user_id,
                               'username', u.username,
                               'email', u.email
                           )
                       ) FILTER (WHERE r.user_id IS NOT NULL),
                       '[]'
                   ) AS recipients
            FROM email_policies p
            LEFT JOIN email_policy_recipients r ON r.policy_id = p.id
            LEFT JOIN users u ON u.id = r.user_id
            WHERE p.id = $1
            GROUP BY p.id, p.name, p.description, p.subject_template,
                     p.body_template, p.created_at, p.updated_at
            """,
            policy_id,
        )
        if row is None:
            raise EmailConfigNotFoundError(f"策略不存在: {policy_id}")
        recipients = row.get("recipients") or []
        if isinstance(recipients, str):
            import json
            recipients = json.loads(recipients)
        return {
            "id": row["id"],
            "name": row["name"],
            "description": row.get("description", ""),
            "recipient_user_ids": [r["user_id"] for r in recipients],
            "recipients": recipients,
            "subject_template": row.get("subject_template", "") or "",
            "body_template": row.get("body_template", "") or "",
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }

    async def create_policy(
        self,
        name: str,
        description: str,
        recipient_user_ids: List[int],
        created_by_user_id: int,
        subject_template: str = "",
        body_template: str = "",
    ) -> Dict[str, Any]:
        """新建邮件发送策略。

        参数:
            name: 策略名称。
            description: 策略描述。
            recipient_user_ids: 收件人用户 ID 列表。
            created_by_user_id: 创建者用户 ID（用于审计）。
            subject_template: 主题模板，含 ``{{var}}`` 占位符；空字符串表示
                使用策略名作为主题。
            body_template: 正文模板，含 ``{{var}}`` 占位符；空字符串表示直接使用
                脚本返回值作为正文。

        返回:
            Dict[str, Any]: 新建策略详情。

        异常:
            EmailConfigValidationError: 名称或收件人列表为空时抛出。
        """
        if self._db is None:
            raise EmailConfigError("数据库未初始化")
        if not name or not name.strip():
            raise EmailConfigValidationError("策略名称不能为空")
        if not recipient_user_ids:
            raise EmailConfigValidationError("收件人列表不能为空")

        async with self._db.acquire() as conn:
            async with conn.transaction():
                row = await conn.fetchrow(
                    """
                    INSERT INTO email_policies (
                        name, description, created_by_user_id,
                        subject_template, body_template
                    )
                    VALUES ($1, $2, $3, $4, $5)
                    RETURNING id, name, description, created_at, updated_at
                    """,
                    name.strip(), description, created_by_user_id,
                    subject_template, body_template,
                )
                policy_id = row["id"]
                # 去重
                unique_ids = list(set(recipient_user_ids))
                if unique_ids:
                    await conn.executemany(
                        "INSERT INTO email_policy_recipients (policy_id, user_id) "
                        "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                        [(policy_id, uid) for uid in unique_ids],
                    )

        return await self.get_policy(policy_id)

    async def update_policy(
        self,
        policy_id: int,
        name: Optional[str] = None,
        description: Optional[str] = None,
        recipient_user_ids: Optional[List[int]] = None,
        subject_template: Optional[str] = None,
        body_template: Optional[str] = None,
    ) -> Dict[str, Any]:
        """更新策略字段（未传入的字段保持原值）。

        参数:
            policy_id: 策略 ID。
            name: 新名称；None 表示不修改。
            description: 新描述；None 表示不修改。
            recipient_user_ids: 新收件人列表；None 表示不修改。
            subject_template: 新主题模板；None 表示不修改。
            body_template: 新正文模板；None 表示不修改。

        返回:
            Dict[str, Any]: 更新后的策略详情。

        异常:
            EmailConfigNotFoundError: 策略不存在时抛出。
            EmailConfigValidationError: 名称或收件人列表为空时抛出。
        """
        if self._db is None:
            raise EmailConfigError("数据库未初始化")

        async with self._db.acquire() as conn:
            async with conn.transaction():
                existing = await conn.fetchrow(
                    "SELECT id FROM email_policies WHERE id = $1",
                    policy_id,
                )
                if existing is None:
                    raise EmailConfigNotFoundError(f"策略不存在: {policy_id}")

                if name is not None:
                    if not name or not name.strip():
                        raise EmailConfigValidationError("策略名称不能为空")
                    await conn.execute(
                        "UPDATE email_policies SET name = $1, updated_at = CURRENT_TIMESTAMP "
                        "WHERE id = $2",
                        name.strip(), policy_id,
                    )
                if description is not None:
                    await conn.execute(
                        "UPDATE email_policies SET description = $1, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                        description, policy_id,
                    )
                if subject_template is not None:
                    await conn.execute(
                        "UPDATE email_policies SET subject_template = $1, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                        subject_template, policy_id,
                    )
                if body_template is not None:
                    await conn.execute(
                        "UPDATE email_policies SET body_template = $1, "
                        "updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                        body_template, policy_id,
                    )
                if recipient_user_ids is not None:
                    if not recipient_user_ids:
                        raise EmailConfigValidationError("收件人列表不能为空")
                    await conn.execute(
                        "DELETE FROM email_policy_recipients WHERE policy_id = $1",
                        policy_id,
                    )
                    unique_ids = list(set(recipient_user_ids))
                    if unique_ids:
                        await conn.executemany(
                            "INSERT INTO email_policy_recipients (policy_id, user_id) "
                            "VALUES ($1, $2) ON CONFLICT DO NOTHING",
                            [(policy_id, uid) for uid in unique_ids],
                        )

        return await self.get_policy(policy_id)

    async def delete_policy(self, policy_id: int) -> bool:
        """删除策略（关联表通过 ON DELETE CASCADE 自动清理）。

        参数:
            policy_id: 策略 ID。

        返回:
            bool: 删除成功返回 True；不存在返回 False。
        """
        if self._db is None:
            return False
        result = await self._db.execute(
            "DELETE FROM email_policies WHERE id = $1",
            policy_id,
        )
        return "DELETE 1" in str(result)


# ==================== 数据库表结构初始化 ====================


def _register_email_schema() -> None:
    """注册邮件系统三张表的建表函数到 DatabasePool。

    通过 ``@register_schema`` 装饰器在模块加载时注册，
    ``app/core/server.py::lifespan`` 启动时统一调用
    ``DatabasePool.register_schemas()`` 触发执行。

    为保持与 FastAPI 解耦的设计，``DatabasePool`` 与 ``register_schema``
    在函数内部 import —— 脚本调用 ``EmailConfigService`` 时不会触发
    ``app.core.database`` 模块加载。
    """
    from app.core.database import DatabasePool, register_schema

    @register_schema
    async def init_email_schema() -> None:
        """初始化邮件系统三张表（email_server_configs / email_policies / email_policy_recipients）。

        异常:
            RuntimeError: 数据库连接池未初始化时由 DatabasePool.execute 抛出。
        """
        # SMTP 服务器配置表（单行，密码字段 Fernet 加密）
        await DatabasePool.execute(
            """
            CREATE TABLE IF NOT EXISTS email_server_configs (
                id                SERIAL PRIMARY KEY,
                host              VARCHAR(200) NOT NULL,
                port              INTEGER NOT NULL DEFAULT 465,
                use_ssl           BOOLEAN NOT NULL DEFAULT TRUE,
                username          VARCHAR(200) NOT NULL,
                password_encrypted TEXT NOT NULL,
                sender_name       VARCHAR(200) DEFAULT '',
                enabled           BOOLEAN NOT NULL DEFAULT TRUE,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 单行启用约束：全局仅允许一条 enabled=TRUE 配置
        await DatabasePool.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS idx_email_server_configs_enabled
                ON email_server_configs(enabled) WHERE enabled = TRUE
            """
        )
        # 邮件发送策略表
        await DatabasePool.execute(
            """
            CREATE TABLE IF NOT EXISTS email_policies (
                id                SERIAL PRIMARY KEY,
                name              VARCHAR(200) NOT NULL,
                description       TEXT DEFAULT '',
                created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        # 策略-收件人多对多关联表
        await DatabasePool.execute(
            """
            CREATE TABLE IF NOT EXISTS email_policy_recipients (
                policy_id   INTEGER NOT NULL REFERENCES email_policies(id) ON DELETE CASCADE,
                user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                PRIMARY KEY (policy_id, user_id)
            )
            """
        )
        await DatabasePool.execute(
            """
            CREATE INDEX IF NOT EXISTS idx_email_policy_recipients_user_id
                ON email_policy_recipients(user_id)
            """
        )
        logger.info("[email] schema initialized: email_server_configs / email_policies / email_policy_recipients")


# 模块加载时触发注册（仅注册，不执行；执行由 lifespan 的 register_schemas() 完成）
_register_email_schema()
