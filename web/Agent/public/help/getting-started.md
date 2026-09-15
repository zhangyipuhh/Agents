# 快速入门

本章节介绍系统的核心功能与基本使用流程，帮助新用户快速上手。

![快速入门](/help/screenshots/getting-started/01-getting-started.png)

## 前置条件

1. 已部署系统并能通过浏览器访问入口（如 `https://your-domain`）
2. 已拥有登录账号
   - admin 账号：请联系系统管理员发放（首次部署由 `AUTH_DEFAULT_ADMIN_PASSWORD` 决定，详见「[基本设置](/help/features/basic-settings)」）
   - 普通用户：可联系管理员开通，或通过注册接口自助申请（如启用了 IP 白名单 + 注册审批双闸门，详见「[IP 白名单配置](/help/features/ip-whitelist)」）
3. 浏览器：Chrome / Edge / Firefox 最新版（推荐 Chrome 120+）
4. 屏幕分辨率：≥ 1366×768（推荐 1440×900，政务蓝三栏布局完整呈现）

## 登录系统

### 登录流程

1. 在浏览器中访问系统地址（如 `https://your-domain/`），进入登录页面
2. 输入**用户名 + 密码 + 验证码**（验证码 4 位字符，鼠标点击图片刷新）
3. 点击「登录」按钮
4. 如系统启用了 MFA，登录后会要求输入 **6 位 TOTP 动态验证码**（详见下文「启用 MFA」）

![登录页](/help/screenshots/getting-started/00-login.png)

> **MFA 说明**：admin 账号首次登录后**强制**要求启用 TOTP（`MFA_ISSUER=AIOps`，可由环境变量覆盖）；普通用户可选。

### 启用 MFA（双因素认证）

#### 前置依赖
- 已登录且未启用 MFA
- 手机安装支持 TOTP 的认证器（Microsoft Authenticator / Google Authenticator / 1Password 等）

#### 设置步骤
1. 进入「个人设置 → MFA 管理」
2. 点击「启用 MFA」按钮，前端展示二维码（含 `otpauth://totp/AIOps:<username>?secret=...`）
3. 用认证器扫码或手动输入密钥
4. 输入认证器显示的 6 位动态码 → 点击「验证」
5. 系统展示 **10 个恢复码**（每个一次性）→ 必须抄写并妥善保管 → 勾选「我已抄写并继续」

#### 启用后效果
- 下次登录时，密码校验通过后会要求输入 6 位 TOTP 码
- 每次密码登录都会产生新会话，触发 `user_login_sessions` 写库 + JWT 携带 `amr=["pwd", "mfa"]`
- 若丢失手机导致无法获取动态码，**使用恢复码**仍可登录（恢复码一次性，使用后失效）
- **若 MFA 与恢复码全部丢失**，请联系管理员调 `mfa_service.reset_user_mfa()` 重置

#### 语法说明

| 字段 | 含义 | 取值 |
|---|---|---|
| `MFA_ISSUER` | TOTP issuer 字段（认证器显示名） | 默认 `AIOps`，可由环境变量覆盖 |
| 恢复码 | 一次性备用码，10 个 | 仅在启用时展示，必须抄写 |
| TOTP 时间窗口 | 30 秒一个码 | 标准 RFC 6238 |

## 主界面导览

登录成功后进入主界面，主要分为三个区域：

- **左侧栏**：会话历史列表、项目列表、用户头像菜单
- **中部对话区**：与智能体对话的主交互区
- **顶部输入区**：消息编辑、文件附件、斜杠命令、智能体切换器

![主界面导览](/help/screenshots/getting-started/01-getting-started.png)

### 切换智能体

系统支持多种智能体（Agent），不同智能体拥有不同的提示词、工具集与领域知识。系统共注册 11 个内置智能体：

| 智能体名 | 适用场景 | 主要工具 |
|---|---|---|
| `project` | 通用对话 + 项目管理 | 文件读写 / 知识库检索 / SSH |
| `map_agent` | 地图 / 地理信息查询 | 高德地图 MCP |
| `knowledge_ydt` | 知识库检索与回答 | 知识库检索 / 文件读取 |
| `contract_host_agent` | 合同文档解析 + 审批 | 文件读取 / 审批流程 |
| `contract_document_agent` | 合同文档结构化抽取 | 文件读取 / answer_template |
| `contract_approval_agent` | 合同审批决策 | 审批规则引擎 |
| `Tagent` | 综合任务编排 | 通用工具集 |
| `audit_document_agent` | 审计文档分析 | 文件读取 / OCR |
| `AI_Coding_Project` | AI 编程项目分析 | 文件读取 / 静态分析 |
| `AI_Coding_Check_agent` | AI 编程代码审查 | diff / 静态分析 |
| `sandbox_agent` | 沙箱代码执行 | execute / 文件操作 |

#### 切换方式
1. 点击主界面顶部智能体名称右侧的下拉箭头
2. 从下拉列表中选择目标智能体
3. 切换后**新消息**会使用新智能体的提示词与工具集；历史消息不受影响

#### ACL 控制
- 普通用户只能看到 `users.allowed_agents` JSONB 字段中授权的智能体
- admin 默认看到全部已启用智能体
- 智能体授权在「权限管理 → 智能体访问」配置（详见「[权限管理](/help/features/permission-management)」）

## 发起对话

在输入框中输入您的问题，按 `Enter` 发送，`Shift+Enter` 换行。系统支持以下增强特性：

- **多轮对话**：上下文自动延续，支持「追问」「澄清」
- **文件附件**：点击附件图标上传文档（详见下文「文件类型白名单」）
- **斜杠命令**：输入 `/` 触发命令面板（如 `/clear`、`/help`）

### 文件类型白名单（来自安全策略）

> ⚠️ **白名单不可在「基本设置」中修改**——属于入侵防范条款，详见 `memory/security-compliance.md`。

| 扩展名 | 备注 |
|---|---|
| `.pdf` | 含魔数嗅探（`%PDF-`） |
| `.doc` | 含魔数嗅探 |
| `.docx` | 含魔数嗅探（PK ZIP 头） |
| `.txt` | 纯文本 |
| `.md` / `.markdown` | Markdown |
| `.csv` | CSV |
| `.json` | JSON |

非白名单类型会被 `/api/core` 与 `/api/files/upload` 双入口拦截，返回 415 Unsupported Media Type。

## 知识库

系统提供独立的知识库模块，支持上传与管理个人或团队文档。

1. 点击左侧菜单的「知识库」按钮（或顶部「知识库」入口）
2. 上传文档后即可在与智能体对话时引用
3. 支持 PDF / Word / Excel / TXT 等格式

详见「[知识库](/help/features/knowledge)」章节。

## 智能运维中心

面向运维人员的工作台，提供：

- **服务器管理**：纳管 SSH 服务器，支持手动 / 定时巡检
- **巡检脚本库**：可视化编辑巡检脚本，复用脚本模板
- **采集记录**：查看历史巡检结果、智能检测分析

> ⚠️ **使用前需确认 Docker daemon 与 `SANDBOX_*` 配置**：详见「[智能运维中心](/help/features/ops-console)」章节的前置条件。

## 退出登录

点击左下角头像，弹出菜单中选择「退出登录」即可。

#### 退出后效果
- 浏览器侧 `access_token` HttpOnly Cookie 立即失效（服务端 `refresh_token_revoke` 触发）
- `user_login_sessions.revoked_at` 落库 + `revoke_reason='logout'`
- 前端 `localStorage` 中的会话标识被清理
- 30 分钟内无操作会自动退出（idle 超时，详见「[基本设置 → 安全认证](/help/features/basic-settings#安全认证)」）

## 下一步

- 查看「[智能体对话](/help/features/chat)」了解对话增强技巧
- 查看「[智能运维中心](/help/features/ops-console)」了解 SSH 巡检 + 智能检测
- 查看「[常见问题](/help/faq)」解决高频问题
