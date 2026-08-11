"""
用户数据库操作模块

提供用户的注册、验证、查询等数据库操作。
使用 bcrypt 进行密码加密。

通过 @register_schema 装饰器自动注册用户表结构。

支持两种模式：
- postgres 模式：使用 PostgreSQL 数据库
- memory 模式：使用内存字典存储

Date: 2026/5/15
"""
import json
import logging
import threading
import bcrypt
import time
from typing import Optional, List, Dict, Any
from datetime import datetime
from app.core.database import DatabasePool, register_schema

logger = logging.getLogger(__name__)

# 2026-08-09 新增（等保三级 Task 2）：历史 admin 默认弱口令集合。
# 当 admin 账号密码哈希能匹配任一项时，bootstrap_enabled=True 会自动轮换；
# bootstrap_enabled=False 时 fail-loud，要求运维主动通过 PUT /api/users/{id}/password 重置。
# 集合只放在 user_db.py，不在 settings 暴露，避免历史弱口令被无意"白名单化"。
_WEAK_DEFAULT_PASSWORDS = {"admin123", "123456"}


def _coerce_allowed_agents(value):
    """
    防御性兜底：把 postgres JSONB 列解码结果规整为 Python list。

    asyncpg 默认将 JSONB 列解码为 JSON 字符串；虽然 DatabasePool.initialize()
    已注册 jsonb codec 将其反序列化为 list，但调用方在 codec 未生效（如 memory
    模式混入、单测 stub 字符串值、第三方 monkeypatch）时仍可能拿到 str。
    此函数统一兜底，保证下游 Pydantic 模型收到合法 list。

    Args:
        value: 来自 DB 行或内存字典的 allowed_agents 原始值。

    Returns:
        list: 规整后的列表；解析失败或非 str/list 时返回 []。
    """
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        try:
            parsed = json.loads(value) if value else []
            return parsed if isinstance(parsed, list) else []
        except (json.JSONDecodeError, ValueError):
            return []
    return []


@register_schema
async def init_user_schema():
    """
    用户表结构初始化

    创建用户表，包含用户名（唯一）、密码哈希、角色、真实姓名、手机号、邮箱、部门、职位、创建时间和更新时间。
    角色字段默认值为 'user'，管理员角色为 'admin'。
    """
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username VARCHAR(100) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(20) DEFAULT 'user',
            real_name VARCHAR(20) DEFAULT '',
            phone VARCHAR(20) DEFAULT '',
            email VARCHAR(100) DEFAULT '',
            department VARCHAR(100) DEFAULT '',
            position VARCHAR(100) DEFAULT '',
            allowed_agents JSONB DEFAULT '[]',
            created_at TIMESTAMP DEFAULT NOW(),
            updated_at TIMESTAMP DEFAULT NOW()
        )
    """)
    # 为已存在的表添加新字段（兼容已有数据库）
    for column, col_type in [
        ('real_name', 'VARCHAR(20) DEFAULT \'\''),
        ('phone', 'VARCHAR(20) DEFAULT \'\''),
        ('email', 'VARCHAR(100) DEFAULT \'\''),
        ('department', 'VARCHAR(100) DEFAULT \'\''),
        ('position', 'VARCHAR(100) DEFAULT \'\''),
        ('allowed_agents', "JSONB DEFAULT '[]'"),
        # 2026-08-07 新增：登录失败计数与锁定到期（MFATOTP 拒绝重放在 ``user_mfa_totp`` 内完成）
        ('failed_login_count', 'INTEGER NOT NULL DEFAULT 0'),
        ('locked_until', 'TIMESTAMP NULL'),
    ]:
        await DatabasePool.execute(
            f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {column} {col_type}"
        )


class UserDB:
    """
    用户数据库操作类

    提供用户的创建、验证、查询等方法。
    支持两种模式：
    - postgres 模式：使用 PostgreSQL 数据库
    - memory 模式：使用内存字典存储
    """

    # 内存存储（当 AUTH_STORAGE_MODE=memory 时使用）
    _memory_users: Dict[str, dict] = {}
    # 2026-08-07 新增：登录锁定字段内存镜像（failed_login_count / locked_until）
    # 持久化模式以 users.failed_login_count / users.locked_until 为单一真相源。
    _memory_id_counter: int = 0
    _memory_login_lock: Dict[int, Dict[str, Any]] = {}
    _lock = threading.Lock()

    @classmethod
    def is_enabled(cls) -> bool:
        """
        检查是否启用数据库模式

        Returns:
            bool: AUTH_STORAGE_MODE=postgres 时返回 True
        """
        return DatabasePool.is_enabled()

    @staticmethod
    def hash_password(password: str) -> str:
        """
        使用 bcrypt 加密密码

        Args:
            password: 明文密码

        Returns:
            str: 加密后的密码哈希
        """
        salt = bcrypt.gensalt()
        return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """
        验证密码

        Args:
            password: 明文密码
            password_hash: 加密后的密码哈希

        Returns:
            bool: 验证通过返回 True
        """
        return bcrypt.checkpw(
            password.encode('utf-8'),
            password_hash.encode('utf-8')
        )

    @classmethod
    async def create_user(cls, username: str, password: str, role: str = 'user',
                          real_name: str = '', phone: str = '', email: str = '',
                          department: str = '', position: str = '',
                          allowed_agents: Optional[List[str]] = None) -> int:
        """
        创建新用户

        Args:
            username: 用户名
            password: 明文密码
            role: 用户角色，默认为 'user'，可选 'admin'
            real_name: 真实姓名
            phone: 手机号
            email: 邮箱
            department: 部门
            position: 职位
            allowed_agents: 允许使用的智能体名称列表，默认为空列表

        Returns:
            int: 新用户 ID

        Raises:
            ValueError: 用户名已存在
        """
        password_hash = cls.hash_password(password)
        allowed_agents = allowed_agents or []

        if not cls.is_enabled():
            # Memory 模式：使用内存存储
            with cls._lock:
                if username in cls._memory_users:
                    raise ValueError("用户名已存在")
                cls._memory_id_counter += 1
                user_id = cls._memory_id_counter
                now = datetime.utcnow()
                cls._memory_users[username] = {
                    'id': user_id,
                    'username': username,
                    'password_hash': password_hash,
                    'role': role,
                    'real_name': real_name,
                    'phone': phone,
                    'email': email,
                    'department': department,
                    'position': position,
                    'allowed_agents': allowed_agents,
                    'created_at': now,
                    'updated_at': now
                }
                return user_id

        # Postgres 模式：使用数据库
        import asyncpg
        try:
            row = await DatabasePool.fetchrow(
                """
                INSERT INTO users (username, password_hash, role, real_name, phone, email, department, position, allowed_agents)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9::jsonb)
                RETURNING id
                """,
                username,
                password_hash,
                role,
                real_name,
                phone,
                email,
                department,
                position,
                json.dumps(allowed_agents)
            )
            return row['id']
        except asyncpg.UniqueViolationError:
            raise ValueError("用户名已存在")

    @classmethod
    async def verify_credentials(cls, username: str, password: str) -> bool:
        """
        验证用户凭据

        Args:
            username: 用户名
            password: 明文密码

        Returns:
            bool: 验证通过返回 True
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储验证
            with cls._lock:
                user = cls._memory_users.get(username)
                if not user:
                    return False
                return cls.verify_password(password, user['password_hash'])

        # Postgres 模式：从数据库验证
        row = await DatabasePool.fetchrow(
            "SELECT password_hash FROM users WHERE username = $1",
            username
        )
        if not row:
            return False
        return cls.verify_password(password, row['password_hash'])

    @classmethod
    async def get_user_by_username(cls, username: str) -> Optional[dict]:
        """
        根据用户名查询用户

        Args:
            username: 用户名

        Returns:
            Optional[dict]: 用户信息（含 role），不存在返回 None
        """
        if not cls.is_enabled():
            with cls._lock:
                user = cls._memory_users.get(username)
                if not user:
                    return None
                return {
                    'id': user['id'],
                    'username': user['username'],
                    'password_hash': user['password_hash'],
                    'role': user.get('role', 'user'),
                    'real_name': user.get('real_name', ''),
                    'phone': user.get('phone', ''),
                    'email': user.get('email', ''),
                    'department': user.get('department', ''),
                    'position': user.get('position', ''),
                    'allowed_agents': user.get('allowed_agents', []),
                    'created_at': user['created_at'],
                    'updated_at': user['updated_at']
                }

        record = await DatabasePool.fetchrow(
            "SELECT id, username, password_hash, role, real_name, phone, email, department, position, allowed_agents, created_at, updated_at FROM users WHERE username = $1",
            username
        )
        if record is None:
            return None
        return {
            'id': record['id'],
            'username': record['username'],
            'password_hash': record['password_hash'],
            'role': record['role'],
            'real_name': record.get('real_name', ''),
            'phone': record.get('phone', ''),
            'email': record.get('email', ''),
            'department': record.get('department', ''),
            'position': record.get('position', ''),
            'allowed_agents': _coerce_allowed_agents(record.get('allowed_agents', [])),
            'created_at': record['created_at'],
            'updated_at': record['updated_at'],
        }

    @classmethod
    async def get_user_by_id(cls, user_id: int) -> Optional[dict]:
        """
        根据 ID 查询用户

        Args:
            user_id: 用户 ID

        Returns:
            Optional[dict]: 用户信息（含 role 和 password_hash），不存在返回 None
        """
        if not cls.is_enabled():
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        return {
                            'id': user['id'],
                            'username': user['username'],
                            'password_hash': user['password_hash'],
                            'role': user.get('role', 'user'),
                            'real_name': user.get('real_name', ''),
                            'phone': user.get('phone', ''),
                            'email': user.get('email', ''),
                            'department': user.get('department', ''),
                            'position': user.get('position', ''),
                            'allowed_agents': user.get('allowed_agents', []),
                            'created_at': user['created_at'],
                            'updated_at': user['updated_at']
                        }
                return None

        record = await DatabasePool.fetchrow(
            "SELECT id, username, password_hash, role, real_name, phone, email, department, position, allowed_agents, created_at, updated_at FROM users WHERE id = $1",
            user_id
        )
        if record is None:
            return None
        return {
            'id': record['id'],
            'username': record['username'],
            'password_hash': record['password_hash'],
            'role': record['role'],
            'real_name': record.get('real_name', ''),
            'phone': record.get('phone', ''),
            'email': record.get('email', ''),
            'department': record.get('department', ''),
            'position': record.get('position', ''),
            'allowed_agents': _coerce_allowed_agents(record.get('allowed_agents', [])),
            'created_at': record['created_at'],
            'updated_at': record['updated_at'],
        }

    @classmethod
    async def list_users(cls, limit: int = 100, offset: int = 0) -> List[dict]:
        """
        查询用户列表

        Args:
            limit: 返回数量限制
            offset: 偏移量

        Returns:
            List[dict]: 用户列表（含 role）
        """
        if not cls.is_enabled():
            with cls._lock:
                users = list(cls._memory_users.values())
                sorted_users = sorted(users, key=lambda u: u['id'])
                paginated_users = sorted_users[offset:offset + limit]
                return [
                    {
                        'id': user['id'],
                        'username': user['username'],
                        'role': user.get('role', 'user'),
                        'real_name': user.get('real_name', ''),
                        'phone': user.get('phone', ''),
                        'email': user.get('email', ''),
                        'department': user.get('department', ''),
                        'position': user.get('position', ''),
                        'allowed_agents': user.get('allowed_agents', []),
                        'created_at': user['created_at'],
                        'updated_at': user['updated_at']
                    }
                    for user in paginated_users
                ]

        records = await DatabasePool.fetch(
            "SELECT id, username, role, real_name, phone, email, department, position, allowed_agents, created_at, updated_at FROM users ORDER BY id LIMIT $1 OFFSET $2",
            limit,
            offset
        )
        return [
            {
                'id': r['id'],
                'username': r['username'],
                'role': r['role'],
                'real_name': r.get('real_name', ''),
                'phone': r.get('phone', ''),
                'email': r.get('email', ''),
                'department': r.get('department', ''),
                'position': r.get('position', ''),
                'allowed_agents': _coerce_allowed_agents(r.get('allowed_agents', [])),
                'created_at': r['created_at'],
                'updated_at': r['updated_at'],
            }
            for r in records
        ]

    @classmethod
    async def delete_user(cls, user_id: int) -> bool:
        """
        删除用户

        Args:
            user_id: 用户 ID

        Returns:
            bool: 删除成功返回 True
        """
        if not cls.is_enabled():
            # Memory 模式：从内存存储删除
            with cls._lock:
                for username, user in list(cls._memory_users.items()):
                    if user['id'] == user_id:
                        del cls._memory_users[username]
                        return True
                return False

        # Postgres 模式：从数据库删除
        result = await DatabasePool.execute(
            "DELETE FROM users WHERE id = $1",
            user_id
        )
        return "DELETE 1" in result

    @classmethod
    async def update_password(cls, user_id: int, new_password: str) -> bool:
        """
        更新用户密码

        Args:
            user_id: 用户 ID
            new_password: 新明文密码

        Returns:
            bool: 更新成功返回 True
        """
        password_hash = cls.hash_password(new_password)

        if not cls.is_enabled():
            # Memory 模式：更新内存存储中的密码
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        user['password_hash'] = password_hash
                        user['updated_at'] = datetime.utcnow()
                        return True
                return False

        # Postgres 模式：更新数据库中的密码
        result = await DatabasePool.execute(
            "UPDATE users SET password_hash = $1, updated_at = NOW() WHERE id = $2",
            password_hash,
            user_id
        )
        return "UPDATE 1" in result

    @classmethod
    async def update_username(cls, user_id: int, new_username: str) -> bool:
        """
        修改用户名

        Args:
            user_id: 用户 ID
            new_username: 新用户名

        Returns:
            bool: 修改成功返回 True

        Raises:
            ValueError: 新用户名已被占用
        """
        if not cls.is_enabled():
            with cls._lock:
                # 检查新用户名是否已存在
                if new_username in cls._memory_users:
                    raise ValueError("用户名已存在")
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        old_username = user['username']
                        user['username'] = new_username
                        user['updated_at'] = datetime.utcnow()
                        # 更新字典键
                        cls._memory_users[new_username] = cls._memory_users.pop(old_username)
                        return True
                return False

        import asyncpg
        try:
            result = await DatabasePool.execute(
                "UPDATE users SET username = $1, updated_at = NOW() WHERE id = $2",
                new_username,
                user_id
            )
            return "UPDATE 1" in result
        except asyncpg.UniqueViolationError:
            raise ValueError("用户名已存在")

    @classmethod
    async def update_profile(cls, user_id: int, phone: str, email: str,
                             department: str, position: str) -> bool:
        """
        更新用户个人资料

        说明：本方法仅维护 phone/email/department/position 四个字段,
        不修改 allowed_agents(可选智能体)。后者由 admin 路径 UserDB.update_user_info 负责。
        历史 Bug：2026-07-19 修复前,本方法曾同时将 allowed_agents 整列覆盖为空数组,
        导致用户在"个人设置"中保存资料后丢失 admin 设置的可选智能体。

        Args:
            user_id: 用户 ID
            phone: 手机号
            email: 邮箱
            department: 部门
            position: 职位

        Returns:
            bool: 更新成功返回 True
        """
        if not cls.is_enabled():
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        user['phone'] = phone
                        user['email'] = email
                        user['department'] = department
                        user['position'] = position
                        user['updated_at'] = datetime.utcnow()
                        return True
                return False

        result = await DatabasePool.execute(
            """
            UPDATE users
            SET phone = $1, email = $2, department = $3, position = $4,
                updated_at = NOW()
            WHERE id = $5
            """,
            phone, email, department, position, user_id
        )
        # 兼容不同数据库驱动返回格式：字符串、CommandComplete、None 等
        result_str = str(result) if result else ''
        return 'UPDATE' in result_str

    @classmethod
    async def update_user_info(cls, user_id: int, real_name: str, phone: str,
                               email: str, department: str, position: str,
                               role: str, allowed_agents: Optional[List[str]] = None) -> bool:
        """
        Admin 更新用户完整资料

        Args:
            user_id: 用户 ID
            real_name: 真实姓名
            phone: 手机号
            email: 邮箱
            department: 部门
            position: 职位
            role: 角色
            allowed_agents: 允许使用的智能体名称列表（可选）

        Returns:
            bool: 更新成功返回 True
        """
        allowed_agents = allowed_agents or []

        if not cls.is_enabled():
            with cls._lock:
                for user in cls._memory_users.values():
                    if user['id'] == user_id:
                        user['real_name'] = real_name
                        user['phone'] = phone
                        user['email'] = email
                        user['department'] = department
                        user['position'] = position
                        user['role'] = role
                        user['allowed_agents'] = allowed_agents
                        user['updated_at'] = datetime.utcnow()
                        return True
                return False

        result = await DatabasePool.execute(
            """
            UPDATE users
            SET real_name = $1, phone = $2, email = $3, department = $4,
                position = $5, role = $6, allowed_agents = $7::jsonb, updated_at = NOW()
            WHERE id = $8
            """,
            real_name, phone, email, department, position, role, json.dumps(allowed_agents), user_id
        )
        return "UPDATE 1" in result

    @classmethod
    async def ensure_admin_exists(cls, settings=None):
        """根据 settings 决定是否创建/迁移默认管理员账号（等保三级 Task 2，2026-08-09 改造）。

        行为矩阵（rows × cols）：

        - admin 不存在 + ``settings.bootstrap_enabled=False`` → logger.error + ``RuntimeError``
          （fail-loud，要求运维先创建 admin）；
        - admin 不存在 + ``bootstrap_enabled=True`` 且 ``default_admin_password`` 通过强校验
          → 创建 admin（``default_admin_username`` / ``default_admin_password``）；
        - admin 已存在 + 哈希命中已知弱默认集 + ``bootstrap_enabled=False`` → ``RuntimeError``
          （fail-loud，要求运维通过 ``PUT /api/users/{id}/password`` 重置后再启）；
        - admin 已存在 + 哈希命中已知弱默认集 + ``bootstrap_enabled=True`` 且强校验通过
          → 用 ``default_admin_password`` 轮换 + 删除该用户所有 Refresh/Portal Refresh Token；
        - admin 已存在 + 哈希不匹配弱默认集 → 静默返回。

        Args:
            settings: ``AuthBootstrapSettings`` 实例（可空，但空 + 无 admin → RuntimeError）。
                兼容鸭子类型：仅访问 ``bootstrap_enabled`` / ``default_admin_username`` /
                ``default_admin_password`` 三个属性。

        Returns:
            None。

        Raises:
            RuntimeError: 缺失 admin + bootstrap_enabled=False；或 admin 哈希命中弱默认
                + bootstrap_enabled=False；或 bootstrap_enabled=True 但 default_admin_password
                不满足强度。
        """
        # 鸭子类型读取，避免依赖 pydantic-settings 导入链（settings 模块可空）
        bootstrap_enabled = bool(getattr(settings, "bootstrap_enabled", False))
        target_username = (
            getattr(settings, "default_admin_username", "admin") or "admin"
        ).strip() or "admin"
        new_password = getattr(settings, "default_admin_password", "") or ""

        admin_row = None
        if not cls.is_enabled():
            # memory 模式：直接在内存字典中查找 role='admin' AND username=target_username
            with cls._lock:
                for user in cls._memory_users.values():
                    if (
                        user.get("role") == "admin"
                        and user.get("username") == target_username
                    ):
                        admin_row = user
                        break
        else:
            # postgres 模式：取 id + password_hash 用于轮换判断
            row = await DatabasePool.fetchrow(
                "SELECT id, password_hash FROM users "
                "WHERE role = 'admin' AND username = $1 LIMIT 1",
                target_username,
            )
            admin_row = row if row else None

        # === 分支 1：已存在 admin → 判断是否需要轮换 ===
        if admin_row is not None:
            need_rotate = False
            for weak in _WEAK_DEFAULT_PASSWORDS:
                try:
                    if cls.verify_password(weak, admin_row["password_hash"]):
                        need_rotate = True
                        break
                except Exception:  # noqa: BLE001  # 容错：旧哈希格式异常时跳过
                    continue
            if not need_rotate:
                # admin 哈希安全（非已知弱默认），静默返回
                return

            if not bootstrap_enabled:
                logger.error(
                    "[ensure_admin_exists] 检测到 admin 账号使用已知弱默认口令，但 "
                    "AUTH_BOOTSTRAP_ENABLED=false，拒绝启动；"
                    "请运维通过 PUT /api/users/{id}/password 重置后再启动。"
                )
                raise RuntimeError("admin account uses known weak default password")

            # bootstrap_enabled=True → 用 default_admin_password 轮换
            from .password_policy import validate_password

            ok, err = validate_password(new_password)
            if not ok:
                logger.error(
                    "[ensure_admin_exists] AUTH_DEFAULT_ADMIN_PASSWORD 不满足复杂度: %s", err
                )
                raise RuntimeError(err)

            updated = await cls.update_password(admin_row["id"], new_password)
            if not updated:
                raise RuntimeError("failed to rotate weak admin password")

            # 撤销该用户所有 Refresh Token / Portal Refresh Token（强制重新登录）
            try:
                from app.shared.utils.auth.refresh_token_db import RefreshTokenDB
                from app.shared.utils.auth.portal_refresh_token_db import (
                    PortalRefreshTokenDB,
                )

                await RefreshTokenDB.delete_user_tokens(admin_row["id"])
                await PortalRefreshTokenDB.delete_user_tokens(admin_row["id"])
            except Exception as exc:  # noqa: BLE001
                logger.warning(
                    "[ensure_admin_exists] token cleanup failed: %s",
                    type(exc).__name__,
                )
            logger.warning(
                "[ensure_admin_exists] 已用 AUTH_DEFAULT_ADMIN_PASSWORD 轮换 admin 的弱默认口令并撤销所有 Token"
            )
            return

        # === 分支 2：admin 不存在 ===
        if not bootstrap_enabled:
            logger.error(
                "[ensure_admin_exists] 未找到 admin 账号且 AUTH_BOOTSTRAP_ENABLED=false；"
                "请运维创建管理员或通过环境变量提供强口令。"
            )
            raise RuntimeError("admin account missing and bootstrap disabled")

        from .password_policy import validate_password

        ok, err = validate_password(new_password)
        if not ok:
            logger.error(
                "[ensure_admin_exists] AUTH_DEFAULT_ADMIN_PASSWORD 不满足复杂度: %s", err
            )
            raise RuntimeError(err)
        await cls.create_user(target_username, new_password, role="admin")
        logger.warning(
            "[ensure_admin_exists] 已通过 AUTH_DEFAULT_ADMIN_PASSWORD 创建默认 admin 账号 (username=%s)",
            target_username,
        )

    # ----------------------------------------------------------------------
    # 2026-08-07 新增：登录锁定相关方法（failed_login_count / locked_until）
    # ----------------------------------------------------------------------
    #
    # 内存模式与 PostgreSQL 模式契约一致：
    # - ``record_failed_login`` 累计失败次数，达到 ``max_attempts`` 时设置 locked_until
    # - ``get_login_lock_state`` 返回当前失败计数与锁定到期时间戳
    # - ``clear_login_lock`` 登录成功（含完成 MFA）后清零
    # 与 ``/login-api`` 不冲突：login-api 不调用这些方法。

    @classmethod
    async def record_failed_login(
        cls,
        user_id: int,
        max_attempts: int,
        lockout_seconds: int,
    ) -> int:
        """累加用户登录失败计数；达到阈值时锁定用户 ``lockout_seconds`` 秒。

        Args:
            user_id: 用户 ID。
            max_attempts: 失败次数上限，达到后启用锁定。
            lockout_seconds: 锁定时长（秒）。

        Returns:
            int: 本次 ``record_failed_login`` 调用后的新失败计数。

        Raises:
            ValueError: ``max_attempts`` 或 ``lockout_seconds`` 为非法值时。
        """
        if max_attempts < 1 or lockout_seconds < 1:
            raise ValueError("max_attempts 与 lockout_seconds 必须 >= 1")

        if not cls.is_enabled():
            with cls._lock:
                state = cls._memory_login_lock.setdefault(
                    user_id, {"failed_login_count": 0, "locked_until": None}
                )
                state["failed_login_count"] = int(state.get("failed_login_count", 0)) + 1
                # 2026-08-08 修复：固定锁定窗口。仅在以下条件成立时才写入
                # ``locked_until``：
                # 1) 新失败计数达到 ``max_attempts``；
                # 2) 当前 ``locked_until`` 为 None，或已不晚于当前时间（已过期）。
                # 活动锁定（``locked_until`` 仍在未来）期间再次失败只能递增
                # 计数，不能顺延截止时间，避免 ZYP 现象：30 分钟后仍被锁定。
                if state["failed_login_count"] >= max_attempts:
                    current_lock = state.get("locked_until")
                    if current_lock is None or current_lock <= time.time():
                        state["locked_until"] = time.time() + lockout_seconds
                return state["failed_login_count"]

        # PostgreSQL 模式：原子 update + 阈值锁定计算（参数化 SQL）。
        # 使用 CTE 同时返回 ``failed_login_count`` 与 ``locked_until``，
        # 既能让 ``DatabasePool.fetchrow`` 拿到旧/新行做精确判定，又避免
        # ``UPDATE ... RETURNING`` 直接喂 ``fetchval`` 时部分 asyncpg 版本
        # 行为不一致的历史坑（曾导致 ``AttributeError: fetchval`` 被外层
        # ``except Exception: pass`` 吞掉 → 锁定机制整体静默失效）。
        # 2026-08-08 修复：固定锁定窗口。``CASE`` 增加守卫：只有
        # ``locked_until`` 为 NULL 或已过期（<=CURRENT_TIMESTAMP）时才允许
        # 写入新的 ``TO_TIMESTAMP($3)``；活动锁定（仍在未来）期间再次失败
        # 只能递增计数，不能覆盖原截止时间。
        lock_until_target = time.time() + lockout_seconds
        row = await DatabasePool.fetchrow(
            """
            WITH updated AS (
                UPDATE users
                SET failed_login_count = COALESCE(failed_login_count, 0) + 1,
                    locked_until = CASE
                        WHEN COALESCE(failed_login_count, 0) + 1 >= $2
                             AND (locked_until IS NULL OR locked_until <= CURRENT_TIMESTAMP)
                            THEN TO_TIMESTAMP($3)
                        ELSE locked_until
                    END,
                    updated_at = NOW()
                WHERE id = $1
                RETURNING failed_login_count, locked_until
            )
            SELECT failed_login_count, locked_until FROM updated
            """,
            user_id,
            max_attempts,
            lock_until_target,
        )
        if row is None:
            # 用户记录不存在；视为失败但计数不动
            new_count = 0
        else:
            new_count = int(row.get("failed_login_count") or 0)
        # 行级锁定生效兜底：如 SQL CASE 未命中阈值（schema 漂移等情况），
        # 在内存层基于 new_count 与 max_attempts 兜底再设一次 locked_until，
        # 保证锁定语义与 max_attempts 阈值一致（路线 B：路由层再次校验）。
        # 2026-08-08 修复：兜底条件扩展为 "IS NULL OR 已过期"，与主路径
        # CASE 守卫保持一致，避免活动锁定被兜底分支顺延。
        if new_count >= max_attempts:
            try:
                await DatabasePool.execute(
                    "UPDATE users SET locked_until = TO_TIMESTAMP($1) "
                    "WHERE id = $2 AND (locked_until IS NULL OR locked_until <= CURRENT_TIMESTAMP)",
                    lock_until_target,
                    user_id,
                )
            except Exception as exc:  # noqa: BLE001
                # 兜底只做 best-effort：主路径已通过 CASE WHEN 写库，
                # 这里失败不致命；保留诊断日志便于追踪。
                import logging
                logging.getLogger(__name__).warning(
                    "[UserDB.record_failed_login] fallback lock write failed: user_id=%s err=%s",
                    user_id,
                    type(exc).__name__,
                )
        return int(new_count or 0)

    @classmethod
    async def get_login_lock_state(cls, user_id: int) -> Dict[str, Any]:
        """读取用户的登录锁定状态。

        Args:
            user_id: 用户 ID。

        Returns:
            Dict[str, Any]: ``{"failed_login_count": int, "locked_until": Optional[float]}``。
            不存在的用户返默认值 (0, None)。
        """
        if not cls.is_enabled():
            with cls._lock:
                state = cls._memory_login_lock.get(
                    user_id, {"failed_login_count": 0, "locked_until": None}
                )
                return {
                    "failed_login_count": int(state.get("failed_login_count", 0)),
                    "locked_until": state.get("locked_until"),
                }

        row = await DatabasePool.fetchrow(
            "SELECT failed_login_count, locked_until FROM users WHERE id = $1",
            user_id,
        )
        if row is None:
            return {"failed_login_count": 0, "locked_until": None}
        lu = row.get("locked_until")
        lu_ts: Optional[float]
        if lu is None:
            lu_ts = None
        else:
            # PG 返回 timestamptz，asyncpg 会按 TZ-aware datetime
            try:
                lu_ts = lu.timestamp()
            except (AttributeError, TypeError):
                lu_ts = None
        return {
            "failed_login_count": int(row.get("failed_login_count") or 0),
            "locked_until": lu_ts,
        }

    @classmethod
    async def clear_login_lock(cls, user_id: int) -> None:
        """登录成功后清零失败计数与锁定状态（覆盖密码 + MFA 两种完成路径）。

        Args:
            user_id: 用户 ID。
        """
        if not cls.is_enabled():
            with cls._lock:
                cls._memory_login_lock.pop(user_id, None)
            return

        await DatabasePool.execute(
            "UPDATE users SET failed_login_count = 0, locked_until = NULL, updated_at = NOW() "
            "WHERE id = $1",
            user_id,
        )