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
import threading
import bcrypt
from typing import Optional, List, Dict
from datetime import datetime
from app.core.database import DatabasePool, register_schema


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
    _memory_id_counter: int = 0
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
                          department: str = '', position: str = '') -> int:
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

        Returns:
            int: 新用户 ID

        Raises:
            ValueError: 用户名已存在
        """
        password_hash = cls.hash_password(password)

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
                    'created_at': now,
                    'updated_at': now
                }
                return user_id

        # Postgres 模式：使用数据库
        import asyncpg
        try:
            row = await DatabasePool.fetchrow(
                """
                INSERT INTO users (username, password_hash, role, real_name, phone, email, department, position)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                RETURNING id
                """,
                username,
                password_hash,
                role,
                real_name,
                phone,
                email,
                department,
                position
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
                    'created_at': user['created_at'],
                    'updated_at': user['updated_at']
                }

        return await DatabasePool.fetchrow(
            "SELECT id, username, password_hash, role, real_name, phone, email, department, position, created_at, updated_at FROM users WHERE username = $1",
            username
        )

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
                            'created_at': user['created_at'],
                            'updated_at': user['updated_at']
                        }
                return None

        return await DatabasePool.fetchrow(
            "SELECT id, username, password_hash, role, real_name, phone, email, department, position, created_at, updated_at FROM users WHERE id = $1",
            user_id
        )

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
                        'created_at': user['created_at'],
                        'updated_at': user['updated_at']
                    }
                    for user in paginated_users
                ]

        return await DatabasePool.fetch(
            "SELECT id, username, role, real_name, phone, email, department, position, created_at, updated_at FROM users ORDER BY id LIMIT $1 OFFSET $2",
            limit,
            offset
        )

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
            SET phone = $1, email = $2, department = $3, position = $4, updated_at = NOW()
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
                               role: str) -> bool:
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

        Returns:
            bool: 更新成功返回 True
        """
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
                        user['updated_at'] = datetime.utcnow()
                        return True
                return False

        result = await DatabasePool.execute(
            """
            UPDATE users
            SET real_name = $1, phone = $2, email = $3, department = $4,
                position = $5, role = $6, updated_at = NOW()
            WHERE id = $7
            """,
            real_name, phone, email, department, position, role, user_id
        )
        return "UPDATE 1" in result

    @classmethod
    async def ensure_admin_exists(cls):
        """
        确保系统中存在管理员账户

        如果不存在 admin 角色的用户，则自动创建默认管理员账户。
        默认用户名: admin，默认密码: admin123，角色: admin。
        """
        # 检查是否已存在 admin 角色用户
        if not cls.is_enabled():
            with cls._lock:
                for user in cls._memory_users.values():
                    if user.get('role') == 'admin':
                        return
            # 不存在则创建
            await cls.create_user('admin', 'admin123', role='admin')
            print("[初始化] 已创建默认管理员账户 (admin/admin123)")
            return

        # 数据库模式
        row = await DatabasePool.fetchrow(
            "SELECT id FROM users WHERE role = 'admin' LIMIT 1"
        )
        if not row:
            await cls.create_user('admin', 'admin123', role='admin')
            print("[初始化] 已创建默认管理员账户 (admin/admin123)")