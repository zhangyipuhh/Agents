# -*- coding:utf-8 -*-
"""
MenuPermissionService —— 用户菜单权限服务。

启动时从 user_menu_acl 全量加载到内存，提供：
- get_visible_menu_ids(user_id, is_admin) -> List[str]
- get_user_grants(user_id) -> Set[str]
- grant(user_id, menu_ids, operator_id)
- revoke(user_id, menu_ids, operator_id)
- replace(user_id, menu_ids, operator_id)

降级策略（fail-secure）：
- db=None 时：admin 返全量；普通用户仅返 ['profile']
- DB 写入失败：抛 RuntimeError（调用方决定如何处理）

详见 docs/superpowers/specs/2026-07-23-menu-permission-design.md § 4
"""

from typing import Any, Dict, List, Optional, Set

from app.core.menu_registry import get_enabled_items


class MenuPermissionService:
    """用户菜单权限服务（内存缓存 + DB 双写）。"""

    def __init__(self, db: Any = None):
        self._db = db
        self._cache: Dict[int, Set[str]] = {}

    # ---------- 启动加载 ----------

    async def preload_all(self) -> None:
        """从 user_menu_acl 全量加载到 self._cache。

        兼容 db=None（no-op，fail-secure）。
        不创建表（建表由 init_user_menu_acl_schema() 在 lifespan 启动阶段完成）。
        """
        if self._db is None:
            return
        rows = await self._db.fetch(
            "SELECT user_id, menu_id FROM user_menu_acl"
        )
        cache: Dict[int, Set[str]] = {}
        for row in rows:
            uid = row["user_id"]
            cache.setdefault(uid, set()).add(row["menu_id"])
        self._cache = cache

    # ---------- 查询 ----------

    async def get_visible_menu_ids(self, user_id: int, is_admin: bool) -> List[str]:
        """返回该用户可见菜单的 id 列表（按 sort_order 升序）。

        - admin：直接返 get_enabled_items() 全量 id，忽略缓存
        - 普通用户：返 cache[user_id] ∩ enabled，末尾强制追加 'profile'
        - db=None：同上语义（fail-secure）
        """
        enabled = get_enabled_items()
        if is_admin:
            return [m.id for m in sorted(enabled, key=lambda m: m.sort_order)]
        granted = self._cache.get(user_id, set())
        visible_ids = {m.id for m in enabled if m.id in granted}
        # 强制保留个人设置（最低可用性保证）
        visible_ids.add("profile")
        visible = [m for m in enabled if m.id in visible_ids]
        return [m.id for m in sorted(visible, key=lambda m: m.sort_order)]

    async def get_user_grants(self, user_id: int) -> Set[str]:
        """返该用户已授权的 menu_id 集合（缓存为空时返空 set）。"""
        return set(self._cache.get(user_id, set()))

    # ---------- 写操作 ----------

    async def grant(self, user_id: int, menu_ids: Set[str], operator_id: Optional[int] = None) -> None:
        """批量添加授权（内存 + DB 双写；db=None 仅写内存）。"""
        menu_ids = set(menu_ids)
        if not menu_ids:
            return
        self._cache.setdefault(user_id, set()).update(menu_ids)
        if self._db is None:
            return
        for mid in menu_ids:
            await self._db.execute(
                """
                INSERT INTO user_menu_acl (user_id, menu_id, created_by_user_id)
                VALUES ($1, $2, $3)
                ON CONFLICT (user_id, menu_id) DO NOTHING
                """,
                user_id, mid, operator_id,
            )

    async def revoke(self, user_id: int, menu_ids: Set[str], operator_id: Optional[int] = None) -> None:
        """批量撤销授权（内存 + DB 双写；db=None 仅写内存）。"""
        menu_ids = set(menu_ids)
        if not menu_ids:
            return
        granted = self._cache.get(user_id, set())
        if not (menu_ids & granted):
            return  # 没有任何要撤销的，跳过
        self._cache[user_id] = granted - menu_ids
        if self._db is None:
            return
        await self._db.execute(
            "DELETE FROM user_menu_acl WHERE user_id = $1 AND menu_id = ANY($2::text[])",
            user_id, list(menu_ids),
        )

    async def replace(self, user_id: int, menu_ids: Set[str], operator_id: Optional[int] = None) -> None:
        """全量覆盖该用户的授权（先清空再批量写；菜单管理 UI 保存用）。"""
        menu_ids = set(menu_ids)
        if self._db is None:
            # 无 DB：直接覆盖缓存
            self._cache[user_id] = set(menu_ids)
            return
        # 1) 删 DB 旧行
        await self._db.execute(
            "DELETE FROM user_menu_acl WHERE user_id = $1",
            user_id,
        )
        # 2) 批量插新行（如果有）
        for mid in menu_ids:
            await self._db.execute(
                """
                INSERT INTO user_menu_acl (user_id, menu_id, created_by_user_id)
                VALUES ($1, $2, $3)
                """,
                user_id, mid, operator_id,
            )
        # 3) 同步缓存
        self._cache[user_id] = set(menu_ids)


# ---------- 建表 schema（供 lifespan 调用） ----------


def _build_init_user_menu_acl_schema():
    """返回 init_user_menu_acl_schema 协程（闭包形式，避免循环 import）。

    由 app/core/server.py::lifespan 在 DatabasePool 初始化完成后显式 await。
    与 init_all_tables.sql 的 DDL 保持一致（双保险）。
    """
    from app.core.database import DatabasePool

    async def _init() -> None:
        await DatabasePool.execute("""
            CREATE TABLE IF NOT EXISTS user_menu_acl (
                id                  SERIAL PRIMARY KEY,
                user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                menu_id             VARCHAR(64) NOT NULL,
                created_at          TIMESTAMP DEFAULT NOW(),
                created_by_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
                UNIQUE (user_id, menu_id)
            )
        """)
        await DatabasePool.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_menu_acl_user_id ON user_menu_acl(user_id)"
        )
        await DatabasePool.execute(
            "CREATE INDEX IF NOT EXISTS idx_user_menu_acl_menu_id ON user_menu_acl(menu_id)"
        )

    return _init


# 提供给 lifespan 调用的建表函数
init_user_menu_acl_schema = _build_init_user_menu_acl_schema()