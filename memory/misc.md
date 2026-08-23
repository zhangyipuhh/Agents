# 其他子系统

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## 邮件系统

### 核心设计

邮件系统采用**核心服务层与 FastAPI 解耦**的设计，支持两种调用方式：

1. **HTTP 路由层**：`/api/admin/email/*` 端点（admin 权限），供前端管理界面调用。
2. **脚本/定时任务直接调用**：`asyncio.run(EmailService(config).send_email(...))`，无需启动 FastAPI 应用。

### 核心服务层

- `EmailService(config: EmailServerConfig)` —— 核心发送服务，构造时仅依赖配置对象（不依赖 `Request` / `app.state`）。使用 `smtplib.SMTP_SSL` (465) 或 `smtplib.SMTP+starttls` (587)，通过 `asyncio.to_thread` 在线程池中执行同步 SMTP 调用。支持 `attachment_paths`（脚本绝对路径）和 `attachment_streams`（FastAPI 上传的 bytes 流）两种附件传入方式。
- `EmailConfigService(db, credential_key)` —— 配置服务，提供 SMTP 配置 CRUD + 策略 CRUD + Fernet 加解密。`@register_schema` 装饰的 `init_email_schema()` 在应用启动时自动建表。

### 脚本调用示例

```python
import asyncio
from app.shared.utils.email.email_models import EmailServerConfig
from app.shared.utils.email.email_service import EmailService

config = EmailServerConfig(host="smtp.qq.com", port=465, use_ssl=True,
                           username="xxx@qq.com", password="授权码",
                           sender_name="管理员", enabled=True)
asyncio.run(EmailService(config).send_email(
    to=["target@example.com"],
    subject="脚本测试",
    body="来自脚本的邮件",
    attachment_paths=["/abs/path/test.pdf"],
))
```

### 数据库表

| 表名 | 用途 |
|---|---|
| `email_server_configs` | SMTP 服务器配置（单行约束，`password_encrypted` Fernet 加密，复用 `DEVOPS_CREDENTIAL_KEY`） |
| `email_policies` | 发送策略（策略名 + 描述 + 创建者用户 ID） |
| `email_policy_recipients` | 策略-收件人多对多关联（policy_id + user_id 联合主键） |

`email_server_configs` 字段：id / host / port / use_ssl / username / password_encrypted / sender_name / enabled / **force_plain** / **verify_ssl** / created_at / updated_at。通过 `CREATE UNIQUE INDEX ... WHERE enabled = TRUE` 保证全局仅一条启用配置。

`force_plain`（BOOLEAN，默认 FALSE）与 `verify_ssl`（BOOLEAN，默认 TRUE）是 2026-07-18 新增的企业邮箱兼容字段：
- `force_plain=True` 时 `smtplib` 不调用 `starttls()`，支持 25 端口明文 SMTP（Foxmail 走 25 时不加密）
- `verify_ssl=False` 时 `SSLContext.check_hostname=False` + `verify_mode=CERT_NONE`，跳过证书校验（企业自签证书场景）
- `EmailConfigService._build_ssl_context(config)` 统一构造 `SSLContext`，默认把 `minimum_version` 降级到 `TLSv1`，兼容老企业 SMTP（Python 3.10+ 默认 `TLSv1.2` 会触发 `[SSL: WRONG_VERSION_NUMBER]`）
- 前端 `EmailSettingsManager.vue` 把这两个选项放在「服务器配置」Tab 末尾的折叠面板「高级选项（企业邮箱兼容）」内，默认收起，避免新手误操作

#### `password_encrypted` 列类型与 Fernet 写入约定

列类型固定为 `TEXT`（**不**用 `BYTEA`）。asyncpg 对 `TEXT` 列不接受 `bytes` 入参，会抛 `DataError: expected str, got bytes`；而 Fernet `encrypt()` / `decrypt()` 默认返回 `bytes`。因此：

- **写库前**：`EmailConfigService._to_db_str(value)` 把 `bytes` 用 `ascii` 解码为 `str`，再作为 `$5` 参数传给 `INSERT` / `UPDATE` SQL。Fernet token 仅含 url-safe base64 ASCII 字符，解码零成本。
- **读库后**：`EmailConfigService.get_active_server_config()` 将 `str` 字段 `encode("ascii")` 回 `bytes` 再喂给 `fernet.decrypt(...)`。
- 两方向不能合并：service 必须同时维护「bytes → DB（str）」与「DB（str） → bytes」两条归一化路径，任何一边遗漏都会立刻抛异常。

`email_policies` 字段：id / name / description / created_by_user_id (FK→users) / subject_template / body_template / created_at / updated_at。

`email_policy_recipients` 字段：policy_id (FK→email_policies, CASCADE) / user_id (FK→users, CASCADE)，联合主键。

#### 策略模板（subject_template / body_template）

策略可携带两个模板字段用于定时任务通知邮件：

- `subject_template VARCHAR(500)` —— 邮件主题模板，含 `{{var}}` 占位符；空字符串时使用策略名作为主题。
- `body_template TEXT` —— 邮件正文模板；空字符串时直接使用脚本返回值（`normalize_script_result` 第一项）作为正文。

占位符白名单（见 `app/shared/utils/email/template_renderer.py::EmailTemplateRenderer.SUPPORTED_VARS`）：`schedule_name` / `schedule_id` / `run_id` / `started_at` / `finished_at` / `trigger_type` / `script_name` / `script_output` / `attachment_paths` / `timestamp`。非白名单占位符保留原样（方便排查）；`datetime` 渲染为 `YYYY-MM-DD HH:MM:SS`；`list` 渲染为逗号拼接；`None` 渲染为空串。

`timestamp` 为特殊变量，不依赖执行上下文，在邮件发送时动态取当前时间：
- `{{timestamp}}` 默认渲染为 `YYYY-MM-DD HH:MM:SS`；
- `{{timestamp|FORMAT}}` 使用自定义 strftime 格式，例如 `{{timestamp|%Y%m%d%H%M}}` 渲染为 `202607201109`，`{{timestamp|%Y-%m-%d %H:%M}}` 渲染为 `2026-07-20 11:09`；
- 格式非法时保留原占位符文本，避免发送失败。

模板渲染不引入 Jinja2，仅 `re.sub(r"\{\{\s*(\w+)(?:\|([^}]*)?)?\s*\}\}", ...)` + 白名单校验，避免任意表达式执行。

### API 端点（`/api/admin/email`，全部 `require_admin`）

| 方法 | 路径 | 用途 |
|---|---|---|
| GET | `/server-config` | 获取 SMTP 配置（密码字段返回空字符串，不外泄） |
| PUT | `/server-config` | 保存 SMTP 配置（密码为空字符串时保留原密码） |
| POST | `/server-config/test` | 测试 SMTP 连接（不发送邮件） |
| GET | `/emailable-users` | 列出已注册且邮箱非空用户（供前端挑选收件人） |
| GET | `/policies` | 策略列表（按 OwnershipScope 过滤：admin 见全部；普通用户仅见自己创建） |
| POST | `/policies` | 新建策略（`created_by_user_id = request.state.user_id`） |
| GET | `/policies/{id}` | 策略详情（越权 404） |
| PUT | `/policies/{id}` | 更新策略（越权 404） |
| DELETE | `/policies/{id}` | 删除策略（越权 404） |
| POST | `/test` | 发送测试邮件（multipart/form-data，支持本地附件上传） |
| POST | `/send-by-policy/{policy_id}` | 按策略发送邮件（越权 404；JSON body：subject / body / attachment_paths） |

### 配置项

- `settings.email_enabled: bool = True` —— 邮件系统总开关（环境变量 `EMAIL_ENABLED`），关闭时 lifespan 跳过 `EmailConfigService` 初始化。

### Lifespan 集成

`app/core/server.py::lifespan` 在 `DatabasePool.register_schemas()` 完成、`db_pool = DatabasePool._pool` 取到之后立即初始化 `EmailConfigService`（**早于 Agent/MCP/ScriptDiscovery/TaskScheduler**），确保 `TaskSchedulerService` 构造时能拿到真实 `email_config_service` 实例：

```python
if DatabasePool.is_enabled() and DatabasePool._pool is not None and settings.email_enabled:
    email_diag = diagnose_credential_key()
    if email_diag.ok:
        app.state.email_config_service = EmailConfigService(
            db=DatabasePool._pool,
            credential_key=settings.devops.credential_key,
        )
        await app.state.email_config_service.preload_all()
```

后续 `TaskSchedulerService(...)` 通过 `email_config_service=getattr(app.state, "email_config_service", None)` 注入同一实例，邮件管理路由（`/api/admin/email/*`）与脚本任务通知共享同一 `EmailConfigService`，避免缓存分叉。

若 `DEVOPS_CREDENTIAL_KEY` 未配置，邮件服务降级（`app.state.email_config_service = None`），API 返回 503。

### 前端

- `web/Agent/src/components/EmailSettingsManager.vue` —— 邮件设置组件（3 Tab：服务器配置 / 发送策略 / 测试发送）。服务器配置表单采用 2 列网格；`密码 / 授权码` 跨两列；`使用 SMTP_SSL` 与 `启用此配置` 两个复选框（`.inline-field`，`gap: 4px` + `justify-self: start`，只占内容宽度，左对齐）并置于操作按钮之前。发送策略 Tab 使用 `recipientKeyword` 响应式状态筛选收件人姓名、用户名和邮箱，并在新建、编辑、取消编辑时重置。策略编辑器在「策略描述」下方、「收件人」上方新增「主题模板」「正文模板」两个字段（`data-testid="policy-subject-template"` / `data-testid="policy-body-template"`），模板支持 `{{var}}` 占位符；前端保存时把 `subject_template` / `body_template` 加入 payload。
- `web/Agent/src/components/TaskSchedulerManager.vue` —— 当 `target_type === 'script'` 时显示「启用邮件通知」复选框（`data-testid="schedule-notify-enabled"`）与「邮件策略」下拉（`data-testid="schedule-notify-policy"`，按需调用 `fetchEmailPolicies()`）；切换 `target_type` 到 `agent` 时自动清空 `notify_enabled` / `notify_policy_id`。通知复选框使用 `.inline-field input[type="checkbox"]` 覆盖通用输入框宽度，保持内容宽度，并与说明文字按 `gap: 4px` 紧凑左对齐。
- `web/Agent/src/components/TaskSchedulerManager.vue` —— 任务计划组件，表单 `保存后启用任务` 复选框使用 `.inline-field`（`gap: 4px` + `justify-self: start`，与 `EmailSettingsManager` 保持一致的紧凑左对齐风格）。
- `web/Agent/src/components/TaskSchedulerManager.vue` —— 「保存任务」按钮从 form 底部 `<div class="form-actions">` 移到 `detail-header` 顶部 `.actions` 行（`data-testid="schedule-save-btn"`），通过 `form="task-scheduler-form"` 显式挂回 `<form id="task-scheduler-form">` 触发原生 submit；`.actions` 在 `isCreating || selectedSchedule` 时渲染，新建模式仅显示「保存任务」，编辑模式追加「停用/启用任务」「立即运行」「删除任务」；CSS 中 `.form-actions` 全宽规则与共用 flex 规则已清理。
- `web/Agent/src/components/TaskSchedulerManager.vue` —— `loadInitialData()` 在首屏并行预加载 `fetchTaskSchedules` / `fetchAdminAgentList` / `fetchScripts`（失败降级为空数组），保证「目标脚本」`<select>` 在用户首次选中脚本类型任务时即已含匹配 `<option>`，避免 `form.script_name` 因缺 option 而 UI 显示空。预加载完成后置 `hasLoadedScripts=true`，后续「脚本扫描入库」Tab 切换不再重复 GET。
- `web/Agent/src/components/UserSettingsDialog.vue` 中「定时任务（admin）」与「邮件设置（admin）」Tab 的外层 wrapper 应用 `.tab-fill-wrapper`（`display: flex; flex: 1; min-height: 0; flex-direction: column; overflow-y: auto`），让下游 `TaskSchedulerManager` / `EmailSettingsManager` 沿父级 flex 高度链撑满 `.dialog-content` 可视高度，避免 `<aside>` / `<main>` 下方留白；**高度链前提**：`.dialog-content` 自身必须是 flex 列容器（`display: flex; flex-direction: column`），否则 wrapper 的 `flex: 1` 惰性失效、高度退化为内容高度导致面板下方留白；`overflow-y: auto` 是安全网——未自滚动填充的组件（如 EmailSettingsManager）内容超高时由 wrapper 滚动，防止被 `.dialog-body-horizontal { overflow: hidden }` 裁剪；对应回归测试见 `src/components/__tests__/UserSettingsDialog.task-scheduler-wrapper.spec.js`（含 `.dialog-content` flex 列容器与 `.tab-fill-wrapper` overflow 安全网两条源码静态契约断言）。
- `web/Agent/src/components/TaskSchedulerManager.vue` 高度链固定后的内部滚动契约（防内容溢出卡片）：`.task-sidebar { overflow-y: auto }`（任务列表内部滚动）；`.tablist { flex-shrink: 0 }`（tab 栏不被压缩）；`.task-detail > section[role="tabpanel"]:not(.task-panel-api) { flex:1; min-height:0; overflow-y:auto }`（编辑任务/服务器扫描/脚本扫描三面板内部滚动）；`.task-detail > .task-panel-api { overflow: hidden }`（API 面板裁剪防外溢，子组件 ApiConfigManager 自滚动）；回归测试见 `TaskSchedulerManager.spec.js` 末尾「内部滚动契约（防溢出）」describe 块（4 条源码静态断言）。
- `web/Agent/src/components/EmailSettingsManager.vue` 高度链固定后的内部滚动契约（防内容溢出卡片，与 `TaskSchedulerManager` 同款）：`.email-settings-manager > section[role="tabpanel"] { flex:1; min-height:0; display:flex; flex-direction:column }`（服务器配置/发送策略/测试发送 三个 panel 沿根 section 高度链铺满剩余高度，外框始终贴满可视区）；`.detail-header { flex-shrink:0 }`（tabpanel flex 列容器下防头部被压成 0）；`.email-form { flex:1; min-height:0; overflow-y:auto }`（服务器配置 Tab「高级选项」展开 + 测试发送 Tab 多附件/长正文 内部自滚动，覆盖 server/test 两个 Tab）；`.policies-layout { flex:1; min-height:0 }`（grid 容器解封 flex 链断点）；`.policies-list { overflow-y:auto; min-height:0 }`（策略列表在左侧独立滚动）；`.policy-editor { overflow-y:auto; min-height:0; flex:1 }`（策略编辑表单在右侧独立滚动）；`.recipient-list` 仍保留 `max-height:240px; overflow-y:auto` 二级滚动；回归测试见 `EmailSettingsManager.spec.js` 末尾「内部滚动契约（防内容溢出）」describe 块（5 条源码静态断言：tabpanel flex 链 / policies-layout 解封 / 策略列表+编辑器自滚动 / email-form 自滚动 / detail-header 防压缩）。
- `web/Agent/src/components/TaskSchedulerManager.vue` 的定时任务卡片为 `article.task-item` 容器，内部由 `.task-select-btn` 负责编辑任务选择、`.task-history-btn` 负责仅图标执行历史入口；点击历史按钮通过 `Teleport to="body"` 打开单任务执行历史弹窗，复用 `fetchTaskRuns(scheduleId, 50)`，支持关闭按钮、遮罩点击和 Escape，不改变后端接口或数据库结构；`TaskSchedulerManager.spec.js` 覆盖弹窗无文字入口、ARIA dialog、目标任务加载、错误展示和关闭交互。
- `web/Agent/src/components/TaskSchedulerManager.vue` —— `.task-scheduler-manager` 与 `web/Agent/src/components/ApiConfigManager.vue` 的 `.api-config-manager` / `.acm-layout` 改用 `flex: 1` 沿 `.tab-fill-wrapper` 传递的高度链撑满父级，并保留 `min-height: 560px` / `480px` 作为小视口兜底；`height: 100%` 不再使用（block 父级下退化为 auto 导致 grid items 不撑满）。
- `web/Agent/src/components/EmailSettingsManager.vue` —— 根 `<section class="email-settings-manager">` 应用 `display: flex; flex-direction: column; flex: 1; min-height: 0`，沿 `.tab-fill-wrapper` 高度链撑满 `.dialog-content` 可视高度；与 `TaskSchedulerManager` / `ApiConfigManager` 共用同一 `flex: 1` 模式，不再使用 `height: 100%`；对应回归测试见 `EmailSettingsManager.spec.js::test_email_settings_section_fills_available_height`（源码静态契约断言 4 个属性同时存在）。
- 在 `web/Agent/src/components/UserSettingsDialog.vue` 中作为「邮件设置」侧边栏项（位于「定时任务」下方，admin 可见）。
- API 封装位于 `web/Agent/src/utils/api.js`：`fetchEmailServerConfig` / `updateEmailServerConfig` / `testEmailServerConfig` / `fetchEmailableUsers` / `fetchEmailPolicies` / `createEmailPolicy` / `updateEmailPolicy` / `deleteEmailPolicy` / `sendTestEmail`（multipart/form-data）/ `sendEmailByPolicy`。

### 设计决策

1. **SMTP 协议**：`SMTP_SSL` (465) 与 `SMTP+starttls` (587) 二选一，由前端表单 `use_ssl` 勾选框决定（QQ 邮箱官方推荐 587+STARTTLS，465 在部分网络环境会被运营商 RST）。**不应**硬编码为某一端。
2. **认证方式**：用户名 + 密码（QQ 用授权码），不实现 OAuth2。
3. **附件支持**：`email.message.EmailMessage.add_attachment`，Python 标准库，无需额外依赖。
4. **密码加密**：复用 `DEVOPS_CREDENTIAL_KEY`（Fernet），避免新增加密基础设施。
5. **策略范围**：仅收件人集合（用户确认），不含主题/正文模板；调用方负责主题/正文。
6. **不实现定时触发**：策略仅是收件人集合，定时发邮件可通过 `agent_task_schedules.target_type='script'` 调用邮件脚本实现。
7. **SMTP 主机与账号域名一致性**：`username` 的域名后缀必须与 `host` 指向的 SMTP 服务匹配。个人 QQ 邮箱 → `smtp.qq.com`；腾讯企业邮箱 → `smtp.exmail.qq.com`；不匹配时服务器会在协议握手后主动断开连接（`smtplib.SMTPServerDisconnected`）。`test_connection` 已对该类异常做单独捕获并给出切换主机建议。
8. **test_connection 异常分类**：错误消息按 `SMTPAuthenticationError` / `SMTPServerDisconnected` / `SMTPConnectError` / `ssl.SSLError` / `OSError` / 其他 6 类细分返回，便于前端展示与日志定位（全部带 `logger.warning` 调用栈）。
9. **企业邮箱协议兼容（2026-07-18 新增）**：`_build_ssl_context(config)` 把 `SSLContext.minimum_version` 降级到 `TLSv1`（Python 3.10+ 默认 `TLSv1.2` 会触发 `[SSL: WRONG_VERSION_NUMBER]`）；`force_plain=True` 时跳过 `starttls()`；`verify_ssl=False` 时关闭证书校验。`EmailService._smtp_send` 复用同一 helper，保证测试连接与实际发送使用一致的协议栈。
10. **send_message refused 静默拒收校验（2026-07-18 新增）**：`smtplib.SMTP.send_message()` 在 RCPT TO 被拒时仅把失败项存到 `smtp.refused` 字典**不抛异常**，导致 UI 显示「发送成功」但实际邮件未送达（典型场景：企业邮箱 → QQ 邮箱被反垃圾拦截）。`EmailService._smtp_send` 在调用 `send_message` 后必须显式检查返回值，非空时抛 `EmailSendError` 让上层返回失败。**这是 P0 防御性检查，不可省略**。
11. **企业邮箱 → QQ 邮箱单向不通的根因（2026-07-18 实测）**：Foxmail 发到 QQ 也收不到，但 QQ 发到企业能收到 → 双向不对称投递。这是**企业邮箱出站 IP 在 QQ 黑名单**或**域名 `geostar.com.cn` 缺 SPF/DKIM**导致被 QQ 拒收。SMTP 协议层返回 250 OK 后企业服务器"接收即丢弃"。**代码层面无法解决，必须 IT 介入**：① `nslookup mail.geostar.com.cn` 拿 IP 查 mxtoolbox.com/blacklists；② `dig TXT geostar.com.cn` 查 SPF；③ `dig TXT default._domainkey.geostar.com.cn` 查 DKIM；④ 收件方在 QQ 邮箱「反垃圾→白名单」加 `geostar.com.cn`。
12. **邮件消息 RFC 5322 必备头缺失导致反垃圾拦截（2026-07-18 修复）**：Python `email.message.EmailMessage` **不会自动添加 `Date` / `MIME-Version` 头**。原 `_build_message` 只设置 `From` / `To` / `Subject` / `Message-ID`，导致我们系统的邮件普遍被反垃圾系统判为"伪造邮件"静默丢弃（QQ 邮箱 / 企业邮箱 / 网易等都会拦截）。同时 `Message-ID` 域用 `cfg.host`（如 `smtp.qq.com`），但 `From` 域是 `cfg.username` 的 `@` 后部分（如 `foxmail.com`），**域不一致**也被反垃圾标记。修复：`msg["Date"] = formatdate(localtime=True)` + `msg["MIME-Version"] = "1.0"` + `make_msgid(domain=cfg.username.rsplit("@",1)[-1])`。这是"显示成功但收不到"的最常见根因，**必须在所有 `_build_message` 路径上加这三个头**。
12a. **反垃圾判定头 + envelope 一致性（2026-07-18 用户实测补充）**：跨域投递（QQ SMTP → 企业邮箱）场景下，仅补齐 Date/MIME-Version/Message-ID 仍会被收件方反垃圾网关静默拒收（SMTP 仍 250 OK）。需要同时满足：
    - `msg["X-Mailer"] = "feature-agent-core/internal-mailer"`：声明发件客户端，未声明被判"未知脚本发信"。
    - `msg["X-Priority"] = "3"`：Normal 优先级，避免 1 (High) 被判为脚本批量通知垃圾特征。
    - `msg["Return-Path"] = cfg.username`：必须与 From 同地址，否则 envelope MAIL FROM 与 header From 域不一致 → SPF/DKIM 校验失败 → 反垃圾直接拒收。
    - `msg["Reply-To"] = cfg.username`：避免空 Reply-To 触发"无回复地址"扣分。
    - `smtp.send_message(..., from_addr=cfg.username, mail_options=["SMTPUTF8"], ...)`：显式传 envelope sender（部分 SMTP 转发时会改写 envelope MAIL FROM）+ UTF-8 envelope（中文 display name 不被 ascii 编码失败）。
    任意一条缺失都可能导致 250 OK 但邮件被静默丢弃。**这 4 个头 + envelope 显式传入是不可省略的反垃圾前置条件**。
13. **QQ SMTP → 企业邮箱可正常投递（2026-07-18 最终实测）**：用本系统配 `smtp.qq.com`（foxmail 账号）发到 `zhangyipu@geostar.com.cn` 已成功送达收件箱。此前"QQ SMTP 出口对陌生域名外发有限制、代码无法解决"的定性系**误判**，真实原因是两个混杂变量：① 失败测试跑在**未重启的旧进程**上，RFC 5322 头修复（第 12 条）尚未生效，缺 `Date` 头被企业网关判伪造静默丢弃；② 测试内容为主题/正文均为"测试"的垃圾特征词。**教训：改完代码必须重启服务再测（否则在测旧代码）；测试邮件避免使用"测试"类垃圾特征词**。归因备注：重启与换内容两个变量同时变化，未做单变量隔离实验，但"QQ 出口封禁"定性已被成功投递事实推翻。
14. **系统代码正确性已最终确认（2026-07-18 用户实测）**：企业邮箱 SMTP（mail.geostar.com.cn）→ 企业内部邮箱能通，且 QQ SMTP（smtp.qq.com）→ 企业邮箱也已实测打通（见第 13 条）→ 系统邮件发送代码两个方向均验证正确；所有代码修改（RFC 5322 必备头、SSL 兼容、STARTTLS 跳过、证书校验关闭、refused 校验）都是**必要且正确的预防性修复**。剩余唯一不通方向是**企业邮箱 → QQ 邮箱**（见第 11 条，系 QQ 侧对 geostar 域的接收策略，与本系统代码无关）。
15. **username 必须含 @ 的防御校验（2026-07-18 新增）**：From 头由 `cfg.username` 构造，纯用户名（无 @ 域名）会生成 `显示名 <zhangyipu>` 这类畸形 From，SMTP 返回 250 但收件方反垃圾网关静默丢弃。两处 fail-fast：① `EmailService.send_email` 发送前抛 `EmailSendError`；② `EmailConfigService.upsert_server_config` 保存时抛 `EmailConfigValidationError`（路由层 `_handle_config_error` 自动映射 400）。`_build_message` 的 Message-ID 域 host fallback 保留作为底层防御。
16. **成功路径日志（2026-07-18 新增）**：`EmailService.send_email` 成功时 `logger.info` 记录 `message_id / from / to`（此前仅有失败日志），用于事后排查"显示成功但收不到"时确认信封信息。前端测试发送 Tab 同步追加说明文案：「发送成功」仅代表 SMTP 服务器已接收（250 OK）不代表对方已投递，跨域发送可能被对方反垃圾网关静默丢弃。
17. **EHLO local_hostname=cfg.host 保留不改（2026-07-18 排查结论）**：曾怀疑从动态 IP 以 `EHLO smtp.qq.com` 声明是伪造特征导致对方网关静默丢弃，但第 13 条的最终实测证明：**同一份 EHLO 代码在重启后投递成功**，EHLO 从来不是拦截因素；且改动 `local_hostname` 会让已验证可用的路径承担回归风险，故保持现状。

## 飞书工具（Feishu Tools）

### 核心模块

| 路径 | 职责 |
|---|---|
| `app/shared/tools/skills/feishu/FeishuClient.py` | `get_lark_client()` 公共工厂：从 `settings.feishu` 读取凭证，构造线程安全单例 `lark.Client`；`reset_lark_client()` 供测试重置缓存 |
| `app/shared/tools/skills/feishu/FeishuMessageTools.py` | 1 个 `@tool(description=...)`：`send_feishu_message`（自动 Markdown 检测 → text / interactive 卡片发送；2026-08-23 起：内容含 Markdown 特征时走 `msg_type="interactive"` + `MarkdownToCardConverter.to_card_json()` schema=2.0 卡片，保证飞书侧正确渲染；纯文本仍走 `msg_type="text"`） |

### 配置（FeishuSettings）

`app/core/config/settings.py::FeishuSettings`，通过 `.env` 环境变量注入：

- `feishu_app_id`（env `FEISHU_APP_ID`）—— 飞书应用 App ID，空字符串表示未配置
- `feishu_app_secret`（env `FEISHU_APP_SECRET`）—— 飞书应用 App Secret
- `feishu_default_receive_id`（env `FEISHU_DEFAULT_RECEIVE_ID`）—— 默认接收方 ID（群 chat_id 或用户 open_id）
- `feishu_default_receive_id_type`（env `FEISHU_DEFAULT_RECEIVE_ID_TYPE`，默认 `chat_id`）—— 接收方类型：chat_id / open_id / user_id / email
- `feishu_log_level`（env `FEISHU_LOG_LEVEL`，默认 `INFO`）—— SDK 日志级别
- `feishu_ws_enabled`（env `FEISHU_WS_ENABLED`，默认 `False`）—— 是否启用 WebSocket 长连接接收消息
- `feishu_ws_agent_name`（env `FEISHU_WS_AGENT_NAME`，默认 `project`）—— 飞书消息路由到的目标智能体名称
- `feishu_ws_receiver_username`（env `FEISHU_WS_RECEIVER_USERNAME`，默认 `feishu_bot`）—— 飞书 WebSocket 产生的会话归属到的系统用户名
- `feishu_card_streaming_enabled`（env `FEISHU_CARD_STREAMING_ENABLED`，默认 `True`）—— 是否启用 CardKit 元素级流式更新；`False` 时回退到整卡更新
- `feishu_card_streaming_print_frequency_ms`（env `FEISHU_CARD_STREAMING_PRINT_FREQUENCY_MS`，默认 `70`）—— CardKit streaming 打印频率（毫秒）
- `feishu_card_streaming_print_step`（env `FEISHU_CARD_STREAMING_PRINT_STEP`，默认 `1`）—— CardKit streaming 打印步长（字符数）
- `feishu_card_streaming_print_strategy`（env `FEISHU_CARD_STREAMING_PRINT_STRATEGY`，默认 `"fast"`）—— CardKit streaming 打印策略
- `feishu_card_update_interval_ms`（env `FEISHU_CARD_UPDATE_INTERVAL_MS`，默认 `600`）—— CardKit 两次更新最小时间间隔（毫秒）
- `feishu_card_update_delta_chars`（env `FEISHU_CARD_UPDATE_DELTA_CHARS`，默认 `50`）—— CardKit 两次更新最小字符增量

字符串布尔值兼容：`feishu_ws_enabled` 与 `feishu_card_streaming_enabled` 的 `@field_validator` 会把 `"true" / "1" / "yes" / "on"` 统一转为 `True`。

`Settings.get_feishu_config()` 返回扁平字典供旧代码访问，包含上述全部字段。

### 依赖

- `lark-oapi>=1.4.0`（见 `app/requirements.txt`）

### 工具发现

- 仅使用 `@tool(description=...)` 装饰，不调用 `register_tool`
- 工具元数据由 `ToolRegistryService` 源码扫描 `app/shared/tools/skills/feishu/FeishuMessageTools.py` 自动发现

### 测试覆盖

- `app/tests/shared/tools/skills/feishu/test_feishu_client.py` —— 9 个用例：导入存在性、凭证缺失抛 RuntimeError、单例缓存、reset 清空、日志级别映射
- `app/tests/shared/tools/skills/feishu/test_feishu_message_tools.py` —— 10 个用例（原 7 个文本路径用例 + 2026-08-23 新增 3 个 Markdown 卡片路径用例：`test_send_feishu_message_renders_markdown_as_card` / `test_send_feishu_message_pure_text_keeps_text_type` / `test_send_feishu_message_card_json_contains_md_elements`）：导入存在性、receive_id 缺失、client 初始化失败、API 成功/失败/异常、显式参数覆盖默认配置、Markdown 触发 interactive 卡片 + schema=2.0、纯文本保持 text 类型、卡片 elements 含 markdown / code_block
- `app/tests/shared/tools/skills/feishu/test_feishu_websocket_service.py` —— 101 个用例：模块导入存在性、消息字段提取（p2p / group / file）、session_id 构造、群聊 @机器人 检测（精确 + 仅 open_id 缺失时宽松降级）、消息分发到 agent、非文本消息跳过、回复发送（含截断）、单条消息异常隔离、agent.stream messages 模式 chunk 拼接、loop 注入、stop 标志、markdown 卡片路由、卡片 API 失败回退文本、HITL interrupt 检测（含 `__interrupt__` 多模式解析）、`_send_interrupt_card` 发送、`_on_card_action` 回调解析与 resume 投递、`_resume_agent` 续跑 + pending 清理、`p2_card_action_trigger` 事件注册、`_fetch_bot_open_id` 原始 HTTP 路径（顶层 bot / 嵌套 data.bot / 非零 code / 请求异常 / 非法 JSON / 缺 open_id / 缺 raw.content）、文件下载、session 记录与 receiver 缺省、URL 过滤、subagent 路由
- `app/tests/shared/tools/skills/feishu/test_feishu_websocket_service.py::_fetch_bot_open_id` 子集 —— 7 个用例：覆盖 `lark.Client.request(BaseRequest)` 路径的成功 / 失败 / 异常 / 严格不返回 app_id / 缺 raw.content 等契约
- `app/tests/shared/tools/skills/feishu/test_markdown_to_card_converter.py` —— 45 个用例：导入存在性、`looks_like_markdown` 触发（粗体 / 斜体 / 行内代码 / 标题 / 列表 / 有序列表(1./1) / 双位数字）/ 引用 / 分隔线 / 代码围栏）、`looks_like_markdown` 否定、`to_card_json` 基本结构、h1-h3 标题、hr、列表合并、有序列表 单层 / 含子项 / 用户复现 / 括号形式(1) / **行内多编号拆分（用户截图复现）/ CJK 终止符触发 / 括号形式行内 / 反例（数字不被误拆）/ 常规多行回归保护 2026-07-17 新增**、引用、代码块（带 / 不带语言）、纯文本段落、粗体保留、截断、Unicode / emoji
- `app/tests/shared/tools/skills/feishu/test_interrupt_to_card_converter.py` —— 13 个用例：导入存在性、单题单选、多题、按钮 value 携带 session_id / chat_id、options=[] 退化、questions=[] 占位、None 请求占位、multiSelect 退化为单选、选项数超限截断、自定义 header_title、`parse_card_action_value` 解析 dict / JSON 字符串 / 失败
- `app/tests/shared/tools/skills/feishu/conftest.py` —— 沙箱环境 mock lark_oapi SDK：Client.builder 链、LogLevel 枚举、CreateMessageRequest/Body builder 链、P2ImMessageReceiveV1 类型占位、GetMessageResourceRequest、cardkit.v1 Card/Create/Update、lark.ws.Client、lark.EventDispatcherHandler 注册 `p2_card_action_trigger`、lark_oapi.core 真实对等模型（HttpMethod / AccessTokenType / BaseRequest builder / RequestOption）

### 飞书 WebSocket 长连接（被动接收）

| 组件 | 文件位置 | 职责 |
|---|---|---|
| `FeishuWebSocketService` | `app/shared/tools/skills/feishu/FeishuWebSocketService.py` | 启动 lark.ws.Client 订阅 `im.message.receive_v1` 与 `card.action.trigger`；将消息路由到目标智能体处理后以"纯文本"或"交互式卡片"回复；HITL 中断发带选项按钮的卡片，接收用户点击后 resume agent；处理 `msg_type=file` 时按后缀白名单下载→解析→注入 user text |

**启动方式**：随 FastAPI lifespan 自动启停，受 `settings.feishu.feishu_ws_enabled` 控制（默认关闭，凭证就绪后开启）。

**会话范围**：
- 私聊（p2p）：全部回复
- 群聊（group）：仅响应 @机器人 消息

**session_id 格式**：
- 私聊：`feishu:p2p:{open_id}`（按用户区分会话上下文）
- 群聊：`feishu:group:{chat_id}:{open_id}`（**Per-User in Group**，2026-07-16 调整）—— 同群不同用户各自维护独立会话上下文，避免群里所有人的消息堆到同一个 LangGraph checkpointer thread 导致上下文无限膨胀、token 飙升

**群聊@机器人检测**：
1. 优先匹配 `data.event.message.mentions[].id.open_id == <bot_open_id>`（启动时通过 `client.bot.v3.bot.get` 一次性缓存）
2. 获取失败降级使用 `'@' in content_raw`（宽松匹配）

**消息处理流程**（lark SDK 同步回调）：
1. 解析 chat_type / chat_id / open_id / msg_type / text / attachments
2. 群聊未 @机器人 → 跳过
3. `msg_type=file` 且后缀在白名单 → 投递 `_handle_file_message`（下载→解析→注入 user text），最终仍调用 `_call_agent` 收尾
4. `msg_type=text` → 直接走 `_handle_message` 普通路径
5. 其他类型（image/post/audio/...）→ 跳过 + 日志
6. 调用 `FeishuWebSocketService._ensure_session_recorded(session_id, chat_id, chat_type, text)` 把 session 写入 `sessions` 表，归属到 `feishu_ws_receiver_username` 配置的固定系统用户；首次创建时 title 取首条消息截 20 字 + `…`、绑定 `agent_type` + `agent_display_name`；后续消息仅刷新 `last_active_at`，title 沿用首次
7. **同一 session 串行化（2026-07-19 新增）**：通过 `self._session_locks.setdefault(session_id, asyncio.Lock())` 获取/创建 per-session `asyncio.Lock`，在锁内执行 `_ensure_session_recorded` → `_call_agent`。避免同一用户连续多条消息并发读写同一个 LangGraph checkpointer thread，以及并发创建多个 CardKit 卡片导致窗口混乱。
8. 调用 `agent_config_service.build_agent_instance(agent_name, session_id, text)`
9. 用 `agent.stream(input_state, context=ctx, config=..., stream_mode=["messages", "updates"])` 收集 message chunk 拼接完整回复；同时检测 `__interrupt__` 触发 HITL
10. 通过 `client.im.v1.message.create(CreateMessageRequest)` 直接发送回复（**不走** `send_feishu_message` LangChain 工具，避免 ToolRuntime 依赖）
11. 回复文本 > 4000 字符时截断并追加 `...(内容过长已截断)`

**回复渲染路由**（2026-07-17 新增，2026-07-19 调整降级策略）：
- 路径 1（被动展示）：正常流式路径由 `FeishuCardConsumer` 通过 CardKit 维护同一张卡片；当 CardKit create/patch 失败进入降级路径时，统一把回复包装为飞书交互式卡片发送（`msg_type="interactive"`，`content={"card": {...}}`），不再根据文本是否含 Markdown 特征分支，确保用户端视觉一致。仅在卡片 API 再次失败时才兜底为 `msg_type="text"` 纯文本。
- 路径 2（HITL 人工回路）：agent 触发 LangGraph `interrupt()` 暂停 → 通过 `InterruptToCardConverter` 转带选项按钮的交互式卡片；用户点击按钮 → 飞书回调 `card.action.trigger` → `_on_card_action` 解析 `session_id` / `qid` / `oid` → 构造 `Command(resume={"answers": [...]})` → `_resume_agent` 续跑 → 最终回复走路径 1。
- 卡片 API 任何失败（网络 / 序列化 / 卡片过大）→ 自动降级 `_send_text_reply`，保证可达性。
- `_pending_interrupts` 内存 dict 存 session_id → `{chat_id, request}`；lifespan 重启后丢失（不持久化）。
- 飞书 SDK 按钮回调 3 秒内必须 ack；`_on_card_action` 仅做解析 + `_dispatch_async` 投递，**不**在 SDK 回调线程内调 agent.stream。

**线程模型**：
- `lark.ws.Client.start()` 同步阻塞，用 `threading.Thread(daemon=True)` 包装到后台线程
- **lark SDK 模块级 loop 陷阱**：`lark_oapi.ws.client` 在模块顶层执行 `loop = asyncio.get_event_loop()` 并把该 loop 缓存在模块级变量。FastAPI/uvicorn 主线程的 loop 在 lifespan 期间已运行，所以后台线程直接调用 `loop.run_until_complete(...)` 会触发 `RuntimeError: This event loop is already running`。
  - 解决方案：在 `_run_ws_blocking` 入口创建独立的新 event loop，把它 `set_event_loop` 到当前线程，并通过 `_lark_ws_client_mod.loop = new_loop` 把 lark SDK 模块级 loop 指向新 loop。
- 事件回调（`_on_message` / `_on_card_action`）内通过 `asyncio.run_coroutine_threadsafe(coro, loop)` 把协程投递回主事件循环（用户消息处理需要 DB pool 与 agent stream）。
- 主事件循环在 lifespan 启动时通过 `service.set_event_loop(asyncio.get_event_loop())` 注入。
- 获取机器人 open_id（同步 HTTP）的 `_fetch_bot_open_id` 走 `asyncio.to_thread(...)` 包装，避免在主线程中阻塞 loop。

**异常隔离**：单条消息处理失败仅记日志，不影响 WebSocket 连接与后续消息。

**关停容忍（2026-07-17 新增）**：uWSGI / uvicorn / Ctrl-C 触发的进程关闭阶段，lark SDK 重连线程仍可能尝试排新 future。后台线程入口与异常分支都有短路/静默退出口：
- `_run_ws_blocking` 入口先检查 `self._should_run`，lifespan stop 后该标志已置 False 时**直接 return**，不再调用 `ws_client.start()`。
- `ws_client.start()` 抛 `RuntimeError("cannot schedule new futures after interpreter shutdown")` / `"Event loop is closed"` / 含 `"interpreter shutdown"` → 静默退出（INFO 日志），不再刷 ERROR。
- 与关停期无关的 `RuntimeError` 仍走 ERROR 日志，正常业务故障可见性不被吞掉。

**飞书文件消息对接**（`msg_type=file` 接收侧，支持自动下载→解析→注入 user text）：
- **后缀白名单**：`docx / pdf / xlsx / md / txt`，实现位于 `FeishuWebSocketService._FILE_EXT_SUPPORTED`。白名单外后缀（png/zip/...）→ `_send_text_reply(chat_id, "暂不支持的文件类型: ...")`，**不**触发 agent。
- **下载**：`FeishuWebSocketService._download_feishu_resource(session_id, message_id, file_key, file_name)` 同步调用 `client.im.v1.message_resource.get(GetMessageResourceRequest.builder().message_id(...).file_key(...).type("file").build())`（**注意**：是 `message_resource` 子资源，不是 `message` 主资源；误用 `client.im.v1.message.get_message_resource` 会抛 `AttributeError: 'Message' object has no attribute 'get_message_resource'`），读 `resp.file.read()` 字节流，写入 `get_session_upload_dir(self._safe_session_marker(session_id), create=True) / file_name`。本方法放线程池（`asyncio.to_thread`）异步执行，避免阻塞主事件循环。
- **Windows 路径安全（跨平台修正）**：`FeishuWebSocketService._safe_session_marker(session_id)` 把原始 session_id（如 `feishu:p2p:ou_xxx`）中的 `:` 替换为 `_`，因为 Windows 上 `:` 是盘符分隔符，会让 `Path.mkdir` 抛 `OSError [WinError 123]`。仅在文件系统路径边界使用该 marker；LangGraph thread_id / PostgreSQL 仍用原始 session_id。
- **大小校验**：`FeishuWebSocketService._resolve_max_file_size_bytes()` 取 `settings.file_parser.file_parser_max_file_size`（MB）与飞书官方隐式 100MB 的较小值，乘 1024²。超过会删除已落盘文件并回发「文件过大已被拒绝」提示。
- **解析**：`FeishuWebSocketService._parse_uploaded_attachment(stored_path, file_name, ext, session_id)` 返回 `{"text": Optional[str], "md_path": Optional[str]}`：
  - 解析产物同时落 `data/tmp/upload/<safe_marker>/<stem>.md` 镜像（与 Web 上传链路一致），agent 可通过 `explore / query_knowledge` 等工具按需读取；
  - `.md / .txt` → 直接读原文件内容并写一份 `.md` 镜像；
  - `.pdf / .docx / .xlsx` + `settings.file_parser.file_parser_enabled == True` → `FileParserClient.parse(output_format="md")` 走 `asyncio.to_thread`，失败降级 `DocumentLoader.load()` 并把内容也落 `.md` 镜像；
  - `.pdf / .docx / .xlsx` + `file_parser_enabled == False` → 直接 `DocumentLoader.load()`；
- **user text 仅含文件名列表（最终契约，2026-07-17 多次迭代）**：
  - 写入形如
    ```
    用户上传了以下文件：
    - <file_name>
    - <file_name>
    ```
    后附 `[用户文本] <text>`（若有）一并送给 `_call_agent`；
  - **不**暴露路径（`original`）、解析镜像路径（`parsed_md`）、preview、文件正文。
  - 文件实际仍按保存在 `data/upload/<safe_marker>/` 与 `data/tmp/upload/<safe_marker>/<stem>.md`，agent 通过 `explore / query_knowledge / file_read` 等工具按文件名**按需**读取。
  - 早期版本曾把 YAML 路径块或 200 字 preview 给 agent，用户最终反馈"只保留文件名称"，所以现在 user text 里只写文件名；下游依赖均通过临时文件路径间接访问。
- **解析失败分支**：`_parse_uploaded_attachment` 抛错 / 返回 `{"text": None, "md_path": None}` 但 `stored_path` 仍有 → 把文件名纳入上方列表后让 agent 继续；只当"文件也没落盘（解析与下载同时失败）"时才回退到提示用户且不调 agent。
- **失败回执**：`白名单外 / 超大 / 下载失败` → `_send_text_reply(chat_id, reason)`，不抛异常，不影响 WebSocket 与后续消息。
- **复用组件**：`FileParserClient`（`app/shared/utils/files/file_parser_client.py`）、`DocumentLoader`（`app/shared/utils/files/DocumentLoader.py`）、`session_path_manager.get_session_upload_dir / get_session_tmp_upload_dir` — 均与 Web 上传共享。

**相关配置**：WebSocket 启停与路由参数见上文「配置（FeishuSettings）」章节（`feishu_ws_enabled` / `feishu_ws_agent_name` / `feishu_ws_receiver_username`）。

**飞书后台要求**：
- 事件订阅 `im.message.receive_v1` 与 `card.action.trigger`，订阅类型必须选 WebSocket（非 HTTP Webhook）。
- 群聊场景需开启相关消息权限。
- 卡片按钮回调要求后端在 3 秒内 ack；后端已通过 `_dispatch_async` 把慢操作投递到主事件循环，避免超时。

### 飞书流式卡片输出（多渠道架构）

**目标**：把飞书侧 LLM 流式 token 实时 patch 到同一张 CardKit 卡片，HITL 按钮也追加到同一张卡片（上下文连贯），解决原方案"流式 token 全丢 / HITL 与终态卡片分离 / 消息编辑次数受限"问题。架构层面抽象出多渠道路由（飞书 / 未来钉钉 / 企微 / Slack 平级），不感知 LangGraph。

**架构分层（依赖倒置）**：

```
FeishuWebSocketService._call_agent
  ├─ channel_registry.resolve(session_id, **ctx) → ChannelConsumer 实例（按前缀路由）
  ├─ StreamEventSource.consume(agent.stream(...))  → 产出 StreamEvent 序列
  └─ 把 StreamEvent 分发到 Consumer 的 6 个回调      → Consumer 翻译为渠道渲染动作
```

- `StreamEventSource`（`app/core/agent/stream_event_source.py`）只负责消费 `agent.stream(stream_mode=["updates", "custom", "messages"])` 多模式 chunk，产出统一 `StreamEvent`，**不感知**任何渠道
- `ChannelConsumer`（`app/shared/tools/channels/base.py`）只声明 6 个回调接口，**不感知** LangGraph
- `ChannelRegistry`（`app/shared/tools/channels/registry.py`）按 session_id 前缀路由到对应 Consumer 类，支持运行时 `register(prefix, consumer_cls)`

**核心模块**：

| 组件 | 文件位置 | 职责 |
|---|---|---|
| `StreamEvent` | `app/core/agent/stream_event.py` | 流式事件 dataclass：`type ∈ {session_start, text_chunk, node_update, interrupt, abort, end}` + `text` / `node_name` / `node_data` / `interrupt_requests` 字段 |
| `StreamEventSource` | `app/core/agent/stream_event_source.py` | 消费 `agent.stream(...)` 多模式 chunk（messages / updates / custom），统一产出 `StreamEvent` 序列；支持 abort 信号检测；HITL interrupt 三形态兼容检测（dict 直含 `__interrupt__` / tuple 嵌套 / node 嵌套）+ `hasattr(item, "value")` 解包 LangGraph `Interrupt` 对象 |
| `ChannelConsumer` | `app/shared/tools/channels/base.py` | 渠道消费者 ABC，6 个抽象回调：`on_session_start` / `on_text_chunk` / `on_node_update` / `on_interrupt` / `on_session_end` / `on_abort`；基类维护 `accumulated_text` / `last_interrupt_req` 公共状态 |
| `ChannelRegistry` | `app/shared/tools/channels/registry.py` | `channel_registry` 全局单例；`register(prefix, consumer_cls)` 注册前缀；`resolve(session_id, **ctx)` 按前缀最长匹配实例化 Consumer；前缀冲突抛 `ValueError` |
| `FeishuCardConsumer` | `app/shared/tools/channels/feishu/FeishuCardConsumer.py` | 飞书渠道 Consumer 实现：`on_session_start` 创建 CardKit 卡片实体 + 关联消息（占位「🤖 AI 正在思考…」）；`on_text_chunk` 累积→节流→patch 同卡片；默认启用元素级流式更新（`UpdateCardElementRequest`），失败时自动回退整卡更新（`UpdateCardRequest`）；流结束时调用 `SettingsCardRequest` 关闭 `streaming_mode`；`on_interrupt` 同卡片 elements 末尾追加按钮；`on_session_end` 强制 flush；`on_abort` 追加「（已停止）」标记 |
| `Throttler` | `app/shared/tools/channels/feishu/Throttler.py` | 时间窗 + 字符增量双条件节流器：默认参数由 `settings.feishu` 的 `feishu_card_update_interval_ms`（默认 600 ms）与 `feishu_card_update_delta_chars`（默认 50）注入；`should_push(last_len, current_len, now)` 同时满足 `now - last_push_time ≥ min_interval_ms` 与 `current_len - last_push_len ≥ min_delta_chars`；`force_flush()` 仅更新 `last_push_len` 不阻塞；初始 `last_push_time = -inf` 保证首次推送必发 |

**飞书渠道前缀路由**：
- `channel_registry.register("feishu", FeishuCardConsumer)` 在 `app/shared/tools/channels/feishu/__init__.py` 包导入时执行
- `lifespan` 中通过 `from app.shared.tools.channels import feishu` 触发自动注册
- ⚠️ **关键约束**：lifespan 中**禁止**用 `import app.shared.tools.channels.feishu` 形式 —— 该语句会让 Python 把 `app` 绑定为 `sys.modules['app']` 模块对象，覆盖 lifespan 函数参数 `app: FastAPI`，导致后续 `app.state.xxx` 抛 `AttributeError: module 'app' has no attribute 'state'`。必须用 `from app.shared.tools.channels import feishu` 形式

**`_call_agent` 重写流程**（`FeishuWebSocketService._call_agent(session_id, text, chat_id, resume=None)`）：
1. 通过 `channel_registry.resolve(session_id, lark_client=self._lark_client, chat_id=chat_id)` 拿到 Consumer 实例
   - interrupt 后保留 Consumer 到 `self._active_consumers[session_id]`；resume 时复用同一实例（保留 `_card_id` / `_message_id`，让续跑 token 继续 patch 同卡片）
2. **Consumer 状态重置**（关键）：resume 复用旧 Consumer 时，必须在驱动事件流前重置 `consumer.accumulated_text = ""` 与 `consumer.last_interrupt_req = None`，否则上轮 interrupt 留下的 `last_interrupt_req` 会让 `_call_agent` 错误返回非 None interrupt_req
3. 调用 `agent_config_service.build_agent_instance(agent_name, session_id, text, resume=resume)` 拿到 agent
4. `StreamEventSource.consume(agent.stream(...))` 产出 StreamEvent 序列
5. 每个 StreamEvent 分发到 Consumer 对应回调（`on_session_start` → `on_text_chunk` × N → `on_interrupt` / `on_node_update` → `on_session_end`）
6. 流自然结束：清理 `_active_consumers[session_id]`，返回 `None`（表示无 HITL pending）
7. 流 interrupt：返回 `consumer.last_interrupt_req`（供 `_handle_message` 写入 `_pending_interrupts`）
8. abort 信号触发：调用 `consumer.on_abort()`，清理 Consumer

**节流策略**（`Throttler` + 单卡片 `asyncio.Lock`）：
- 时间窗 600ms + 字符增量 50 字符 + 单卡片 `asyncio.Lock` 三重保险
- 飞书官方限频：CardKit update 单卡片 10 QPS / 秒（global 50 QPS）；600ms 时间窗 ≈ 1.6 QPS，远低于限频
- 卡片 30KB 上限 → 沿用 `MarkdownToCardConverter._MAX_CARD_TEXT_LEN = 4000` 字符截断
- patch 序号 `sequence` 严格递增（飞书要求）

**HITL 同卡片按钮**（与原"独立卡片"方案的关键差异）：
- `on_interrupt` 把 `InterruptToCardConverter` 生成的按钮 elements **追加到当前卡片 elements 末尾**，不发独立卡片
- 用户点击按钮 → `_on_card_action` 解析 → `_resume_agent` 复用同一 Consumer 实例 → 续跑 token 继续 patch 同卡片
- 上下文连贯：用户在原卡片看到 token 流 + 按钮选择 + 续跑 token，不需要切换消息
- 仅在 CardKit create 失败降级模式下才走 `_send_interrupt_card`（独立卡片）

**降级路径**（鲁棒性优先）：
- CardKit create 失败 → Consumer 内部 `_degraded = True` → `on_text_chunk` / `on_interrupt` 改走一次性 `_send_card_reply` / `_send_interrupt_card`
- CardKit patch 连续失败 ≥ 3 次（`_MAX_PATCH_FAILURES`）→ 降级为一次性发送
- `_send_card_reply` 失败 → 降级 `_send_text_reply`（最终兜底，保证可达性）

**元素级流式更新与 streaming_mode 关闭（2026-07-19 新增）**：
- 默认启用元素级流式更新：`FeishuCardConsumer._patch_card_safe` 优先调用 `lark_client.cardkit.v1.card_element.update(UpdateCardElementRequest)`，只更新主 markdown 元素（`element_id="markdown_main"`），payload 更小、符合 CardKit streaming 协议。
- 元素级更新失败时，单次回退到整卡更新（`UpdateCardRequest`）；下次新 token 到来时仍优先尝试元素级更新。
- 当 `settings.feishu.feishu_card_streaming_enabled=False` 时，直接走整卡更新，不尝试元素级更新。
- 流自然结束 / abort 时调用 `_close_streaming_mode`，通过 `lark_client.cardkit.v1.card.settings(SettingsCardRequest)` 将卡片 `config.streaming_mode` 置为 `false` 并保留 `update_multi=True`，避免后续整卡更新被 streaming 状态拒绝。失败仅记日志，不影响主流程。

**abort 信号机制**：
- 复用全局 `register_abort_signal(session_id)` / `trigger_abort(session_id)` / `unregister_abort_signal(session_id)`（与前端 SSE abort 通道共用一套基础设施）
- `StreamEventSource.consume` 每轮迭代检查 `is_abort_triggered(session_id)`，触发后 yield `StreamEvent(type="abort")` 并 break
- Consumer 在 `on_abort` 中追加 `_STOPPED_MARKER = "\n\n_（已停止）_"` + 设置 `_stopped = True` 停止后续 patch

**测试覆盖**：
- `app/tests/core/agent/test_stream_event_source.py`（13 个）：导入 / messages 模式 text 提取 / 空内容跳过 / updates 模式 / interrupt 三形态检测 / abort 信号 / 流结束 / session_start 首事件 / tools 节点完成触发 abort / 异常隔离 / 无 abort 信号不检查
- `app/tests/shared/tools/channels/feishu/test_feishu_card_consumer.py`（30 个）：导入 / CardKit create + 关联消息 / create 失败降级 / 节流 patch / 节流跳过 / 空文本 noop / 降级模式仅累积 / HITL 同卡片按钮 / 空 requests noop / 降级模式新卡片 / session_end force_flush / 降级模式一次性回复 / abort 后跳过 session_end / abort 标记 / 降级模式 abort / patch 失败静默重试 / 连续失败降级 / `_send_card_reply` 失败降级文本 / sequence 严格递增 / 截断 / 从 `settings.feishu` 读取 6 个流式/节流参数 / 节流参数透传至内部 Throttler / `_build_card_json` 使用 streaming 配置 / streaming 禁用回退整卡更新
- `app/tests/shared/tools/channels/feishu/test_throttler.py`（9 个）：导入 / 时间窗满足 / 时间窗内跳过 / 字符增量不足跳过 / 双条件满足 / force_flush 更新 len / force_flush 后允许立即推送 / 并发 should_push 串行化 / 默认值
- `app/tests/shared/tools/skills/feishu/test_feishu_websocket_service.py`（89 个）：原 70+ 测试改造（`_call_agent` 签名加 `chat_id` + Consumer 路由）+ 新增 3 个 Consumer 相关测试（`test_call_agent_routes_to_feishu_consumer_by_session_prefix` / `test_call_agent_returns_interrupt_consumer_state` / `test_resume_agent_continues_same_consumer`）+ 文件消息处理 / session 记录 / 群聊 @检测等

**与前端 SSE 的边界**：
- 前端 SSE 流式（`/api/agent/*`）仍走 `app/routers/_stream_helper.py`，**一行未改**（硬约束）
- 飞书侧流式走独立路径：`FeishuWebSocketService._call_agent` → `StreamEventSource` → `ChannelConsumer`
- 两条路径互不影响：前端 SSE 通过 HTTP 响应流推送；飞书侧通过 CardKit API patch 同一张卡片

**关键设计决策**：

| 决策点 | 选择 | 理由 |
|---|---|---|
| 是否改 `_stream_helper` | **不改** | 用户硬约束；前端 SSE 行为完全冻结 |
| 事件源抽象层 | 新建 `StreamEventSource`（独立于 `_stream_helper`） | `_stream_helper` 内 SSE 推送逻辑不抽离；新模块从零实现核心循环 |
| 渠道抽象 | `ChannelConsumer` 接口 + `ChannelRegistry` 路由 | 飞书 / 钉钉 / 企微平级；按 session_id 前缀分发 |
| 更新通道 | CardKit（卡片实体） | 消息编辑有隐性 ~20-30 次上限；CardKit 无明确上限；官方推荐流式方案 |
| 节流策略 | 时间窗 + 长度增量 双条件 + 单卡片 asyncio.Lock；默认值由 `settings.feishu` 注入（`feishu_card_update_interval_ms=600`、`feishu_card_update_delta_chars=50`） | 统一配置入口，便于线上快速调整；官方限频 50 QPS / 秒；600ms 留余量；50 字符避免无意义 patch |
| 流式更新粒度 | 默认元素级 `UpdateCardElementRequest`（`element_id="markdown_main"`），失败单次回退整卡 `UpdateCardRequest`；流结束调 `SettingsCardRequest` 关闭 `streaming_mode` | payload 更小、符合 CardKit streaming 协议；关闭 streaming 避免后续整卡更新被状态拒绝 |
| HITL 按钮位置 | 同一卡片 elements 末尾追加 | 用户上下文连贯；避免再发一张图 |
| abort 信号 | 复用 `register_abort_signal` / `trigger_abort` | 与前端 abort 通道共用一套基础设施 |
| 降级触发 | CardKit create 失败 / 连续 N 次 patch 失败 → 一次性 `_send_card_reply` | 鲁棒性优先，避免无限重试 |
| 多 Consumer 实例化 | 每次 `_call_agent` 新建 Consumer，resume 时复用同一实例 | session 内 Consumer 持有同一 card_id / message_id，跨 resume 续写 |

### 飞书 Markdown 卡片 + HITL 按钮回路

| 组件 | 文件位置 | 职责 |
|---|---|---|
| `MarkdownToCardConverter` | `app/shared/tools/skills/feishu/MarkdownToCardConverter.py` | Markdown 文本 → 飞书交互式卡片 JSON；提供 `looks_like_markdown` 自动检测；支持 h1-h6 标题、`**粗体**` / `*斜体*` / `` `code` ``、列表项每项独立、有序列表项(1. / 1) 形式,2026-07-17 新增)、`> 引用`每行独立、`---` 分隔线、``` ``` ``` 代码围栏；>4000 字符截断；**schema=2.0 输出**（2026-07-17）：顶层 `{"schema": "2.0", "config": {...}, "header": {...}, "body": {"elements": [...]}}`；header.template 默认 `"blue"`；预处理剥离独立成行的 `**xxx**` / `*xxx*` 包装，行首/行尾 `**`/`*` 标记被清理，每个 markdown 元素强制单行；行首 emoji 前补 ASCII 空格 |
| `InterruptToCardConverter` | `app/shared/tools/skills/feishu/InterruptToCardConverter.py` | LangGraph interrupt 请求 → 飞书带选项按钮的交互式卡片（schema=2.0，header.template=`"orange"`）；每个按钮 value 含 `action="hitl_answer"` / `qid` / `oid` / `session_id` / `chat_id`；每题最多 5 个选项 + 1 个 "其他（自由输入）" 按钮；提供 `parse_card_action_value` 反序列化回调 value |

**卡片协议依据**：[飞书消息卡片文档](https://open.feishu.cn/document/develop-a-card-interactive-bot/card-building-steps)；当前使用 [JSON 2.0 schema](https://open.feishu.cn/document/feishu-cards/card-json-v2-components/content-components/rich-text)（2026-07-17 从 v1 升级，原因为：v1 schema 下"独立加粗行 + 全角冒号"组合触发 `ErrCode: 200621; ErrMsg: parse card json err`，导致卡片发送失败 → 自动降级纯文本 → 用户看到 `**xxx**` 原始 markdown 源码）

**按钮 value 契约**（飞书回调时由 `_on_card_action` 解析）：
```json
{
  "action": "hitl_answer",
  "qid": 0,
  "oid": 1,
  "session_id": "feishu:p2p:ou_alice",
  "chat_id": "oc_chat_001"
}
```
- `oid == -1` 或 `"is_other": true`：表示用户点击"其他（自由输入）"按钮，清理 pending 并提示用户直接输入。
- `qid` / `oid` 对应 LangGraph `interrupt({"action": "ask_user_question", "questions": [...]})` 中的问题 / 选项索引。

**resume 数据契约**：`_resume_agent` 调用 `build_agent_instance(..., resume={"answers": [{"qid": 0, "oid": [1]}]})`，与 `app/core/agent/agent.py::hitl_check_node` 的 `interrupt(request)` 恢复后的 `response.get("answers", [])` 解析对齐。

**失败策略**：
- `_send_card_reply`：API 失败（`resp.success() == False` 或抛异常）→ 自动降级 `_send_text_reply`，同时记录完整卡片 JSON 前 500 字符到 ERROR 日志，便于排查 `code=200621`（parse card json err）等卡片 schema 问题
- `_send_interrupt_card`：失败仅记录日志（不能降级为纯文本，否则按钮失效；用户需重新提问或等待）
- `_pending_interrupts` 未命中（lifespan 重启 / 超时）：`_resume_agent` 仅警告，不抛异常

**schema 版本演进（2026-07-17）**：
- 升级前（v1 schema）：`{"config": {...}, "card": {"header": {...}, "elements": [...]}}`，在 markdown 元素含独立加粗行（如 `**核心原则：**`）时，飞书 API 返回 `code=230099 ext=ErrCode: 200621 parse card json err`，导致整张卡片失败降级为纯文本——用户看到 `**xxx**` / `- xxx` 原始 markdown 源码
- 升级后（v2 schema）：`{"schema": "2.0", "config": {...}, "header": {"template": "blue", "title": {...}}, "body": {"elements": [...]}}`，markdown 解析器对孤立加粗行 / 全角符号 / 列表项前缀的兼容性显著优于 v1；`MarkdownToCardConverter` 与 `InterruptToCardConverter` 已同步升级
- `_send_card_reply` / `_send_interrupt_card` 调用方无需感知 schema 版本变化（card JSON 整体序列化后传给 SDK）

**有序列表支持扩展（2026-07-17 新增）**：
- 新增 `_RE_ORDERED_LIST = (?m)^\s{0,3}\d{1,2}[.)]\s+\S` 正则；`looks_like_markdown` 增补触发；`_parse_block_elements` 在无序列表分支之后新增"有序列表项"分支，匹配 `^\s*\d{1,2}[.)]\s+\S`（同时支持 `1.` 与 `1)` 写法，编号限定 1~2 位避免误吞带年份等的长数字）；普通段落分支的 while 退出条件增加 `^\s*\d{1,2}[.)]\s+\S` 检测，遇到编号行立刻终止段落。
- 每个编号项独立成 markdown 元素（保留 `1.` 原前缀），由飞书原生渲染编号递增；`_solo_bold` / `_safe_leading_emoji` 预处理对编号行同样生效（不会误给数字行首补空格，因为 emoji 字符集不含数字）。
- 修复用户反馈的"`1. xxx` 编号项被合并到同一个 markdown 元素、`**4. 便于管理**` / `**5. 提高效率**` 被串到上一子项目末尾"问题（编号项原本被当作普通段落，多行内容累加到 `para_lines`，飞书 markdown 渲染无法正确展示编号位置）。

**行内多编号拆分（2026-07-17 同一日第二轮新增）**：
- 新增 `_RE_INLINE_ORDERED_SPLIT = (?<=[一-鿿。,，;:；、！？」】）)])\s*(\d{1,2})[.)]\s+`：在有序列表项 emit 之前对内容做 `re.split`，捕获到的数字单独成 entry。
- 触发场景：LLM 把多个编号项挤在同一行（如 `1. xxx2. xxx3. xxx4. xxx`，用户最新截图复现）。仅靠 CJK 字符 / CJK 标点 / 半角中英标点作 `lookbehind` 锚，避免误拆"今天是 2026 年 7 月 17 日。苹果 20 元一斤。"等含数字的非编号文本。
- 拆分后 walk：`re.split` 返回 `[seg1, num1, seg2, num2, seg3, ...]`，parts[0] 是含行首编号的第一个 item（保留 `1. xxx`），其余按 `(num, seg)` 对重组为 `"N. xxx"`。
- 修复用户反馈"依然有问题"(前 4 个编号项挤一行,只看到 1 项)问题。

## CI 测试（pytest + GitHub Actions）

### 后端测试目录（`app/tests/`）

- **配置**：`app/pytest.ini`（`testpaths = tests`、`addopts = -v --tb=short`）
- **基础设施**：`app/tests/conftest.py` 与 `app/tests/shared/conftest.py`
  - 在收集阶段 autouse mock 外部依赖：`asyncpg`、`langchain.*`、`langgraph.*`、`docx.*`、`aiofiles`、`pypdf`、`pymupdf`、`deepagents.*`、`mcpClient.*`、`sse_starlette`、`markitdown`、`unstructured` 等
  - 对 `docx.enum`、`docx.shared`、`docx.oxml` 等子包使用 `types.ModuleType` + `__path__` 注入，保证 `from docx.enum.section import WD_SECTION_START` 等子模块导入可用
  - 对 `langgraph.types.Command`、`langgraph.prebuilt.ToolNode`、`langgraph.graph.MessagesState/StateGraph/START/END` 等提供 `Mock` 或自定义 `_Command` 类
  - 在 `app` fixture 中 patch `typing._type_check`，遇到带 `_mock_name` 属性的对象直接跳过原始类型检查，避免 `Optional[Mock]`、`Union[AgentState, LGCommand]` 等注解触发 SyntaxError
  - 提供 fixtures：`app`（session 级 FastAPI 实例）、`client`（function 级 TestClient）、`jwt_auth`、`admin_token`/`user_token`/`admin_headers`/`user_headers`

### 测试覆盖

- **`tests/core/`**：核心模块（config、database、server、prompts、agent_context、dependencies）
- **`tests/core/tools/`**：HITL 工具、BaseTools、MCP 适配器
- **`tests/shared/`**：auth_router、file_router、session_router、user_router、user_db、session_db、refresh_token_db、portal_refresh_token_db、captcha、safety、DocumentLoader
- **`tests/features/*/`**：9 个 Agent 冒烟测试（config 可导入、提示词非空、tools 可导入、router 已注册到 `/api/*` 路径）
- **`tests/features/sandbox_agent/`**：沙箱 Agent 专项测试
  - `test_docker_backend.py`：DockerSandboxBackend 容器生命周期、命令执行、文件操作、异常处理
- **`tests/scripts/`**：项目根 `scripts/` 目录的离线脚本测试
  - `test_seed_tools_from_source.py`：13 用例（AST 装饰器识别 / description 提取 / 路径推断 / 分类推断 / scan_all_tools 端到端 / SQL+JSON 转义 / render_sql upsert / 空列表降级 / CLI --dry-run / CLI --output），通过 `monkeypatch` 隔离 `TOOL_ROOTS` / `PROJECT_ROOT` 到 `tmp_path`，不污染真实工程文件
- **`tests/integration/`**：端到端集成测试
  - `test_end_to_end_auth.py`：认证流程（注册→登录→validate→logout）
  - `test_agent_chat_e2e.py`：`/api/agent/chat` 端到端测试（2 用例：SSE 流式响应正常返回 / 未知 agent 返回 404）

### Mock 策略

- **不引入真实 PostgreSQL / 真实 LLM / 真实文件系统**，全部内存 + Mock
- 数据库：`AUTH_STORAGE_MODE=memory` + `UserDB._memory_users`、`SessionDB` 内存字典
- LLM：所有 `langchain_*.Chat*`、`init_chat_model` 均为 `Mock`
- 文件系统：`pypdf`、`PyMuPDF`、`docx`、`PIL`、`numpy` 均为 `Mock` 或 `ModuleType`
- `app/main.py::register_routers(target_app=None)`：支持在测试中注入 test app 实例，避免依赖全局 `app`

### CI 工作流（`.github/workflows/pr-check.yml`）

- **触发**：`pull_request` 与 `push` 到 `main` / `preview` 分支
- **Jobs**：
  - `backend-test`：`ubuntu-latest` + `actions/setup-python@v5`（Python 3.11，`cache: pip`）→ `pip install -r app/requirements.txt` → `pytest --tb=short -q`
  - `frontend-test`：`ubuntu-latest` + `actions/setup-node@v4`（Node 20，`cache: npm`）→ `npm ci` → `npm run test`（vitest）
  - `docker-build-check`：`ubuntu-latest` + `docker/setup-buildx-action@v3` + `docker/build-push-action@v5` 构建 `app/Dockerfile` 与 `web/Agent/Dockerfile`，不 push
- **缓存**：pip 与 npm 均启用 GHA 缓存加速

### 已知工程实践

- **TestClient.delete() 不支持 `data` / `json` 关键字**：Starlette `TestClient.delete` 显式仅暴露 `params`、`headers`、`cookies` 等；如需发送 JSON body，应改用 `client.request("DELETE", url, headers=..., json=...)`（参见 `app/tests/shared/test_file_router.py::test_delete_files`）
- **PortalRefreshTokenDB 仅暴露物理删除**：使用 `delete_token(token_hash)`，不存在 `revoke_token`（参见 `app/tests/shared/test_portal_refresh_token_db.py`）

