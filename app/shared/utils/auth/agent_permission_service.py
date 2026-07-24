# -*- coding:utf-8 -*-
"""
AgentPermissionService —— 用户智能体访问权限服务。

启动时从 user_agent_acl 全量加载到内存，提供：
- preload_all()                         从 DB 加载到缓存
- get_user_agent_grants(user_id)        查该用户已授权智能体
- get_visible_agents(user_id, all_agent_names, is_admin)
                                        按 ACL 过滤智能体列表
- grant(user_id, agent_names, operator_id)
- revoke(user_id, agent_names, operator_id)
- replace(user_id, agent_names, operator_id)

降级策略（fail-secure）：
- db=None 时：调用方传 all_agent_names + is_admin；
  admin 返全量，普通用户返 []
- DB 写入失败：抛 RuntimeError（调用方决定如何处理）

数据迁移：lifespan 启动时若 user_agent_acl 为空，从 users.allowed_agents (JSONB) 复制
（幂等，ON CONFLICT DO NOTHING；被显式删除的字段不会回流）。

完全 mirror MenuPermissionService 模式（menu_permission_service.py）。
"""

from typing import Any, Dict, List, Optional, Set


class AgentPermissionService:
    """用户智能体访问权限服务（内存缓存 + DB 双写）。"""

    def __init__(self, db: Any = None):
        self._db = db
        self._cache: Dict[int, Set[str]] = {}

    # ---------- 启动加载 ----------

    async def preload_all(self) -> None:
        """从 user_agent_acl 全量加载到 self._cache。

        兼容 db=None（no-op，fail-secure）。
        不创建表（建表由 init_user_agent_acl_schema() 在 lifespan 启动阶段完成）。
        """
        if self._db is None:
            return
        rows = await self._db.fetch(
            "SELECT user_id, agent_name FROM user_agent_acl"
        )
        cache: Dict[int, Set[str]] = {}
        for row in rows:
            uid = row["user_id"]
            cache.setdefault(uid, set()).add(row["agent_name"])
        self._cache = cache

    # ---------- 查询 ----------

    async def get_user_agent_grants(self, user_id: int) -> Set[str]:
        """返该用户已授权的 agent_name 集合（缓存为空时返空 set）。"""
        return set(self._cache.get(user_id, set()))

    def get_user_agent_grants_sync(self, user_id: int) -> Set[str]:
        """同步版本（auth/validate 同步上下文使用）。"""
        return set(self._cache.get(user_id, set()))

    def get_visible_agents(
        self,
        user_id: int,
        all_agent_names: List[str],
        is_admin: bool,
    ) -> List[str]:
        """根据 ACL 过滤智能体列表。

        参数:
            user_id: 用户 ID
            all_agent_names: 全量智能体 name 列表（来自 agent_config_service）
            is_admin: 是否管理员角色

        返回:
            过滤后的 agent_name 列表；admin 返全量，普通用户返 cache[user_id] ∩ all_agent_names

        规则:
        - admin：直接返 all_agent_names（admin 绕过 ACL）
        - 普通用户：cache[user_id] ∩ all_agent_names；ACL 为空时返 []
        - db=None：同上（fail-secure：普通用户 ACL 视为空）
        """
        if is_admin:
            return list(all_agent_names)
        granted = self._cache.get(user_id, set())
        return [name for name in all_agent_names if name in granted]

    # ---------- 写操作 ----------

    async def grant(
        self,
        user_id: int,
        agent_names: Set[str],
        operator_id: Optional[int] = None,
    ) -> None:
        """批量添加授权（内存 + DB 双写；db=None 仅写内存）。"""
        agent_names = set(agent_names)
        if not agent_names:
            return
        self._cache.setdefault(user_id, set()).update(agent_names)
        if self._db is None:
            return
        for name in agent_names:
            await self._db.execute(
                """
                INSERT INTO user_agent_acl (user_id, agent_name, created_by_user_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, agent_name) DO NOTHING
                """,
                user_id, name, operator_id,
            )

    async def revoke(
        self,
        user_id: int,
        agent_names: Set[str],
        operator_id: Optional[int] = None,
    ) -> None:
        """批量撤销授权（内存 + DB 双写；db=None 仅写内存）。"""
        agent_names = set(agent_names)
        if not agent_names:
            return
        granted = self._cache.get(user_id, set())
        if not (agent_names & granted):
            return  # 没有任何要撤销的，跳过
        self._cache[user_id] = granted - agent_names
        if self._db is None:
            return
        await self._db.execute(
            "DELETE FROM user_agent_acl WHERE user_id = $1 AND agent_name = ANY($2::text[])",
            user_id, list(agent_names),
        )

    async def replace(
        self,
        user_id: int,
        agent_names: Set[str],
        operator_id: Optional[int] = None,
    ) -> None:
        """全量覆盖该用户的智能体授权（先清空再批量写；智能体访问权限 UI 保存用）。"""
        agent_names = set(agent_names)
        if self._db is None:
            # 无 DB：直接覆盖缓存
            self._cache[user_id] = set(agent_names)
            return
        # 1) 删 DB 旧行
        await self._db.execute(
            "DELETE FROM user_agent_acl WHERE user_id = $1",
            user_id,
        )
        # 2) 批量插新行（如果有）
        for name in agent_names:
            await self._db.execute(
                """
                INSERT INTO user_agent_acl (user_id, agent_name, created_by_user_id)
                VALUES ($1, $2, $3)
                """,
                user_id, name, operator_id,
            )
        # 3) 同步缓存
        self._cache[user_id] = set(agent_names)


# ---------- 建表 schema + 迁移（供 lifespan 调用） ----------


def _build_init_user_agent_acl_schema():
    """返回 init_user_agent_acl_schema 协程（闭包形式，避免循环 import）。

    由 app/core/server.py::lifespan 在 DatabasePool 初始化完成后显式 await。
    与 init_all_tables.sql 的 DDL 保持一致（双保险）。
    """
    from app.core.database import DatabasePool

    async def _init() -> None:
        await DatabasePool.execute("""
            CREATE TABLE IF NOT EXISTS user_agent_acl (
                id                  SERIAL PRIMARY KEY,
                user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                agent_name          VARCHAR(128) NOT NULL,
                created_at          TIMESTAMP DEFAULT NOW(),
                created_by_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE (user_id, agent_name)
            )
        """)
        await DatabasePool.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_agent_acl_user_id ON user_agent_acl(user_id)"
        )
        await DatabasePool.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_agent_acl_agent_name ON user_agent_acl(agent_name)"
        )

    return _init


async def migrate_from_users_allowed_agents(db: Any) -> int:
    """从 users.allowed_agents (JSONB) 一次性迁移到 user_agent_acl。

    幂等：使用 ON CONFLICT DO NOTHING，重复调用不会重复插。
    仅迁移 users.allowed_agents 非空的用户；老 admin 全量授权过的话可能没存 JSONB，
    此时该 admin 走 ACL 旁路（is_admin=True），不受影响。

    参数:
        db: asyncpg 连接池（DatabasePool._pool）

    返回:
        实际新插入的行数（重复调用一般返 0）
    """
    # 一次性把 users.allowed_agents (JSONB) 解构并插入 user_agent_acl
    # jsonb_array_elements_text 把 JSONB 数组拆成 text 行
    # ON CONFLICT DO NOTHING 保证幂等
    result = await db.execute(
        """
        INSERT INTO user_agent_acl (user_id, agent_name, created_by_user_id)
        SELECT u.id, a.agent_name, NULL
        FROM users u,
             jsonb_array_elements_text(COALESCE(u.allowed_agents, '[]'::jsonb)) AS a(agent_name)
        ON CONFLICT (user_id, agent_name) DO NOTHING
        """
    )
    # asyncpg 返回的 status 形如 "INSERT 0 5"，解析末尾数字
    try:
        return int(str(result).rsplit(" ", 1)[-1])
    except (ValueError, IndexError):
        return 0


# 提供给 lifespan 调用的建表函数
init_user_agent_acl_schema = _build_init_user_agent_acl_schema()
