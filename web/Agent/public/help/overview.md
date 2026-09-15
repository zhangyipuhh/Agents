# 帮助中心

欢迎使用本帮助文档。这里汇集了系统各功能模块的使用说明、常见问题解答与最佳实践建议。

![帮助中心总览](/help/screenshots/overview/01-overview.png)

## 关于本平台

本平台是一个集成了**智能体对话、知识库管理、智能运维控制**的统一工作台，面向管理员与普通用户提供差异化的能力：

- **管理员**：可以使用所有功能模块，包括用户管理、权限管理、Agent 管理、运维任务调度等
- **普通用户**：可以使用智能体对话、知识库查询、智能运维中心（受 ACL 控制）等模块

![主会话界面（admin 视角）](/help/screenshots/overview/00-homepage.png)

## 前置条件

在阅读本帮助文档之前，请确认以下条件：

1. 已部署本系统并能通过浏览器访问入口（如 `https://your-domain`）
2. 已拥有登录账号（admin 账号请联系系统管理员发放；普通用户可通过注册流程申请）
3. 浏览器已启用 JavaScript 与 Cookie（部分功能需要登录态 Cookie）

## 阅读指引

请根据您的角色与需求，从左侧目录选择对应章节：

- **新用户**：建议先阅读「[快速入门](/help/getting-started)」了解基础概念
- **运维人员**：可跳转到「[智能运维中心](/help/features/ops-console)」查阅服务器管理、巡检脚本、SSH 执行等
- **管理员**：可查阅「[权限管理](/help/features/permission-management)」「[基本设置](/help/features/basic-settings)」与「[常见问题](/help/faq)」

## 功能模块概览

![主界面备选视角](/help/screenshots/overview/01-overview.png)

平台按一级菜单划分 14 个主要模块，按用户角色归类如下：

### 个人设置（所有用户）

| 菜单 | 说明 |
|---|---|
| 个人资料 | 修改昵称 / 邮箱 / 手机号 / 部门 / 职位 |
| 修改密码 | 旧密码校验 + 新密码复杂度校验 |
| MFA 管理 | TOTP 双因素认证的启用 / 禁用 / 恢复码管理 |

### 知识库（所有用户）

- 上传 / 下载 / 检索文档（PDF / Word / Excel / TXT / Markdown 等）
- 与智能体对话时自动引用知识库
- 文件夹管理与索引重建（管理员）

### 智能运维中心（admin + ACL 授权用户）

- 服务器管理（devops_servers + user_server_nodes）
- 巡检脚本库（inspection_scripts）
- 定时任务调度（agent_task_schedules）
- API 接口配置
- SSH 工具 + 第三方 SSH 执行器

### 智能体对话（所有用户，按 ACL 过滤）

- 11 个内置智能体（map_agent / project / knowledge_ydt / contract_host_agent 等）
- 多模态输入（文件 / 图片 / 表格）
- 流式响应 + 中止
- 反馈机制（👎）

## 设置 → 效果速查表

每篇文档遵循统一骨架：前置依赖 → 快速上手（截图）→ 详细设置与效果 → 常见问题。

| 章节 | 前置依赖 | 设置后效果 |
|---|---|---|
| [快速入门](/help/getting-started) | 浏览器 + 登录账号 | 进入主界面，可与智能体对话 |
| [智能体对话](/help/features/chat) | 已登录 | 上传文件 / 切换智能体 / 工具调用 |
| [知识库](/help/features/knowledge) | 已登录 | 上传文档 / 检索引用 |
| [智能运维中心](/help/features/ops-console) | Docker daemon + SANDBOX_* 11 字段 + devops_server | SSH 执行 / 巡检 / 智能检测 |
| [IP 白名单配置](/help/features/ip-whitelist) | REGISTRATION_SECURITY_ENABLED + IP_WHITELIST | 注册接口仅白名单内 IP 可访问 |
| [基本设置](/help/features/basic-settings) | admin 角色 | 22 组配置写入 DB（**重启后生效**） |
| [权限管理](/help/features/permission-management) | admin + permission-management.menu ACL | 菜单 / 智能体可见性按用户授权 |
| [智能体管理](/help/features/agent-management) | admin + AGENTS.md 文件 | 智能体配置 / 工具绑定 / 技能绑定 |
| [定时任务调度](/help/features/task-scheduler) | devops_server + inspection_script | cron 触发 SSH 巡检 + 落库 |
| [飞书通知](/help/features/feishu-notification) | DEVOPS_CREDENTIAL_KEY + 飞书 channel/target | LLM send_feishu_message 自动路由 |
| [MCP 服务器管理](/help/features/mcp-servers) | MCP server 进程 + enabled=true | 智能体可调用 MCP 工具 |
| [合同审批](/help/features/contract-approval) | 合同 .docx 上传 + CONTRACT_LLM_* 配置 | 合同三智能体自动审批 |
| [用户管理](/help/features/user-management) | admin 角色 | 用户列表 / 待审批 / 密码 / MFA / 会话 |

## 获取支持

如在使用过程中遇到问题，可以：

1. 查看「[常见问题](/help/faq)」中的高频问题解答
2. 通过智能体对话直接提问（系统会根据上下文给出操作建议）
3. 联系系统管理员提交工单
