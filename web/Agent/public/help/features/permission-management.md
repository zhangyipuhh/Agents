# 权限管理

权限管理模块负责**菜单可见性**与**智能体访问**两维度的 ACL 控制。本章节介绍菜单注册表、ACL 矩阵与授权流程。

## 前置条件

- **admin 角色**（菜单 ACL 由 admin 维护）
- 拥有 `permission-management.menu` 菜单权限（默认 admin 全开）
- 浏览器已登录

## 菜单注册表

菜单注册表是单一代码真相源，位于 `app/core/menu_registry.py::MENU_CATALOG`。

### 一级菜单（14 个）

| id | label | sort_order | required_role |
|---|---|---|---|
| `system.basic-settings` | 基本设置 | 0 | admin |
| `profile` | 个人设置 | 1 | 全部 |
| `user-management` | 用户管理 | 2 | admin |
| `permission-management` | 权限管理 | 3 | admin |
| `agent-management` | 智能体管理 | 4 | admin |
| `mcp-management` | MCP 管理 | 5 | admin |
| `tool-management` | 工具管理 | 6 | admin |
| `skill-management` | Skill 管理 | 7 | admin |
| `task-scheduler` | 运维任务 | 8 | admin |
| `messaging` | 消息设置 | 9 | admin |

### 二级菜单（12 个）

每个一级菜单下的 Tab 也是独立授权单元。如：
- `messaging.email` / `messaging.feishu`（channel 入口）
- `messaging.feishu.apps` / `policies` / `test`（孙 Tab）
- `task-scheduler.scheduled` / `script-scan` / `server-management` / `inspection-script-library` 等

## 可见性规则

### admin
- 返全量 `enabled=True` 项（按 `sort_order` 排序）
- 忽略 `user_menu_acl` 表

### 普通用户
- `user_menu_acl.menu_id` 集合 ∩ enabled
- 末尾强制追加 `profile`（最低可用性保证）
- 按 `sort_order` 排序

#### 数据流
```
用户登录 → fetchValidate() 读 /api/session/admin/menu-visible
       → get_visible_for_user(user_id, is_admin, granted_menu_ids)
       → 返回 MenuItem 列表
       → 前端 visibleMenus prop 渲染 UserSettingsDialog
```

## 授权粒度

权限管理提供两套独立授权：

### 1. 菜单权限（`MenuPermissionManager`）
- 按「用户 × 菜单 id」粒度授权
- 路由级 ACL 用 `require_admin_or_menu_acl(menu_id)`
- 存储表：`user_menu_acl`（含 `user_id` / `menu_id` / `granted_by_user_id` / `granted_at`）

### 2. 智能体访问（`AgentAccessManager`）
- 按「用户 × 智能体 name」粒度授权
- 存储表：`user_agent_acl`（mirror `user_menu_acl`）
- 普通用户只能看到 `users.allowed_agents` JSONB 字段中授权的智能体

## 修改菜单

> ⚠️ **菜单 id 永不改**——id 是身份，改 id = 删菜单 + 建菜单，老 ACL 全部失效。

可修改的字段（无 ACL 失效风险）：

| 字段 | 说明 |
|---|---|
| `label` | 显示名（可改） |
| `icon_key` | 图标 key（前端映射） |
| `sort_order` | 排序（可改） |
| `level` | 层级（1 / 2） |
| `parent_id` | 二级菜单指向一级菜单 id |
| `required_role` | `admin` / `None`（None = 所有登录用户可看） |
| `enabled` | `False` 时菜单管理 UI 隐藏但 ACL 保留 |

## 新增菜单流程

1. **修改 `app/core/menu_registry.py`**：在 `MENU_CATALOG` 追加一条 `MenuItem` 注册项
2. **前端图标元数据**（如需）：`web/Agent/src/components/UserSettingsDialog.vue` 的 `NAV_MENU_METADATA` 加对应元数据
3. **如需独立 Tab 渲染区**：在 `UserSettingsDialog.vue` 模板加 `<div v-show="activeTab === '<id>'">` 块
4. **完成**——菜单管理 UI 自动出现该项，admin 可在「权限管理 → 菜单管理」勾选授权

## 授权普通用户流程

1. 进入「权限管理 → → 菜单管理」或「智能体访问」
2. 选择目标用户
3. 勾选要授权的菜单 / 智能体
4. 点击「保存」
5. **用户需重新登录**才会生效（`users.allowed_agents` 在登录时缓存）

#### 重新登录提示
- 前端可见性变化：用户**必须刷新页面 + 重新登录**
- 后端 ACL 实时生效：`require_admin_or_menu_acl` 每次请求都校验

## 路由级 ACL

### 三种守卫（位于 `app/shared/utils/auth/Safety.py`）

| 装饰器 | 用途 |
|---|---|
| `require_admin` | 仅 admin 可访问（router 级 `Depends`） |
| `require_admin_or_menu_acl(menu_id)` | admin 直通 / 普通用户需 menu_id ACL |
| `require_admin_or_any_menu_acl(*menu_ids)` | admin 直通 / 普通用户命中任一 menu_id ACL 即可 |

### 使用示例

```python
# router 级（影响整个 router）
router = APIRouter(prefix="/api/admin/mcp", dependencies=[Depends(require_admin)])

# 端点级（精细控制）
@router.get("/tree", dependencies=[Depends(require_admin_or_any_menu_acl("task-scheduler.api-config", "task-scheduler.scheduled"))])
async def list_tree(request: Request):
    ...
```

### ACL 命名约定

- 一级菜单 ACL key：`task-scheduler`、`messaging`
- 二级菜单 ACL key：`task-scheduler.scheduled`、`messaging.feishu`
- 孙 Tab ACL key：`messaging.feishu.apps`、`task-scheduler.email-settings.server`（历史上保留 email-settings 不变）

## 常见问题

### admin 直通 vs 普通用户 ACL？
- **admin 直通**：admin 角色无视所有 ACL（默认能看全部菜单 / 调用所有 admin 端点）
- **普通用户 ACL**：必须命中 `user_menu_acl` 表中具体 menu_id

### 修改菜单后老 ACL 失效？
- 仅当改 `id` 时失效
- 改 `label` / `sort_order` / `icon_key` / `enabled` 等字段不影响 ACL
- 改 `parent_id` 仅影响显示分组，不影响 ACL key

### 菜单不显示但能调用 API？
- 路由级 ACL 与菜单可见性是**正交**的两套控制
- 菜单不显示仅影响 UI 可见性，**不会阻止 API 调用**
- API 调用由 `require_admin` / `require_admin_or_menu_acl` 守护

### 普通用户被授权但看不到菜单？
- 用户必须**重新登录**（`user_menu_acl` 在登录时一次性读入 `users.allowed_agents`）
- 或检查 `enabled` 字段是否为 true

## 相关章节

- [用户管理](/help/features/user-management) — 用户账号状态
- [智能体管理](/help/features/agent-management) — 智能体配置
- [基本设置](/help/features/basic-settings) — 22 组配置
- [常见问题 → 注册审批问题](/help/faq#注册审批问题) — pending_approval 三态