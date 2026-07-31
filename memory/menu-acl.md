# 菜单权限与用户配置

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## 用户菜单权限管理（2026-07-23 新增）

### 核心契约
- 方案：菜单静态化（代码注册表）+ `user_menu_acl` 表
- 授权粒度：一级 + 二级菜单都支持
- admin 行为：完全绕过 ACL，看到全量菜单
- 菜单注册机制：`app/core/menu_registry.py` 显式注册，启动时载入内存
- 菜单 id 稳定性：**id 终身不变**（硬规则）
- 未授权用户：强制保留「个人设置」可见（最低可用性）
- 「权限管理」菜单本身：admin-only
- 菜单下架：`enabled=False`（ACL 记录保留，不清空授权历史）

### MenuItem 字段

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | str | 稳定 key，永不改 |
| `level` | int | 1 = 一级, 2 = 二级 |
| `parent_id` | Optional[str] | 二级菜单指向一级菜单 id |
| `label` | str | 显示名（可改） |
| `icon_key` | str | 图标 key（前端映射） |
| `sort_order` | int | 排序（可改） |
| `required_role` | Optional[str] | 'admin' / None |
| `enabled` | bool | False 时菜单管理 UI 隐藏但 ACL 保留 |

完整定义见 `app/core/menu_registry.py`。

### 一级菜单顺序（最终态，2026-07-31）

`MENU_CATALOG` 一级菜单按 `sort_order` 升序排列如下：

| sort_order | id | label | required_role |
|---|---|---|---|
| 1 | profile | 个人设置 | None |
| 2 | user-management | 用户管理 | admin |
| 3 | permission-management | 权限管理 | admin |
| 4 | agent-management | 智能体管理 | admin |
| 5 | mcp-management | MCP 管理 | admin |
| 6 | tool-management | 工具管理 | admin |
| 7 | skill-management | Skill 管理 | admin |
| 8 | task-scheduler | 运维任务 | admin |
| 9 | （已删除，见消息设置父菜单章节；中间层 task-scheduler.email-settings 于 2026-07-31 二次调整删除） | — | — |
| 10 | messaging | 消息设置 | admin |

前端 `web/Agent/src/components/UserSettingsDialog.vue` 的 `NAV_MENU_METADATA` 对象
key 声明顺序与上表一致；2026-07-23 调整后，`email-settings` 不再是前端一级壳，
其 key 改为 `task-scheduler.email-settings` 与后端注册表对齐；`MENU_CHILD_PREFIX`
兼容映射已删除。

### 数据模型 `user_menu_acl`

| 字段 | 类型 | 说明 |
|---|---|---|
| `id` | SERIAL PK | 自增 |
| `user_id` | INT FK→users CASCADE | 授权目标用户 |
| `menu_id` | VARCHAR(64) | 菜单注册表里的 id |
| `created_at` | TIMESTAMP | DEFAULT NOW() |
| `created_by_user_id` | INT FK→users SET NULL | 授权人（删除授权人不影响授权） |

- UNIQUE `(user_id, menu_id)` 防止重复授权
- 索引：`(user_id)` / `(menu_id)`

### 服务层 MenuPermissionService
- 位置：`app/shared/utils/auth/menu_permission_service.py`
- 6 个接口：`preload_all` / `get_visible_menu_ids` / `get_user_grants` / `grant` / `revoke` / `replace`
- 内存缓存：`Dict[int, Set[menu_id]]`
- DB 双写：`grant` / `revoke` / `replace` 都同步
- 降级：db=None 时 admin 全量，普通用户仅 `['profile']`（fail-secure）

### API 端点
- `GET  /api/admin/permissions/menu-catalog` —— 全量注册表
- `GET  /api/admin/permissions/users/{id}/grants` —— 查用户授权
- `PUT  /api/admin/permissions/users/{id}/grants` —— 全量覆盖保存
- `/api/auth/login` + `/api/auth/validate` 响应新增 `visible_menus` 字段

全部受 `require_admin` 守护（除 `/api/auth/*`）。

### 前端组件
- `UserSettingsDialog.vue`：`navItems` 由 `visibleMenus` prop 驱动（不再硬编码 `isAdmin`）
- `MenuPermissionManager.vue`：左侧人员选择 + 右侧树形 checkbox（先选人再选菜单）
- `App.vue` / `Sidebar.vue`：透传 `visible_menus`

### 菜单修改示例：邮件设置

菜单 id 保持稳定（`task-scheduler.email-settings`），2026-07-23 起升级为独立一级菜单，显示名为“邮件设置”：

```python
MenuItem(id="task-scheduler.email-settings", level=1,
         parent_id=None,
         label="邮件设置", icon_key="mail", sort_order=9, required_role="admin"),
```

前端模板同步：`task-scheduler.email-settings` 作为独立顶级 tab 渲染邮件设置组件，不再挂在「运维任务」下。

授权数据全自动保留（因 id 不变）。

### 消息设置父菜单（2026-07-31 新增，2026-07-31 二次调整为 channel 三级结构）

为支持未来新增钉钉/飞书/企业微信等多通道消息管理，引入新一级菜单 `messaging`（「消息设置」）。

**结构**（2026-07-31 二次调整后，最终态）：

```
messaging (level=1, sort_order=10, icon_key='message')
  └── messaging.email (level=2, sort_order=1, label='邮件设置', icon_key='mail')  ← channel 级
        ├── task-scheduler.email-settings.server    (level=2, parent_id='messaging.email', sort_order=1)
        ├── task-scheduler.email-settings.policies  (level=2, parent_id='messaging.email', sort_order=2)
        └── task-scheduler.email-settings.test      (level=2, parent_id='messaging.email', sort_order=3)
```

**关键设计**（最终态）：

- **id 全程未改**：`task-scheduler.email-settings.{server,policies,test}` 三个 id 全部保持稳定，老 ACL 全自动保留
- **中间层删除**（2026-07-31 二次调整）：原 `task-scheduler.email-settings` 中间层在 UI 中"看不见"却参与 ACL，体验反直觉 → 删；新增 channel 级 id `messaging.email`
- **三级结构**：messaging 顶级 → messaging.email channel → 三个孙 tab（孙 tab 仍为 level=2，靠 `parent_id` 指向 channel 区分层级；数据模型只支持 2 级 `level` 字段，但允许 channel 作为孙级的父级）
- **端点 ACL 契约零变化**：后端 router 仍以 `task-scheduler.email-settings.{server,policies,test}` 作为 `require_admin_or_menu_acl` key，零改动
- **channel `messaging.email` 自身可独立 ACL 授权**：admin 在「权限管理 → 菜单管理」可独立勾选它；隐藏邮件通道时只取消勾选 channel 即可

**前端 `isMenuVisible` alias 映射**（`UserSettingsDialog.vue::PARENT_TO_CHILDREN_ALIAS`）：

- 历史约定：子菜单 id 形如 `${parent}.xxx`，前缀匹配天然让父级可见
- `messaging.email` 子菜单 id 以 `messaging.` 开头 → messaging 顶级的前缀匹配天然让父级可见，无需列在 alias
- 但孙 tab id `task-scheduler.email-settings.*` 不以 `messaging.` 开头 → 必须显式列在 messaging 的 alias
- 类似地，孙 tab id 不以 `messaging.email.` 开头 → 必须显式列在 messaging.email 的 alias
- 解决方案：在 `isMenuVisible` 增加 alias 映射：
  ```js
  PARENT_TO_CHILDREN_ALIAS = {
    messaging: [
      'messaging.email',                                          // 冗余（messaging.email 已天然匹配），保留作显式声明
      'task-scheduler.email-settings.server',
      'task-scheduler.email-settings.policies',
      'task-scheduler.email-settings.test',
    ],
    'messaging.email': [
      'task-scheduler.email-settings.server',
      'task-scheduler.email-settings.policies',
      'task-scheduler.email-settings.test',
    ],
  }
  ```
- 未来添加新通道（如 `messaging.dingtalk`），子菜单 id 推荐用 `messaging.<channel>.xxx` 形式，可继续走前缀匹配

**前端 template 渲染**（messaging 顶级 tab）：

- 顶级 tab 挂载点：`v-if="isVisibleTab('messaging') && activeTab === 'messaging'"`
- 内部加 `.sub-tabs` 容器（参考 `permission-management` 的 sub-tab 模式）：
  ```html
  <div class="sub-tabs" data-testid="messaging-sub-tabs">
    <button class="sub-tab" :class="{ active: activeEmailChannel === 'messaging.email' }"
            @click="switchEmailChannel('messaging.email')">邮件设置</button>
  </div>
  <div v-show="activeEmailChannel === 'messaging.email'" class="tab-fill-wrapper">
    <EmailSettingsManager :visible-menus="visibleMenus" :is-admin="isAdmin" />
  </div>
  ```
- 状态：`activeEmailChannel = ref('messaging.email')` + `switchEmailChannel(channelId)` 方法
- 仅 1 个 channel 时仍保留 sub-tab 容器（视觉一致性 + 未来加 dingtalk/feishu 时零改动）
- `EmailSettingsManager.vue` 内部仍管理 server/policies/test 三个内部 tab（按 id 授权过滤）
- 组件内「邮件」字面量保留（功能是 SMTP 邮件发送，描述真实职责）

**`MenuPermissionManager.vue` 三级树形渲染支持**（2026-07-31 二次调整升级）：

- 原 `getChildren(parentId)` 仅支持 2 级（`level=2 && parent_id`）
- 升级：`parentState` / `toggleParent` / `toggleChild` 通用化为任意级（递归统计"所有后代"）
- 新增 `getGrandchildren(channelId)` / `toggleGrandchild(grandchildId, channelId, parentId, checked)` / `grandchildState(gcId, channelId)`
- 模板用 3 级 `v-for` 嵌套手写（不引入组件递归，避免过度工程化）
- CSS：`.menu-checkbox-row.grandchild`（缩进 + 字号缩）+ `.grandchildren`（虚线左边框视觉分组）

### 邮件设置二级菜单（2026-07-23 新增，2026-07-31 二次调整 parent_id）

`EmailSettingsManager.vue` 内部三个 Tab 注册为可独立授权的二级菜单：

| sort_order | id | label | parent_id（最终态） |
|---|---|---|---|
| 1 | task-scheduler.email-settings.server | 服务器配置 | messaging.email |
| 2 | task-scheduler.email-settings.policies | 发送策略 | messaging.email |
| 3 | task-scheduler.email-settings.test | 测试发送 | messaging.email |

**2026-07-31 二次调整**：`parent_id` 从 `task-scheduler.email-settings`（中间层）改为 `messaging.email`（channel 级）。id 全程未变，端点 ACL 契约零影响。

注册后 `MenuPermissionManager.vue` 按三级树形渲染（见上节「消息设置父菜单」），admin 可按 Tab 粒度授权（例如只授权「服务器配置」+「发送策略」）。

- 父级（messaging）勾选 → 自动勾选全部子级（沿用 `toggleParent` 既有行为，2026-07-31 升级支持三级联动）
- 子级任一可见 → 父级 `messaging.email` 可见（`UserSettingsDialog.vue::isMenuVisible` alias 映射，孙 tab id 不以 `messaging.email.` 开头）
- 孙级任一可见 → 父级 `messaging` 顶级可见（前缀匹配 + alias 映射）
- 数据库无迁移；现有授权记录不受影响

### 运维任务二级菜单（最终态）

`TaskSchedulerManager.vue` 内部四个 Tab 注册为可独立授权的二级菜单，父级 `task-scheduler`（sort_order=8）：

| sort_order | id | label | parent_id |
|---|---|---|---|
| 1 | task-scheduler.scheduled | 定时任务 | task-scheduler |
| 2 | task-scheduler.script-scan | 脚本扫描 | task-scheduler |
| 3 | task-scheduler.script-inventory | 脚本扫描入库 | task-scheduler |
| 4 | task-scheduler.api-config | API接口配置 | task-scheduler |

注册后 `MenuPermissionManager.vue` 自动按 `level=2 && parent_id=...` 渲染子 checkbox，
admin 可按 Tab 粒度授权。前端 `TaskSchedulerManager.vue::TAB_MENU_IDS` 将每个 Tab 常量映射到对应的 menu_id，`availableTabs` 计算按 ACL 过滤：

- admin：返全量
- 普通用户：仅保留 `TAB_MENU_IDS[tab] ∈ visible_menus` 的项

### 端点 ACL 粒度对齐（2026-07-24 修复）

**问题**：ZYP 用户已被授权子菜单 `task-scheduler.email-settings.policies`，
但调用 `GET /api/admin/email/emailable-users` 仍返回 403 Forbidden
（响应体 `{"detail":"权限不足，需要菜单 task-scheduler.email-settings 授权"}`）。

**根因**：`emailable-users` 端点（`app/routers/email_admin_router.py`）
要求 `require_admin_or_menu_acl('task-scheduler.email-settings')`（父菜单 ACL），
而 ZYP 的 ACL 集合只含子菜单 `policies`，不含父菜单。按设计意图
（父菜单 ACL 控制一级菜单入口可见性、子菜单 ACL 控制 tab 可见性与端点访问），
端点应使用子菜单 ACL 而非父菜单 ACL。

**修复**：将该端点 ACL 要求改为
`require_admin_or_menu_acl('task-scheduler.email-settings.policies')`，
使其与所服务的「发送策略」tab ACL 对齐。父菜单 `task-scheduler.email-settings`
的语义（控制「邮件设置」一级入口可见性）不变。

**端点 ACL 粒度原则**：
- 端点 ACL 必须与所服务的 tab 粒度对齐（子菜单端点对齐子菜单）
- 父菜单 ACL 只用于一级入口可见性，不直接作为端点守护
- 避免「已授权子菜单但调端点仍 403」的不一致

**回归测试**（`app/tests/routers/test_email_admin_router.py`）：
- `test_normal_user_acl_policies_passes_emailable_users`：ACL 含 policies 子菜单 → 200
- `test_normal_user_acl_parent_only_not_enough_for_emailable_users`：ACL 仅含父菜单（无 policies）→ 403
  （防止后续误把 ACL 改回父菜单而无人察觉）

**其他邮件设置端点的 ACL 粒度（保持不变）**：
- `server-config` / `server-config/test` → `email-settings.server`
- `policies` CRUD → `email-settings.policies`
- `test` / `send-by-policy` → `email-settings.test`

### API 接口配置 ACL 双重门（2026-07-24 落地）

`app/routers/api_config_router.py` 从 Router 级 `require_admin` 改造为每 endpoint
挂载 `Depends(require_admin_or_menu_acl('task-scheduler.api-config'))`。

**契约**：被授予 `task-scheduler.api-config` 菜单 ACL 的普通用户可完整访问
`/api/admin/api-configs/*` 全部 endpoint（读 / 写 / 删 / 发送 / 查历史）；
admin 角色绕过 ACL 直接放行；普通用户未授权 → 403
（响应体 `{"detail":"权限不足，需要菜单 task-scheduler.api-config 授权"}`）。

**覆盖 endpoint**（共 8 个）：
- `GET /tree`
- `POST /nodes`
- `PUT /nodes/{node_id}`
- `DELETE /nodes/{node_id}`
- `GET /nodes/{node_id}/config`
- `PUT /nodes/{node_id}/config`
- `POST /nodes/{node_id}/send`
- `GET /nodes/{node_id}/runs`

**参照实现**：`app/routers/task_scheduler_router.py`
（`task-scheduler.scheduled` ACL 双重门）。

**回归测试**（`app/tests/routers/test_api_config_router.py`）：
- `test_normal_user_no_acl_get_tree_403`：ACL 空 → 403 + 错误信息含 `task-scheduler.api-config`
- `test_normal_user_acl_api_config_passes_get_tree`：ACL 含子菜单 → 200
- `test_normal_user_acl_parent_only_still_blocked`：ACL 仅含父菜单 → 403
- `test_admin_bypasses_acl_for_api_config`：admin 角色 + ACL 空 → 200
- `test_normal_user_acl_can_send_request`：ACL 含子菜单 + 写操作 → 200

### 前端挂载门控（2026-07-23 修复普通用户打开 dialog 报 403）

**问题**：普通用户被授权了某个二级菜单（例如 ZYP 被授权 `task-scheduler`）后，打开「用户设置」对话仍会触发三个 admin-only 接口（`/api/admin/permissions/menu-catalog`、`/api/users`、`/api/admin/agents`）并被后端 `require_admin` 返回 403。

**根因**：`UserSettingsDialog.vue` 顶级 tab 切换用 `v-show`（仅切 display，不卸载子组件），导致 `MenuPermissionManager` / `AgentManager` 等 admin-only 子组件在 dialog 首次打开时即被挂载，`onMounted` 立即触发 admin-only 数据请求。

**修复契约**（两段防御）：
1. **template 层（前端主防线）**：admin-only 顶级 tab 子组件从 `v-show` 改为 `v-if="isVisibleTab(tabId) && activeTab === tabId"`，按 `visibleMenus` 决定是否挂载。
   - `isVisibleTab(tabId)`：`isAdmin.value || props.visibleMenus.includes(tabId) || props.visibleMenus.some(m => m.startsWith(tabId + '.'))`
2. **script 层（fail-safe 兜底）**：所有 admin-only 子组件新增 `defineProps({ isAdmin: Boolean })`，`onMounted` 内 `if (!props.isAdmin) return`。即便父组件漏挂 v-if，本组件也不会触发 admin-only 请求。
   - 涉及组件：`MenuPermissionManager` / `AgentManager` / `TaskSchedulerManager` / `McpServerManager` / `ToolManager` / `SkillManager` / `EmailSettingsManager`
   - **父组件必须传 `:is-admin="isAdmin"` prop** —— 这是修复成败的关键契约。漏传会导致 admin 用户打开 dialog 时 tab 右侧空白（onMounted 早退）。

**反模式**：不能把后端改为「普通用户也能访问 menu-catalog 等 admin-only 端点」——这是 admin-only 接口，降低鉴权等级是安全反模式。

**真实环境验证要点**（2026-07-23）：
- 早期一版只改了 3/7 个子组件的 prop 注入，`McpServerManager` / `AgentManager` / `ToolManager` / `EmailSettingsManager` 漏传，导致 admin 用户打开 dialog 后这些 tab 右侧空白。修复后所有 7 个子组件统一传 `:is-admin="isAdmin"`。
- vitest 单测通过 ≠ 真实浏览器通过。第一次提交时 vitest 测试全绿，但用户在真实 vite dev 环境立刻发现 admin tab 空白。教训：UI 集成 bug 必须用真实浏览器/HMR 验证，不能只信单元测试。

**TaskSchedulerManager 子 tab 拦截（2026-07-23 第二轮修复）**：

第一次修复在 `TaskSchedulerManager` 的 `onMounted` 加了 fail-safe，但普通用户被授权 task-scheduler 顶级 tab 后，**点击「服务器扫描入库」子 tab 仍会触发 `/api/admin/devops-servers` → 403 → 红色 banner「服务器列表加载失败」**。

根因：`TaskSchedulerManager` 是一个 **admin 功能聚合体**，它内部的 4 个子 tab（编辑任务/服务器扫描入库/脚本扫描入库/API接口配置）**全部依赖 admin-only 数据源**。`onMounted` 拦截不住 `switchTab` / watch 触发的 `loadDevopsServers` / `loadScripts` / `loadApiConfigTree`。

修复（两段防御）：
1. **数据加载入口 fail-safe**：在 `loadDevopsServers` / `loadScripts` / `loadApiConfigTree` 函数顶部都加 `if (!props.isAdmin) return`。
2. **template 整体权限占位**（UX 改进）：非 admin 用户直接渲染 `v-if="!isAdmin"` 的「此功能仅对管理员开放」占位（data-testid=`task-scheduler-no-permission`），不再显示会触发 403 的子 tab 按钮。模板外层 `v-else` 渲染原有内容。

**验证**：前端 vitest 覆盖：
- `UserSettingsDialog.user-role-no-403.spec.js`：普通用户打开 dialog 不发起 admin-only 请求；admin 逐个点击 8 个顶级 tab 后**所有 7 个 admin-only 数据 URL 都被调用**（回归保护 prop 漏传 bug）
- 各 admin-only 子组件 spec 已统一传 `isAdmin: true` 测试 fixture（防御性契约）

### 按 required_role 过滤菜单可见性（2026-07-23 第三轮修复，2026-07-24 收口）

**最终契约（2026-07-24 统一）**：

`required_role` 与 `user_menu_acl` 的职责边界如下，二者不是冲突而是正交：

- `required_role`（registry 元数据）：菜单的**声明式意图**——标记菜单"业务语义上是 admin 范畴"，用于：
  1. `MenuPermissionService.get_visible_menu_ids` 在普通用户路径上**过滤可见性**（即便 ACL 误授权也不可见）；
  2. 前端 `UserSettingsDialog.navItems` 派生 tab 渲染。
- `user_menu_acl`（数据库 ACL）：菜单的**端点访问授权**——通过 `require_admin_or_menu_acl(...)` 守卫路由端点，决定"已可见菜单下哪些端点允许调用"。

**最终统一行为**：

| 角色 | 可见性（菜单树） | `GET /api/admin/devops-servers` | `scan/detail/delete` |
|---|---|---|---|
| admin | 全量 enabled | ✅ 通过（bypass ACL） | ✅ 通过 |
| 普通用户 + `task-scheduler.server-management` ACL | 不可见（required_role=admin 过滤） | ✅ 通过（ACL 端点授权） | ❌ 403 |
| 普通用户无 ACL | 不可见 | ❌ 403 | ❌ 403 |

**核心规则**：
- 菜单 ACL 控制**可见性**（`required_role != "admin"` 才允许授权给普通用户）与**ACL 端点访问**（被授权后即可调用）。
- `required_role='admin'` 菜单的普通用户可见性**始终为空**；但**该菜单下若有端点声明** `require_admin_or_menu_acl(<menu_id>)` **的非 admin-only 端点**（例如 `GET /api/admin/devops-servers`），admin 仍可显式授权给普通用户调用，前端通过 `visible_menus` 派生链路默默拦截 tab 渲染，但不影响端点访问——这是 admin 主动赋能场景的合法路径。
- `scan_and_upsert` / `get_server_detail` / `delete_server` 仍只挂 `Depends(require_admin)`，与可见性无关。

**反模式警示**：不能简单地把后端改为「让 admin 看到所有菜单后用前端 ACL 渲染」——ACL 是 fine-grained 权限，required_role 是 coarse-grained 角色权限，二者职责不同。混用会导致：
1. 误授权 admin-only 菜单给普通用户 → 组件挂载后触发 admin-only 请求 → 403
2. 前端需要单独维护「哪些菜单 admin 才能看见」的清单（散落多处难一致）

**修复**：
- `MenuPermissionService.get_visible_menu_ids`：普通用户路径增加 `non_admin_only = [m for m in enabled if m.required_role != "admin"]` 过滤层，再与 ACL 取交集。即便 ACL 里错误地写入了 admin-only 菜单，service 也会过滤掉。
- `core.menu_registry.get_visible_for_user`：同样的修复。

**效果**：
- admin：返全量 enabled（绕过 ACL 和 required_role 检查）
- 普通用户：仅可见 `required_role != "admin"` 且 ACL 授权且 enabled 的菜单
- 前端 `UserSettingsDialog.navItems` 跟着 visible_menus 自然不渲染 admin-only 顶级 tab
- 前端 `UserSettingsDialog.isVisibleTab` 仍是双层兜底（基于 props.visibleMenus）

**测试**：
- `test_get_visible_menu_ids_normal_excludes_admin_only_even_if_granted`：ZYP（普通用户）ACL 里授权了 task-scheduler 等 admin-only 菜单 → service 返回的 visible_menus 不包含这些菜单
- `test_get_visible_menu_ids_admin_still_returns_admin_only`：admin 仍能看到全部
- 更新 `test_get_visible_menu_ids_normal_returns_granted_intersect_enabled`：反映新语义（admin-only 不出现在结果里）

## 用户服务器配置管理（2026-07-24 新增）

「运维任务」一级菜单下新增第 5 个子 tab —— **「服务器管理」**（id=`task-scheduler.server-management`，admin only）。每个登录用户维护一个**自己的私有**服务器配置 tree，可组织"关心的服务器"。

### 数据模型：user_server_nodes / user_server_configs

数据库表结构（`app/migrations/init_all_tables.sql` 第 22 段）：

- `user_server_nodes`：
  - `id` / `parent_id`（多级 folder）/ `node_type`（`folder` / `server`，CHECK 约束）
  - `name` / `sort_order`（同级排序）
  - `source_devops_server_id`（**server 节点必须**指向 `devops_servers.id`；folder 必须为 NULL；CHECK 约束）
  - `created_by_user_id`（**归属字段**）
  - `created_at` / `updated_at`
  - 索引：`idx_user_server_nodes_parent` / `idx_user_server_nodes_created_by_user_id` / `idx_user_server_nodes_source_devops_server_id`
- `user_server_configs`：
  - `node_id`（FK，UNIQUE）/ `notes`（预留字段，第一版不写入）
  - 第一版仅做占位表，详情完全从 `devops_servers` JOIN 读取

### 多对多关系实现

底层 `devops_servers` 共享（admin 通过「服务器扫描入库」维护），用户私有层 `user_server_nodes` 通过 `source_devops_server_id` 共享引用：

```
devops_servers (admin 管理的共享资源)
       ▲
       │ source_devops_server_id (FK ON DELETE CASCADE)
       │
user_server_nodes (node_type='server' 的行，每个用户导入时生成一行)
       ▲
       │ created_by_user_id 区分归属 → 多对多：用户 × devops_servers
```

实际行为：两个用户可"添加"同一台 devops_servers；用户 A 看到的 server 节点和用户 B 看到的 server 节点是独立的 user_server_nodes 行（同 source_devops_server_id），但 server 详情（business_name / server_type / whitelist / inspection_script 等）通过 JOIN 实时从 devops_servers 读，**共享引用不复制内容**。

### 共享引用 + OwnershipScope 策略

- **共享引用**：server 节点**不存**任何业务字段（ip / port / 账号 / 密码 / 白名单 / 巡检脚本），全部从 `devops_servers` JOIN 读
  - 删除 devops_servers 一行时通过 `ON DELETE CASCADE` 自动清理所有引用它的 user_server_nodes 行
  - devops_servers 的任何修改（重新扫描、白名单调整）实时反映到所有用户的详情
- **OwnershipScope**：`admin` 透传全量；`普通用户` 仅看 `created_by_user_id == self.user_id` 的节点；父节点不可见时**提升为根**（`parent_id` 重写为 None），不泄露隐藏父节点的存在

### 后端 service：`app/shared/utils/user_server_service.py`

类 `UserServerService(db, devops_server_service=None)`，结构对标 `ApiConfigService`：

- `preload_all()`：启动时把全部节点载入内存缓存
- `list_nodes(scope)`：返回扁平节点列表，按 scope 过滤；不可见父节点时 parent_id 提升为 None
- `create_node(parent_id, node_type, name, scope, source_devops_server_id=None)`：folder 必须 source_id=None；server 必须 source_id 指向已存在的 devops_servers；父节点必须可见且为 folder 类型
- `update_node(node_id, scope, name=None, parent_id=None, sort_order=None)`：含父节点成环检测
- `delete_node(node_id, scope)`：folder 非空时抛 `UserServerNodeNotEmptyError`（路由层映射 400）
- `get_node_config(node_id, scope)`：folder 节点返元数据；server 节点 JOIN devops_servers 取 7 字段白名单（business_name / server_type / updated_at / whitelist / inspection_script / inspection_parser / inspection_fields）；**绝不含** ip / port / 账号 / password
- `import_from_devops_servers(parent_id, business_names, scope)`：批量把 devops_servers 导入到用户 tree；按 business_name 匹配 devops_servers；同用户同 parent 下 dedup（计入 skipped）

### 后端 router：`app/routers/user_server_router.py`

- 前缀：`/api/admin/user-servers`（与 `devops_server_admin_router` 同级 admin 路径）
- 全部使用 `Depends(require_admin_or_menu_acl('task-scheduler.server-management'))`
- 端点：
  - `GET /tree` → `{"nodes": [...]}`
  - `POST /nodes`（创建 folder / server）→ 201
  - `PUT /nodes/{id}`（重命名 / 移动 / sort_order）
  - `DELETE /nodes/{id}`（folder 非空 → 400）
  - `GET /nodes/{id}/config`（节点详情）
  - `POST /import`（批量导入 devops_servers）→ `{imported, skipped, failed, node_ids}`

### 前端组件

- `web/Agent/src/components/UserServerManager.vue`：左右布局（左侧 tree + 搜索 + 「+ 新建」下拉按钮 + inline 重命名/删除；右侧只读详情）
  - 「+ 新建」菜单三项：新建文件夹（可用）/ 新建服务器配置（**disabled** + 提示「该功能暂未开放」——按需求预留）/ 导入已有配置（弹出 ImportServerDialog）
  - server 节点详情只展示 7 字段白名单（无 ip/port/账号/密码），与「服务器扫描入库」详情契约一致
  - 提供 `isAdmin` prop 接收父组件的 admin 状态
  - 布局契约：根容器通过 `flex: 1; min-width: 0` 填满「服务器管理」Tab，左侧 tree 保持 320px，右侧详情占据剩余宽度并在自身内部滚动。
  - 布局回归测试：`UserServerManager.spec.js` 通过 SFC 样式契约断言根容器必须填满父级剩余宽度，详情区必须允许 flex 收缩。
- `web/Agent/src/components/ImportServerDialog.vue`：导入弹窗（顶部搜索 + label 卡片网格 + 全选/确认/取消）
  - 复用现有 `fetchDevOpsServers()` 拉取 devops_servers 脱敏列表
  - 调用 `importDevopsServers(parentId, businessNames)` 批量创建

### 菜单 id

`task-scheduler.server-management`（level=2, parent_id=task-scheduler, sort_order=5, required_role=admin），id 终身不变。

### 端点 ACL 矩阵（2026-07-24 收口）

`app/routers/devops_server_admin_router.py` 最终授权契约：

| 端点 | 守卫 | admin | 普通用户 + `task-scheduler.server-management` ACL |
|---|---|---|---|
| `GET /api/admin/devops-servers` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ |
| `POST /api/admin/devops-servers/scan` | `require_admin` | ✅ | ❌ 403 |
| `GET /api/admin/devops-servers/{server_id}` | `require_admin` | ✅ | ❌ 403 |
| `DELETE /api/admin/devops-servers/{server_id}` | `require_admin` | ✅ | ❌ 403 |

`app/routers/user_server_router.py` 端点授权契约（2026-07-26 调整）：

| 端点 | 守卫 | admin | 普通用户 + `task-scheduler.server-management` ACL | 普通用户 + 仅 `task-scheduler.scheduled` |
|---|---|---|---|---|
| `GET /api/admin/user-servers/tree` | JWT-only（仅读） | ✅ | ✅ | ✅ |
| `POST /api/admin/user-servers/nodes` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ | ❌ 403 |
| `PUT /api/admin/user-servers/nodes/{id}` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ | ❌ 403 |
| `DELETE /api/admin/user-servers/nodes/{id}` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ | ❌ 403 |
| `GET /api/admin/user-servers/nodes/{id}/config` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ | ❌ 403 |
| `POST /api/admin/user-servers/import` | `require_admin_or_menu_acl('task-scheduler.server-management')` | ✅ | ✅ | ❌ 403 |

**2026-07-26 GET /tree 放宽为登录态**：跟随 2026-07-26 `GET /api/admin/scripts` 先例。`UserServerService.list_nodes` 已按 `OwnershipScope` 过滤，普通用户仅见自己的节点；server 节点附带 `business_name` / `server_type`（由 `source_devops_server_id` 关联 devops_servers，内存 join 零 DB IO），供「编辑任务」表单 server_list 候选直接复用——无需前端再 join 公开 devops 列表。写端点 ACL 不变，避免普通用户误删或误改共享资源。

**为什么 GET 列表端点放开**：admin 通过「用户服务器配置管理」授权该 ACL 后，授权用户需读取 devops_servers 库（脱敏列表）来填充 ImportServerDialog 的可选项；放开 GET 列表端点是该 UX 闭环的必备前提。scan / detail / delete 保持 admin-only，避免普通用户误删或误改共享资源。

**GET /tree 放宽为登录态的另一动机（2026-07-26）**：普通用户编辑定时任务时，server_list 控件候选需从 user-server tree 拉取；若端点强制要求 `task-scheduler.server-management` ACL，编辑任务链路需要 admin 同时授权两个菜单才能使用。放宽为登录态后，OwnershipScope 保证普通用户只看自己的节点，UX 闭环。

### 与「服务器扫描入库」tab（`task-scheduler.script-scan`）的差异

- 「服务器扫描入库」：admin 全局管理 `devops_servers` 行（扫 YAML 入库 / 删除），全表
- 「服务器管理」：每个用户私有视图（`user_server_nodes` tree），按 created_by_user_id 隔离；server 节点共享引用底层 devops_servers
- 前者负责"哪些服务器存在"；后者负责"我关心哪些服务器、怎么组织"

### 智能体访问权限（2026-07-24 新增，B 方案）

`permission-management` 一级菜单下新增二级 Tab `permission-management.agent-access`，
数据源从 `users.allowed_agents` JSONB 字段切换到独立的 `user_agent_acl` 表，
完全 mirror `user_menu_acl` 模式。

| 表 / 服务 | 字段 / 方法 | 说明 |
|---|---|---|
| `user_agent_acl` | user_id, agent_name, created_at, created_by_user_id | UNIQUE (user_id, agent_name)，索引 user_id / agent_name |
| `AgentPermissionService` | preload_all / get_user_agent_grants / get_user_agent_grants_sync / get_visible_agents / grant / revoke / replace | in-memory cache + DB 双写（fail-secure：db=None 时 admin 旁路，普通用户返 []） |
| `app/routers/agent_permission_router.py` | GET /api/admin/permissions/agents/catalog, GET /api/admin/permissions/agents/users/{id}/grants, PUT /api/admin/permissions/agents/users/{id}/grants | 全部 require_admin 守护 |
| `app/migrations/init_all_tables.sql` § 23 | user_agent_acl DDL | 一次性建表 + 启动时迁移 |

启动迁移（lifespan 阶段）：
```sql
INSERT INTO user_agent_acl (user_id, agent_name)
SELECT u.id, a.agent_name
FROM users u, jsonb_array_elements_text(COALESCE(u.allowed_agents, '[]'::jsonb)) AS a(agent_name)
ON CONFLICT (user_id, agent_name) DO NOTHING;
```
幂等（ON CONFLICT DO NOTHING），被显式删除的字段不会回流。

前端聊天组件（按角色分流）：
- `app/shared/routers/auth_router.py::_compute_allowed_agents`：
  - admin：返回 `[]`（前端 InputBox 与 isAdmin 旁路配合，全量可见）
  - 普通用户：从 `agent_permission_service.get_user_agent_grants_sync(user_id)` 读 ACL
  - service 不可用或 ACL 为空：fallback 到 `users.allowed_agents` 字段（迁移兜底）
- `App.vue` 透传 `:is-admin="currentUser.role === 'admin'"` 给 InputBox
- `InputBox.vue` 加 `isAdmin` prop + `filteredAgents` / `suggestionAgents` 按角色分流：
  - admin：全量智能体（绕过 ACL）
  - 普通用户：按 `allowedAgents` 过滤（来自后端 user_agent_acl）

前端菜单管理 UI：
- `UserSettingsDialog.vue` `permission-management` 一级 Tab 加 sub-tabs 切换：
  - 菜单管理（保留 MenuPermissionManager）
  - 智能体访问（新增 AgentAccessManager）
- `AgentAccessManager.vue`：左选人 → 右勾选智能体，debounce 300ms 自动保存
- 「用户管理 → 编辑用户」表单「可选智能体」复选块整体移除；提交 payload 不再带 `allowed_agents`

`users.allowed_agents` 字段保留（被动字段，迁移兼容），前端不再写入；服务优先读 `user_agent_acl`。

测试覆盖：
- 后端 `app/tests/routers/test_agent_permission_router.py`：11 个 P0/P1 测试覆盖 admin-only 守卫、catalog / grants 读写、PUT 失败 500
- 后端 `app/tests/shared/utils/auth/test_agent_permission_service.py`：22 个 P0/P1 测试覆盖 db=None 降级 / preload / grant / revoke / replace / 迁移函数
- 前端 `web/Agent/.../AgentAccessManager.spec.js`：8 个测试覆盖 catalog / users / 选人 / 勾选 / debounce / 全选 / 清空 / 搜索
- 前端 `web/Agent/.../UserSettingsDialog.user-form-no-agents.spec.js`：3 个防回归测试，验证表单中无 agent-checkbox-list 元素 + permission-management 两子 Tab 切换
- 前端 `web/Agent/.../InputBox.command.spec.js`：新增 2 个 isAdmin 兼容测试，验证 admin 走全量 / 普通用户 fail-secure 返 []

### zyp 用户越权修复（2026-07-24）

现象：zyp 用户（id=2，role=user）在「智能体访问」Tab 授权为空、`user_agent_acl` 无记录、`users.allowed_agents` 残留 `["project"]`，但登录后仍可使用 `project` 智能体。

根因（auth_middleware 链路）：`Safety.py::JWTAuth.authenticate()` 在注入 `request.state.allowed_agents` 时，**直接读 `users.allowed_agents` JSONB 旧字段**，从未走 `user_agent_acl`。`agent_router.list_agents` 与 `agent_router.chat` 又以 `request.state.allowed_agents` 为权威，导致整个新 ACL 系统形同虚设：admin 在「智能体访问」Tab 写 `user_agent_acl`，但生产链路不读。

修复：
| 文件 | 变更 |
|---|---|
| `app/shared/utils/auth/Safety.py` | `authenticate()` 中 `request.state.allowed_agents` 数据源从 `users.allowed_agents` JSONB 字段切换到 `agent_permission_service.get_user_agent_grants_sync(user_id)`；admin 返 `[]` 走 bypass；service 不可用时返 `[]`（fail-secure，不再 fallback 到旧字段） |
| `app/routers/agent_router.py` | `chat` 与 `list_agents` 加 `role == 'admin'` bypass，避免 admin 被踢出 |
| `app/shared/routers/auth_router.py` | `LoginResponse` 加 `allowed_agents` 字段；`login` / `login_api` 透传 |
| `app/migrations/2026_07_24_clear_users_allowed_agents_for_non_admin.sql` | 数据修复：`UPDATE users SET allowed_agents = '[]' WHERE role != 'admin'`，清掉历史 JSONB 残留 |
| `app/tests/shared/test_safety.py` | `test_authenticate_sets_allowed_agents` 改造为 mock agent_permission_service；新增 `test_authenticate_admin_role_empty_allowed_agents` 与 `test_authenticate_service_unavailable_fail_secure` |
| `app/tests/routers/test_agent_router.py` | `test_list_agents_empty_allowed_returns_empty` / `test_list_agents_filters_by_allowed_agents` / `test_chat_forbidden_agent_returns_403` 改用 testuser；新增 `test_list_agents_admin_role_returns_all` / `test_chat_admin_role_bypasses_allowed_agents` / `test_chat_normal_user_empty_allowed_agents_returns_403` |

执行时机：P0 代码修复完成后立即执行清空 SQL；admin 用户 bypass 设计确保清空操作不影响 admin。

