# -*- coding: utf-8 -*-
"""
菜单注册表（单一代码真相源）。

新加菜单 / 修改菜单 / 下架菜单都通过修改本文件的 MENU_CATALOG 实现。
详见 docs/superpowers/specs/2026-07-23-menu-permission-design.md § 3.1
以及 AGENTS.md "菜单管理规则" 章节。

硬规则：
- id 终身不变（改 id = 删菜单 + 建菜单，老 ACL 全部失效）
- 可改字段：label / icon_key / sort_order / level / parent_id / required_role / enabled
"""

from typing import List, Optional, Set

from pydantic import BaseModel


class MenuItem(BaseModel):
    """菜单注册项。"""

    id: str                       # 稳定 key，永不改
    level: int                    # 1 = 一级, 2 = 二级
    parent_id: Optional[str] = None  # 二级菜单指向一级菜单 id
    label: str                    # 显示名（可改）
    icon_key: str                 # 图标 key（前端映射）
    sort_order: int               # 排序（可改）
    required_role: Optional[str] = None  # 'admin' / None（None = 所有登录用户可看）
    enabled: bool = True          # False 时菜单管理 UI 隐藏但 ACL 保留


# === 一级菜单 ===
MENU_CATALOG: List[MenuItem] = [
    MenuItem(id="profile", level=1, label="个人设置", icon_key="user",
             sort_order=1, required_role=None),
    MenuItem(id="user-management", level=1, label="用户管理", icon_key="users",
             sort_order=2, required_role="admin"),
    # 2026-07-23 调整：将「权限管理」从末尾（sort_order=8）上移到「用户管理」正下方（sort_order=3），
    # 后续一级菜单 sort_order 顺次 +1。id 保持不变，ACL 自动保留。
    MenuItem(id="permission-management", level=1, label="权限管理", icon_key="shield",
             sort_order=3, required_role="admin"),
    MenuItem(id="agent-management", level=1, label="智能体管理", icon_key="robot",
             sort_order=4, required_role="admin"),
    MenuItem(id="mcp-management", level=1, label="MCP 管理", icon_key="server",
             sort_order=5, required_role="admin"),
    MenuItem(id="tool-management", level=1, label="工具管理", icon_key="wrench",
             sort_order=6, required_role="admin"),
    MenuItem(id="skill-management", level=1, label="Skill 管理", icon_key="book",
             sort_order=7, required_role="admin"),
    MenuItem(id="task-scheduler", level=1, label="运维任务", icon_key="clock",
             sort_order=8, required_role="admin"),
    # 2026-07-23 调整：「邮件设置」从「运维任务」下的二级菜单升级为独立一级菜单。
    # - id 保持 `task-scheduler.email-settings` 不变（id 终身不变硬规则，老 ACL 自动保留）
    # - level 2 → 1，parent_id None
    # - sort_order 4 → 9（排在一级菜单末尾）
    MenuItem(id="task-scheduler.email-settings", level=1, parent_id=None,
             label="邮件设置", icon_key="mail", sort_order=9, required_role="admin"),

    # === 二级菜单（tab）===
    MenuItem(id="user-management.users", level=2, parent_id="user-management",
             label="用户列表", icon_key="list", sort_order=1, required_role="admin"),
    MenuItem(id="user-management.online-monitor", level=2, parent_id="user-management",
             label="在线监控", icon_key="eye", sort_order=2, required_role="admin"),
    MenuItem(id="user-management.session-query", level=2, parent_id="user-management",
             label="会话查询", icon_key="search", sort_order=3, required_role="admin"),
    MenuItem(id="task-scheduler.scheduled", level=2, parent_id="task-scheduler",
             label="定时任务", icon_key="cron", sort_order=1, required_role="admin"),
    MenuItem(id="task-scheduler.script-scan", level=2, parent_id="task-scheduler",
             label="脚本扫描", icon_key="scan", sort_order=2, required_role="admin"),
    MenuItem(id="task-scheduler.api-config", level=2, parent_id="task-scheduler",
             label="API接口配置", icon_key="api", sort_order=3, required_role="admin"),
    # 2026-07-23 新增：「邮件设置」的三个内部 Tab 注册为可独立授权的二级菜单
    # - id 前缀与一级菜单保持一致：task-scheduler.email-settings.*
    # - 与 EmailSettingsManager.vue::TAB_LABELS 一一对应（server / policies / test）
    # - MenuPermissionManager.vue 已按 level=2 + parent_id 自动渲染，无需前端改动
    MenuItem(id="task-scheduler.email-settings.server", level=2,
             parent_id="task-scheduler.email-settings",
             label="服务器配置", icon_key="server", sort_order=1, required_role="admin"),
    MenuItem(id="task-scheduler.email-settings.policies", level=2,
             parent_id="task-scheduler.email-settings",
             label="发送策略", icon_key="list", sort_order=2, required_role="admin"),
    MenuItem(id="task-scheduler.email-settings.test", level=2,
             parent_id="task-scheduler.email-settings",
             label="测试发送", icon_key="send", sort_order=3, required_role="admin"),
    MenuItem(id="permission-management.menu", level=2, parent_id="permission-management",
             label="菜单管理", icon_key="menu", sort_order=1, required_role="admin"),
]


def get_full_catalog() -> List[MenuItem]:
    """返回注册表全量（含 enabled=False 项，admin 配权限时用）。"""
    return list(MENU_CATALOG)


def get_enabled_items() -> List[MenuItem]:
    """返回 enabled=True 的项（运行时过滤用）。"""
    return [m for m in MENU_CATALOG if m.enabled]


def get_visible_for_user(
    user_id: int,
    is_admin: bool,
    granted_menu_ids: Optional[Set[str]] = None,
) -> List[MenuItem]:
    """
    合并 ACL + 角色，返回该用户可见的菜单项列表。

    Args:
        user_id: 用户 ID
        is_admin: 是否管理员角色
        granted_menu_ids: 该用户在 user_menu_acl 表里的 menu_id 集合；admin 角色忽略此参数

    Returns:
        按 sort_order 排序后的 MenuItem 列表

    权限规则（2026-07-23 修复）：
    - admin：返全量 enabled（绕过 ACL）
    - 普通用户：cache[user_id] ∩ enabled（ACL 是唯一可见性控制）
      - 末尾强制追加 'profile'（最低可用性保证）
    - 实际按钮调用由后端 require_admin 守护（与菜单可见性正交）：
      普通用户即便 ACL 授权了 admin-only 菜单，看到菜单但功能调用被后端拒绝

    历史说明：早期版本曾在普通用户路径上过滤掉 required_role='admin' 的菜单
    （认为该类菜单不能给普通用户授权），但这与产品需求"普通用户通过 ACL 获得
    菜单可见性"矛盾——admin 应该独立决定**谁**能看到该菜单，菜单背后的功能
    访问控制交给路由层的 require_admin 守护即可。已修复。
    """
    enabled = get_enabled_items()
    if is_admin:
        return sorted(enabled, key=lambda m: m.sort_order)
    granted = granted_menu_ids or set()
    # 普通用户：ACL ∩ enabled，末尾追加 profile（最低可用性）
    visible_ids = {m.id for m in enabled if m.id in granted}
    visible_ids.add("profile")
    visible = [m for m in enabled if m.id in visible_ids]
    return sorted(visible, key=lambda m: m.sort_order)