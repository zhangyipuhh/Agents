# 前端架构

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## 前端架构（web/Agent）

`web/Agent/` 是基于 Vite + Vue 3 的多入口 SPA，对外提供三套独立页面（主 Agent、知识库、门户），共享同一套组件、工具函数与设计 token。

### 技术栈

- **核心框架**：Vue 3.4 + Vite 5（JavaScript，无 TypeScript）
- **UI 渲染**：marked（Markdown）+ highlight.js（代码高亮）+ @vue-office/{docx,excel,pdf,pptx}（Office 文档预览）
- **测试**：Vitest 4 + @vue/test-utils + happy-dom
- **包管理**：npm；脚本 `dev` / `build` / `preview` / `test` / `test:watch` / `test:coverage`
- **关键依赖**：vue-demi（@vue-office 的 Vue 2/3 兼容垫片）

### 多入口与挂载

`vite.config.js` 的 `build.rollupOptions.input` 显式声明三个 HTML 入口，分别对应不同的业务场景：

| 入口文件           | 挂载组件                                          | 部署路径       | 用途                                                                                                 |
| ------------------ | ------------------------------------------------- | -------------- | ---------------------------------------------------------------------------------------------------- |
| `index.html`     | `App.vue`（`src/main.js`）                    | `/`          | 主聊天界面 + router-view 承载三个一级路由（/、/knowledge、/ops-console）                                                  |
| `knowledge.html` | `KnowledgeApp.vue`（`src/knowledge-main.js`） | `/knowledge` | 知识库独立页（文件侧栏 + 聊天；保留独立入口供 PortalApp iframe 嵌入）                                                                      |
| `portal.html`    | `PortalApp.vue`（`src/portal-main.js`）       | `/portal`    | 门户导航（顶部蓝色导航栏 + iframe 嵌入 `/knowledge`）                                              |
| `login.html`     | `LoginView`（`src/login-main.js`）            | `/login`     | 登录页统一入口（`App.vue` / `PortalApp.vue` 不再内联渲染 `LoginView`；由 `/login` 唯一承载） |

三个入口共享 `src/components`、`src/utils`、`src/styles`，构建后产出三个独立的 JS Chunk。

### vue-router 4 路由表（2026-08-XX 落地）

主应用 `index.html` 入口通过 vue-router 4 管理 SPA 内子路由，运维控制台 / 知识库 / 主聊天均为标准路由；`/login` 不在路由表内，仍由独立 `login.html` 入口承载，避免「主应用挂载 → 渲染 LoginView → /login 独立挂载」的双 mount 与 captcha 双调用。

#### 路由表（`src/router/index.js`）

| 路径 | name | 组件 | meta.pageKey |
|---|---|---|---|
| `/` | `agent` | `views/AgentWorkspace.vue` | `'agent'` |
| `/knowledge` | `knowledge` | `views/KnowledgeWorkspace.vue` | `'knowledge'` |
| `/ops-console` | `ops-console` | `views/OpsConsoleWorkspace.vue` | `'ops-console'` |
| `/:pathMatch(.*)*` | `not-found` | redirect → `/` | — |

#### 全局守卫（`router.beforeEach`）

- 当前落地：守卫逻辑收敛在具名导出 `requiresAuthGuard(to)` 中（`router.beforeEach(requiresAuthGuard)`），测试直接调用真实守卫函数
- `requiresAuth` 路由 + 本地无 `username` 线索（`hasLocalAuthToken()`）→ **`window.location.href = buildLoginUrl(to.fullPath)` 整页跳 `/login?redirect=<from>` 并 `return false`**（不 await `validateToken`，避免每次切路由阻塞；真正鉴权由 `fetchWithAuth` 自动 401 refresh 重试链路兜底）
- **禁止**在守卫内 `return { path: '/login...' }` 应用内跳转：`/login` 不在路由表内，会命中 not-found 兜底 → 回 `/` → 再被守卫拦截 → 无限重定向循环，微任务链饿死 fetch 回调 → 页面白屏 + 主线程占满（外部调试器 evaluate 也会挂起）
- meta 字段 schema 已建 9 个等保三级扩展位（本期不消费，下期工单接入）：
  - `menuAcl: string | string[]` —— 后端 `require_admin_or_menu_acl` 同名，路由级 ACL 校验
  - `requiredRole: 'admin' | 'user'` —— 角色校验
  - `ownershipScope: boolean` —— 标记本路由需走 OwnershipScope 数据过滤
  - `auditEvent: string` —— 路由切换时 LogService 写入事件名
  - `auditFields: string[]` —— 审计白名单字段
  - `redactFields: string[]` —— 前端展示脱敏字段
  - `csrf: boolean` —— 标记非 GET 请求需 X-Requested-With 头
  - `sessionTimeoutSec: number` —— 路由级 idle 超时（覆盖全局默认）
  - `sensitiveOperation: boolean` —— 进入路由前需二次确认
  - `logoutOnLeave: boolean` —— 离开路由时自动 clearAuth

#### Workspace 组件（`src/views/`）

- `AgentWorkspace.vue`：主聊天界面；通过 `inject('chatWorkspace')` 拿到 App.vue 提供的状态与方法（messages / sessionId / isStreaming / toolStopPending / approvalMode / approvalData / currentProject / agentName / agentDisplayName / allowedAgents / sessionTitle / queueStatus / subAgentDrawerVisible / currentSubAgent / sessionFileDrawerVisible / sessionFileTree / sessionFileDrawerLoading / sessionFileDrawerError / filePreviewOpen / filePreviewData / dislikeDialog / isAdmin / canEditProject），渲染 ChatArea + QueueStatusBanner + HumanApprovalBox + InputBox + SessionFileDrawer + FilePreviewModal + DislikeDialog
- `KnowledgeWorkspace.vue`：包裹 KnowledgePage 透传 `new-chat` / `open-subagent-drawer` 事件
- `OpsConsoleWorkspace.vue`：包裹 OpsConsoleApp；`onMounted` 调 `ensureOpsConsoleStyles()`（从 App.vue 抽到 `utils/ops-console-styles.js`，单例守卫）

#### App.vue ↔ Workspace 通信

- App.vue 在 setup 同步 `provide('chatWorkspace', reactive({ ...state..., ...methods..., isAdmin: computed(...), canEditProject }))`；AgentWorkspace 通过 `inject('chatWorkspace')` 拿到响应式引用
  - **必须用 `reactive(...)` 包裹**：vue 3.4+ template compiler 对 reactive 属性访问递归 unref；若 chatWorkspace 是普通对象字面量，嵌套 ref（如 `ws.filePreviewOpen` / `ws.filePreviewData`）不会被自动解包，ref 对象传给子组件 Boolean/Object prop 后导致 `FilePreviewModal` 始终弹窗、`content` 为 undefined 等异常。详见 `.trae/documents/file-preview-modal-auto-open-bug.md`
- SessionFileDrawer / FilePreviewModal / DislikeDialog 由原 App.vue 顶层迁移到 AgentWorkspace 内部（仅在 / 路由下渲染）
- App.vue 移除 `currentPage` 字符串 ref + `handlePageChange` 函数 + `<main v-if="currentPage === 'agent'">` + `<KnowledgePage v-if="currentPage === 'knowledge'">` + `<OpsConsolePage v-if="currentPage === 'ops-console'">` 三段 v-if 渲染
- Sidebar 移除 `currentPage` prop + `page-change` emit；改用 `useRouter()` 调 `router.push('/' | '/knowledge' | '/ops-console')`；activeMenu 由 `computed(() => route.name 映射)` 派生；computed 首行加 `if (!route || !route.name) return 'new-task'` 保护，应对单测 mount / PortalApp iframe 等无 router 上下文场景
- KnowledgePage 移除 `page-change` emit（仅保留 `new-chat` / `open-subagent-drawer`）

#### nginx.conf（`/ops-console` SPA fallback）

`/ops-console` 与 `/` 同形态 `try_files $uri $uri/ /index.html`，由前端路由接管 `/ops-console/*` 路径。

#### 路由级 layout 切换（2026-08-09 落地）

`App.vue` 加 `useRoute()` + `isOpsConsoleRoute` computed；`/ops-console` 路由下走独立分支 `<div v-else-if="isOpsConsoleRoute" class="app-layout app-layout--ops"><OpsConsoleWorkspace /></div>`，**不挂**主会话的 `<Sidebar>` / `<ProjectDialog>` / `<SubAgentDrawer>` / `<UserSettingsDialog>`。离开路由时该分支自动 unmount，主会话 layout 自动恢复。`useRoute()` 在 vitest 4 happy-dom 下偶发 named export 解析失败，try/catch 兜底 + 读 `window.location.pathname` 推导；`useRouter().currentRoute.value.name` 失败时降级为 `path.startsWith('/ops-console')`。`Sidebar` 内部 `useRoute()` 调用仍依赖其 `if (!route || !route.name) return 'new-task'` 既有保护（`Sidebar.vue:230-237`），无破坏。`Sidebar.vue` 的 `currentPage` 历史死代码 prop **未动**（保持最小改动面）。

#### 运维顶层关闭点（2026-08-09 落地，2026-08-13 GNOME 化）

`OpsMenuBar.vue` 顶部菜单栏右侧全局唯一关闭入口：**GNOME 风格原生 `<button class="close-all-btn">✕ Close`**（替代原 mac 红/黄/绿交通灯），aria-label="关闭运维控制台"，原生 button 自动支持 Enter/Space 键盘可达（替代原 tabindex=0 + 手动 keydown）。事件链路：`OpsMenuBar.close-all-btn @click.stop="emit('exit')"` → `OpsConsoleApp` 透传 `<OpsMenuBar :time="currentTime" @exit="emit('exit')" />` + `defineEmits(['exit'])` → `OpsConsoleWorkspace.handleExit` → 优先 `window.close()`（仅对被 `window.open` 打开的 Tab 有效；通过 `window.opener || window.history.length === 1` 判定），失败/无 opener 降级 `router.push('/')`。样式落在 `ops-console.css` 的 `.ops-console-root .menubar .close-all-btn` 选择器下，hover 政务蓝底，focus 政务蓝 outline。

#### 运维控制台 GNOME / Ubuntu 风格化（2026-08-13）

将整套运维控制台从 macOS 风格（圆角 + 毛玻璃 + 三色交通灯 + 底部 Dock 弹跳）调整为 GNOME / Ubuntu 风格（窗口直角 + 顶部全局菜单栏 + 标题栏右侧 max/close 两按钮 + 顶部菜单栏原生 ✕ Close + 底部 taskbar 替代底部 Dock）。详见 `.trae/documents/ops-console-gnome-style.md`。

要点：
- **字体栈**：`system-ui, "Ubuntu", "Cantarell", "Noto Sans CJK SC", "Microsoft YaHei", sans-serif`（GNOME 系 + 中文回退兜底）
- **窗口**：圆角 12px → 0px（GNOME Adwaita 直角）；毛玻璃 `backdrop-filter` 全部去除；投影 `box-shadow` → 1px 政务蓝边框 `0 0 0 1px rgba(0,58,140,.45)`；窗口背景 `#fafcff` 实色
- **标题栏**：高度 40px → 38px（兼容 OpsServerWindow 内嵌搜索框）；`cursor: grab` → `cursor: move`（保留拖拽功能）；右侧 `.traffic` 圆点 → `.win-controls` 两按钮原生 `<button>`（maximize `▢` + close `✕`，**本轮不实现 minimize**）+ SVG icon；close hover 复用项目红 `#ff453a`（与 LED/badgen 同系），max hover 复用政务蓝 hover `rgba(30,106,221,.12)`
- **顶部菜单栏**：毛玻璃 → 政务蓝系实色 `rgba(255,255,255,.85)`；应用名右侧新增中文全局菜单占位（文件 / 编辑 / 视图 / 帮助），hover 蓝底；SVG 监视器图标保留
- **底部 Dock → 底部 taskbar**：OpsDockBar.vue 模板类名全量重命名 `dock-*` → `taskbar-*`（6 类）；样式从 `position: fixed; bottom: 10px; left: 50%` 居中胶囊 → `position: fixed; bottom: 0; left: 0; right: 0` 整宽政务蓝实色（`var(--gov-blue-deep)` = `#003a8c`）；高度 36px，三图标（服务器管理 / 日志管理 / 一键智能检测）水平居中，无 hover 弹跳；`.taskbar-run-dot` 位置由 `bottom:-5px` 改 `top:2px; right:2px`（栏内无底部空间）；**不新增** `close-all` emit（全局关闭入口唯一在 OpsMenuBar ✕ Close）
- **`.win.maximized`**：`height: calc(100vh - 28px)` → `calc(100vh - 64px)`（窗口避让底部 36px taskbar）；CSS 注释明确 `64 = 28 menubar + 36 taskbar`
- **LED**：`.led` 边框 `2px solid #fff` → `2px solid rgba(0,58,140,.3)`（政务蓝边框，更"机架 LED"）；颜色映射 `.green/.red/.gray` 不变（OpsServerIcon.spec.js 5 个用例零改动通过）
- **动效**：`@keyframes pop` 缩放 `.94→1` 改 `.98→1`，时长 `.2s` 改 `.15s`（GNOME 克制）
- **零业务逻辑改动**：OpsConsoleApp.vue / OpsServerIcon.vue 仅 docstring 追加，业务代码（`runDetect` / `loadLatest` / `detectAll` / `mapSnapshotToServer` / `startDrag` / 拖拽边界 28px menubar 高度）完全未触动

测试同步（4 个 spec 共 17 用例全绿）：
- `OpsServerIcon.spec.js`：5 用例零改动（LED class 映射未破坏）
- `OpsConsoleApp.spec.js`：4 用例零改动（stub 子组件，不受模板变化影响）
- `__tests__/logFoldersDataSource.spec.js`：契约测试零改动
- `__tests__/OpsConsoleApp.exit.spec.js`：新增用例 `test_close_all_button_in_menu_bar_still_emits_exit`（真实 click `.close-all-btn` 触发 exit 透传，回归保护「移除 mac 红点后保证新按钮接管语义」）

变更文件清单（按文件大小排序）：
- `web/Agent/src/styles/ops-console.css`（主战场，政务蓝 + 全部重写）
- `web/Agent/src/components/ops-console/OpsMenuBar.vue`（顶栏模板重写）
- `web/Agent/src/components/ops-console/OpsDockBar.vue`（底部 Dock → 任务栏 + 类名重命名）
- `web/Agent/src/components/ops-console/OpsServerWindow.vue` / `OpsDetailWindow.vue` / `OpsLogManager.vue` / `OpsLogViewer.vue`（4 窗口标题栏两按钮替换）
- `web/Agent/src/components/ops-console/OpsConsoleApp.vue`（仅 docstring 追加）
- `web/Agent/src/components/ops-console/__tests__/OpsConsoleApp.exit.spec.js`（新增 1 用例 + docstring 更新）

#### 运维控制台菜单栏重构（2026-08-14，用户需求）

应用户要求把顶部菜单栏的中文全局菜单占位移除、把原底部 taskbar 的两个入口上移至顶部菜单栏中部水平居中、彻底删除「一键智能检测」入口及底部 taskbar。

要点：
- **顶部菜单栏三段式布局**：左 = `.menubar-left`（应用图标 SVG + `智能运维中心` 应用名）；中 = `.menubar-center`（`flex: 1 + justify-content: center`）内嵌两个 `.menubar-nav-btn`（服务器管理 / 日志管理，含原 taskbar 同款 SVG 图标 + 中文标签）；右 = `.menubar-right`（时间 + ✕ Close 原生 button）。spacer 删除。
- **新增 emit('open', name)**：OpsMenuBar 在点击两个 nav 按钮时 `@click="emit('open', 'servers'|'logs')"`；OpsConsoleApp 模板 `@open="openWin"` 透传给既有 `openWin(name)`（若关则打开 + bringFront）。**不引入新逻辑**，复用既有 4 窗口状态机。
- **删除 OpsDockBar.vue 组件**：`bottom-taskbar` 已无意义（只剩空的政务蓝栏）；`OpsConsoleApp.vue` 同步移除 `import OpsDockBar`、`template` 中的 `<OpsDockBar>` 引用、`detectAll()` 函数、`detailRef`、`nextTick` 引用；`.taskbar-*` CSS（`.taskbar-wrap` / `.taskbar-item` / `.taskbar-tip` / `.taskbar-run-dot`）全套删除；`.win.maximized` 高度回 `calc(100vh - 28px)`（不再额外减 36px）。
- **彻底删除 detectAll**：原「一键智能检测」链路（找 err 服务器 → 打开详情 → `nextTick` 触发 `runDetect`）连同 `detailRef` / `nextTick` import 一起删除，避免死代码。
- **零业务逻辑改动**：服务器/详情/日志/日志查看 4 个窗口组件（OpsServerWindow / OpsDetailWindow / OpsLogManager / OpsLogViewer）完全未触碰；close / max / front / drag 事件契约不变；LED class 映射不变。

测试同步（4 个 spec 共 21 用例全绿，17 → 21）：
- `OpsServerIcon.spec.js`：6 用例零改动（LED class 映射未破坏）
- `OpsConsoleApp.spec.js`：3 用例零改动（stub 子组件，不受模板变化影响），移除 `OpsDockBar: true` stub
- `__tests__/logFoldersDataSource.spec.js`：4 用例零改动
- `__tests__/OpsConsoleApp.exit.spec.js`：3 个旧用例零改动（移除 `OpsDockBar: true` stub）；新增 4 个用例：
  - `test_menu_bar_nav_button_servers_opens_servers_window`：`vm.$emit('open', 'logs')` → `wins.logs.open` 变 true
  - `test_menu_bar_nav_button_logs_opens_logs_window`：`vm.$emit('open', 'servers')` → `wins.servers.open` 仍 true（幂等）
  - `test_menu_bar_renders_two_centered_nav_buttons`：DOM 端到端断言中部两个 `.menubar-nav-btn` + aria-label
  - `test_menu_bar_no_longer_renders_global_menu_placeholders`：DOM 端到端断言 `.menubar-menu-item` 数量为 0（占位移除回归保护）

变更文件清单：
- `web/Agent/src/components/ops-console/OpsMenuBar.vue`（重写：删 文件/编辑/视图/帮助；新增两个 `.menubar-nav-btn`；emit `open`）
- `web/Agent/src/components/ops-console/OpsConsoleApp.vue`（删 OpsDockBar import + template；删 detectAll / detailRef / nextTick；`<OpsMenuBar>` 加 `@open="openWin"`）
- `web/Agent/src/components/ops-console/OpsDockBar.vue`（**删除**）
- `web/Agent/src/styles/ops-console.css`（删 `.taskbar-*` 4 个块；`.win.maximized` 高度回 28px；新增 `.menubar-left/center/right/nav-btn` 4 个块；docstring 头部 2026-08-14 段落追加）
- `web/Agent/src/components/ops-console/OpsConsoleApp.spec.js`（删 `OpsDockBar: true` stub × 3；docstring 追加 2026-08-14 说明）
- `web/Agent/src/components/ops-console/__tests__/OpsConsoleApp.exit.spec.js`（删 `OpsDockBar: true` stub × 3；describe 改名；新增 4 用例；docstring 头部 2026-08-14 段落）

### 密码框显示/隐藏切换（2026-08-14，用户需求）

用户反馈「登录页 `input` 显示密码的功能没了，需要恢复」。git 全仓 `-S showPassword / eye / show_password` 检索确认该功能不在历史 commit 中——属于**新增需求**。统一封装共享组件 `src/components/PasswordInput.vue`，登录 / 注册 / 个人设置三场景所有密码框统一接入。

要点：
- **共享组件 `PasswordInput.vue`**：props 含 `modelValue` / `inputId` / `inputClass` / `placeholder` / `autocomplete` / `disabled` / `usePasswordMask` / `inputTestId`；emits `update:modelValue` + `caps-lock`；内置 inline SVG 眼睛图标（heroicons 风格 24x24 stroke），`aria-label` + `aria-pressed` 完整。
- **两种切换模式**：
  - 默认（`usePasswordMask=false`）：点击眼睛切 `type=password ↔ type=text`，图标 eye ↔ eye-slash。
  - 兼容模式（`usePasswordMask=true`，用于 UserSettingsDialog 旧密码 / MFA 当前密码）：**不切 type**（始终 `text`，避免触发浏览器密码管理器重置），改为 toggle `.password-mask` class——脱敏时加 class（`-webkit-text-security: disc` 圆点兜底），可见时移除 class（明文）。
- **按钮外置（2026-08-14 第二轮调整）**：wrapper 改为 `display: flex` 行布局（input + button 横向并排），按钮**外置**在 input 框右侧外，不再用 absolute 覆盖 input `padding-right`——保证 input 完整继承 `.form-input` 样式（高度 44px / 背景 / 边框 / 圆角 / focus 态），与其它输入框视觉一致。注册页（两列 grid 布局）密码框同步加 `full-width` 跨两列，避免眼睛按钮挤压 input 宽度。
- **autocomplete 不破坏**：原 `current-password` / `new-password` 属性透传。
- **capsLock 提示**：组件 keydown / keyup emit `caps-lock` 布尔值给父级，父级（原 LoginView / RegisterView）保留原 `caps-lock-hint` 提示块不变。
- **零运行时依赖**：inline SVG 不引入图标库，与项目一贯"零额外依赖"基调一致。

覆盖入口（共 9 处）：
1. `LoginView.vue`：#login-password
2. `RegisterView.vue`：#register-password + #register-confirm-password
3. `UserSettingsDialog.vue`：
   - 修改密码区：#settings-old-password（usePasswordMask=true）、#settings-new-password、#settings-confirm-new-password
   - MFA 区：#mfa-enroll-current-password（usePasswordMask=true + inputTestId 透传保 0a5cf42 旧测试）、#mfa-regen-password（usePasswordMask=true）
   - admin 创建/编辑用户：#form-password

测试同步（4 个 spec 共 ~23 用例全绿）：
- `components/__tests__/PasswordInput.spec.js`（新增）：10 用例覆盖导入 / 默认渲染 / type 切换 / v-model / caps-lock / usePasswordMask class 切换 / disabled / 透传属性
- `views/__tests__/LoginView.show-password.spec.js`（新增）：4 用例覆盖默认 type / 切 text / 还原 / 提交不被破坏
- `views/__tests__/RegisterView.show-password.spec.js`（新增）：5 用例覆盖默认 / 两个框独立切换 / 还原 / 复杂度提示仍工作
- `components/__tests__/UserSettingsDialog.show-password.spec.js`（新增）：4 用例覆盖 profile 区三个框（含 oldPassword class 切换）+ admin users 区 #form-password

变更文件清单：
- `web/Agent/src/components/PasswordInput.vue`（新增）
- `web/Agent/src/views/LoginView.vue`（替换 #login-password input；保留 `checkCapsLock` 函数供 MFA 阶段复用；新增 `handleCapsLock(on)` 桥接 PasswordInput emit）
- `web/Agent/src/views/RegisterView.vue`（替换两个 input）
- `web/Agent/src/components/UserSettingsDialog.vue`（替换 6 处 input；新增 PasswordInput import）
- 上述 4 个 spec 文件（新增）

### vue-router 接入回归修复（2026-08-XX 同步）

接入 vue-router 后 AgentWorkspace 子页面使用 `.content-area` / `.welcome-title` / `.queue-banner-wrapper` 三个 layout 类，原定义在 App.vue `<style scoped>` 内。**Vue scoped CSS 机制只匹配父组件自身根元素，不穿透到子组件根元素**，导致接入后 AgentWorkspace 主聊天界面坍缩（Sidebar 仍正常显示，因为 `.app-layout` 在 App.vue 自己根元素）。

修复：把这三个 layout 类从 App.vue scoped CSS 抽出到全局 `src/styles/layout.css`，由 `main.js` 与 `styles/main.css` 一起 import。App.vue 自己的局部样式（`.app-layout` / `.auth-loading-screen` / spinner / keyframes）保留在 `<style scoped>` 内，不参与跨组件。

### Portal 入口 Tab 标题驱动（2026-06-30 落地）

`portal.html` 的浏览器 Tab 标题跟随运行时配置 `web/Agent/public/app-config.json` 的 `brandTitle` 字段：

- **首帧（编译期）**：`portal.html` 的静态 `<title>` 已被同步为 `brandTitle` 的默认值（`沈阳市自然资源和规划"一点通"`），避免首帧 Tab 标题闪烁为无关文案
- **运行时覆盖**：`PortalApp.vue` 的 `onMounted` 在 `checkAuth()` 之前 `await loadAppConfig()` 拉取最新 `brandTitle`，加载完成后 `document.title = appConfig.brandTitle`，支持配置变更无需重新构建即生效
- **配置缺失时**：fetch 失败或字段缺失均不报错，保留默认 `brandTitle`，Tab 标题不会出现空白
- **依赖模块**：`src/config/portal.js::loadAppConfig()` + `src/config/portal.js::getNavItems()`；调用方为 `PortalApp.vue` 单入口（其他入口不消费本逻辑，避免重复 fetch）
- **变更影响**：仅前端 SPA，无后端/数据库 schema 改动；`init_all_tables.sql` 无需同步

### 组件清单（src/components）

> 全部组件的「组件 → 文件 → 数据来源 API」速查见根目录索引 `project_memory.md` 的「前端组件速查表」；本节记录组件级行为契约与迭代细节。

- **根组件**：`App.vue`（主）、`KnowledgeApp.vue`（知识库）、`PortalApp.vue`（门户）、`KnowledgePage.vue`（旧版，被 `KnowledgeApp.vue` 替代，仍保留以兼容旧引用）
- **登录入口**：`login.html` + `src/login-main.js`（独立 Vite 入口；承载 `LoginView`；由 `redirectToLogin()` 跳到 `/login?redirect=...` 统一访问）
- **运维控制台（App.vue 内嵌子页面，2026-08-08 等保三级改造）**（历史：2026-08-05 独立入口）：删除 `ops-console.html` + `src/ops-console-main.js`，取消 `vite.config.js` 的 `opsConsole` 入口；改为 `App.vue::currentPage === 'ops-console'` 条件渲染 `OpsConsolePage`（即 `OpsConsoleApp.vue`），复用主应用 `fetchWithAuth` + HttpOnly Cookie + `X-Requested-With` CSRF 头鉴权链路，解决「独立子窗口 Cookie 失效 → /api/admin/server-inspection/latest 拉不到数据」反模式；`src/styles/ops-console.css` 改为 `.ops-console-root` 作用域前缀（避免政务蓝 `* { margin: 0; padding: 0 }` 污染主应用），并通过 `App.vue::ensureOpsConsoleStyles()` 在首次切到 ops-console 时按需引入（单例守卫）；`src/components/ops-console/` 下 7 个组件 + `src/data/ops-console/mockData.js` 静态样例数据保留。组件全部以 `Ops` 前缀命名（与主 Agent 业务命名空间隔离）：
  - `OpsConsoleApp.vue`：根组件，10 个 ref 状态机（currentTime / searchKey / zTop / wins / detailServer / activeFolder / logFile / inspectionLogServer / inspectionLogRecords / inspectionLogLoading / detectServer）+ 14 个函数（tick / bringFront / openWin / toggleMax / closeWin / openDetail / openInspectionLog / closeInspectionLog / onOpenDetect / closeDetect / openLog / startDrag / genLogContent / loadLatest）；6 个窗口（servers / detail / logs / logview / inspectionLog / detect）可独立 open/close/max/front/drag；`startDrag` 拖拽时限制窗口四边边界：顶部不低于菜单栏底部（`28px`），左右/底部至少保留 `60px` 可见区域，防止标题栏被顶部菜单栏压盖后无法再次拖动；`onOpenDetect(srv)` 写 `detectServer` + 开 `wins.detect` 窗 + bringFront；`mapSnapshotToServer` 透传 `businessName`（智能检测 chat `referenced_servers.name` 与 `query_inspection_records` business_name 精确反查契约对齐）
  - `OpsMenuBar.vue`：顶部菜单栏（GNOME top bar 实色 + 时间 + 标题「智能运维中心」+ 中文全局菜单占位 + ✕ Close 原生 button，高度 `28px`；2026-08-13 从 mac 毛玻璃 + 红/黄/绿交通灯改造）
  - `OpsServerWindow.vue`：服务器管理窗口（GNOME 直角 + 标题栏 max/close 两按钮 + **两列横向长方形卡片**（每行 2 个；卡片含 OpsServerIcon 小号 + LED 红绿灯 + 服务器名称 + **最后检测时间（绝对时间 `YYYY-MM-DD HH:MM`，显示为「最新检测时间:YYYY-MM-DD HH:MM」，无快照显示 `最新检测时间:-`，2026-08-16）** + **CPU/内存/存储/服务器负载单行指标（竖线分隔，CSS ::before 生成 `|`，2026-08-14；2026-08-16 负载 label 改为「服务器负载」）** + **Linux 限定「服务器负载」项（`serverType === 'linux'` 才渲染，2026-08-16）** + 搜索 + 状态点；阈值与 `data/devops/inspection_scripts.yaml::warn` 对齐（CPU 80 / 内存 80 / 磁盘 80 → 红 #ff453a；null → 灰 #9aa3af）；**负载阈值独立**为 `≥ 4 红 / < 4 绿 / null 灰`（`loadColor(v)` 具名函数），与百分比指标 80 解耦，对齐 `inspection_scripts.yaml::load_1m warn=4.0`；**存储行改造（2026-08-16）**基于后端 `field_results` 智能选异常盘（`pickAnomalyDisks(fieldResults, disks)` 具名函数）：任一 `disk_used_pct` / `io_util_pct` / `io_await_ms` 超 warn/crit 即把该盘符 + 异常指标概要标红（`#ff453a`），多盘符用逗号串联 + flex-wrap 换行；全 pass → 显示 `-`；`fieldResults` 为空（老数据 / 未落库）→ 兜底既有 `pickDisplayDisk` 行为；老数据兜底时仍按 `metricColor(displayDiskOf(srv)?.used)` 标色；单击卡片仍 `emit('open-detail', srv)` 打开 OpsDetailWindow，详情契约不变；新增 6 个具名导出函数 `formatCollectedAt(iso)` / `isLinuxType(serverType)` / `loadColor(v)` / `pickAnomalyDisks(fieldResults, disks)` / `formatAnomalyItem(item)` / `pickDisplayDisk(disks)` 供单测直接 import）；**2026-08-17 卡片头操作按钮**：时间标签 DOM 顺序紧贴服务器名称之后（顺序调整，`flex-shrink:0` 不变），同行追加两个 22×22 图标按钮「📄 日志」+「✦ 智能检测」；日志按钮 `emit('open-log', srv)`（父级 OpsConsoleApp 调 `openInspectionLog(srv)` 拉取 `server_inspection_records` 后挂载 OpsInspectionLogWindow）；智能检测按钮 `emit('open-detect', srv)` 触发 OpsConsoleApp.onOpenDetect 打开 OpsDetectChatWindow（`/api/agent/chat` SSE 流式 chat，agent=project）；按钮 `@click.stop` 阻止冒泡到卡片整体的 `open-detail`；新增 emit `open-log / open-detect` 两条契约
  - `OpsDetailWindow.vue`：服务器详情窗口（GNOME 直角 + 标题栏 max/close 两按钮 + 指标卡 + 智能检测动画 + 磁盘列表），暴露 `runDetect()` 方法供父组件调用；2026-08-17 改造为双 script 块：`<script>` 模块导出纯函数 `fmtPct / fmtMs / fmtStr / warnColor / IOWAIT_WARN / SWAP_WARN / INODE_WARN / ioAwaitValue / diskGroupLabel / partitionCardStatus / diskHeadStatus / peakIoAwait / peakIoUtil / groupDisksByPhysicalDisk / statusLabel / formatDuration`，`<script setup>` 仅保留组件 setup 逻辑（props / emits / computed），与 OpsServerWindow.vue 双块结构一致；供 OpsInspectionLogWindow 直接 import 复用详情区渲染，避免嵌套窗口外壳造成双重标题栏
  - `OpsLogManager.vue`：日志管理窗口（GNOME 直角 + 标题栏 max/close 两按钮 + 左侧文件夹 + 右侧文件列表）
  - `OpsLogViewer.vue`：日志查看窗口（GNOME 直角 + 标题栏 max/close 两按钮 + 终端风格日志内容）
  - `OpsInspectionLogWindow.vue`（2026-08-17 新增）：采集记录窗口（GNOME 直角 + 标题栏 max/close 两按钮 + **左 280px 列表 + 右自适应详情区**）。左栏：每条 `server_inspection_records` 行渲染「时间 + 状态徽章（pass/warn/crit/skipped/unassessed 五态色块）+ 耗时（formatDuration 友好展示）+ exit_code + 错误摘要（error_message 红字 + ellipsis）」；列表点击切换选中态，默认首条 active；右栏：复用 OpsDetailWindow 的指标卡 / kv / 物理磁盘分组样式（inline 渲染避免嵌套窗口外壳），数据通过 `mapRecordToServer(record, baseServer)` 纯函数把后端 `parsed_values / field_results` 归一化为 ServerItem 形状；loading=true → 显示「加载中…」；records=[] → 显示「暂无采集记录」空态。Props: `win / server / records / loading`；Emits: `close / max / front / drag`。触发源：OpsServerWindow 卡片头「日志」按钮（`emit('open-log', srv)`）→ OpsConsoleApp 调 `openInspectionLog(srv)` 拉取 `GET /api/admin/server-inspection/records?server_id=X&limit=100` → 写入 `inspectionLogRecords` 后挂载本窗口。
  - `OpsDetectChatWindow.vue`：智能检测流式聊天窗口（GNOME 直角 + 政务蓝渐变标题栏 + **仅关闭按钮（无最大化入口，固定尺寸 640×520）+ ✦ 装饰图标 + AI 回答区白底卡片 markdown 渲染（流式光标位于卡片内尾部）+ 错误横幅（含 `!` 圆形图标）+ 空态提示**；**不**显示用户问题气泡，仅输出 AI 答案）。onMounted 自动调 `chatStream(sessionId, DETECT_QUESTION, [], null, 'project', null, buildDetectOverrides(server))` 一次：合成 `ops-detect:{server_id}:{ts}` session_id（由后端 `session_auth_middleware` 在 `/api/agent/` 前缀下对该前缀自动建行并归属当前用户；`SessionDB.get_user_sessions` 过滤该前缀，主侧边栏不显示），`DETECT_QUESTION` 为固定两段式问题（① 最新巡检记录问题分析 + 优化建议 ② 最近 2 天巡检趋势总结），`buildDetectOverrides(server)` 构造 `context_overrides.referenced_servers=[{name: businessName, server_type}]`（name 优先用 `businessName`，与 `query_inspection_records` business_name 精确反查契约对齐，兜底卡片 `name`）；SSE 经 `processSSEEvent` 累积 `aiMsg.text` → `safeMarkdown` 渲染 + 流式光标；`onBeforeUnmount` 调 `triggerAbort(sessionId)` + `reader.cancel()` 优雅中止（幂等，对永不 done 的流也安全）。HTTP 403（agent ACL 不含 project）/ 429 排队 / 网络错误通过 `chatStream` 抛出的 `err.status / err.detail` 转错误横幅。Props: `win / server`；Emits: `close / front / drag`（**无 max**）。触发源：OpsServerWindow 卡片头「智能检测」按钮（`emit('open-detect', srv)`）→ OpsConsoleApp 调 `onOpenDetect(srv)` 打开本窗口。`<script>` 块具名导出 `DETECT_QUESTION / DETECT_AGENT_NAME / buildDetectSessionId(server, now?) / buildDetectOverrides(server)` 纯函数供单测直接 import。
  - `OpsDockBar.vue`：底部 taskbar 任务栏（政务蓝实色 `#003a8c` 整宽 36px + 三图标按钮：服务器/日志/一键智能检测；2026-08-13 从底部 mac Dock 改造，模板类名 `dock-*` → `taskbar-*`）
  - `OpsServerIcon.vue`：公共服务器图标（被 ServerWindow / DetailWindow 共用）；2026-08-05 新增 `unknown` 灰色 LED 态（从未采集 / 无快照 / 采集跳过），与 `ok` 绿、`err` 红共三态
  - 数据：2026-08-05 起 `servers` 改为从 `GET /api/admin/server-inspection/latest` 拉取（按当前用户 `OwnershipScope` 过滤：admin 透传全量 `devops_servers`，普通用户按 `user_server_nodes` 可见集去重；响应**不含 ip**）；**2026-08-12 起** `logFolders` 改为本地 `ref([])`，等待后端 `GET /api/admin/log-folders` 落地（接口落地期间日志管理窗口显示空态，不再持有前端 mock 数据，避免被 Vite 打生产 bundle 污染 Docker 镜像）；原 mock 数据迁入 `src/components/ops-console/__tests__/fixtures/opsConsoleMockData.js` 仅供单测使用；**不**走 `src/utils/api.js` 之外的 axios 封装（独立桌面，不依赖主 Agent 业务）

#### logFolders 去前端 mock（2026-08-12 落地）

- **根因**：`src/data/ops-console/mockData.js` 此前被 `OpsConsoleApp.vue` 生产代码 `import { logFolders } from '../../data/ops-console/mockData.js'` 直接依赖，Vite 通过 `import graph` 把整个 mock 数据（4 个文件夹 / 10 个文件名 / 时间戳字符串）打入生产 bundle 污染 Docker 镜像
- **修法**：mock 数据迁入 `src/components/ops-console/__tests__/fixtures/opsConsoleMockData.js`（路径已落在 Vitest 自动发现的 `__tests__/` 子树下，被 `include` 收集但不会进生产 bundle）；`OpsConsoleApp.vue` 改为 `const logFolders = ref([])` 等待后端接口落地
- **接入点**：后端 `GET /api/admin/log-folders` 落地后，只需在 `OpsConsoleApp.vue::onMounted` 内新增 `loadLogFolders()` 调 `fetchWithAuth('/api/admin/log-folders')` 写入 `logFolders.value`，无需调整 `OpsLogManager.vue`（其 `folders` prop 本就要求 `Array`，空数组 + v-for 自然渲染空态）
- **契约测试**：`src/components/ops-console/__tests__/logFoldersDataSource.spec.js`（P0 fixture 可导入 + 数据结构完整 + `OpsConsoleApp.vue` 源码不再含 `src/data` 路径字符串 + 不再含 `import { logFolders }` + 仍声明本地 `ref([])`），防止后续误回退到旧 mock 路径
  - 跳转：Sidebar.vue `handleMenuClick('ops-console')` 2026-08-08 等保三级改造：由 `window.open('/ops-console.html', '_blank', 'noopener')` 改为 `emit('page-change', 'ops-console')`，行为与「新建任务」一致（active 视觉保留）；不注册 menu（用户级入口，非管理 Tab）；知识库入口仍保留独立 `window.open('/knowledge.html')`（业务上需要在多 Tab 长期挂着的会话流，与运维控制台场景不同）
- **聊天**：`ChatArea.vue`、`InputBox.vue`、`MessageBubble.vue`、`SkillTags.vue`、`HumanApprovalBox.vue`、`TopBar.vue`
  - `ChatArea.vue`（2026-07-01 新增，2026-07-02 修正头部 sticky + 改为撑满主区宽度与贴顶，2026-07-02 二次修正 header 内部居中，2026-07-02 三次修复滚动按钮「跳一下又回到原位」竞态）：顶部显示会话名称（`sessionName`）与绿色文件夹图标按钮；头部使用 `position: sticky` 固定在聊天区域顶部，不随消息滚动；header **外层** `.chat-area-header` 撑满主区宽度（背景色铺满两侧），**内层** `.chat-area-header-inner` 与下方 `.messages-container` 一致采用 `max-width: 900px + margin: 0 auto + padding: 0 40px` 居中布局，实现"外层连接两侧 + 内容向中间靠拢与聊天区对齐"；紧贴主区顶部（去掉 chat-area 顶 padding、改为 header 外层 padding: 8px 0），与左侧 sidebar-logo 形成水平对齐节奏；点击图标 emit `open-session-file-drawer` 事件，由 `App.vue` 打开右侧会话文件抽屉
  - **2026-07-02 滚动按钮修复**（仅 ChatArea.vue 单文件改动）：右下角 `.scroll-buttons-wrapper` 内的 `scroll-to-top-btn` / `scroll-to-bottom-btn` 之前包裹 `<transition name="fade">`，结合 `scrollTo({ behavior: 'smooth' })` 在 click 同一帧触发时，leave 动画的 reflow/repaint 会中断 in-flight smooth 滚动，导致 scrollTop 回弹到原值（用户反馈「会话跳了一下又回到原位」）；修复方案：① 去掉两层 `<transition>` 包裹，依赖 v-show 的 display 切换（无动画）；② `scrollToBottom` / `scrollToTop` 改为直接赋值 `chatContainer.value.scrollTop`（瞬时），并用 `nextTick` 包裹读取最新 `scrollHeight`；③ 移除 `handleScrollToBottomClick` 中间函数；④ 删除 `.fade-enter-active / .fade-leave-active / .fade-enter-from / .fade-leave-to` CSS（保留为注释占位，避免误用恢复原 bug）；⑤ `onMounted` 中 `scrollToBottom('auto')` 改为无参调用。若未来需要按钮淡入淡出动画，必须改用 `<transition-group>` 包整组按钮并配合 RAF/nextTick 调度，**禁止**再次对单按钮用 `<transition>` + `v-show` + `scrollTo({ behavior: 'smooth' })` 同帧触发。
- **文件**：`FileList.vue`、`FilePreview.vue`、`FolderTree.vue`、`FileManagerModal.vue`
  - `SessionFileDrawer.vue`（2026-07-01 新增，2026-07-07 追加文件下载入口，2026-07-07 三次迭代：UUID 抽取 → stored_path → fetch blob）：右侧可拖拽宽度的抽屉，仅展示当前会话/项目文件空间中的原文件目录；复用 `FolderTree.vue`，点击文件 emit `file-click`；**下载入口（2026-07-07）**：根级与嵌套子文件节点均渲染 `<button class="download-btn">`（Lucide 三段式下载图标）；外层文件节点由 `<button>` 改为 `<div role="button" tabindex="0" @keydown.enter/space>` 以规避 HTML 按钮嵌套违规；**v1（已废弃）**：抽 `extractFileUuid(file.path)` 调 `GET /api/files/download/{file_uuid}` —— 工作空间文件并非都经过 UUID 命名，basename 是原中文名时抽出即原名，必 404；**v2（已废弃）**：用 `file.stored_path || file.path` 拼 `<a download>` 直链调 `GET /api/session/{sessionId}/files/download?stored_path=...` —— `<a>` 触发的导航请求不携带 `Authorization` 自定义头，被 `auth_middleware` 直接 401 拒绝（终端日志 2026-07-07 984-1007 行确认）；**v3（当前）**：保持 v2 的 URL 与 `sessionId`/`stored_path` 参数，但**改用 `fetchWithAuth` 拉 blob → `URL.createObjectURL` → 临时 `<a download>` 触发原生下载**；`fetchWithAuth` 自动注入 `Authorization: Bearer <jwt>` 与 `X-Session-ID`，并自动处理 401 刷新重试；下载文件名优先解析后端 `Content-Disposition: filename*=UTF-8''<encoded>` 头，fallback 到 `file.name`；`SessionFileDrawer` 新增 `sessionId` prop 由 `App.vue` 通过 `:session-id="sessionId.value"` 注入；`FolderTree` 同步加 `sessionId` prop 并递归透传；CSS 新增 `.file-row` / `.file-row-main` / `.download-btn` 三段，hover 用 `--color-accent-light` 背景 + `--color-accent` 边框。**不修改后端**。详见计划文档 `.trae/documents/workspace-drawer-download-feature.md`
  - `FilePreviewModal.vue`（2026-07-01 新增）：文件预览弹窗，复用 `FilePreview.vue`；支持点击遮罩层、按 ESC 键关闭；为避免弹窗标题与 `FilePreview.vue` 自身标题重复，弹窗内调用 `FilePreview` 时传入 `:show-header="false"`
  - `FilePreview.vue`：文件预览面板组件，新增 `showHeader` prop（默认 `true`），用于控制是否渲染内部标题栏和关闭按钮
- **知识库**：`KnowledgeChat.vue`、`ProfileInputBox.vue`
- **公共**：`Sidebar.vue`、`HelloWorld.vue`、`UserSettingsDialog.vue`
  - `Sidebar.vue`（2026-07-02 调整）：侧边栏「项目」分组默认展开，其下各项目内的会话列表默认折叠，点击项目头部可切换展开/折叠
- **Admin 管理**：
  - `UserSettingsDialog.vue`：admin 角色可访问的「用户设置与管理」对话框；左侧主导航固定宽度为 200px，导航项采用图标与文字左对齐、浅蓝圆角面高亮当前项，不使用彩色侧边强调条；hover、focus-visible、active 分别使用全局中性背景、inset 焦点环和强调色 token。左侧主导航包含 8 个 Tab —— `profile`（个人设置）/ `user-management`（用户管理）/ `agent-management`（智能体管理，调用 `AgentManager.vue`）/ `mcp-management`（MCP 管理，调用 `McpServerManager.vue`）/ `tool-management`（工具管理，调用 `ToolManager.vue`）/ `skill-management`（Skill 管理，调用 `SkillManager.vue`）/ `task-scheduler`（运维任务，调用 `TaskSchedulerManager.vue`）/ `email-settings`（邮件设置，调用 `EmailSettingsManager.vue`）。其中 `user-management` Tab 内部以水平子 tab（`.sub-tabs` / `.sub-tab`）形式展示三个子页面：用户列表 / 在线监控 / 会话查询，由 `activeUserMgmtTab` 状态控制，`switchUserMgmtTab` 切换并触发对应数据加载；`session-query` 子 tab 为两级视图：人员列表 → 点击人员进入该用户的会话列表；会话表格支持复选框批量选择、批量删除、单条导出 Markdown，点击会话标题弹出历史消息对话框，使用 `MessageBubble` 渲染完整消息（含 `ToolCallCard` 工具卡片与 `SubAgentCard` 子智能体卡片）。`initialTab` 仍兼容传入 `online-monitor` / `session-query` 旧值，会自动映射到 `user-management` 主 tab + 对应子 tab
    - **历史会话详情弹窗布局**：
      1. **居中显示**：历史会话详情弹窗使用 `.dialog-overlay--centered`（flex + 居中对齐）+ `.dialog-overlay--centered > .dialog-card`（position:relative + 圆角 + max-height:90vh），宽度 800px；主弹窗（用户设置与管理）仍铺满全屏
      2. **子智能体抽屉就地打开**：历史弹窗内的 `SubAgentCard` 点击后不再冒泡到 `App.vue`，而是在弹窗内就地打开独立的 `<SubAgentDrawer>`（`historySubAgentDrawerVisible` / `historyCurrentSubAgent` 状态控制）
      3. **左右并排布局（2026-07-04）**：header 下方新增 `.history-dialog-main` flex-row 容器，左侧 `.history-dialog-body` 保留会话消息流，右侧通过 Teleport 挂载 `SubAgentDrawer`，两者同时可见；废弃原 `.history-dialog-body--collapsed` 折叠隐藏方案
      4. **抽屉消息区滚动（2026-07-04）**：Teleport 到 `.history-dialog-main` 的抽屉使用 `.subagent-drawer--teleported { align-self: stretch; height: auto; min-height: 0; }`，避免弹窗卡片仅有 `max-height` 时 `height:100%` 解析失败导致抽屉被内容撑高、消息区无法滚动
      5. 数据契约：后端 `/api/session/admin/{id}/messages` 返回的 `type:"subagent"` 元素含完整 `messages` 数组（`app/shared/utils/memory/checkpoint_history.py:411-423`），`convertSubAgentHistoryToAiSubAgent`（`sseParser.js:743`）直接转成 `SubAgentDrawer` 所需的 props 结构，无需额外接口
  - `EmailSettingsManager.vue`：admin 邮件设置三 Tab（服务器配置 / 发送策略 / 测试发送），挂载在 UserSettingsDialog 「消息设置」(messaging) → channel「邮件设置」(messaging.email) 下，按 `visibleMenus` + `isAdmin` 过滤子 tab；三个 Tab 走 `.email-settings-manager`（flex:1）+ `section[role="tabpanel"]`（flex:1 + min-height:0）+ `.email-form`（flex:1 + overflow-y:auto）三级高度链契约；发送策略走 `.policies-layout`（grid 260px + 自适应）+ `.policies-list` + `.policy-editor` 独立滚动三段式；SMTP 密码字段 GET 永远返空串，前端「密码留空」表示不修改原密码；测试发送走 `multipart/form-data` 支持附件；`emailableUsersError` 单独 ref 隔离失败警示不污染 `policyError`（防"收件人拉取失败 → 整个策略面板红 banner"反模式）；**2026-08-19 `.email-form` 加 `align-content: start`**：外层 `.tab-fill-wrapper` 在窗口拉高时高度变大，`.email-form` `flex:1` 拿到确定高度后 Grid 默认 `align-content: normal/stretch` 会把多余高度均分到行间导致控件距离变大；改 `align-content: start` 后 Grid 行紧凑贴顶，多余空间留在卡片底部，符合"section 扩大到底"契约；与运维控制台 `ops-console.css:240` 同款修复模式；新增 `EmailSettingsManager.spec.js::test_email_form_aligns_content_to_top` 源码静态断言防回归
  - `McpServerManager.vue`：MCP server CRUD + 方法列表 + 启禁用切换（前后端）
  - `AgentManager.vue`：智能体管理 Tab 内容；左侧智能体列表 + 右侧 Tab 结构（「基本信息」Tab + 「配置字段」Tab + 「工具绑定」Tab）；支持完整 CRUD：
    - **新增智能体**：弹窗表单（8 字段）+ 内嵌 config_schema 编辑器；调用 `fetchAgentConfigFieldTemplates` 获取字段模板做下拉选择
    - **基本信息 Tab**（2026-06-29 新增）：编辑当前智能体的 `display_name` 和 `description`，调用 `updateAdminAgent(name, {display_name, description})`（PUT `/api/admin/agents/{name}`）保存；保存成功后刷新左侧列表和当前详情头部
    - **编辑字段**：每组表格独立增删改；section = `root` / `state_fields` / `context_fields`；通过 `updateAdminAgentConfigSchema` / `addAdminAgentConfigField` / `updateAdminAgentConfigField` / `deleteAdminAgentConfigField` 增量更新
    - **字段模板下拉选择**：`root` / `state_fields` / `context_fields` 三组均支持「覆盖来源 = 已有字段」时下拉选择对应基类字段（AgentConfig / AgentState / AgentContext），自动填充字段名、类型、默认值
    - **保存策略**：`modified` 字段改用 `PUT /config-schema/field` 直接覆盖，避免旧版"先删后加"导致的数据丢失；`delete` 失败时记录具体字段名并继续处理其他变更，错误信息汇总展示；失败时保留 `pendingChanges` 不自动清空
    - **删除智能体**：含确认弹窗（保留历史会话）
    - **启用/禁用开关**：右上角 switch，立即调用 `setAdminAgentEnabled`，不进入「未保存修改」队列
    - **工具绑定 Tab**（2026-06-25 新增）：右侧第三个 Tab，展示所有可用工具（内置 + MCP）按分类分组，复选框勾选绑定到当前 agent；内置工具分类 = `tools.category`，MCP 工具分类 = `mcp_server.display_name`；工具列表全局缓存（`toolsInitialized`，避免每次切换 agent 重复拉取），切换 agent 时仅重新加载该 agent 的绑定；绑定格式 `{tool_name, tool_type: "builtin"|"mcp", enabled: true, sort_order}`；保存调用 `updateAgentToolBindings(name, bindings)`（PUT 全量替换）；MCP 工具的 `tool_name` = `method_name`（不带 server 前缀，与后端 `mcp_registry.get_tools_with_server` 匹配逻辑一致）；API 函数 `listTools` / `getAgentToolBindings` / `updateAgentToolBindings` 定义在 `api.js`
  - `ToolManager.vue`：工具管理 Tab 内容，挂载于 `UserSettingsDialog.vue` 的 `tool-management` Tab（admin 可见）；左侧已注册工具列表按 `category` 分组（可折叠）+ 右侧详情/扫描结果面板；调用 `listTools` / `scanTools` / `listUnregisteredTools` / `registerTool` / `setToolEnabled` / `deleteTool`（对应后端 `tool_admin_router` 的 `/api/admin/tools/*` 端点）；支持扫描未注册工具、注册弹窗（回填自动解析的只读字段 + 补充 description/category）、启用/禁用 toggle（失败回滚 DOM）、删除（含 confirm）
  - `TaskSchedulerManager.vue`（2026-07-10 新增，2026-07-29 增强智能体任务 context_overrides 编辑器；**2026-08-03 巡检脚本按需两段式加载 + 脚本库扫描面板**）：智能体定时任务管理 Tab 内容，挂载于 `UserSettingsDialog.vue` 的 `task-scheduler` Tab（admin 可见）；左侧展示定时任务列表（名称、agent_name、cron、启停状态），右侧表单编辑 `name/description/agent_name/prompt/cron_expression/timezone/enabled/context_overrides`；支持新增、保存、启停、立即运行、删除和最近 50 条执行历史展示；调用 `fetchTaskSchedules` / `createTaskSchedule` / `updateTaskSchedule` / `deleteTaskSchedule` / `setTaskScheduleEnabled` / `triggerTaskSchedule` / `fetchTaskRuns`（对应后端 `task_scheduler_router` 的 `/api/admin/task-schedules/*` 端点）
    - **2026-07-29 智能体任务 context_overrides 参数化编辑器**：把旧的「context_overrides JSON」textarea 替换为「添加参数 + 参数行」结构（参考 AgentManager 的 config_schema 字段编辑体验）。参数行支持 `str/int/float/bool/list/dict` 六种类型；`reference_server` 特殊行使用现有 `devopsServers` 候选（admin 走 `fetchDevOpsServers`，普通用户走 `fetchUserServerTree` 映射为同形态候选），勾选后序列化为后端契约 `context_overrides.referenced_servers`（元素 `{name, server_type}`），运行时仍由 `TaskSchedulerService.execute_schedule → build_agent_instance(context_overrides=...)` 透传给 AgentContext。模板与转换逻辑独立在 `web/Agent/src/utils/contextOverrides.js::parseContextOverrides / serializeContextOverrides / listContextParameterTemplates`，配套单测 16 用例。旧字段（`legacy_marker`）与新增标量字段会作为参数行出现并可继续编辑；旧 `contextJson` textarea 仅作为「JSON 预览」只读展示，不再参与提交。运行时执行链不变，无需修改后端。
    - **2026-08-03 巡检脚本按需两段式加载 + 2026-08-04 即时绑定**：`openScriptDialog(row)` 保持两段式按需加载——1) 先 `fetchDevOpsServerDetail(row.id)` 调 `GET /api/admin/devops-servers/{id}` 取 `inspection_script_id` 等元数据；2) 若未配置则展示空态，否则调 `fetchInspectionScriptDetail(scriptId)` 获取完整脚本原文并合并展示。服务器扫描入库表格的「巡检脚本」列同时提供脚本库下拉选择，选项来自 `fetchInspectionScripts()` 白名单列表；改选或选择「未配置」后立即调用 `updateDevOpsServerInspectionScript(serverId, scriptId|null)`，保存期间仅禁用当前行，失败时完整恢复 id/name/display_name 三字段并显示脱敏文案；脚本列表加载期间禁用下拉，原「查看脚本」按钮继续保留。
    - **2026-08-03 巡检脚本库扫描面板**（2026-08-04 迁移至独立 Tab）：服务器 Tab 内新增 `<section class="inspection-script-scan" data-testid="inspection-script-scan-section">`，仅 admin 可见；含扫描按钮（`data-testid="scan-inspection-scripts-btn"`）+ 提示文案「从 `data/devops/inspection_scripts.yaml` 同步所有平台巡检脚本；仅展示扫描统计，不暴露脚本原文」+ 独立的扫描统计 / 错误区域（`inspectionScanSummary` / `inspectionScanErrorMessage` / `inspectionScanSuccessMessage`）；触发函数 `triggerInspectionScriptsScan` 带防重复提交（`isScanningInspectionScripts` 短路），失败时脱敏文案「巡检脚本扫描失败，请稍后重试」，不回显后端 detail；扫描成功后强制刷新统计区
    - **2026-08-04 巡检脚本库独立 Tab + 编辑保存**：服务器 Tab 内的脚本库扫描入口迁出为独立第 6 个 Tab（`TAB_LIBRARY = 'library'`，菜单 id `task-scheduler.inspection-script-library`，`data-testid="panel-library"`）；左右分栏：左侧 `InspectionScriptLibraryPanel.vue` 节点列表（`onMounted` 调 `fetchInspectionScripts` 加载白名单 7 字段，顶部搜索框按 `name / display_name / platform / version` 不区分大小写过滤，点击节点通过 `select` 事件通知父组件），右侧 `InspectionScriptEditorPanel.vue` 编辑面板（`scriptId` prop；`null` 时显示「请选择左侧节点查看详情」；非空时 watch 监听 `props.scriptId` 调 `fetchInspectionScriptDetail` 拉详情，渲染可编辑表单 `display_name / platform / version / inspection_parser / 脚本正文（<textarea class="editor-textarea"> white-space: pre）/ 字段规则表（v-for 渲染 key / name_zh / unit / direction / warn / crit 6 列 + 「新增字段」/「删除」按钮）`；点保存调 `updateInspectionScript`，成功同步 form + emit 'saved'，失败仅显示脱敏文案「保存失败，请稍后重试」）；扫描按钮迁至 panel 顶部（`data-testid="library-scan-btn"`），5 字段统计（`scanned / inserted / updated / skipped / failed`）写入 `libraryScanSummary`；「服务器扫描入库」Tab 旧 `inspection-script-scan-section` 段已删除
    - **2026-08-05 服务器扫描入库 Tab 切回时强制刷新 inspectionScripts 下拉**：`switchTab(tabId)` 内的 inspectionScripts 加载剥离 `hasLoaded` 短路，改为每次切到 TAB_SCAN 都调用 `loadInspectionScripts()`，保证「巡检脚本库」Tab 删除/修改脚本后下拉数据不陈旧；`devopsServers` 仍保留 `hasLoaded` 短路避免重复请求；`loadInspectionScripts` 内部 `inspectionScriptsLoadPromise` 复用 in-flight 请求，同一帧内多次切换不会触发 N 次 GET；新增测试 `test_switch_to_scan_tab_always_refetches_inspection_scripts` 验证 inspectionScripts 次数 +1 且 devopsServers 次数不变
- 「巡检脚本库」独立组件：
  - `InspectionScriptLibraryPanel.vue`：左侧节点列表 + 搜索框 + 选中态；`onMounted` 调 `fetchInspectionScripts()`；接收数值型 `refreshToken`，变化后重新拉取列表，使父组件扫描成功后新增/更新脚本立即展示，同时保留搜索词与仍有效的选中态，选中节点消失时 emit `select(null)`；顶部搜索框按 `name / display_name / platform / version` 不区分大小写过滤；点击节点通过 `select` 事件向父组件派发 `script_id`（删除选中节点时传 `null`，父组件据此清空 `librarySelectedScriptId`）；行尾 hover / 选中态时显示 icon-btn 操作组（复用 UserServerManager `icon-btn` 风格）：`✎` 编辑按钮（触发同点击行的 `select`，便于直接定位/刷新右侧编辑器）+ `×` 删除按钮（浏览器原生 `confirm` 二次确认 → 调 `deleteInspectionScript`；失败显示脱敏文案「删除失败，请稍后重试」且节点保留在 `scripts.value`）
  - `InspectionScriptEditorPanel.vue`：右侧编辑表单 + 字段规则表 + 保存；`scriptId` prop；watch 监听 `props.scriptId` 调 `fetchInspectionScriptDetail` 拉详情；表单字段 `display_name / platform / version / inspection_parser / 脚本正文（等宽 textarea）/ inspection_fields`；点保存调 `updateInspectionScript`；成功 emit 'saved'；失败脱敏文案「保存失败，请稍后重试」
- 前端 API 封装（`web/Agent/src/utils/api.js`）：
  - `fetchInspectionScripts()` / `scanInspectionScripts()` / `fetchInspectionScriptDetail(scriptId)`
  - `updateInspectionScript(scriptId, payload)` → `PUT /api/admin/inspection-scripts/{scriptId}`（admin only）
  - `deleteInspectionScript(scriptId)` → `DELETE /api/admin/inspection-scripts/{scriptId}`（admin only；204 No Content）
- **运维控制台去 mock 化 + 智能检测接 collect（2026-08-05 新增）**：
  - `OpsConsoleApp.vue`：`servers` 由 `src/data/ops-console/mockData.js` 静态 import 改为 `ref([])` + `onMounted` 调 `fetchServerInspectionLatest()` 加载；新增 `loadLatest()` 与 `mapSnapshotToServer()` 映射函数：后端 `node_name || business_name` → 前端 `name`；`metrics.cpu/mem/disk` 直传（`null` 显示 `-`）；`disks` 由 `parsed_values.disks` 映射（mount → name，disk_used_pct → used，total 留 `-`）；`os/cpuModel/memTotal/diskTotal/netIn` 本期未采集 → `-`；`ip` 不返 → `-`；`collectedAt` / `errorMessage` 透传。加载失败时 `serversLoadError` 记录原因，servers 保持空数组。
  - `OpsDetailWindow.vue` `runDetect()`（2026-08-05 改造）：原 6 步假动画改为调 `collectServerInspection([server.id])` 触发真实采集+落库，面板输出真实结果（`success / inspection_status / duration_ms / error_message / 逐字段 field_results`），完成后 `emit('collected')`；`OpsConsoleApp` 监听 `collected` 重新调 `loadLatest` 刷新列表；metric 值 `null` 时显示 `-` + 进度条灰底。
  - 前端 API 封装新增：
    - `fetchServerInspectionLatest()` → `GET /api/admin/server-inspection/latest`（admin OR `task-scheduler.server-management` ACL；OwnershipScope 由后端按当前用户过滤）
    - `fetchServerInspectionRecords(serverId, {start, end, limit})` → `GET /api/admin/server-inspection/records`
    - `collectServerInspection(serverIds)` → `POST /api/admin/server-inspection/collect`（404=目标不存在；403=归属越权；response `{collected, items: [{server_id, business_name, success, inspection_status, duration_ms, error_message, field_results}]}`）
- **Subagent 折叠与抽屉**：
  - `SubAgentCard.vue`：通用子智能体折叠卡片（含沙箱），挂在父 AI 气泡的 `timeline.tool` 块内（按 toolCallId 匹配，遵循事件流时序）；工具图标 + 父 prompt 预览 + 状态徽章 + 耗时 + 消息数 + "查看详情" 入口；点击 emit('click', subAgent)
  - `SubAgentDrawer.vue`：通用子智能体详情 Push Drawer；分层展示父 prompt / HumanMessage / AIMessage（含 tool_calls 决策区） / ToolMessage 三类消息 + 底部耗时/消息数/工具调用次数摘要；`renderMessageContent` 扩展支持 LangChain 0.3+ 多模态 ContentBlock（text / thinking / tool_use / tool_result）
- **普通工具卡片**：
  - `ToolCallCard.vue`：普通（非 subagent）工具调用专属卡片，与 `SubAgentCard` 视觉风格对齐；**关键差异：不触发抽屉**（普通工具没有子智能体消息流），body 以"步骤"形式逐步展示每条 SSE 事件（tool_start / tool_progress / tool_stop / tool_error）；头部扳手图标在 `status='running'` 时使用 SubAgentCard 同款 `subagentIconBounce` 闪动动画；默认 `running` 展开、`success/error` 折叠
- **动态排队提示横幅**：
  - `QueueStatusBanner.vue`：**挂在 ChatArea 与 InputBox 之间**（用户要求位置），实时显示 Agent 聊天接口的并发排队状态；黄色系背景 + 橙色感叹号图标 + 位置 badge（带 2s pulse 动画）；Props：`queueStatus: {event, waitingCount, activeCount, maxConcurrency, position, timestamp}` + `isVisible: Boolean`；进场 `slide-down 200ms` / 退场 `fade-out 200ms`；数据由后端 SSE `queue` 事件（`onQueueEvent` 回调）或 HTTP 429 响应驱动
- **视图**（`src/views/`）：`LoginView.vue`、`RegisterView.vue`

### 停止按钮 - 中断待生效（toolStopPending，2026-07-06 新增 / 重构）

**两阶段演进**：
- **第一阶段（2026-07-06 上午）**：UI 态从"发送"扩展到"发送/停止/中断待生效"三态，使用 `toolStopPending` 锁 + `reader.cancel()` + `_stream_helper` 延迟中断机制
- **第二阶段（2026-07-06 下午）**：发现 reader.cancel() 仍会导致子智能体被粗暴取消（前端 reader 关闭 = 收不到后续 SSE 事件），改用 **LangGraph 标准做法**：工具内部检测 abort_event + 主动构造 ToolMessage 返回（避免 CancelledError 打断 ToolMessage 写入）

**核心问题与根因**：
- LLM API 报 `tool call result does not follow tool call (2013)` 的根因是：用户点停止 → 前端 `reader.cancel()` → LangGraph `astream` 协程被粗暴取消 → 工具子智能体来不及 return ToolMessage → checkpoint 中 AIMessage 含 tool_calls 但无对应 ToolMessage → 下次会话恢复时 LLM API 报 2013
- 第一阶段（reader.cancel + `_stream_helper` 延迟中断）只解决"前端不丢事件"，但仍让子智能体被 CancelledError 取消 → ToolMessage 写入被打断
- 第二阶段（abort_event 通道）：让工具**自己检测** abort signal，**主动构造** ToolMessage + `return Command` —— 这是 LangGraph 推荐的"工具失败语义"，比 CancelledError 优雅

**核心机制（第二阶段最终态）**：
1. **前端** `handleStopMessage` 调 `POST /api/agent/{sessionId}/abort`（或知识库路径 `/api/map/knowledge/{sessionId}/abort`）→ 后端 `trigger_abort(session_id)` → 全局 dict `_abort_signals[session_id].set()`
2. **后端 `_stream_helper.py`** 入口 `register_abort_signal(session_id)` 创建 event；finally 块 `unregister_abort_signal(session_id)` 清理；`is_disconnected` 检测时同时 `trigger_abort`（双保险）
3. **后端工具**（sandbox / explore）：从 `request.is_disconnected()` 改为 `get_abort_signal(session_id).is_set()`，主循环每 N chunk 检测一次 → 触发 `stopped_by_user` 分支 → **主动构造** `ToolMessage(tool_call_id=...)` 通过 `return Command` 返回
4. **LangGraph** 收到 `Command(update={"messages": [ToolMessage]})` → 正常推进 → yield `tools` 节点 update → yield `end` 事件 → 自然关闭 SSE
5. **前端 SSE while 循环** 识别白名单事件：`end` / `error` / `interrupt` / **`tools` 节点 update 含 ToolMessage**（abort 真正生效的信号）→ 触发 `clearToolStopPending()` + 清 60s 兜底 timer

**为什么不用 reader.cancel() + 延迟中断**：
- reader.cancel() 让前端 SSE 立即 done → 收不到后续任何事件 → `toolStopPending` 锁只能靠 finally 立即清锁 → UI 永远来不及呈现 stop-pending 态
- abort_event 通道不依赖 reader 状态，事件走全局 dict，后端 yield 的 tools 节点 update 仍能到达前端

**为什么不用纯 LangGraph SDK `AsyncGraphRunStream.abort()`**：
- LangGraph 1.x 的 abort 是 SDK 层概念（`client.threads.stream()` 上下文管理器）
- 项目用裸 `agent.graph.astream()` + 手动 SSE 透传，没有用 LangGraph SDK
- 所以自建 `POST /abort` 端点作为"应用层 abort 协议"，核心机制遵循 LangGraph 推荐做法

**60s 兜底 timer 是什么**：
- 防止后端工具卡死在长 I/O（Docker exec 大文件解压、shell 等待），导致 `toolStopPending` 锁永远不清
- 用户点 stop → 启动 60s timer
- 60s 内收到白名单事件 → clearToolStopPending 清掉 timer
- 60s 到期仍未收到 → 强制 `reader.cancel()` + 追加「[工具执行超时，已强制停止]」+ 清锁

**关键文件改动**：
- 后端 `app/core/tools/_stop_signal.py`（Phase 1）：新增全局 dict `_abort_signals` + `register_abort_signal` / `trigger_abort` / `unregister_abort_signal` / `get_abort_signal` 四个函数；保留原有 ContextVar 机制作为 `is_disconnected` 兜底
- 后端 `app/core/tools/SandboxTools.py`（Phase 2）：从 `request.is_disconnected()` 改为 `get_abort_signal(session_id).is_set()`；保留每 5 chunk 检测频率（不激进到每 chunk）；新增进入 stream 前的预检查
- 后端 `app/routers/_stream_helper.py`（Phase 3）：入口 `register_abort_signal` 创建 event；finally 块 `unregister_abort_signal` 清理；`is_disconnected` 检测时同时 `trigger_abort`（双保险）
- 后端 `app/routers/agent_router.py`（Phase 3）：新增 `POST /api/agent/{session_id}/abort` 路由
- 后端 `app/routers/knowledge_router.py`（Phase 3）：新增 `POST /api/map/knowledge/{session_id}/abort` 路由
- 前端 `web/Agent/src/utils/api.js`（Phase 4）：新增 `triggerAbort(sessionId, options)` 函数
- 前端 `web/Agent/src/App.vue`（Phase 4）：模块级 `toolStopPending` ref + `clearToolStopPending` + `startStopTimeout` 函数；`handleStopMessage` 调 `triggerAbort` 而非 `reader.cancel`；SSE while 循环新增"tools 节点 update 含 ToolMessage"识别分支
- 前端 `web/Agent/src/KnowledgeApp.vue`（Phase 4）：同 App.vue 模式（知识库路径 `isKnowledge=true`）
- 前端 `web/Agent/src/components/InputBox.vue`（第一阶段遗留）：`isStopPending` prop + `stop-pending-mode` class + `handleSendBtnClick` 三态分支 + `.stop-pending-badge` 角标

**状态机矩阵**：

| 触发点 | toolStopPending | isStreaming | 说明 |
|--------|----------------|------------|------|
| handleStopMessage 入口（无 pending） | true | 保持 true | 加锁 + 调 triggerAbort + 启动 60s timer |
| handleStopMessage 入口（已 pending） | - | - | 直接 return（重复点击短路） |
| SSE `client_disconnected` 事件 | true | 保持 true | 锁保持（后端在等工具） |
| SSE `tools` 节点 update 含 ToolMessage | false | 保持 true | **新白名单：abort 真正生效** |
| SSE `end` / `error` / `interrupt` 事件 | false | false | 流走完 |
| SSE 流 done=true | false | false | 自然结束 |
| 60s 兜底 timer 到期 | false | false | reader.cancel + 追加「[工具执行超时]」 |
| handleSendMessage catch / finally | false | - | 异常兜底 |
| newSession / handleSessionSwitch | false | false | 切换兜底 |
| handleApprovalCancel | false | false | HITL 取消兜底 |

**测试覆盖（90+ 用例）**：
- 后端 `app/tests/core/tools/test_stop_signal.py`（11 + 10 = 21 用例）：原有 ContextVar 机制 + 新增 abort signals dict 全套测试（register/trigger/unregister 生命周期、idempotent、并发隔离）
- 后端 `app/tests/core/tools/test_sandbox_abort.py`（4 用例，新增）：abort_event 触发 stopped_by_user 分支、is_disconnected 兜底、abort_event 优先于 is_disconnected、正常完成路径
- 后端 `app/tests/routers/test_agent_router_abort.py`（5 用例，新增）：/abort 端点注册、未注册 session 兜底、已注册 session 触发、idempotent、与 agents-md 路由不冲突
- 后端 `app/tests/features/map_agent/test_map_router_disconnect.py`（9 用例，未改）：原有延迟中断机制测试，仍通过
- 后端 `app/tests/features/map_agent/test_map_router_subagent_stop.py`（5 用例，未改）：子智能体停止信号端到端测试，仍通过
- 后端 `app/tests/core/tools/test_sandbox_tools.py`（45 用例，未改）：辅助函数全套，仍通过
- 前端 `web/Agent/src/components/__tests__/InputBox.stop-pending.spec.js`（11 用例）：三态 class 切换、旋转圆环 + badge 渲染、title 文案、canSend 禁用、点击拦截、handleSendBtnClick 三态分支
- 前端 `web/Agent/src/components/__tests__/App.stop-pending.spec.js`（25 用例，含第二阶段扩展）：纯函数复刻 handleStopMessage + clearToolStopPending + shouldClearToolStopPending（识别 end/error/interrupt/tools update）；新增 triggerAbort 调用、60s timer 启动断言
- 前端 `web/Agent/src/components/__tests__/KnowledgeChat.stop.spec.js`（11 用例，扩展）：stop-pending 样式、handleStop 重复点击短路、handleSendBtnClick 拦截、handleNewChat/handleApprovalCancel 入口清锁

**与既有章节关系**：
- 「精确延迟中断」（`_stream_helper.py:101-201`）：后端延迟中断机制仍存在，但**不是 abort 主路径**（仅作 is_disconnected 兜底）；abort 主路径是 abort_event 通道
- 「停止按钮（中断 LLM 生成）」（知识库章节，2026-06-15 新增）：原始"request.is_disconnected() 检测"机制，保留作为非主动关闭场景的兜底
- 「前端 `isStreaming` 状态同步」（并发排队修复）：保持 isStreaming 复位路径不变
- 「ToolNode 错误处理（handle_tool_errors）」（LangGraph 推荐做法）：本节实现与该做法同源 —— 工具失败时主动 return ToolMessage 而非抛异常

### 口令策略共享 util

- 位置：`web/Agent/src/utils/passwordPolicy.js`
- 暴露：`MIN_LENGTH` / `UPPER_RE` / `LOWER_RE` / `DIGIT_RE` / `SPECIAL_RE` / `validatePassword(value)` / `getPasswordHints(value)`
- 接入：`views/RegisterView.vue`、`components/UserSettingsDialog.vue`（管理员新增 + 本人改密）
- 与后端 `app/shared/utils/auth/password_policy.py` 保持完全同口径；如修改任一端需同步另一端并在 PR 描述中明确。

### 工具函数（src/utils）

- **`api.js`**：登录/注册/验证码/登出/refresh/validate；会话创建/列表/删除/详情/标题/附件/消息/文件空间；文件上传（普通 + 分片 + base64）/下载/列表/删除；SSE `chatStream`（ 起改用 `/api/agent/chat`，新增 `agentName` 参数默认 `map_agent`）/ `knowledgeChatStream`（仍用 `/api/map/knowledge-chat`）；`X-Session-ID` 头注入；附件元数据组装
  - **会话文件空间 API 段**（2026-07-01 新增）：`fetchSessionFileTree(sessionId)` 获取 `/api/session/{id}/files/tree` 树形结构；`previewSessionFile(sessionId, storedPath)` 获取 `/api/session/{id}/files/preview` 预览数据（文本/Markdown 返回 content，Office/PDF/图片返回 file_url）
  - **Admin 会话管理 API 段**（2026-07-01 新增）：`adminBatchDeleteSessions(sessionIds)` 调用 `DELETE /api/session/admin/batch` 批量删除；`adminFetchSessionMessages(sessionId, limit)` 调用 `GET /api/session/admin/{session_id}/messages` 获取任意会话历史消息；`adminExportSessionMarkdown(sessionId)` 调用 `GET /api/session/admin/{session_id}/export/markdown` 导出 Markdown
  - **工具管理 API 段**（2026-06-25 新增）：`listTools` / `listUnregisteredTools` / `registerTool` / `updateTool` / `deleteTool` / `setToolEnabled` / `scanTools` 对应后端 `tool_admin_router` 的 `/api/admin/tools/*` 端点；`getAgentToolBindings` / `updateAgentToolBindings` / `fetchAgentAvailableTools` 对应后端 `agent_admin_router` 的 `/api/admin/agents/{name}/(tool-bindings|available-tools)` 端点
  - **Skill 管理 API 段**（2026-06-29 新增）：`listSkills` / `listUnregisteredSkills` / `registerSkill` / `updateSkill` / `deleteSkill` / `setSkillEnabled` / `scanSkills` 对应后端 `skill_admin_router` 的 `/api/admin/skills/*` 端点；`getAgentSkillBindings` / `updateAgentSkillBindings` / `fetchAgentAvailableSkills` 对应后端 `agent_admin_router` 的 `/api/admin/agents/{name}/(skill-bindings|available-skills)` 端点；所有函数复用既有 `fetchWithAuth` 包装器（401 自动重试一次）
- **AgentManager Skill 绑定 Tab**（2026-06-29 新增，`web/Agent/src/components/AgentManager.vue`）：在 basic / config / tools 三个 Tab 之外新增 `skills` Tab；调用 `fetchAgentAvailableSkills` 拉取可绑定 skill 后按 category 分组渲染可折叠列表，复用工具绑定 Tab 的折叠/勾选/保存模式；`localSelectedSkillBindings` 用 `{skill_name: {enabled, sort_order}}` 记录勾选；`saveSkillBindings` 按分组顺序生成 sort_order 调用 `updateAgentSkillBindings`；`selectAgent` 切换 agent 时若当前在 skills Tab 则立即重载；切换 skill Tab 由 `onSwitchToSkillsTab` 触发
- **`sseParser.js`**：`isThinkingBlock` / `tryParsePythonLiteral` / `extractTextFromBlock` / `processContentBlocks` / `parseMessageContent` / `processSSEEvent` / `createAiMessage`；支持 Python 风格单引号字面量、JSON.parse、regex 回退三级解析
- **`index.js`**：聚合导出

### 浏览器登录 TOTP 两阶段流程

`LoginView.vue` 使用 standalone template，登录状态分为 `password`、`mfa_verify`、`mfa_enroll` 三阶段：

- `password` 阶段调用 `/api/auth/login`，普通成功响应才写入 `localStorage.auth_token/user_role/username/user_id` 并触发 `login-success`。
- `mfa_verify` 阶段仅在内存保存 challenge token，支持 TOTP 与一次性恢复码切换；调用 `/api/auth/mfa/login/verify` 成功后才进入统一登录完成路径。
- `mfa_enroll` 阶段调用登录绑定 start 获取二维码/otpauth URI，再提交动态码确认；恢复码只在当前组件内存中一次性展示，不写 localStorage/sessionStorage。
- `mfa_enroll` 阶段绑定成功 → 暂存 `pendingLoginAuth` + 仅展示恢复码块（含"我已抄写并继续"按钮，data-testid=`mfa-recovery-ack-btn`），**不**立刻调用 `finalizeLogin`：父级 `login-main.js::handleLoginSuccess` 会 `window.location.href = '/Agent/'` 跳页，若同步 finalize 则恢复码"一闪而过"，用户根本看不到；用户点击 ack 按钮后才 `finalizeLogin(pendingLoginAuth)` 走统一完成登录路径。
- challenge/验证码失败、过期或返回密码阶段时清理所有 MFA 临时状态并刷新图形验证码；`resetMfaState()` 同步清空 `pendingLoginAuth` 防内存泄漏。

`UserSettingsDialog.vue` 的个人设置页包含 MFA 管理区域：普通用户可启用、轮换、禁用和重置恢复码；管理员显示强制状态并隐藏禁用操作。二维码、TOTP URI 和恢复码在对话框关闭时清理。

### 认证流（前端）

- **三段式认证**（`App.vue:checkAuth` / `PortalApp.vue:checkAuth` / `KnowledgeApp.vue:onMounted`）：
  1. 优先调用 `validateToken` 验证当前 access token
  2. 失败则调用 `refreshToken` 换新 token，再 `validateToken`
  3. 仍失败则 `clearAuth` + 跳登录页
- **登录页统一入口**：`/login`（独立 HTML 入口，由 `vite.config.js` 多入口构建；`nginx.conf` 通过 `location /login { try_files ... /login.html; }` 路由）。
  - 由 `web/Agent/src/login-main.js` 启动，挂载 `LoginView`，监听 `login-success` 事件并按 `?redirect=` 回跳。
  - `App.vue`（`/Agent/`）与 `PortalApp.vue`（`/portal`）**不**再渲染 `LoginView` / `RegisterView`；未登录时统一通过 `redirectToLogin()` 跳到 `/login?redirect=<原页面>`。
  - `auth.js#isAlreadyOnLoginPage()` 把 `/login` 视为登录页（`buildLoginUrl` 默认目标）。
- **PortalApp 登录页归属**：`PortalApp.vue`（`/portal` 入口）**不**渲染 `LoginView`；未登录时只通过 `redirectToLogin()` 跳转到 `/login?redirect=/portal`，由 `/login` 入口统一渲染登录页。
  - 原因：避免在 `/portal` 短暂渲染 `LoginView` 触发 `/api/auth/captcha` 后被浏览器取消（造成"captcha 调两次，第一次失败"），以及避免"登录页闪烁两次"。
  - `PortalApp.checkAuth` 失败路径**不**置 `authReady.value = true`；只有成功路径（已登录）才置 `authReady=true`，让 Vue 渲染门户导航栏。
- **App.vue 不再渲染 LoginView**：`App.vue`（`/Agent/` 入口）同样**不**渲染 `LoginView` / `RegisterView`；未登录时通过 `redirectToLogin()` 跳到 `/login?redirect=/Agent/`。这样消除了"`auth-loading-screen` 占位 → `LoginView`"的一次视觉切换。
- **localStorage 键**：
  - `auth_token`：access token（每次请求 `Authorization: Bearer`）
  - `username` / `user_role` / `user_id`：用户基本信息
  - `session_id`：主 Agent 当前会话
  - `knowledge_session_id`：知识库独立会话（与主会话隔离，独立创建）
- **refresh_token 不存 localStorage**，由后端通过 HttpOnly Cookie 下发（`SameSite=Strict; Path=/api/auth`）
- **401 自动重试**：API 返回 401 → 自动 `refreshToken` → 用新 token 重试原请求，最多 1 次，失败跳登录

### SSE 流式与 HITL

- **后端 SSE 端点**：`/api/agent/*`（主聊天）、`/api/map/knowledge-chat`（知识库聊天）
- **事件格式**：`data: {json}\n\n`，由 `sseParser.js` 解析为以下块：
  - `text`：AI 回复正文
  - `thinking`：思考过程（折叠展示）
  - `timeline`：工具调用时间线
  - `tools`：工具调用记录
  - `interrupt`：HITL 中断（payload = `{action: "ask_user_question", questions: [...]}`）
- **HITL 恢复**：`HumanApprovalBox` 提交 `{answers: string[][]}` → `chatStream(..., resumeData)` → 后端 `Command(resume=...)` 继续执行
- **渲染**：`MessageBubble` 统一展示，marked 转 HTML、highlight.js 代码高亮
- **与飞书侧流式的边界**：本节 SSE 流式仅服务前端 Web 入口，由 `app/routers/_stream_helper.py` 统一包装（**飞书流式卡片输出改造一行未改此文件**）。飞书 WebSocket 入口的流式输出走独立路径：`FeishuWebSocketService._call_agent` → `StreamEventSource` → `ChannelConsumer` → CardKit patch（详见「飞书流式卡片输出（多渠道架构）」章节）。两条路径互不影响，abort 信号共用 `register_abort_signal` / `trigger_abort` 全局 dict

### Vite 开发代理（vite.config.js）

- 代理 `/api` → `VITE_API_TARGET`（默认 `http://localhost:8001`）
- 对 `/api/*/chat` 路径做 SSE 友好头处理：
  - 请求头：`Connection: keep-alive`、`Cache-Control: no-cache`、`Accept: text/event-stream`
  - 响应头：删除 `content-length`、设置 `cache-control: no-cache`、`connection: keep-alive`、`x-accel-buffering: no`
- **目的**：保证 LLM 流式输出不被 nginx/反代 buffer 截断

### 前端 XSS 加固（2026-08-07 新增）

- **目标**：消除 marked.parse + v-html、contenteditable、PortalApp iframe、HTTP 响应头缺失等 9 类 XSS 风险。
- **覆盖范围**：`web/Agent/src/utils/sanitize-marked.js`（新建）+ `MessageBubble.vue` + `FilePreview.vue` + `InputBox.vue` + `PortalApp.vue` + `nginx.conf`。

#### 1. 公共 Markdown 安全渲染工具 — `src/utils/sanitize-marked.js`

- **职责**：marked 解析 + DOMPurify sanitize + 字符串兜底注入安全属性。
- **关键设计**：
  - 显式 `marked.parse(text, { async: false })` 强制同步返回 string（不受全局 `marked.use({ async: true })` 影响；T1 验证）。
  - DOMPurify 默认 `ALLOWED_URI_REGEXP` 已支持 http/https/mailto/相对路径，禁止 `javascript:` / `data:` / `vbscript:` 等（T5 验证）。
  - **双保险**：DOMPurify `afterSanitizeAttributes` hook（浏览器原生）+ 字符串 regex 兜底（happy-dom / jsdom 等 DOM 半残环境）注入 `<a target="_blank" rel="noopener noreferrer">` 与 `<img loading="lazy" style="max-width:100%;height:auto">`。
  - happy-dom 下 DOMPurify hook `setAttribute` 写入后会被最终字符串化时丢失（验证见 `__tests__/sanitize-marked.test.js`），所以生产代码也保留字符串兜底逻辑。
- **适用范围**：`MessageBubble.vue::renderedText`、`renderMarkdown`；`FilePreview.vue::renderedContent`。
- **测试**：`src/utils/__tests__/sanitize-marked.test.js`，主动构造 `JSDOM + DOMPurify` 实例跑端到端验证；11 个用例全部通过。

#### 1.1 iframe src 校验（`PortalApp.vue::safeIframeUrl`）

- **2026-08-07 验证事件**：单独诊断时发现 `ProfileInputBox.vue` 缺 `import { onMounted }` 的 bug（**与本次加固无关**, 已存在），导致 `<KnowledgeApp>` 在 `showChat=false` 路径上渲染 setup 抛 `onMounted is not defined`，整个组件树渲染失败 → 用户看到的"规则库 iframe 空白"实际是 `<KnowledgeApp>` 没渲染完。修复后 iframe 正常显示。
- **iframe 加固仅保留**：`:src="safeIframeUrl(getActiveItem().url)"` + 新增 `safeIframeUrl()` 函数拒绝 `javascript:` / `data:` / `vbscript:` / `file:` 协议；**不**额外加 `sandbox` / `referrerpolicy` / `loading="lazy"`（保守起见，dev 阶段 iframe 渲染已稳定后再考虑引入）。

#### 2. `MessageBubble.vue` 改造

- 替换 `import { marked } from 'marked'` → `import { safeMarkdown } from '../utils/sanitize-marked.js'`。
- `renderedText` 与 `renderMarkdown` 函数体从 `marked.parse(renderTriggerMentions(text))` 改为 `safeMarkdown(renderTriggerMentions(text))`。
- 用户消息已用 `renderTriggerMentions(..., { escapeHtml: true })` 渲染，本次未改 `renderedContent`。

#### 3. `FilePreview.vue` 改造

- `renderedContent` computed 从 `marked.parse(props.content)` 改为 `safeMarkdown(props.content)`。

#### 3.5 `ProfileInputBox.vue` 预存 bug 修复（与加固无关）

- **症状**：在 PortalApp 规则库 iframe（指向 `/knowledge.html`）打开后，整个页面渲染失败 → 完全空白。
- **根因**：`<script setup>` 中只 `import { ref, computed, nextTick } from 'vue'`，但第 131 行调用了 `onMounted(...)`。
- **修复**：补 `onMounted` 到 import 语句。
- **触发链路**：`KnowledgeApp.vue` 在 `welcome-section`（`v-if="!showChat"`）渲染 `<ProfileInputBox>` → setup 抛 `onMounted is not defined` → 整个组件树渲染异常 → `#app` 子节点为 0。
- **影响范围**：`KnowledgeApp.vue` 进入页面的所有路径（不仅是规则库 iframe）。

#### 4. `InputBox.vue` 改造

- `sanitizeEditorHtml` 升级：
  - 显式列出 `allowedAttrs`（仅保留 chip 必需属性：`data-trigger-id` / `data-business-name` / `data-server-type` / `data-mention-class` / `class` / `title` / `contenteditable`）。
  - 黑名单属性：`/^(on\w+|formaction|srcdoc|action)$/i`，命中即 `removeAttribute`。
  - 黑名单 URL 协议：`javascript: / data: / vbscript: / file:` 用于 `href` / `src`。
- `handleEditorPaste` 注释更新为「仅取纯文本 + 现代 Range API」，已有实现本就如此，仅补注释说明。

#### 5. `PortalApp.vue` 改造

- `safeIframeUrl(url)` 函数：拒绝 `javascript: / data: / vbscript: / file:`，返回 `'about:blank'`。
- `<iframe>` 元素：
  - `:src="safeIframeUrl(getActiveItem().url)"`
  - `sandbox="allow-scripts allow-same-origin allow-forms allow-popups"`
  - `referrerpolicy="no-referrer"`
  - `loading="lazy"`

#### 6. `nginx.conf` 改造

- `server { ... }` 顶部新增 4 个响应头（`always;` 持久化）：
  - `Content-Security-Policy: default-src 'self'; script-src 'self' 'unsafe-inline' 'unsafe-eval'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; font-src 'self' data:; connect-src 'self'; frame-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self';`
  - `X-Frame-Options: SAMEORIGIN`
  - `X-Content-Type-Options: nosniff`
  - `Referrer-Policy: strict-origin-when-cross-origin`
- CSP 第一版保留 `unsafe-inline` / `unsafe-eval` 以兼容 Vite dev 模式；后续评估移除。

#### 7. 依赖变更（package.json）

- `dompurify: ^3.2.0`（新增，`dependencies`）。
- `jsdom: ^x.x.x`（`devDependencies`，仅供 sanitize-marked 单测使用）。

#### 8. 后续工单（不在本期范围）

- **iframe sandbox 收紧**：本期保留 `allow-same-origin`，第三方 iframe 仍能访问 localStorage；后续应改 `postMessage` 父传子 + 关闭 `allow-same-origin`（`sandbox="allow-scripts allow-forms allow-popups"`）。
- **frame-src 动态白名单**：当前 `frame-src 'self'` 与 PortalApp 跨域 URL（`http://10.20.8.178:7777/webgis/kjzr`）有冲突；阶段 1 已要求运维治理 app-config.json 维护规范，阶段 2 应在 Vite 构建期读取 navItems 生成白名单注入 nginx。
- **localStorage token**：已落地 HttpOnly Cookie（2026-08-08 后端 + 2026-08-08 前端 api.js/auth.js + 4 入口组件切换；2026-08-08 完成 15 个存量 spec 适配清理）；后续工单仅剩"4 入口组件之外是否还有组件残留 auth_token 引用"的兜底审查（按需）。

### 部署（Nginx + Docker）

- **`Dockerfile`**：多阶段构建 — `node:20-alpine` 构建 → `nginx:alpine` 运行
- **启动注入**：通过 `envsubst ${VITE_API_TARGET}` 把环境变量写入 `nginx.conf` 模板
- **`nginx.conf` 关键点**：
  - **SPA fallback**：`try_files $uri $uri/ /index.html`
  - **静态资源**：1 年缓存 + `Cache-Control: public, immutable`
  - **/api 反代**：`proxy_buffering off`、`proxy_cache off`、`chunked_transfer_encoding on`、支持 WebSocket Upgrade
  - **超时**：connect 60s、send/read 300s（支持长时 LLM 生成）
  - **健康检查**：`/health` 返回 `200 healthy\n`
  - **2026-08-07 新增**：见「前端 XSS 加固」章节，新增 CSP + 三大响应头。

### Portal 运行时配置

- **配置来源**：`public/app-config.json`（运行时 JSON，Vite 构建时自动复制到输出根目录）
- **配置模块**：`web/Agent/src/config/portal.js`（统一配置中心）
  - `loadAppConfig()`：应用启动时 `fetch('/app-config.json')`，将配置合并到响应式 `appConfig`
  - `getNavItems()`：获取导航项列表（从 `appConfig.navItems` 读取，校验失败回退默认）
  - `appConfig`：Vue `reactive` 对象，含 `brandTitle`、`brandDesc`、`navItems`
- **配置字段**：
  - `brandTitle`：品牌主标题（显示在导航栏、登录页、注册页、浏览器标签页）
  - `brandDesc`：品牌副标题/描述（显示在登录页品牌区）
  - `navItems`：导航项数组，字段同 NavItem
- **NavItem 字段**：
  - `key`：唯一键
  - `label`：显示文字
  - `type`：`'placeholder'`（占位提示） | `'iframe'`（嵌入 iframe）
  - `url`：type=iframe 时必填，相对路径或绝对 URL
  - `targetOrigin`：postMessage 的 targetOrigin；缺省时按 url 推断
- **默认配置**（`app-config.json` 缺失或解析失败时回退）：
  ```js
  {
    brandTitle: '沈阳市自然资源和规划"一点通"',
    brandDesc: '智慧政务服务平台',
    navItems: [
      { key: 'site-select', label: '智能选址', type: 'iframe', url: 'http://59.197.227.228/webgis/kjzr' },
      { key: 'pre-check', label: '智能预检', type: 'iframe', url: 'http://59.197.227.228/webgis/kjzr' },
      { key: 'rule-lib', label: '规则库', type: 'iframe', url: '/knowledge.html' }
    ]
  }
  ```
- **使用示例**（修改 `web/Agent/public/app-config.json`，无需重新打包）：
  ```json
  {
    "brandTitle": "自定义标题",
    "brandDesc": "自定义描述",
    "navItems": [
      { "key": "site-select", "label": "智能选址", "type": "iframe", "url": "http://59.197.227.228/webgis/kjzr" },
      { "key": "pre-check", "label": "智能预检", "type": "iframe", "url": "http://59.197.227.228/webgis/kjzr" },
      { "key": "rule-lib", "label": "规则库", "type": "iframe", "url": "/knowledge.html" }
    ]
  }
  ```

### 配置优先级契约「JS DEFAULT_LOGIN_THEME 全局优先」（2026-08-20 升级）

`web/Agent/src/config/portal.js` 模块内的 `DEFAULT_LOGIN_THEME`（含 brandTitle / brandDesc / loginTitle / loginSubtitle / registerSubtitle / footerText / footerLink / copyright 八个 LoginTheme 字段）是**主配置源**；`app-config.json` 仅作为「JS 未声明字段」的兜底数据源。

- **核心判据**：`isJsDeclared(key) === (typeof DEFAULT_LOGIN_THEME[key] === 'string' && DEFAULT_LOGIN_THEME[key].trim() !== '')`。返回 true → JSON 同名字段**不得写入** appConfig / `loginThemes.default`；返回 false（用户主动把 JS 改成空字符串占位） → JSON 接管。
- **`loadAppConfig()` 写入规则**：
  1. 顶层 `brandTitle` / `brandDesc` → 仅在 `isJsDeclared(...) === false` 时由 JSON 兜底写入
  2. `loginThemes.default` → 走 `normalizeLoginTheme(raw, { allowJsOverride: false })`：JSON 同名字段被忽略；合并阶段 `{ ...themesMap, default: { ...DEFAULT_LOGIN_THEME } }` 强制以 JS 字面量为准
  3. `loginThemes.<非 default>`（如 `xemployee` / `YDT`） → 完全由 JSON 控制，JS 不参与（`normalizeLoginTheme(raw)` 默认行为）
  4. `navItems` → 维持旧行为：JSON 存在且合法则使用 JSON，否则回退 `DEFAULT_NAV_ITEMS`
- **`syncBrandFields()` 反向保护**：仅当主题对象 `brandTitle` / `brandDesc` 是非空字符串时才同步到 `appConfig.brandTitle` / `brandDesc`——避免主题对象空字符串占位时擦掉 JSON 顶层刚写入的值。
- **导出约定**：`DEFAULT_LOGIN_THEME` 同时 `export` 仅供测试用例等价比对字面量；**生产代码禁止依赖此 export**，应走 `appConfig` / `getCurrentLoginTheme`。
- **对运维的副作用**：修改 JSON 中与 JS 同名的 default 主题字段**不再生效**（top-level brandTitle/brandDesc / `loginThemes.default.*` 字段都是）；用户若需 JSON 接管某个字段，需要把 JS `DEFAULT_LOGIN_THEME` 对应字段置空字符串占位。`public/app-config.json.example` 顶部 `_precedence_comment` 已声明此约束。
- **测试**：`web/Agent/src/config/__tests__/portal.theme.spec.js` 15 用例覆盖「JS 优先 / JSON 接管 / YDT 等非 default 主题不受影响 / 大小写 key / 删除主题回退 default」。

### 设计系统（src/styles/variables.css）

- **颜色 token**：`--color-bg-{primary,secondary,tertiary,hover,active}`、`--color-border`、`--color-border-light`、`--color-text-{primary,secondary,muted,inverse}`、`--color-accent` / `-hover` / `-light`、`--color-{success,warning,error,info}`
- **Tag 配色**：`--color-tag-{beta,new,free}` + 对应文字色
- **圆角**：`--radius-{sm:8, md:10, lg:12, xl:16, full:9999}`
- **阴影**：`--shadow-{sm, md, lg}`
- **间距**：`--space-{xs:4, sm:8, md:12, base:16, lg:24, xl:32, 2xl:48}`
- **字体**：`--font-family`（系统字体栈 + PingFang SC + Microsoft YaHei）、`--font-size-{xs..2xl}`、`--font-weight-{normal,medium,semibold,bold}`
- **过渡**：`--transition-fast` / `--transition` / `--transition-slow` / `--transition-colors` / `--transition-transform` / `--transition-opacity` / `--transition-shadow`
- **可访问性**：`--focus-ring` / `--focus-ring-inset`
- **布局**：`--sidebar-width: 260px`、`--topbar-height: 56px`、`--min-layout-width: 1024px`
- **z-index 分层**：dropdown 100 / sticky 200 / modal 300 / tooltip 400

### 测试（Vitest）

- **配置文件**：`vitest.config.js`（happy-dom 环境）
- **运行脚本**：`npm test`（单次）、`npm run test:watch`（监听）、`npm run test:coverage`（覆盖率）
- **测试分布**（`src/**/__tests__` 与 `src/components/__tests__`）：

  - `HumanApprovalBox.spec.js`：HITL 组件（多 Tab、虚拟 Other 项、多选、`canSubmit` 门控，14 用例）
  - `api.test.js`：`utils/api.js` 工具方法
  - `api.mcp.test.js`：MCP 管理 API 封装（**18** 用例 = 8 happy-path URL/方法/请求体验证 + 1 `updateMcpServer` PUT body + 9 失败路径验证 `detail` 错误消息）
  - `sseParser.test.js`：SSE 解析（含 Python 字面量兼容）
  - `subAgentParser.test.js`：subagent 解析（custom 事件维护 subAgents 列表 + sandbox_summary 合并 + 工具函数，**14** 用例）
  - `SubAgentCard.spec.js`：折叠卡片（**11** 用例）
  - `SubAgentDrawer.spec.js`：独立 Push Drawer（**19** 用例）
  - `MessageBubble.spec.js`：timeline.tool 内按 toolCallId 渲染 SubAgentCard 等（5 用例）
  - `UserSettingsDialog.subagent.spec.js`（2026-07-02 新增）：历史会话详情弹窗居中 CSS 回归保护 + 子智能体事件冒泡链路（**5** 用例）


**背景**：上一节"停止按钮（中断 LLM 生成）"仅停止主智能体的 LangGraph astream，但子智能体（sandbox / explore）工具函数内的 `for chunk in child_agent.stream(...)` 是同步 for 循环，没有任何停止信号感知。子智能体会一直运行直到自然结束，消耗 LLM token、占用 Docker 容器，停止按钮无法真正中断。

**目标**：让前端停止按钮的 `reader.cancel()` 信号穿透到子智能体层，使前端停止按钮真正中断所有 LLM 生成。

### 核心机制：contextvars 传递 Request

**新增文件**：`app/core/tools/_stop_signal.py`

通过 ``contextvars.ContextVar`` 在主路由入口挂 FastAPI Request，工具函数（sandbox / explore）内通过 ``get_current_request()`` 取出，调用 ``await request.is_disconnected()`` 检测客户端断开。

- asyncio 任务在同一 context 内自动继承 ContextVar，多请求并发时各请求独立隔离，无竞态
- 同步工具函数也能兼容（先 `get_current_request()` 取出 Request，在需要时 `await is_disconnected()`）
- finally 块必须 reset，避免后续请求继承到错误的 request 引用导致内存泄漏 + 跨请求误判

**API**：

```python
from app.core.tools._stop_signal import (
    set_current_request,   # 主路由入口：挂 request
    reset_current_request, # finally 块：清理（传 token）
    get_current_request,   # 工具函数：取出（可能为 None）
)
```

### sandbox / explore 工具 async 化

核心改动：

- ``def sandbox`` → ``async def sandbox``（同步 for → async for + astream）
- ``def explore`` → ``async def explore``（同上）
- astream 循环内每 ``_STOP_CHECK_INTERVAL = 5`` 个 chunk 检查一次 ``request.is_disconnected()``
- 客户端断开时立即 break + 推送 ``tool_stop`` 事件，``data.status = "stopped_by_user"``（区别于 "success" / "failure"）
- sandbox 停止时**必须 cleanup middleware**（Docker 容器清理），避免容器残留

**停止事件数据格式**（`tool_stop` 事件）：

```json
{
  "status": "stopped_by_user",
  "result": { "answer": "子智能体已被用户中止", ... },
  "duration_ms": ...,
  "final_summary": { "current_step": 0, "status_message": "已被用户中止", ... },
  "thread_id": "...",
  "final_messages": [...],   // 保留 subagent 字段，前端仍能看到中间消息
  "parent_prompt": "..."
}
```

### map_router 挂载 ContextVar

map_router 实现：

- `generate_stream_response` 函数入口 `set_current_request(request)`，把 FastAPI Request 挂到 ContextVar
- finally 块 `reset_current_request(cv_token)`，避免后续请求继承错误引用
- 即使 `is_disconnected()` 触发 return 提前退出，也保证清理

### 客户端状态显示

**`web/Agent/src/components/SubAgentCard.vue`** + **`web/Agent/src/components/ToolCallCard.vue`** 状态映射：

- `status === 'stopped_by_user'` 状态映射：显示"已中止"文本
- CSS class `.stopped_by_user`：橙色徽章（区别于 success 绿色、error 红色、running 紫色）
- stopped_by_user 状态**静态显示**（无 pulse 动画），与 running 区分

**`web/Agent/src/utils/sseParser.js`** 状态判定：

- `updateSubAgentFromCustomEvent` 中 tool_stop 事件状态判定逻辑优先级（向后兼容）：`stopped_by_user` > `error` / `failure` > 其他（含无 status / `success`）→ success
- 旧事件无 status 字段默认 success（向后兼容普通工具 tool_stop）

### 测试覆盖

### 兼容性

- **旧工具 tool_stop 事件**（无 status 字段）：默认 success 状态（向后兼容）
- **HuggingFace 客户端**：不感知停止按钮，行为不变
- **HITL 场景**：与现有 interrupt 路径共存（前端 `reader.cancel()` 触发后端 `is_disconnected()`，主 astream 跳出后子智能体也跳出）
- **第三方 iframe / portal 调用方**：不感知停止按钮，按原行为运行到底

### 已知工程实践

- **conftest 下 @tool 是 identity**：`@tool` 装饰器在 conftest 中被 mock 为 `lambda *args, **kwargs: lambda func: func`，所以 `sandbox` / `explore` 在测试环境就是原 async 函数。生产环境（conftest 不生效时）`@tool` 会把 async 函数包装为 `StructuredTool` 并保留 `.coroutine` 指向原函数。两种环境下 `asyncio.run(SandboxTools.sandbox(prompt, runtime))` 都能工作
- **MagicMock 属性赋值**：`mock_agent.astream = fake_astream` 后，`mock_agent.astream` 返回 fake_astream，调用 `mock_agent.astream(args, kwargs)` 拿 async generator object。`call_args_list` 记录的是直接调用，需要用 `mock_writer.return_value.call_args_list` 才能拿到 sandbox/explore 函数内部 `writer(...)` 的调用
- **contextvar reset LIFO 语义**：`set(A) → token1, set(B) → token2, reset(token2) → get() == A, reset(token1) → get() == default`

## 前端 MCP 管理 API 封装

在 `web/Agent/src/utils/api.js` 末尾追加 9 个导出函数，对应后端 `mcp_admin_router`的 8 个端点 + Agent 列表端点。所有函数复用已有的 `fetchWithAuth` 包装器（自动注入 `Authorization: Bearer` 与 `X-Session-ID`，401 自动重试）。

### 模块位置

```
web/Agent/src/utils/
├── api.js                              # 追加 9 个 MCP/Agent API 函数
└── __tests__/
    └── api.mcp.test.js                 # MCP API 测试（8 用例）
```

### 函数清单

| 函数                                             | HTTP 方法 | 路径                                                                     | 说明                                     |
| ------------------------------------------------ | --------- | ------------------------------------------------------------------------ | ---------------------------------------- |
| `listMcpServers()`                             | GET       | `/api/admin/mcp/servers`                                               | 列出所有 MCP server 配置                 |
| `createMcpServer(config)`                      | POST      | `/api/admin/mcp/servers`                                               | 新增 server；body 为 JSON 配置           |
| `updateMcpServer(name, config)`                | PUT       | `/api/admin/mcp/servers/{name}`                                        | 更新 server 配置                         |
| `deleteMcpServer(name)`                        | DELETE    | `/api/admin/mcp/servers/{name}`                                        | 删除 server；无返回值                    |
| `toggleMcpServer(name, enabled)`               | POST      | `/api/admin/mcp/servers/{name}/toggle?enabled={bool}`                  | 启用/禁用 server                         |
| `listMcpMethods(name)`                         | GET       | `/api/admin/mcp/servers/{name}/methods`                                | 列出 server 下所有 method                |
| `refreshMcpMethods(name)`                      | POST      | `/api/admin/mcp/servers/{name}/refresh-methods`                        | 刷新 method 列表                         |
| `toggleMcpMethod(serverName, method, enabled)` | POST      | `/api/admin/mcp/servers/{name}/methods/{method}/toggle?enabled={bool}` | 启用/禁用单个 method                     |
| `fetchAgentList()`                             | GET       | `/api/agent/list`                                                      | 获取可用 Agent 列表（供 MCP 配置页绑定） |

### 设计要点

- **复用 fetchWithAuth**：所有函数通过 `fetchWithAuth` 发起请求，自动处理鉴权与 401 重试，无需重复实现
- **URL 编码**：`name` / `method` 路径参数使用 `encodeURIComponent` 编码，防止特殊字符破坏 URL
- **错误处理**：`createMcpServer` 解析后端 `detail` 字段抛出具体错误信息；其余函数抛 `HTTP {status}` 通用错误
- **deleteMcpServer**：唯一无返回值的函数（204 No Content），不调用 `response.json()`

### 测试

- 路径：`web/Agent/src/utils/__tests__/api.mcp.test.js`（8 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../api.js')` 使 mock 生效
- 覆盖：listMcpServers URL + 返回值 / createMcpServer body / deleteMcpServer DELETE 方法 / toggleMcpServer enabled 参数 / listMcpMethods URL / refreshMcpMethods POST / toggleMcpMethod enabled 参数 / fetchAgentList URL + 返回值

## 前端 MCP 服务器管理组件

创建 `McpServerManager.vue` 组件，基于  的 8 个 MCP API 函数实现 MCP 服务器的可视化管理界面。

### 模块位置

```
web/Agent/src/components/
├── McpServerManager.vue                          # MCP 服务器管理组件
└── __tests__/
    └── McpServerManager.spec.js                  # 组件测试（6 用例）
```

### 功能要点

- **左侧服务器列表**：展示所有 MCP server，每项含 toggle 开关（启用/禁用）、类型标签、tags
- **右侧详情面板**：三种状态切换
  - 新增/编辑表单（`.server-form`）：支持 sse/stdio/http 三种类型，stdio 类型显示 Command JSON 输入框
  - 服务器详情（`.server-detail`）：展示名称/类型/URL/tags/状态，含编辑/删除按钮
  - 方法列表（`.methods-section`）：含"刷新方法列表"按钮，每个方法可独立 toggle
- **空状态**：无服务器时显示"暂无 MCP 服务器"提示

### 依赖关系

- 复用  的 `api.js` 中 8 个 MCP 函数（listMcpServers/createMcpServer/updateMcpServer/deleteMcpServer/toggleMcpServer/listMcpMethods/refreshMcpMethods/toggleMcpMethod）
- 使用 Vue 3 `<script setup>` 语法，`onMounted` 时自动加载服务器列表

### 测试

- 路径：`web/Agent/src/components/__tests__/McpServerManager.spec.js`（6 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，使用 `mount` + `flushPromises` 模式
- 覆盖：组件可导入 / 渲染服务器列表 / 点击服务器项选中 / 点击新增按钮显示表单 / 选中后显示刷新方法按钮 / 空状态提示

## 前端 UserSettingsDialog MCP 管理 Tab 集成

将  的 `McpServerManager.vue` 组件集成到 `UserSettingsDialog.vue` 的 admin Tab 中，让管理员可以在用户设置对话框中管理 MCP 服务器。

### 修改要点

- **import**：在 `UserSettingsDialog.vue` 顶部新增 `import McpServerManager from './McpServerManager.vue'`
- **navItems**：在 admin 分支的 `session-query` 之后追加 `{ id: 'mcp-management', label: 'MCP 管理', icon: '...' }`
- **template**：在 session-query 的 `v-show` div 之后平级追加 `<div v-show="activeTab === 'mcp-management'" class="tab-content mcp-tab-content"><McpServerManager /></div>`，遵循现有 `v-show` 模式（非 `v-else-if`）

### 测试

- 路径：`web/Agent/src/components/__tests__/UserSettingsDialog.mcp.spec.js`（3 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`；因 `UserSettingsDialog` 使用 `<Teleport to="body">`，nav-item 与 tab 内容渲染到 `document.body`，需通过 `document.body.querySelectorAll` / `document.body.querySelector` 查询元素（`wrapper.findAll` / `wrapper.find` 无法穿透 Teleport）
- 覆盖：admin 角色显示 MCP 管理 Tab / 普通用户不显示 MCP 管理 Tab / 点击 MCP Tab 后渲染 `.mcp-server-manager` 组件

## 前端 UserSettingsDialog 普通用户显示左侧导航栏

`UserSettingsDialog` 不再根据 `role` 条件渲染 `.dialog-nav`，所有角色都使用水平布局（`dialog-body-horizontal`），左侧导航栏始终可见；普通用户仅展示「个人设置」一项，admin 维持原有 8 项不变。标题文案统一为「用户设置与管理」。

### 修改要点

- **template（dialog-title）**：去掉 `isAdmin` 三元表达式，统一为静态文本 `用户设置与管理`
- **template（dialog-body）**：`:class="{ 'dialog-body-horizontal': isAdmin }"` → 静态 `class="dialog-body dialog-body-horizontal"`，所有角色均使用水平布局
- **template（dialog-nav）**：`v-if="isAdmin"` 移除，左侧导航栏对所有用户可见
- **navItems 计算属性**：保持原状——普通用户天然只返回 `[{ id: 'profile', label: '个人设置', ... }]`，admin 在此基础上追加 7 项
- **isAdmin 计算属性**：保留（组件内部仍依赖其判断 admin 专属 tab 的 `v-show` 与数据加载）

### 视觉与行为契约

- 普通用户打开「设置」后：左侧出现 200px 宽导航栏，仅显示「个人设置」一项且默认 active；右侧内容区域为个人资料表单
- 单项导航栏下方空白由 `.dialog-nav` 的 `flex-direction: column` 自然处理，菜单项贴顶部对齐
- 原有 admin 多 Tab 工作流（用户管理 / 智能体管理 / MCP / 工具 / Skill / 运维 / 邮件）不受影响

### 测试

- 路径：`web/Agent/src/components/__tests__/UserSettingsDialog.user-sidebar.spec.js`（6 用例）
- 测试策略：与 mcp.spec.js 一致，依赖 `document.body.querySelectorAll` 穿透 `<Teleport to="body">`
- 覆盖：普通用户能看到 `.dialog-nav` / 普通用户只显示「个人设置」一项 / 普通用户 dialog-body 含 `dialog-body-horizontal` 类 / 普通用户标题统一为「用户设置与管理」 / 普通用户进入 dialog 时「个人设置」默认 active / admin 回归 8 项导航 + 标题不变

## 前端斜杠命令注册表

新建 `web/Agent/src/utils/commandRegistry.js` 作为前端斜杠命令的统一注册表与分发器。`InputBox.vue` 检测到 `/` 开头输入时调用 `handleCommand`。

### 模块位置

```
web/Agent/src/utils/
├── commandRegistry.js                 # 命令注册表 + handleCommand 分发器
└── __tests__/
    └── commandRegistry.test.js        # 测试（9 用例）
```

### 命令清单

| 命令              | 用法                 | 说明                                           | requiresBackend |
| ----------------- | -------------------- | ---------------------------------------------- | --------------- |
| `/agent <name>` | `/agent map_agent` | 切换当前会话使用的智能体；找不到时返回可用列表 | true            |
| `/agents`       | `/agents`          | 列出所有可用智能体（调用 `fetchAgentList`）  | true            |

### 导出 API

| 导出                             | 作用                                                                             |
| -------------------------------- | -------------------------------------------------------------------------------- |
| `COMMAND_REGISTRY`             | 命令元数据数组，供 InputBox 自动补全/提示                                        |
| `handleCommand(command, args)` | 命令分发器，返回 `{text, switchAgent?}`；未知命令返回 `未知命令：/<command>` |
| `listAgentsCommand()`          | `/agents` 命令实现，返回格式化文本；空列表返回"暂无可用智能体"                 |

### 设计要点

- **复用 fetchAgentList**：`/agent` 与 `/agents` 均调用 `api.js::fetchAgentList`（GET `/api/agent/list`），返回 `Array<{name, display_name}>`（**无 description 字段**，渲染时只用 name + display_name）
- **错误传播**：`fetchAgentList` 失败时抛出 `Error`（含后端 `detail`），`handleCommand` 与 `listAgentsCommand` 均不吞错，由调用方（InputBox）捕获并展示友好提示
- **requiresBackend 预留字段**：当前未消费，预留给未来离线模式跳过后端调用
- **switchAgent 信号**：`/agent <name>` 成功时返回 `switchAgent` 字段，InputBox 据此切换实际请求的 agent_name

### 测试

- 路径：`web/Agent/src/utils/__tests__/commandRegistry.test.js`（9 用例）
- 测试策略：mock `global.fetch` 与 `global.localStorage`，通过动态 `import('../commandRegistry.js')` 使 mock 生效
- 覆盖：COMMAND_REGISTRY 含 agent+agents / handleCommand 切换智能体 / 未知命令 / 缺参数 / 智能体不存在 / listAgentsCommand 列表非空 / listAgentsCommand 空列表 / listAgentsCommand 网络错误 / handleCommand 后端失败错误传播

### InputBox 集成

`InputBox.vue` 已接入命令注册表，检测到 `/` 开头输入时走命令分支，不再触发 refreshToken 与文件上传流程。

**改动点**：

1. **import**：新增 `import { handleCommand, COMMAND_REGISTRY } from '../utils/commandRegistry.js'`
2. **计算属性**：新增 `isCommand`（判断 `/` 开头）、`parsedCommand`（统一解析命令名+参数）与 `commandHint`（复用 `parsedCommand` 匹配 COMMAND_REGISTRY 返回描述+用法提示，未知命令返回 `未知命令：/<cmd>`）
3. **emits 声明**：新增 `agent-switched` 事件（`/agent <name>` 成功时携带目标 agent name）
4. **executeCommand 函数**：从 handleSend 抽取的独立命令执行函数；通过 `isExecutingCommand` ref + try/finally 保证命令执行期间 `canSend` 为 false，防止用户重复点击发送导致重复触发
5. **handleSend 命令分支**：在函数开头检测 `text.startsWith('/')`，命中时调用 `executeCommand(text)` 后提前 return；不进入 refreshToken 流程
6. **template**：textarea 后新增 `<div v-if="isCommand" class="command-hint">{{ commandHint }}</div>`
7. **CSS**：新增 `.command-hint` 样式（accent 色 + accent-light 背景 + radius-sm 圆角）

### InputBox 智能体快速选择

输入 `/` 后不再仅显示命令提示，而是弹出下拉菜单列出所有可用智能体，选中后以上方标签形式展示，发送消息时自动切换至该智能体。

**改动点**：

1. **placeholder**：默认状态改为 `输入 / 快速使用智能体`；选中智能体后改为 `请输入消息，按「Enter」发送`
2. **数据状态**：新增 `agentList`（智能体列表）、`isLoadingAgents`（加载中）、`selectedAgent`（当前选中智能体）、`showAgentDropdown`（下拉菜单显隐）、`activeAgentIndex`（键盘高亮索引）
3. **loadAgents**：组件内异步调用 `fetchAgentList`（GET `/api/agent/list`）加载智能体列表；已缓存或加载中时跳过
4. **filteredAgents**：computed，输入 `/` 显示全部，输入 `/xxx` 按 name / display_name 过滤
5. **handleInput**：精确输入 `/` 时打开下拉菜单并加载数据；输入 `/xxx` 保持菜单开启（过滤模式）；非 `/` 输入关闭菜单
6. **handleKeydown**：下拉菜单开启时支持 `↓`/`↑` 移动高亮、`Enter` 选中、`Esc` 关闭
7. **selectAgent**：选中后设置 `selectedAgent`，清空输入框，关闭菜单，聚焦 textarea
8. **removeSelectedAgent**：点击标签上的移除按钮清空 `selectedAgent`
9. **handleSend**：存在 `selectedAgent` 时，emit 消息前先 emit `agent-switched`（携带 agent.name），发送后自动清空 `selectedAgent`
10. **handleBlur**：延迟 200ms 关闭下拉菜单，保证 `mousedown` 选中事件先触发
11. **template**：textarea 前新增 `selected-agent-tag`（含 `/` 前缀 + display_name + 移除按钮）与 `agent-dropdown`（loading / 空状态 / 可点击列表项）
12. **CSS**：新增 `.selected-agent-tag`（accent 色边框 + 背景 + 圆角标签）、`.agent-dropdown`（白色浮层 + 阴影 + 圆角 + 最大高度 240px）、`.agent-dropdown-item`（hover/active 高亮）

**测试**：

- 路径：`web/Agent/src/components/__tests__/InputBox.command.spec.js`（11 用例）
- 测试策略：mount InputBox + mock `global.fetch`（按 URL 分发 `/api/auth/refresh` 与 `/api/agent/list`）+ mock `global.localStorage`
- 覆盖：普通文本触发 send 且不触发 agent-switched / `/` 开头显示命令提示 / `/agent map_agent` 命令触发 agent-switched 事件 / 未知命令显示未知命令提示 / `/agent non_exist` 不触发切换且 send 含「不存在」 / `/api/agent/list` 返回非 ok 时 send 含「命令执行失败」 / `/agents` 命令 send 含智能体列表 / 输入 `/` 显示智能体下拉菜单 / 点击下拉菜单项选中后显示标签并清空输入框 / 选中智能体后发送触发 agent-switched 与 send / 移除按钮可清空已选智能体标签

### InputBox 会话切换清理本地态（2026-07-28 新增）

**问题**：用户在新建会话输入 `/` → 选中智能体 → 不发送即切换历史会话，输入框同时显示"已选智能体标签"与历史会话绑定的"bound-agent-tag"，出现两个同名智能体标签。

**修复点**：`InputBox.vue` 的 `watch(() => props.sessionId, ...)` 回调内，在 `sid !== oldSidKey` 时清空与"待发送的本地态"相关的 ref：`selectedAgent` / `selectedFiles` / `showAgentDropdown` / `activeAgentIndex` / `isExecutingCommand`。`immediate: true` 阶段 `sid === oldSidKey`（均空），不会误清初始态；`projectLockedByUpload` 仍由父组件 App.vue 维护，InputBox 只清本地态。

**语义边界**：`selectedAgent` 是"本会话待发送的临时态"，跨会话应清空；与既有按 session 隔离的 `triggerSelectionsBySession` / `editorSnapshotsBySession` 不同，本地态不需要按 session 缓存。

**测试**：
- 路径：`web/Agent/src/components/__tests__/InputBox.session-switch.spec.js`（5 用例）
- 覆盖：已选智能体 + 切 session 后 selectedAgent 被清空（只剩 bound-agent-tag）/ 下拉菜单收起 / 编辑器 DOM 清空 / immediate 阶段不清空初始态

## 前端触发器注册表（「#」服务器引用）

与 `commandRegistry` 平级的另一种「输入触发」体系：以单字符为锚（`#`），在可编辑正文中输入触发字符唤起通用面板（搜索 + 平铺 + 键盘导航），选中项以**不可编辑的灰色 Chip** 直接渲染在原 `#查询词` 位置（与正文混排）。发送时由 trigger 的 `buildOverrides` 转成 `context_overrides` 片段经 `chatStream` 透传给后端，由后端 `DYNAMIC_NODE_REGISTRY` 镜像渲染进系统提示词末尾的 XML 节点；同时把正文中每个 Chip 在其 DOM 位置序列化为 `⟦{mentionLabel}：{chipLabel}⟧` 一并写入消息文本，使问题文本本身也显式携带引用（与历史协议保持兼容）。**两侧 registry 镜像对称，未来新增触发类型只需各注册一条（前端 trigger + 后端 DynamicNodeSpec），签名不变**。

### 模块位置

```
web/Agent/src/utils/
├── triggerRegistry.js             # 触发器注册表 + searchTriggerByChar / buildOverridesFor / renderTriggerMentions
├── inputEditor.js                 # contenteditable 编辑器 DOM 工具：serializeEditor / getTextBeforeCaret / replaceTriggerRangeWithServerChip / setCaretAfter
└── __tests__/
    ├── triggerRegistry.test.js    # 18 用例：契约 / 搜索 / buildOverrides / 数据源拍平 / 去重 / renderTriggerMentions
    └── inputEditor.test.js        # 3 用例：序列化、光标前文本、触发范围替换
```

#### 运维控制台 OpsDetailWindow 磁盘物理盘纵向分组（2026-08-16，用户需求）

应用户需求把详情页磁盘由「多列网格」改为「按物理盘纵向分组」：每块物理盘一行，磁盘头显示 `排队 / IO 利用率`，分区卡片只显示 `使用率`；物理盘分组同时覆盖 Linux 与 Windows。

数据契约（`OpsConsoleApp.vue::mapSnapshotToServer`）：
- `disks[].hostDisk` 物理盘标识（Linux `lsblk -o NAME,PKNAME` 推得；Windows `PHYSICALDRIVE{n}`；旧 snapshot 缺字段时留空串，前端按 mount 兜底不跨 mount 猜盘）。
- `disks[].diskIndex` 物理盘稳定展示序号（Linux 按 `lsblk` 首次出现顺序自增；Windows `Win32_PerfFormattedData_PerfDisk_PhysicalDisk.Name` 前缀数字；缺失 null）。
- `disks[].partition` 分区标识（Linux 分区记录的 NAME，如 `sda2`；Windows 盘符 `C:`；整盘 IO 记录留空串 `""`）。
- `used` 字段：分区记录由 `disk_used_pct` 映射；整盘 IO 记录为 `null`（不进分区卡）。

`OpsDetailWindow.vue::groupDisksByPhysicalDisk` 纯函数（`<script>` 段导出）：
- 分组键优先级 `disk:${diskIndex}` > `host:${hostDisk}` > `legacy:${mount|name}`，确保分区记录与整盘 IO 记录必然归入同一物理盘（不会因 hostDisk 存在而拆成两个组）。
- 兼容历史 Windows WMI mount 文案：`0 C: D:[SSD]`（旧 snapshot）→ 解析 C:/D: 映射到 PHYSICALDRIVE0。
- `Intl.Collator` numeric 自然排序：`sda1 < sda2 < sda10`、`PHYSICALDRIVE0 < PHYSICALDRIVE1`。
- 不修改输入数组（保持调用方原始顺序）。

模板结构 `.disk-groups > .disk-group > .disk-group-head + .disk-group-partitions`：
- `.disk-group-head`：左侧 LED + 标题「磁盘 N」+ `#N` + hostDisk 设备名；右侧 `.dgh-metrics` 两指标「排队 / IO 利用率」，同组多记录取 `Math.max`。
- `.disk-group-partitions > .disk-pcard`：每张分区卡仅显示 `使用率`（partition 非空记录）。
- LED 三态：磁盘头取组内 `ioUtilPct` / `ioAwaitMs` 任一 ≥80 红，都正常绿，全 null 灰；分区卡 `used ≥80` 红，否则绿，null 灰。
- 分区卡渲染判定 `partition` 非空字符串 → 保证整盘 IO 记录（partition=""）不渲染为分区卡。

`ops-console.css` 新样式：
- `.disk-groups` flex column gap；
- `.disk-group` 圆角 10px 1px 政务蓝边框白底；
- `.disk-group-head` flex 横向 `space-between`，左 LED/标题/索引/设备名，右 `.dgh-metrics`；
- `.disk-group-partitions` flex 横向 `flex-wrap`，`.disk-pcard` `flex: 1 1 112px` 自适应；
- `.disk-pcard .dcp-header` LED + 盘符，`.dg-m` label + value。

测试同步（`OpsDetailWindow.redesign.spec.js` 重写为 27 用例全绿）：
- Linux 同盘多分区归一：`sda` 物理盘下 `/` + `/data` 两张分区卡 + 整盘 IO 记录 `sda[SSD]` 不渲染为分区卡；磁盘头按 IO 记录贡献的 5ms / 12% 显示。
- Windows 多物理盘：`PHYSICALDRIVE0` 下 `C:\\` + `D:\\`，`PHYSICALDRIVE1` 下 `E:\\`，按 diskIndex 升序两组。
- 磁盘头只显示 `排队 / IO 利用率`（不含使用率）。
- 分区卡只显示 `使用率`，无 IO 指标。
- 阈值标红：分区 used ≥80 → `#ff453a`；正常 → `#1d9a40`；null → `-` + 灰 `#9aa3af`。
- IO 整盘记录（partition=""）不渲染为分区卡，反向测试：3 条记录（2 分区 + 1 IO）只渲染 2 张分区卡。
- 未知归属（缺 host_disk）独立成组（旧 snapshot），不与已知组合并。
- 旧 `.disk-grid` 类不再渲染。

ops-console 目录 6 个 spec 文件共 **98 个用例全绿**（88 → 98，新增磁盘分组 12 + 老用例零回归）。
├── components/
│   └── TriggerPanel.vue               # 通用触发面板（搜索 + 列表 + 键盘导航）
└── components/__tests__/
    ├── TriggerPanel.spec.js           # 12 用例
    └── InputBox.trigger.spec.js       # 15 用例：#触发 / 词边界 / 工具栏按钮 / 行内 Chip 渲染与原位插入 / 多位置 Chip 顺序 / 精确替换触发串 / 发送原位序列化 + extras / chip 移除同步 / 删除后发送不再携带 / 发送清空编辑器 / 会话切换 / 流式禁用 / 已绑定智能体
```

### TRIGGER_REGISTRY 条目契约

| 字段 | 类型 | 含义 |
|---|---|---|
| `id` | string | 唯一标识；与后端 `DYNAMIC_NODE_REGISTRY` 条目 `overrides_key` 语义对应 |
| `char` | string (1字符) | 触发字符（如 `#`） |
| `title` | string | 工具栏按钮 tooltip / 面板标题 |
| `fetchItems` | async () => Array | 异步拉取候选项（本期 = `fetchUserServerTree` 拍平 + `node_type==='server'` 过滤 + business_name 去重） |
| `searchKeys` | string[] | 面板搜索 OR 匹配的字段集合 |
| `itemKey` | (item) => any | 去重键（chips 渲染 key + 去重判定） |
| `chipLabel` | (item) => string | chip 显示文本 |
| `buildOverrides` | (items) => object | 选中项 → context_overrides 片段；与后端 `DYNAMIC_NODE_REGISTRY.overrides_key` 镜像 |

### 导出 API

| 导出 | 作用 |
|---|---|
| `TRIGGER_REGISTRY` | 注册条目数组 |
| `searchTriggerByChar(char)` | 按触发字符查找条目 |
| `searchTriggerById(id)` | 按 id 查找条目 |
| `buildOverridesFor(triggerId, items)` | 选中项 → context_overrides 片段；空数组/未注册 id 返回 `{}` |

### 设计要点

- **前后端镜像**：前端 `buildOverrides` 输出键（如 `referenced_servers`）= 后端 `DynamicNodeSpec.overrides_key`，两侧键名一致
- **数据源已是用户权限范围**：前端 `fetchUserServerTree` 已按 `OwnershipScope` 过滤，后端 `sanitize_dynamic_nodes` 仅做白名单字段清洗（name/server_type 两键、长度/条数上限），不做归属校验
- **词边界触发**：trigger 字符须位于行首或前一个字符为空白，避免 `C#` / `#` 作为普通文本误触
- **行内原子 Chip**：选中服务器后通过 `replaceTriggerRangeWithServerChip` 在原 `#查询词` 位置替换为 `contenteditable="false"` 的 `<span class="selected-trigger-chip inline-trigger-chip">`，与正文文本节点混排；用户可在 Chip 前后继续输入，Backspace/Delete 紧邻 Chip 时整块删除
- **DOM 是发送期间的引用源**：`extras.referenced_servers` 直接由正文中实际存在的 Chip 派生并按 name 去重，不再依赖 `selectedTriggers` 缓存；`buildOverridesFor('server', items)` 仍作为唯一 contract 出口
- **按 session 隔离**：编辑器 DOM 快照与触发器选择都按 `sessionId` 缓存；切换 session 时保存当前 DOM 快照并恢复目标 session 的快照（无快照则为空白）；每轮发送后清空编辑器与选择
- **内部 mention 协议序列化**：发送文本中按 Chip DOM 位置生成 `⟦{mentionLabel}：{chipLabel}⟧`；该文本仅在发送和历史消息渲染时出现，输入框内不显示
- **可扩展边界**：未来新增 `@` 知识库等只需在前端 `TRIGGER_REGISTRY` 追加条目 + 后端 `dynamic_context.DYNAMIC_NODE_REGISTRY` 追加一条 `DynamicNodeSpec`；`chatStream` 签名 / `build_dynamic_system_suffix` 签名 / MessageBubble 渲染路径零改动（仍通过 `renderTriggerMentions` 解析 mention 标记）

### MessageBubble 统一渲染 mention 标记（2026-07-26 新增）

`triggerRegistry.js` 新增导出 `renderTriggerMentions(text, options)`，将文本中的 `⟦{mentionLabel}：value1、value2⟧` 统一渲染为样式化 HTML chip。`MessageBubble.vue` 在用户消息与 AI 消息文本的两条渲染路径均调用该函数，因此实时会话与历史会话弹窗同步生效。

- **注册表驱动**：`TRIGGER_REGISTRY` 条目新增 `mentionLabel`（匹配文本标签）与 `mentionClass`（CSS 类名）。当前 `server` 条目为 `mentionLabel: '引用服务器'`、`mentionClass: 'mention-server'`；未来新增 trigger 时无需改动 `MessageBubble.vue`。
- **渲染产物**：每个服务器名渲染为一个 `.mention-chip`，含 `#` 前缀字符与服务器名；整组 chip 包裹在 `.mention-block` 中。
- **安全**：`renderTriggerMentions({ escapeHtml: true })` 对用户消息非标记文本做 HTML 转义；服务器名始终 HTML 转义，避免 `v-html` 引入注入风险。
- **AI 消息**：`renderedText` / `renderMarkdown` 先调用 `renderTriggerMentions` 替换 mention 标记为内联 HTML，再交给 `marked.parse` 处理 markdown。
- **样式**：`.mention-chip` 与输入区 `.selected-trigger-chip` 视觉对齐；因 mention HTML 通过 `v-html` / `marked.parse` 注入，scoped CSS 使用 `:deep(.mention-chip)` 命中。`.user-message :deep(.mention-chip)` 在用户消息蓝色背景上使用半透明白色系，保证可读性。

### InputBox 集成

`InputBox.vue` 工具栏附件按钮后新增 `#` 按钮（由 `TRIGGER_REGISTRY` 驱动渲染）；正文输入区为 `contenteditable` 编辑器，输入 `#` 时唤起 `TriggerPanel`，选中服务器后由 `replaceTriggerRangeWithServerChip` 在原 `#查询词` 位置插入不可编辑的灰色 Chip（与文本混排）。发送时 `serializeEditor` 把 DOM 序列化为「文本 + 内部 mention 标记」并由正文中实际存在的 Chip 派生 `extras.referenced_servers`（按 name 去重），经 `buildOverridesFor('server', items)` 统一出口。当前 session 内每次发送后清空编辑器与触发器选择；切换 / 新建 session 时按 session 隔离 DOM 快照与触发器选择。

**改动点**：

1. **import**：`TRIGGER_REGISTRY` / `searchTriggerByChar` / `buildOverridesFor` / `TriggerPanel` / `serializeEditor` / `getTextBeforeCaret` / `replaceTriggerRangeWithServerChip` / `setCaretAfter`
2. **响应式状态**：新增 `editorRef` / `editorSnapshotsBySession`（按 session 缓存 DOM）；`inputValue` 改为只读派生，由 `syncEditorState()` 从 DOM 序列化得到；`triggerSelectionsBySession` 保留以兼容非服务器类 trigger 的 `buildOverrides` 调用
3. **编辑器 DOM 工具**（`inputEditor.js`）：`serializeEditor` / `getTextBeforeCaret` / `replaceTriggerRangeWithServerChip` / `setCaretAfter`，不管理 Vue 状态、不直接读取 `triggerRegistry`
4. **detectEditorTriggerAtCaret**：从 Selection 与 DOM 读取光标前文本，搜索词自动 trim 尾随空白（避免用户在搜索串后再输入其他字符时把空白一并吞掉）；命中后保存 `Range` 用于原位替换
5. **createServerChip**：DOM 工厂创建 `<span class="selected-trigger-chip inline-trigger-chip" contenteditable="false">`，含 `data-trigger-id` / `data-business-name` / `data-server-type` / `data-testid` 与「#」前缀、名称 label、移除按钮（移除按钮 `mousedown` preventDefault）
6. **removeInlineChip**：直接 DOM 操作删除 Chip，并同步 `inputValue` 与光标位置
7. **onTriggerPanelSelect**：选中时调用 `replaceTriggerRangeWithServerChip` 原位替换触发串；取消（null）时删除触发串不插入 Chip
8. **onTriggerButtonClick**：基于当前 Selection/Range 在光标处插入触发字符并补前导空格，遵循词边界规则
9. **handleEditorInput**（替代原 `handleInput`）：先 `syncEditorState()` 同步 `inputValue`，再走命令下拉分支与 trigger 检测分支
10. **handleEditorKeydown**（替代原 `handleKeydown`）：Backspace/Delete 紧邻行内 Chip 时整块删除（`handleAdjacentChipDelete`），避免光标进入 Chip 内部；**判定条件必须按光标在文本节点内的 offset 校验"贴边"**：Backspace 仅在 offset===0 时整块删 chip（offset>0 让原生退格删字）；Delete 仅在 offset===textLength 时整块删 chip；否则不拦截，避免在 chip 旁文本节点中删字时误删 chip
11. **handleEditorPaste**：仅接受 `text/plain`，`\n` 转为 `<br>`，禁止粘入任意 HTML
12. **handleSend**：调用 `serializeEditor` 得到 `{ text, referencedServers }`，基于 `referencedServers` 重建 `business_name/server_type` 项后交给 `buildOverridesFor('server', items)`，按 DOM 原位置序列化文本；发送后清空编辑器与触发器选择
13. **executeCommand finally**：命令执行后清空编辑器
14. **watch sessionId**：切换时先保存当前 session 的编辑器快照，再为目标 session 初始化空快照并恢复（无快照即空白）
15. **template**：textarea 替换为 `<div contenteditable data-testid="input-editor">`，移除原 textarea 上方集中 chip 渲染区；`#` 工具栏按钮 + TriggerPanel 位置不变
16. **CSS**：`.message-editor`（contenteditable 容器：min/max-height / 滚动 / placeholder via `:empty::before` / `white-space: pre-wrap` / `caret-color`）；`.selected-trigger-chip.inline-trigger-chip`（行内 `vertical-align: baseline` / `white-space: nowrap` / `margin: 0 2px` / `user-select: none`）

**测试**：

- `web/Agent/src/utils/__tests__/triggerRegistry.test.js`（18 用例）：注册项契约 / searchTriggerByChar / searchTriggerById / fetchServerItems 过滤 / dedup / buildOverrides / 空 items / 未注册 trigger id / `renderTriggerMentions` 单服务器 / 多服务器 / 无标记 / HTML 转义
- `web/Agent/src/utils/__tests__/inputEditor.test.js`（3 用例）：序列化按 DOM 顺序并按 name 去重服务器；Chip 作为可搜索占位节点参与光标前文本读取；触发范围替换原子插入 chip 并保留前后文本
- `web/Agent/src/components/__tests__/TriggerPanel.spec.js`（12 用例）：基础渲染 / loading / error / 空态 / 搜索过滤（OR + case-insensitive）/ ArrowDown / ArrowUp 环绕 / Enter 选中 / Escape 选 null / 点击 select / mouseenter 更新 activeIndex
- `web/Agent/src/components/__tests__/InputBox.trigger.spec.js`（15 用例）：工具栏 `#` 按钮 / 输入 `#` 触发面板 / `C#` 不触发 / 空白后 `#` 触发 / 工具栏按钮在光标处插入字符并触发面板 / 选择服务器在原位置渲染灰色 Chip + 不显示内部 mention / 精确替换 `#查询串` 保留周围文本 / 多位置 Chip 保持 DOM 顺序 / 发送按原位置序列化并携带 extras / 点击 Chip 移除按钮保留周围文本 / 删除 Chip 后发送不携带服务器 / 发送后清空编辑器 / 新 session 清空编辑器 / 已绑定智能体时 `#` 仍能触发 / 流式期间 `#` 按钮 disabled
- `web/Agent/src/components/__tests__/MessageBubble.spec.js`（5 用例）：用户消息 / AI 消息 / 多服务器 / 无标记回归 / HTML 特殊字符转义

### App.vue 透传 extras

`App.vue::handleSendMessage(message, attachments, extras)` 新增第 3 参数 `extras`，透传到 `chatStream` 第 7 参数。原历史会话重发调用 `handleSendMessage(userMsg.content, userMsg.attachments || [])` 保持兼容（extras 缺省为 null）。

### api.js chatStream 第 7 参数

`chatStream(sessionId, message, attachments, resume, agentName, projectId, extras)` 新增第 7 参数 `extras`，非空对象时通过 `context_overrides` 通道传给后端。null / 空对象时不写入 `context_overrides`。

### App.vue agentName 状态管理

`App.vue` 新增 `agentName` 响应式状态，承接 InputBox 的 `agent-switched` 事件，并将当前激活智能体名称透传到 `chatStream` 调用。

**改动点**：

1. **状态**：新增 `const agentName = ref('map_agent')`（位于 `currentPage` 之前），默认 `map_agent`，与后端 `agents` 表 `name` 字段一致
2. **事件处理**：新增 `handleAgentSwitched(name)` 函数（位于 `handleToolAction` 之后），含空值/类型守卫与同值短路；更新 `agentName.value` 并打印日志
3. **chatStream 透传**：`handleSendMessage` 与 `handleApprovalSubmit` 两处 `chatStream` 调用均追加第 5 参数 `agentName.value`，确保发送消息与 resume 都携带当前激活智能体
4. **template 绑定**：`<InputBox>` 新增 `@agent-switched="handleAgentSwitched"` 事件监听

**测试**：

- 路径：`web/Agent/src/components/__tests__/App.agent-switch.spec.js`（2 用例）
- 测试策略：mount App.vue + mock `global.fetch`（按 URL 分发 `/api/auth/refresh` 与 `/api/auth/validate` 使 `authReady=true`，InputBox 得以渲染）+ mock `global.localStorage`；通过 `findComponent({ name: 'InputBox' }).vm.$emit('agent-switched', ...)` 模拟子组件事件
- 覆盖：App.vue 有 agentName 状态默认 `map_agent` / 监听 agent-switched 事件后 agentName 更新为目标值

## TaskSchedulerManager 普通用户数据源分流（2026-07-26 新增）

「普通用户的定时任务时，需要选择已授权的智能体和所有的脚本」诉求触发本次前端改造。

**改动点**：

1. **`loadInitialData` 智能体数据源按 `props.isAdmin` 分流**（`TaskSchedulerManager.vue:1079-1082`）：
   - admin → `fetchAdminAgentList`（`GET /api/admin/agents`，全量含禁用项）
   - 普通用户 → `fetchAgentList`（`GET /api/agent/list`，后端按 `user_agent_acl` 过滤、仅启用项）
2. **`loadScripts` 移除 `if (!props.isAdmin) return` 拦截**：后端已把 `GET /api/admin/scripts` 改为 JWT-only，所有登录用户都能拉脚本列表
3. **`fetchAgentList` 已存在于 `web/Agent/src/utils/api.js:1721-1733`**，无需新增
4. **`loadDevopsServers` 按 `props.isAdmin` 分流**（2026-07-26 新增）：
   - admin → `fetchDevOpsServers`（`GET /api/admin/devops-servers`，全量共享）
   - 普通用户 → `fetchUserServerTree`（`GET /api/admin/user-servers/tree`，后端按 `OwnershipScope` 过滤、对 server 节点附带 `business_name` / `server_type`）
   - 新增 helper `mapUserServerNodesToCandidates(nodes)`：过滤 `node_type='server'` 节点，映射为 `{id, business_name, server_type}`，喂入既有 `maskServers` 与候选/失效项检测逻辑
5. **`loadApiConfigTree` 移除 `if (!props.isAdmin) return` 拦截**（2026-07-26 新增）：后端 `GET /api/admin/api-configs/tree` 已改为 JWT-only，按 `OwnershipScope` 过滤，普通用户天然只看到自己添加的接口节点；api_list 控件按需加载触发（添加 api_list 参数 / 切换到 API Tab）

**与 ACL 双重门的协同**：

- 「定时任务」菜单（`task-scheduler.scheduled`）受 `require_admin_or_menu_acl` + OwnershipScope 双重保护
- 普通用户被授权该菜单后，进入「编辑任务」面板时：
  - 「目标智能体」下拉只列其已授权智能体（来自 `user_agent_acl`）
  - 「目标脚本」下拉列全部已注册脚本（白名单字段，不暴露源码）
  - 「目标服务器列表」候选只列该用户自己添加的服务器（来自 `user_server_nodes`）
  - 「目标接口列表」候选只列该用户自己添加的接口（来自 `api_config_nodes`）
- 「脚本扫描入库」子 tab（`task-scheduler.script-inventory`）与「服务器管理」子 tab（`task-scheduler.server-management`）仍需独立授权；普通用户未授权时子 tab 不显示，写端点被后端 `Depends(require_admin_or_menu_acl(...))` 拦下

**失效授权处理**：

- admin 收回某智能体授权后，普通用户编辑老任务时 `form.agent_name` 下拉不含该 option
- Vue `v-model` 自然归零（select 值为空），用户必须重选才能保存（`schedule-agent` select 已带 `required` 校验）
- 不在前端做"当前值兜底"显示（按用户选择："仅显示授权项，编辑时显示空值"）

**测试**（`web/Agent/src/components/__tests__/TaskSchedulerManager.spec.js`）：

- `setupFetchMock` 改造支持 `agentListResponse` / `userServerTreeResponse` 参数与 `/api/agent/list` / `/api/admin/user-servers/tree` mock 分发
- `mockUserServerNodes` 提供 2 个 server 节点 + 1 个 folder 节点
- 新增 describe 块「TaskSchedulerManager 普通用户数据源分流（2026-07-26 新增）」8 用例：
  - `test_non_admin_uses_agent_list_endpoint`：普通用户拉智能体走 `/api/agent/list` 而非 `/api/admin/agents`，不再显示「权限不足」占位
  - `test_non_admin_loads_scripts`：普通用户也能拉脚本列表（不再被 isAdmin 短路）
  - `test_admin_still_uses_admin_agents_endpoint`：admin 仍走 `/api/admin/agents`（向后兼容）
  - `test_non_admin_agent_dropdown_renders_filtered_options`：智能体下拉来自已授权列表（`mockAgents` 启用项），不含 `disabled_agent`
  - `test_non_admin_servers_loads_from_user_server_tree`：普通用户 server_list 候选走 `/api/admin/user-servers/tree` 而非 `/api/admin/devops-servers`（通过切 script + 添加 server_list 触发）
  - `test_admin_still_uses_devops_servers`：admin server_list 候选仍走 `/api/admin/devops-servers`（向后兼容）
  - `test_non_admin_server_candidates_rendered`：普通用户 server_list 候选仅含 mockUserServerNodes 的 server 节点（folder 被过滤）
  - `test_non_admin_api_list_loads`：普通用户 api_list 候选可加载 `/api/admin/api-configs/tree`（不再被 isAdmin 短路）

**关联改动**：
- 后端 `app/routers/script_admin_router.py` 移除 router 级 `require_admin`（GET 登录态、POST /scan admin-only），详见 [api-routes.md § 脚本管理接口权限拆分（2026-07-26 新增）](api-routes.md)
- 后端 `app/routers/user_server_router.py` 与 `app/routers/api_config_router.py` 仅 `GET /tree` 端点改为 JWT-only（写端点 ACL 不变），详见 [menu-acl.md § 用户服务器配置管理](menu-acl.md)
- 后端 `app/shared/utils/user_server_service.py::list_nodes` 对 server 节点附加 `business_name` / `server_type`（通过 `_build_devops_index` 内存 join 零 DB IO）

#### 运维控制台 OpsServerWindow 卡片增强（2026-08-16，用户需求）

应用户要求在「服务器管理」窗口的每张卡片补「最后检测时间」、保留并强化磁盘指标（默认显示磁盘利用率、有问题哪个有问题显示哪个并标红）、Linux 限定加 1 分钟负载。澄清后口径：保持单行指标布局（不拆行）；时间用绝对时间 `YYYY-MM-DD HH:MM`，放卡片头部右侧。

要点：
- **后端** `app/shared/utils/server_inspection_record_service.py::_derive_metrics`：返回值从 `{cpu, mem, disk}` 扩为 `{cpu, mem, disk, load}`。linux 取 `parsed_values.load_1m`（保留 2 位小数），windows / 其他平台返回 `None`（白名单策略，避免误读其他键名）。零迁移（`server_latest_snapshot` 表结构未变，仅 `metrics` 字典新增键）。
- **前端映射** `web/Agent/src/components/ops-console/OpsConsoleApp.vue::mapSnapshotToServer`：追加 `serverType: item.server_type || ''` 与 `load: item.metrics?.load ?? null` 两个字段；其他字段（`name` / `ip` / `os` / `status` / `cpu` / `mem` / `disk` / `disks` / `collectedAt`）不变。
- **前端渲染** `OpsServerWindow.vue`：
  - 卡片头部 `srv-card-head` 在标题之后追加 `<span class="srv-card-time">`（`.srv-card-title` flex:1 自动让位挤压，省略号不变；`title` 属性附 ISO 原始串便于悬停校对）。
  - 指标行在「存储」项之后追加 `<div v-if="isLinuxType(srv.serverType)" class="srv-metric">`（windows / 空 / 未知一律 false，避免未来新 platform 误显示）。
  - 磁盘指标行为零改动：复用既有 `displayDiskOf(srv) = pickDisplayDisk(srv.disks)` + `metricColor(displayDiskOf(srv)?.used)`，已覆盖「默认显示利用率、有问题标红」需求。
- **样式** `web/Agent/src/styles/ops-console.css`：追加 `.ops-console-root .srv-card-time { font-size: 11px; color: #5a6f9c; font-variant-numeric: tabular-nums; white-space: nowrap; flex-shrink: 0; }`；不修改 `.srv-card-head` 容器布局（已是 `display:flex; gap:8px`，标题 `flex:1` 自动让位）。
- **新增具名导出函数**（参照 `pickDisplayDisk` / `metricColor` 模式，便于单测直接 import）：
  - `formatCollectedAt(iso)`：ISO 字符串 → `YYYY-MM-DD HH:MM`（本地时区）；null / undefined / 非字符串 / 解析失败 → `'-'`。
  - `isLinuxType(serverType)`：仅 `serverType.toLowerCase() === 'linux'` 返回 true（不区分大小写，白名单）。
  - `loadColor(v)` + 常量 `LOAD_WARN = 4`：null 灰、`< 4` 绿、`≥ 4` 红；与 CPU/Mem/Disk 的 80% 阈值解耦，对齐 `inspection_scripts.yaml::load_1m warn=4.0`。

测试同步：
- 后端 `app/tests/shared/utils/test_server_inspection_record_service.py`：新增 3 个用例 — `test_derive_metrics_includes_load_linux`、`test_derive_metrics_load_is_none_for_windows`、`test_list_latest_view_dict_metrics_contains_load_admin`。57 → 57+3 全绿（其余 54 个用例零改动）。
- 前端 `web/Agent/src/components/ops-console/__tests__/OpsServerWindow.card.spec.js`：新增 12 个用例（纯函数 9 + 组件 3）。ops-console 目录 5 个 spec 共 56 用例全绿。

**不在范围内**：`pickDisplayDisk` 阈值不变（保持 80% 与 YAML 对齐）；`server_latest_snapshot` 表结构不变；OpsDetailWindow 详情页不变；顶部菜单栏 `tick` 时间格式不变。

#### 运维控制台 OpsServerWindow 卡片磁盘异常指标（2026-08-16，用户需求）

应用户要求把卡片存储行改造为「异常盘符智能展示」：linux 卡片负载 label 由「负载」改为「服务器负载」。

要点：
- **后端** `app/shared/utils/server_inspection_record_service.py::_row_to_view` 与 `_merge_user_view`：视图 dict 新增 `field_results` 字段（已在数据库 `server_latest_snapshot.field_results` JSONB 列落库；之前视图 dict 未透出，前端无法消费）。无快照分支兜底 `field_results = []`（前端访问 `.length` 安全）。view dict 白名单键追加 `field_results`，docstring 同步更新。
- **前端映射** `web/Agent/src/components/ops-console/OpsConsoleApp.vue::mapSnapshotToServer`：追加 `fieldResults: item.field_results || []`；`disks[]` 元素追加 `mount` / `ioUtilPct` / `ioAwaitMs` / `diskType` 字段（用于 `pickAnomalyDisks` 兜底 mount 提取 + 后续可选详情展示）。
- **前端渲染** `OpsServerWindow.vue`：
  - 新增 2 个具名导出函数 `pickAnomalyDisks(fieldResults, disks)` / `formatAnomalyItem(item)`：从后端 `field_results` 过滤 `key ∈ {disk_used_pct, io_util_pct, io_await_ms}` 且 `status ∈ {warn, crit}` 的项，按 mount 分组聚合（mount 提取优先级：后端 `message` 字段「磁盘 {mount}」→ `disks[]` 兜底）；同 mount 多异常指标合并到 `items` 数组；整体排序 crit 优先、warn 次之、同状态按 mount 升序。
  - 卡片「存储」模板由 `盘符 [使用率%]` 改为：① 有异常盘 → 盘符 + 异常概要（`使用 92%` / `IO 92%` / `等待 150ms` 简写）盘符与概要统一标红 `#ff453a`，多个异常盘用 flex-wrap 换行；② 全 pass → 显示 `-`（沿用 `metricColor(null)` 灰）；③ `fieldResults` 为空（老数据 / 未落库）→ 退化到既有 `pickDisplayDisk` 行为，保留旧 UI 不破坏。
  - 卡片「负载」label 由「负载」改为「服务器负载」（`srv-metric-label` 字面值更新，`loadColor` 函数 / `LOAD_WARN=4` 阈值逻辑不变）。
- **样式** `web/Agent/src/styles/ops-console.css`：新增 `.srv-metric-disk--problem`（盘符红色 `font-weight: 600`） / `.srv-metric-disk-name`（盘符子元素 `nowrap`） / `.srv-metric-anomaly`（异常概要红色 `font-size: 11px; tabular-nums; nowrap`） / `.srv-metric-storage`（`flex-wrap: wrap` 支持多盘符换行）；不修改 `.srv-card-metrics` 容器（既有 `flex-wrap: wrap` 已生效）。
- **缓存优化** `anomaliesById` computed：把 `pickAnomalyDisks` 结果缓存到 `Map<id, list>`，避免模板 `v-for` 中重复调用；模板用 `anomaliesOf(srv)` 取值。

测试同步：
- 后端 `app/tests/shared/utils/test_server_inspection_record_service.py`：新增 2 个用例 — `test_list_latest_view_dict_contains_field_results_admin`（admin 分支有/无快照两种 field_results 透出 + 元素字段断言）+ `test_list_latest_user_view_dict_contains_field_results`（普通用户分支透出）。57 → 59 全绿（其余 57 个用例零改动）。
- 前端 `web/Agent/src/components/ops-console/__tests__/OpsServerWindow.card.spec.js`：
  - 新增 `pickAnomalyDisks` 纯函数 4 例（全 pass → [] / 有 warn → 返回 warn 项 / warn + crit → crit 优先 / 同一 mount 多异常聚合）；`formatAnomalyItem` 3 例（% / ms / IO 简写）；组件 3 例（异常盘符 + 标红 / 全 pass → '-' / 兜底老数据行为）。
  - 更新 2 个旧用例：`test_load_metric_visible_only_for_linux` label 断言改为「服务器负载」；`test_storage_shows_dash_when_no_disks` 改为通过 `.srv-metric-value` 节点断言 '-'（模板重构后 `.srv-metric-disk` 节点不再渲染）。
  - ops-console 目录 5 个 spec 共 66 用例全绿。

**不在范围内**：`pickDisplayDisk` 阈值不变（保留作为 `fieldResults` 为空时的兜底）；`server_latest_snapshot` 表结构不变；OpsDetailWindow 详情页不变；前端不复算阈值（完全消费后端 `field_results`）。

#### 运维控制台 OpsDetailWindow 详情页改造（2026-08-16，用户需求）

应用户要求把详情页改造为只读、风格与外层卡片一致、长方形 4 联指标 + 多列磁盘网格。

要点：
- **`web/Agent/src/components/ops-console/OpsDetailWindow.vue` 重构**：
  - **移除「智能检测」按钮 + detect-panel + runDetect() 整段逻辑**（用户要求「去掉智能检测按钮」）：删除 `import { collectServerInspection }`，删除 `detecting` / `detectLogs` ref / `resetDetect()` / `runDetect()` 函数 / `defineExpose({ runDetect })` / `watch(() => props.server.id, resetDetect)`。详情页只读，采集入口留给外层卡片右侧「重新采集」（后续单独工单）。
  - **头部 sub 由 `ip · os` 改为「最新检测时间:YYYY-MM-DD HH:MM」绝对时间**（与外层卡片 `srv-card-time` 文案/格式完全一致）：复用 `OpsServerWindow.formatCollectedAt`；title 属性放 ISO 全文。无快照 → `最新检测时间:-`。
  - **顶部 3 个圆角指标卡（含 .bar 进度条）整段删除**：旧的 `.metric` 块（CPU / 内存 / 存储 + 进度条）改造为与外层卡片同款长方形 4 联指标条 `.detail-metric-bar`：CPU 使用率 / 内存占用 / 存储使用 / 服务器负载（仅 linux 显示）。复用 `metricColor` / `loadColor` / `isLinuxType` 阈值口径；删除 `.bar` 进度条样式。
  - **kv 表格精简**：移除「内存总量 / 存储总量 / 网络流入」3 项；保留「操作系统 / CPU 型号 / 运行时长」3 项；改 `.kv` 列数 `1fr 1fr` → `repeat(3, 1fr)`。
  - **磁盘展示由单列行（盘符 + 已用% + 共 + 进度条）改造为多列网格**：`.disk-grid`（`grid-template-columns: repeat(auto-fill, minmax(135px, 1fr))`），每列 `.disk-cell`：头部 `OpsServerIcon` + 盘符，下方 3 项指标「使用率 / 排队(ms) / IO 利用率」，无进度条样式。`diskIconStatus(d)` 派生 LED 三态（任一指标 ≥80 → 红，都正常 → 绿，全 null → 灰）。
  - **详情窗口宽度 500 → 460**：用户要求「四联的框需要缩小」。
- **`web/Agent/src/styles/ops-console.css` 改造**：
  - **删除死样式**：`.metrics` / `.metric*` / `.m-label` / `.m-value` / `.bar` / `.disk-row*` / `.disk-info` / `.disk-name*` / `.gov-btn*` / `.detect-panel*` / `.cursor` / `@keyframes fadeIn` / `@keyframes blink`（智能检测 + 老磁盘单列 + 老指标卡全删）。
  - **新增样式**：
    - `.detail-metric-bar`：flex 横向 + 政务蓝渐变 + 圆角 10px + 1px 边框；item 间 `border-left` 1px 分隔；`.dm-value` 15px bold tabular-nums。
    - `.disk-grid`：`repeat(auto-fill, minmax(135px, 1fr))` 多列。
    - `.disk-cell`：白底圆角 10px 1px 政务蓝边框；`.dc-head`（图标 + 盘符 + 下边框）/ `.dc-name`（政务蓝深 bold nowrap 省略号）/ `.dc-metrics`（纵向三行）/ `.dc-m`（label + value 横排）/ `.dc-m-label`（#7a8db3 11px）/ `.dc-m-value`（font-weight 600 tabular-nums）。
    - `.disk-empty`：无磁盘数据时 fallback 文案样式。
    - `.badge.unknown`：补齐 unknown 状态 badge（卡片未覆盖此态但详情页可能存在）。
  - 调整 `.win-detail { width: 460px }`、`.detail-body` padding 缩窄、`.srv-head h3` 加 `flex` 支持 badge 同行、`.kv div > span:last-child` 加省略号避免长内容溢出。

测试同步：
- 新增 `web/Agent/src/components/ops-console/__tests__/OpsDetailWindow.redesign.spec.js`：19 个用例（导入存在 / 最新检测时间 + 无快照 dash / linux 4 联指标 + windows 3 联指标 + CPU/内存 ≥80 红 + <80 绿 + linux 负载 ≥4 红 / kv 精简 3 项 + 不含 3 项被删字段 / 磁盘每列 3 指标 + 数值格式 + 阈值标红 + null 全 '-' + 灰色 / 无进度条 / 无 gov-btn/无 detect-panel / 窗口类名）。
- ops-console 目录 5 个 spec 文件共 **81 个用例全绿**（66 → 81，新增 19 + 老用例零回归）。

**不在范围内**：详情页不重新提供「重新采集」入口（外层卡片按用户要求也是只读入口）；`OpsConsoleApp.mapSnapshotToServer` 形状不变（卡片契约保护）；后端 `ServerInspectionRecordService` 接口不变；运维控制台其他 3 个窗口（Servers / Logs / LogViewer）不动。

#### 运维控制台 OpsDetailWindow 详情页 KV 字段从 DB 读取修复（2026-08-16，用户反馈）

应用户反馈「这些数据没有从数据库中读取」—— `OpsConsoleApp.vue::mapSnapshotToServer` 硬编码 `os: '-'` / `cpuModel: '-'`，导致详情页 kv 表格「操作系统 / CPU 型号」始终显示 `-`，即使 DB `server_latest_snapshot.parsed_values` JSONB 已落库真实数据（windows-ps-5.1 脚本通过 `Get-WmiObject Win32_OperatingSystem.Caption` + `Get-WmiObject Win32_Processor.Name` 采集）。

要点：
- **`web/Agent/src/components/ops-console/OpsConsoleApp.vue::mapSnapshotToServer`**：
  - 移除硬编码 `os: '-'` / `cpuModel: '-'`，改为从 `parsed_values.os` / `parsed_values.cpu_model` 读取；
  - 新增 `fmtStr` 内联防御：null / undefined / 空串 / 纯空白 → '-'（trim 兜底，避免前端渲染空白格）；
  - `uptime` 字段已正确读 `pv.uptime_hours`，文档注释同步说明来源（windows 由 `$bootTime → (Now-bootTime).TotalHours` 计算；linux `inspection_scripts.yaml::linux-bash` 当前未输出该字段，fallback `-`）。
- **`web/Agent/src/components/ops-console/OpsDetailWindow.vue`**：
  - 新增 `fmtStr(v)` 本地函数（与卡片映射同语义），kv 表格 `{{ server.os }}` / `{{ server.cpuModel }}` 改走 `fmtStr` 双保险（即使上游 `mapSnapshotToServer` 漏 trim 也能保持显示一致）。

测试同步：
- 新增 `OpsConsoleApp.spec.js` 3 个用例：
  - `test_map_snapshot_reads_os_cpu_model_uptime`：验证 `parsed_values` 缺字段时降级 `-`，`uptime_hours=36` 渲染为「36 小时」。
  - `test_map_snapshot_consumes_real_db_os_cpu_model`：mock 后端返回 `os: 'Microsoft Windows 11'` / `cpu_model: '13th Gen Intel(R) Core(TM) i7-13620H'` / `uptime_hours: 3.4`，验证前端映射后真实展示这 3 个字段（模拟用户实际 DB 数据形态）。
  - `test_map_snapshot_dash_when_os_empty`：防御性兜底测试，`parsed_values.os=''` / `cpu_model='   '`（纯空白）→ 渲染为 `-`。
- 新增 `OpsDetailWindow.redesign.spec.js` 4 个用例：
  - `test_kv_os_displays_from_server_os`：验证 kv「操作系统」渲染 `server.os` 实际值。
  - `test_kv_cpu_model_displays_from_server_cpu_model`：验证 kv「CPU 型号」渲染 `server.cpuModel` 实际值。
  - `test_kv_uptime_displays_runtime`：验证 kv「运行时长」渲染 `server.uptime` 实际值。
  - `test_kv_os_dash_when_empty_string`：`server.os` 为空串时降级为 `-`（双保险）。

ops-console 目录 5 个 spec 文件共 **88 个用例全绿**（81 → 88，新增 4 详情页 + 3 映射 = 7 个，老用例零回归）。

**不在范围内**：后端 `_row_to_view` / `_merge_user_view` 接口不变（已透出 `parsed_values` 字段）；`server_inspection_record_service` 不变；不修改 inspection_scripts.yaml（windows-ps-5.1 已输出 `os` / `cpu_model`，linux-bash 当前未输出 `uptime_hours` 由运维按需追加）。

#### 运维控制台 `mapSnapshotToServer` OS 关键指标输出 + 移除冗余展示字段（2026-08-16）

`OpsConsoleApp.vue::mapSnapshotToServer` 输出形状当前契约：
  - 移除 `os` / `cpuModel` / `uptime` / `memTotal` / `diskTotal` / `netIn`：详情页不再消费；「操作系统」改为展示 `serverType` 原值（`linux` / `windows`）；DB `parsed_values` 当前不含 `os` / `cpu_model` / `uptime_hours`，渲染端不再尝试取这些键。
  - 新增 `iowait` / `swap` / `inode`：分别取 `parsed_values.cpu_iowait_pct` / `swap_used_pct` / `inode_used_pct`，linux/windows 双平台均采集，缺失 → `null`。每字段独立 `?? null` 兜底，不互相影响。
  - 保留 `load`（linux 1 分钟平均负载原始数值，非百分比，windows → `null`）。
  - 保留 `serverType: item.server_type || ''`：供 `OpsServerWindow` 卡片「负载」按平台显隐 + 详情页「操作系统」原值展示。
  - 保留 `disks[]` 完整契约（`name` / `mount` / `used` / `ioUtilPct` / `ioAwaitMs` / `diskType` / `hostDisk` / `diskIndex` / `partition` / `total`）+ `fieldResults` + `collectedAt` + `errorMessage` + `ip: '-'`（脱敏约定）。

测试同步：`OpsConsoleApp.spec.js` 6 → 9 用例全绿（新增 3 个：`iowait/swap/inode` 缺失 → `null` / 缺失 → 实值 / `not.toHaveProperty` 断言移除字段）。ops-console 目录 6 个 spec 共 **109 个用例全绿**（99 → 109，新增 3 + 老用例零回归）。

**不在范围内**：后端 `_row_to_view` / `_merge_user_view` 接口不变（仍透出完整 `parsed_values` JSONB，调用方按需取键）；`server_inspection_record_service` 不变；不修改 inspection_scripts.yaml（linux-bash / windows-ps-5.1 当前已输出 `cpu_iowait_pct` / `swap_used_pct` / `inode_used_pct` 三键）。

#### 运维控制台 OpsDetailWindow 详情页当前契约（2026-08-16 最终态）

> 历史演进：初始改造（只读卡片 + 4 联指标 + 多列磁盘网格）见上一节；磁盘物理盘分组见 891-930；kv 字段从 DB 读取修复见 1163-1188；mapSnapshotToServer OS 关键指标输出见上节。本节汇总上述迭代后的 **当前契约**，作为后续维护的唯一基线。

- **kv 区 4 项**（`OpsDetailWindow.vue` template 257-262）：
  - 操作系统 / CPU IOWait / Swap 使用率 / Inode 使用率，每项 1 行
  - 「操作系统」展示 `server.serverType` 原值（`linux` / `windows`），走 `fmtStr` 兜底空值 / 纯空白 → `-`
  - OS 三指标按 YAML `warn` 阈值标红：模块级具名函数 `warnColor(v, warn)` + 常量 `IOWAIT_WARN = 20` / `SWAP_WARN = 30` / `INODE_WARN = 80`（对齐 `data/devops/inspection_scripts.yaml::cpu_iowait_pct / swap_used_pct / inode_used_pct` 的 `warn` 字段）
  - 颜色：null → 灰 `#9aa3af`；< 阈值 → 绿 `#1d9a40`；≥ 阈值 → 红 `#ff453a`
  - 展示：null → `-`；其他值 → `${v}%`（`fmtPct` 函数）
  - **CPU 型号 / 运行时长已移除**（详情页不再消费 `server.cpuModel` / `server.uptime`，模板 kv 仅 4 项）

- **服务器负载格式化**（`OpsServerWindow.vue` 模块级导出，卡片 + 详情页共用）：
  - `fmtNum(v)`（`OpsServerWindow.vue:76-79`）：null → `-`；其他原样输出**不带 %** 后缀。负载是 1 分钟平均负载原始数值，非百分比。
  - `fmtPct(v)` 仍用于百分比指标（CPU / 内存 / 存储 / IO 等）：null → `-`；其他值追加 `%` 后缀。
  - 阈值：`loadColor(v)` + 模块级常量 `LOAD_WARN = 4`。null 灰 / < 4 绿 / ≥ 4 红，与 `metricColor` 的 80% 阈值解耦，对齐 `inspection_scripts.yaml::load_1m warn=4.0`。

- **布局最终契约**（`web/Agent/src/styles/ops-console.css`）：
  - `.kv` 2 列网格：`grid-template-columns: repeat(2, 1fr)`（460px 窗宽下 4 列过挤，改为 2×2 排布）
  - `.disk-groups` 内部滚动：`max-height: 320px; overflow-y: auto; padding-right: 4px`（窗口头部 / 指标 / kv 保持固定可见；物理盘较多时区域内部滚动，滚动条复用 `.ops-console-root ::-webkit-scrollbar` 政务蓝样式）

#### 运维控制台 OpsServerWindow 卡片头操作按钮 + OpsInspectionLogWindow 采集记录窗口（2026-08-17，用户需求）

应用户要求把 `srv-card-time` 标签贴近服务器名称（DOM 顺序调整 + `flex-shrink:0`），同行追加两个 22×22 图标按钮「📄 日志」+「✦ 智能检测」；日志按钮打开新窗口 `OpsInspectionLogWindow`（左 280px 列表 + 右自适应详情，复用 `OpsDetailWindow` 同样式）。

要点：
- **卡片头 DOM 顺序**：`[LED] [服务器名] [最新检测时间] [日志] [智能检测]`。时间标签 `flex-shrink:0` 保证不被按钮挤压。CSS 不动（`.srv-card-time` 块注释追加「DOM 顺序调整」说明）。
- **按钮样式 `.srv-card-btn`**（`web/Agent/src/styles/ops-console.css`，2026-08-17 新增）：22×22 紧凑尺寸；圆角 5px；白底 + 1px 政务蓝边框；hover 政务蓝半透明；disabled 状态 45% 不透明 + not-allowed 光标 + hover 不变色；SVG 13×13。
- **按钮事件契约**：
  - 日志：原生 `<button>`，无 `disabled`，`@click.stop="emit('open-log', srv)"` —— 父级 OpsConsoleApp 调 `openInspectionLog(srv)` 拉取 `server_inspection_records` 后挂载 OpsInspectionLogWindow。
  - 智能检测：原生 `<button disabled>`，不 emit 任何事件（即使尝试 trigger 也被 disabled 拦截）。`title="智能检测(暂未开放)"` 鼠标悬停提示；父级仍注册 `@open-detect="onOpenDetect"` 占位回调（`console.warn` 警告），便于后续 PR 接入时定位入口。
- **`@click.stop` 阻断冒泡**：按钮点击不会触发卡片整体的 `@click="emit('open-detail', srv)"`（即日志按钮不会顺带打开详情页）。
- **新窗口 `OpsInspectionLogWindow.vue`**（GNOME 直角 + 标题栏 max/close 两按钮，760×460）：
  - **左栏 `.inslog-list`**（280px 固定宽度 + 政务蓝半透明背景 + 右侧 1px 分割线 + overflow-y auto）：
    - 每条记录行 `.inslog-item`：第一行 `formatCollectedAt(collected_at)` + `.inslog-badge` 状态徽章（pass/warn/crit/skipped/unassessed 五态色块，与运维 LED 同系配色）；第二行「耗时 `formatDuration(duration_ms)`」+「exit `exit_code`」+「成功 / 失败」；`error_message` 非空时红字 ellipsis 摘要（`title` 完整 hover 提示）。
    - 默认选中首条（`active` 类：政务蓝 16% 底 + 3px 政务蓝左 border + `padding-left:9px` 补偿）；点击切换；`records` 切换时 `watch` 把选中态重置到第一条。
    - 空态：records=[] → 「暂无采集记录」；loading=true → 「加载中…」。
  - **右栏 `.inslog-detail .detail-body`**（flex:1 + 自适应宽度）：
    - inline 渲染 OpsDetailWindow 的指标卡 / kv / 物理磁盘分组（避免嵌套窗口外壳造成双重标题栏）；
    - 数据通过 `mapRecordToServer(record, baseServer)` 纯函数把后端 `parsed_values` 归一化为 ServerItem 形状（系统盘 mount 优先 + 兜底首块可用盘 + parsed_values JSON 字符串防御性 parse + field_results list 校验）。
- **OpsDetailWindow 双 script 块改造**：原 `<script setup>` 内的纯函数（`fmtPct / fmtMs / fmtStr / warnColor / ioAwaitValue / diskGroupLabel / partitionCardStatus / diskHeadStatus / peakIoAwait / peakIoUtil / IOWAIT_WARN / SWAP_WARN / INODE_WARN` + 既有 `groupDisksByPhysicalDisk`）搬到 `<script>` 块并加 `export`，与 `OpsServerWindow.vue` 同款模式。`<script setup>` 仅保留 `props / emits / hasDisks / diskGroups` 4 个组件 setup 实体。新增具名导出 `statusLabel(inspection_status)`（pass/warn/crit/skipped/unassessed → 中文明文）与 `formatDuration(ms)`（<1000 显示 `ms`，≥1000 显示 `s`，与运维读卡器一致）。组件 setup 行为完全不变（DOM 渲染逻辑未动）。
- **OpsConsoleApp 状态机新增 4 项**：
  - `wins.inspectionLog: { open: false, max: false, x: 220, y: 100, z: 1 }`（默认关闭）
  - `inspectionLogServer: ref(null)` —— 当前查看记录的服务器
  - `inspectionLogRecords: ref([])` —— 历史采集记录数组
  - `inspectionLogLoading: ref(false)` —— 拉取中标记
  - 新增 `import { fetchServerInspectionRecords } from '../../utils/api.js'`
  - 新增函数 `async openInspectionLog(srv)`：写入 server → 开窗 → bringFront → loading=true → 异步拉取 `GET /api/admin/server-inspection/records?server_id=X&limit=100` → 写入 records（失败回空列表 + warn 日志）；`closeInspectionLog()`：清空 4 个状态；`onOpenDetect(_srv)`：console.warn 占位。
  - 模板 `<OpsServerWindow>` 加 `@open-log / @open-detect`；末尾挂载 `<OpsInspectionLogWindow>`（仅在 `inspectionLogServer && wins.inspectionLog.open` 时渲染）。
- **完全复用现有后端**：`GET /api/admin/server-inspection/records`（`app/routers/server_inspection_router.py::get_records`）已存在 5 个月，无需任何后端改动；`server_inspection_records` 表 `parsed_values` / `field_results` JSONB 字段自 2026-08-05 起已落库。
- **不引入新菜单 / ACL**：`OpsInspectionLogWindow` 仅在运维控制台内部由卡片头按钮触发，不进 `MENU_CATALOG`，不消耗单独权限；现有 `/api/admin/server-inspection/records` 复用 `task-scheduler.server-management` 菜单 ACL。
- **零业务逻辑回退**：`OpsServerWindow` 单击卡片整体仍正常 emit `open-detail`（单元测试 `test_card_body_click_still_emits_open_detail` 覆盖）。

测试同步：
- `OpsServerWindow.card.spec.js` 新增 `describe('OpsServerWindow 卡片头操作按钮（2026-08-17 新增）')` 5 用例：`test_card_renders_two_action_buttons`（按钮数量 + aria-label + disabled 属性）/ `test_log_button_emits_open_log`（emit 载荷校验）/ `test_log_button_click_does_not_bubble`（@click.stop 不触发 open-detail）/ `test_detect_button_disabled_does_not_emit`（disabled 拦截）/ `test_card_body_click_still_emits_open_detail`（卡片非按钮区域点击回归保护）。老用例零回归。
- `OpsInspectionLogWindow.spec.js` 新增 13 用例：组件可 import + `mapRecordToServer` 纯函数 6 用例（基础字段映射 / pass → ok / warn → err / success=false → err / 缺 parsed_values → null / null record → baseServer 兜底）+ 左栏列表 5 用例（records 渲染 + 默认选中首条 / 状态徽章颜色映射 / 点击切换 / 空态 / loading 态）+ 右栏指标渲染 + 错误摘要 + 窗口 max / close 事件 + 窗口标题包含服务器名。
- `OpsConsoleApp.exit.spec.js` 老用例零回归（添加 `OpsInspectionLogWindow: true` stub 时未触及）。
- `OpsDetailWindow.redesign.spec.js` 老用例零回归（双 script 改造未触动组件 setup 行为）。

变更文件清单：
- `web/Agent/src/components/ops-console/OpsServerWindow.vue`（卡片头新增两个按钮 + 注释 + emits 新增 `open-log / open-detect`）
- `web/Agent/src/components/ops-console/OpsDetailWindow.vue`（纯函数从 `<script setup>` 搬到 `<script>` + 新增 `statusLabel / formatDuration`）
- `web/Agent/src/components/ops-console/OpsInspectionLogWindow.vue`（**新增**，左 280 列表 + 右自适应详情）
- `web/Agent/src/components/ops-console/OpsConsoleApp.vue`（状态机 + 3 个新函数 + 模板挂载新窗口 + `<OpsServerWindow>` 加 2 个事件监听）
- `web/Agent/src/styles/ops-console.css`（`.srv-card-btn` 6 个块 + `.win-inspection-log / .inslog-body / .inslog-list / .inslog-item / .inslog-row1 / .inslog-row2 / .inslog-time / .inslog-badge / .inslog-meta / .inslog-err / .inslog-empty / .inslog-detail` 12 个新块）
- `web/Agent/src/components/ops-console/__tests__/OpsServerWindow.card.spec.js`（新增 5 用例）
- `web/Agent/src/components/ops-console/__tests__/OpsInspectionLogWindow.spec.js`（**新增**，13 用例）

