# 架构与目录

> 本文件是项目记忆分片，索引见根目录 project_memory.md。

## 项目概述

Agent User Management 是一个基于 FastAPI 的 AI Agent 管理平台，提供用户认证、会话管理、文件管理、多 Agent 功能等。

## 技术栈

- **后端**: FastAPI + Uvicorn
- **数据库**: PostgreSQL（通过 asyncpg），支持 Memory 模式降级
- **认证**: JWT（双 Token 体系：Access Token + Refresh Token）
- **AI**: LangGraph + LangChain，支持多种 LLM 模型（版本详见下方 "AI 依赖版本与文档约定"）
- **SSH 执行分层**：`app/shared/tools/skills/devops/SSHTools.py` 保留大模型 LangChain 工具路径，继续负责 CommandInterceptor 黑白名单、ToolMessage 封装和业务配置解析；`app/shared/utils/ssh/` 提供与 LangChain 解耦的传统脚本 SSH 执行 helper，接收已解析连接配置和脚本内容，执行后只返回原始 stdout/stderr/exit_code/success，不读取 DevOpsServerService、不处理 inspection_parser、不经过通用命令拦截器。两条路径在 `exec_command` 后统一关闭 stdin 写端（发送 EOF，规避 Windows OpenSSH 非 PTY 通道挂死）；Windows 脚本输出统一经 `Out-String -Width 4096` + `[Console]::Out.Write` 包装（规避非控制台宿主 80 列硬换行）。

### AI 依赖版本与文档约定

#### LangChain / LangGraph 全家桶版本（锁定自 `app/requirements.txt`）

| 包                                | 版本   | 用途                                                 |
| --------------------------------- | ------ | ---------------------------------------------------- |
| `langchain`                     | 1.2.16 | LangChain 1.x 主包（统一入口）                       |
| `langchain-core`                | 1.3.2  | 核心抽象（Message、Runnable、@tool 等）              |
| `langchain-classic`             | 1.0.2  | LangChain 1.x 兼容层（旧链式 API、AgentExecutor 等） |
| `langchain-community`           | 0.4.1  | 社区工具/向量库集成                                  |
| `langchain-text-splitters`      | 1.1.1  | 文本切分器                                           |
| `langchain-openai`              | 1.1.6  | OpenAI / 兼容 OpenAI 协议模型                        |
| `langchain-anthropic`           | 1.4.2  | Anthropic Claude                                     |
| `langchain-google-genai`        | 4.2.2  | Google Gemini                                        |
| `langchain-deepseek`            | 1.0.1  | DeepSeek                                             |
| `langchain-ollama`              | 1.0.1  | Ollama 本地模型                                      |
| `langchain-mcp-adapters`        | 0.2.1  | MCP 工具适配为 LangChain 工具                        |
| `langchain-protocol`            | 0.0.14 | 协议层（实验）                                       |
| `langgraph`                     | 1.1.10 | LangGraph 主包（图编排、Checkpoint、Store）          |
| `langgraph-checkpoint`          | 4.1.1  | Checkpoint 抽象基类与内存实现                        |
| `langgraph-checkpoint-postgres` | 3.1.1  | PostgreSQL Checkpoint 后端                           |
| `langgraph-prebuilt`            | 1.0.13 | 预构建节点（ToolNode、create_react_agent 等）        |
| `langgraph-sdk`                 | 0.3.1  | LangGraph 远程部署 SDK                               |
| `langmem`                       | 0.0.30 | 长期记忆扩展                                         |
| `langsmith`                     | 0.7.38 | LangSmith 追踪/评估 SDK                              |
| `deepagents`                    | 0.5.5  | LangChain 官方 subagent 库（沙箱 Agent 依赖）        |

## 数据目录约定

运行时数据目录位于**项目根**（非 `app/` 内），便于与代码解耦并避免被打入 Docker 镜像。

```
data/                          # 项目根运行时数据目录（原 app/data）
├── Knowledge/                 # 知识库数据（地图 Agent）
│   ├── metadata.json
│   ├── sync_metadata.py
│   └── tmp/                   # 临时缓存（doc 转换、large_tool_results）
├── upload/                    # 用户上传原文件（按日期 + session_id 分目录；"不使用文件夹"场景）
│   ├── session_index.json     # session_id -> 日期目录的映射索引
│   └── yyyy/mm/dd/{session_id}/
├── project/                   # 2026-06-30 新增：项目文件夹原文件（按日期 + project_uuid 分目录）
│   └── yyyy/mm/dd/{project_uuid}/
├── tmp/
│   ├── upload/yyyy/mm/dd/{session_id}/    # 上传文件的 .md 转换结果（与 upload 平行）
│   └── project/yyyy/mm/dd/{project_uuid}/            # 2026-06-30 新增：项目文件夹解析缓存
├── download/                  # 用户下载文件（按 session_id 分目录）
├── upload_chunks/             # 分片上传临时目录（按 file_id 分目录）
├── demonstration/download/    # 演示模式专用下载目录
├── logs/Task/{任务名 slug}/   # 定时任务运行日志根目录（TASK_LOG_DIR）
└── attachments/Task/{任务名 slug}/   # 定时任务附件存储根目录（TASK_ATTACHMENT_DIR），用于定时脚本生成的邮件附件
```

### 路径常量集中管理（2026-06-29 新增，2026-06-30 扩展）

`app/core/config/paths.py` 是项目内所有数据目录绝对路径的**唯一真相源**：
- `KNOWLEDGE_DIR` = `<项目根>/data/Knowledge` —— 知识库检索根目录
- `METADATA_FILE` = `<项目根>/data/tmp/Knowledge/metadata.json` —— 知识库元数据缓存
- `TMP_DIR` = `KNOWLEDGE_DIR` 别名（兼容历史）
- `PROJECT_ROOT` = `<项目根>/data/project` —— 2026-06-30 新增；项目文件夹原文件根目录
- `PROJECT_TMP_ROOT` = `<项目根>/data/tmp/project` —— 2026-06-30 新增；项目文件夹解析缓存根目录
- `resolve_project_dir(relative_path: str) -> Path` —— 2026-07-01 新增；将相对路径解析为 `<项目根>` 下的绝对路径，空字符串抛 `ValueError`
- `resolve_project_tmp_dir(relative_path: str) -> Path` —— 2026-07-01 新增；将 `data/project/...` 形式的相对路径映射为 `<项目根>/data/tmp/project/...` 绝对路径，空字符串抛 `ValueError`
- `resolve_tmp_mirror_path(original_path: str | Path) -> Path | None` —— 2026-07-07 新增；将 `data/...` 下的原文件路径映射为 `<项目根>/data/tmp/.../.md` 镜像路径，不在 `data/` 下时返回 `None`，扩展名统一替换为 `.md`
- `TASK_LOG_DIR` = `<项目根>/data/logs/Task` —— 2026-07-15 新增；定时任务运行日志根目录
- `TASK_ATTACHMENT_DIR` = `<项目根>/data/attachments/Task` —— 定时任务附件存储根目录，用于定时脚本生成的邮件附件；完整结构：`<项目根>/data/attachments/Task/{任务名 slug}/{YYYYMMDD_HHMMSS}_{run_id}.docx`
- `TASK_ATTACHMENT_SUFFIX = "docx"` —— 2026-07-22 新增；定时任务附件默认文件扩展名，与 `TASK_ATTACHMENT_DIR` 配合使用；保留常量以便未来扩展（如 pdf）一处改全局生效
- `resolve_task_attachment_path(name, run_id, when, *, suffix="docx") -> Path` —— 2026-07-22 新增；生成 `<项目根>/data/attachments/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.{suffix}` 附件路径，`run_id` 必须为正整数（严格 `int`，排除 `bool`/`float`/`str`，与 `resolve_task_log_path` 的弱校验 `int(run_id)` 行为不同）、`when` 非 `None`、`suffix` 非空，任一校验失败抛 `ValueError`；与 `resolve_task_log_path` 路径模板对齐，便于日志与附件归档
- `DEVOPS_SERVER_CONFIG_PATH` = `<项目根>/data/devops/servers.yaml` —— 2026-07-15 新增；DevOps 服务器配置默认路径（运行时由 ``settings.devops.servers_config_path`` 覆盖）
- `DEVOPS_SERVER_CONFIG_DIR` = `<项目根>/data/devops` —— 2026-07-15 新增；DevOps 配置目录（用于 ``scan_and_upsert`` 自动创建）
- `slugify_task_name(name: str) -> str` —— 2026-07-15 新增；把任务名安全化为目录片段，非字母数字下划线连字符替换为 `_`，空字符串返回 `"task"`
- `resolve_task_log_path(name: str, run_id: int, when: datetime) -> Path` —— 2026-07-15 新增；生成 `<项目根>/data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log` 路径，`run_id` 非正整数或 `when` 为 `None` 时抛 `ValueError`
- `app/shared/utils/files/project_path_manager.py` —— 2026-07-01 重构；`get_project_upload_dir(relative_path, create=False)` 与 `get_project_tmp_upload_dir(relative_path, create=False)` 不再自行计算项目根，统一委托给上述 `resolve_project_dir` / `resolve_project_tmp_dir`，入参由 `project_uuid` 改为完整的相对路径（如 `data/project/2026/07/01/uuid`）
- `app/shared/utils/files/fileTransfer.py` —— 2026-07-01 同步改造；`delete_session` 处理 `project_id` 时直接读取 `project['relative_path']` 并传入 `get_project_upload_dir` / `get_project_tmp_upload_dir`，不再使用 `project['uuid']` 推导路径
- `app/core/router/file_upload_router.py` —— 2026-07-01 同步改造；`uploadfile` 与 `merge-chunks` 的 project 分支均改为读取 `project['relative_path']` 并传入 `get_project_upload_dir` / `get_project_tmp_upload_dir`，docstring 路径示例同步更新为日期化格式；2026-07-01 新增 `DELETE /api/core/attachments` 端点，按 `stored_path` 批量删除 `.md` 缓存、原文件及 `attachments` 记录，并校验 session_id/project_id 归属
- `app/shared/tools/middleware/filesystem_encoding_fix.py` —— 2026-07-01 确认：`_patched_read` 与 `_patched_python_search` 基于 `data/` → `data/tmp/` 前缀映射，天然兼容 `data/project/yyyy/mm/dd/{uuid}/` ↔ `data/tmp/project/yyyy/mm/dd/{uuid}/` 的日期化项目目录，无需额外修改；**2026-07-07 改造**：`_patched_read` 仅对 `pdf/docx/xlsx/md/txt` 扩展名重定向到 `.md` 缓存，非文档类扩展名（如 `.py/.json`）直接读取 `self.cwd` 下的原文件；新增 `_patched_write` 并在 `apply_fix()` 中注册，写入 `pdf/docx/xlsx/md/txt` 时同步生成 `data/tmp/.../.md` 镜像
- `app/shared/tools/middleware/docker_sandbox_backend.py` —— 2026-07-07 改造：`DockerSandboxBackend` 重写 `write`/`awrite`，直接在当前 Python 进程（宿主机侧）写入 workspace 并同步生成 `.md` 镜像，避免 `BaseSandbox.write` 在 Docker 容器内执行 preflight 路径检查时可能无法识别宿主机路径的问题，同时支持 Docker 与 local fallback 模式

**禁止**在业务代码中通过 `os.path.dirname(__file__)` 自行计算项目根；**禁止**通过 `runtime.context["knowledge_root"]` 传递路径（该字段已废弃）。

### Docker 部署 - agents/ 目录（2026-07-09 新增）

agents 表 `agents_md_path` 字段存储**相对路径**（如 `agents/project/AGENTS.md`），容器内 CWD=`/app`，`AgentsMdLoader.load()` 通过 `Path.is_file()` 判断时依赖 CWD 能解析到仓库根 `agents/` 目录。

**最终镜像/卷配置**：

- `app/Dockerfile`：`COPY agents/ /app/agents/` 把仓库根 `agents/` 打进镜像 `/app/agents/`，保证 `docker compose up` 启动即可访问
- `docker-compose.yml`：在 `agents` 服务 volumes 段追加 `- ./agents:/app/agents:rw`，运行时覆盖镜像内文件，便于开发期修改 `AGENTS.md` 后立即生效（AgentsMdLoader 有 `clear_cache()` 但此处未依赖，卷挂载 + 重启即可）；同时不需要 `docker compose build` 重建镜像

**根因**：原 Dockerfile 只 `COPY app/ /app/app/`，未把仓库根 `agents/` 入镜像 → docker 启动后 `get_agent_config()` 触发 `_loader.load('agents/project/AGENTS.md')` → `FileNotFoundError`。

### 项目文件夹（2026-06-30 新增）

用户在聊天框下拉框选择「新建空白项目」或「使用现有文件夹」后，会话文件会落到独立的 `data/project/yyyy/mm/dd/{project_uuid}/` 目录。`projects` 表通过 `relative_path` 字段持久化存储该相对路径（从 `data` 开始，如 `data/project/2026/07/01/uuid`），作为项目文件夹物理路径的唯一真相源；读取时优先从 `ProjectDB` 内存缓存获取，写入时同步更新数据库与内存缓存。详细设计见下文「项目文件夹方案」章节。

通用规则见 `AGENTS.md` "Path Management Rules"。

### asyncpg JSONB codec（2026-07-01 新增）

`app/core/database.py::DatabasePool.initialize()` 创建连接池时通过 `init` 回调
注册 JSONB / JSON 列类型 codec，使 asyncpg 自动将 JSONB 列反序列化为 Python
原生对象（list / dict）而非默认的 JSON 字符串。

- **注册方式**：`await conn.set_type_codec('jsonb', encoder=json.dumps, decoder=json.loads, schema='pg_catalog')`，`json` 同理；`_init_connection` 作为 `asyncpg.create_pool(init=cls._init_connection)` 回调
- **影响范围**：全项目所有 JSONB 字段均自动按 Python 原生类型返回，包括：
  - `users.allowed_agents`
  - `agents.config_schema` / `agents.tool_bindings` / `agents.skill_bindings` / `agents.mcp_tags` / `agents.state_schema` / `agents.context_schema`
  - `agent_tool_bindings.*`（含 `tool_type` 等元数据）
  - `conversation_records.tool_calls`
  - `tools.args_schema`
- **写入端约定**：保留 `$N::jsonb` 显式 cast + `json.dumps(...)` 调用（asyncpg 会先 dumps 再入库，与 codec 无冲突；未来单独 PR 清理）
- **防御性兜底**：`UserDB.list_users` / `get_user_by_username` / `get_user_by_id` 三处 postgres 返回路径统一调用 `_coerce_allowed_agents()`，把 JSONB 字符串 / 异常 JSON / 原生 list 规整为合法 list，避免 codec 注册失败或单测 stub 字符串值时下游 Pydantic 校验失败
- **修复触发**：2026-07-01 `GET /api/users` 返回 500 —— Pydantic 校验 `UserResponse.allowed_agents` 时收到 `str '[]'` 而非 `list`
- **修复触发**:2026-07-18 `GET /api/users` 编辑用户时邮箱/手机/部门/职位显示为空 —— `UserResponse` 模型仅声明 7 个字段(缺 `email/phone/department/position`),路由层 `list_users` 又显式构造 `UserResponse` 只传 7 个字段,Pydantic 用默认值 `''` 填充,前端 `UserSettingsDialog.vue::openEditUser` 拿到 `user.email === undefined` 被 `|| ''` 兜底为空字符串。修复:`UserResponse` 追加 4 个字段 + 路由构造时显式 `u.get(...)` 透传
- **修复触发**:2026-07-19「个人设置」Tab 打开时邮箱输入框显示 placeholder 而非数据库已有值(`admin` 用户 DB `email='542995981@qq.com'` 实际存在)。根因:双重缺失 —— (1) 后端 `UserProfileResponse` 字段全部无默认值(无 `str=''` 兜底),`get_user_profile` 路由又用 `user.get(key, '')`(仅在字段缺失时兜底,不接管显式 `None`),当 DB 行字段为 `None` 时 Pydantic V2 抛 ValidationError(500),前端 catch 后 `editEmail` 保持 `''`,渲染时显示 placeholder; (2) 前端 `switchTab` 函数缺少 `profile` 分支调用 `loadUserProfile`,当 admin 先点"管理后台"(activeTab='user-management')再在 dialog 内切换到"个人设置"时,`activeTab` 切换不会触发 `watch(props.visible)`,**`loadUserProfile` 永远不被调用**,邮箱等字段保持初始空字符串显示 placeholder。修复:`UserProfileResponse` 各字段补默认值 + 路由层 `user.get(key) or ''` 接管显式 `None` 形成「模型 + 路由」双层防御 + `switchTab` 增加 `if (tabId === 'profile') loadUserProfile()` 分支;与 2026-07-18 的 `UserResponse` 修复形成「列表 + 详情」对称契约,与 watch 形成「visible 切换 + activeTab 切换」对称触发
- **修复触发**:2026-07-19「个人设置 → 修改密码 → 旧密码」输入框在 Chrome/Edge 浏览器下即使 value 为空也会渲染 6 个默认占位圆点,造成"密码框已填"错觉。根因:`<input type="password">` 在 WebKit/Blink 内核下,空值时仍会渲染无障碍默认的占位圆点。修复:`type="password"` → `type="text"` + CSS class `password-mask` 应用 `-webkit-text-security: disc; text-security: disc;`,输入字符仍以圆点形式保护隐私,但空值时只显示 placeholder;**仅作用于旧密码**,新密码/确认新密码保持 `type="password"`(用户未要求改动)
- **修复触发**:2026-07-19「个人设置 → 保存资料」覆盖 admin 设置的可选智能体(`allowed_agents`)Bug。根因:`UserDB.update_profile()` 的 SQL `SET ... allowed_agents = $5::jsonb` 无条件覆盖该列,前端 `updateUserProfile` 不发该字段时被 `|| []` 兜底为空数组,后端整列写 `[]`。修复:`UserDB.update_profile` 签名移除 `allowed_agents` 参数 + SQL 移除该列写入 + `ProfileUpdateRequest` 移除 `allowed_agents` 字段 + `PUT /api/users/{user_id}/profile` 路由不再透传该字段 + 前端 `updateUserProfile` body 删除 `allowed_agents` 构造。三层防御(数据 → 契约 → 前端)任一层失守也不会再次出现该 Bug。`allowed_agents` 写入路径收敛为:admin 路径 `POST /api/users`(`UserCreateRequest`)与 `PUT /api/users/{user_id}`(`UserUpdateRequest`)。回归保护:`app/tests/shared/test_user_db.py::test_update_profile_does_not_overwrite_allowed_agents` + `test_update_profile_signature_no_allowed_agents`;`app/tests/shared/test_user_router.py::test_update_profile_route_does_not_overwrite_allowed_agents` + `test_profile_update_request_excludes_allowed_agents`
- **测试**:
  - `app/tests/shared/test_user_db_postgres_jsonb.py` —— 7 用例覆盖 postgres 分支 JSONB 字符串 / 空串 / 非法 JSON / 原生 list / 未命中记录
  - `app/tests/core/test_database_jsonb_codec.py` —— 2 用例覆盖 `_init_connection` 行为 + `initialize` 源码静态分析
  - `app/tests/shared/test_user_router.py` —— 追加 `test_list_users_returns_200_with_native_list_allowed_agents` 路由契约测试 + `test_list_users_response_model_includes_profile_fields` 锁定 `email/phone/department/position` 字段;2026-07-19 追加 `test_get_user_profile_response_includes_profile_fields`(详情接口响应契约)+ `test_get_user_profile_handles_none_fields`(防御性 None 兜底)
  - `web/Agent/src/components/__tests__/UserSettingsDialog.profile-email.spec.js` —— 2026-07-19 新增;端到端验证「visible:false→true」切换后 `#settings-email` 输入框正确显示后端 email
  - `web/Agent/src/components/__tests__/UserSettingsDialog.admin-profile-switch.spec.js` —— 2026-07-19 新增;端到端验证 admin 先点"管理后台"再切回"个人设置"时邮箱也能正确加载(锁定 switchTab profile 分支契约)
- `web/Agent/src/components/__tests__/UserSettingsDialog.old-password.spec.js` —— 2026-07-19 新增;验证旧密码 input 为 type=text + .password-mask 类,空值时不显示 Chrome/Edge 默认占位圆点,同时 v-model 仍正确工作

- `app/scripts/server_ops.py` 的 `ServerOpsItem` 在执行字段后追加 `inspection_parser`、`parsed_values`、`field_results`、`inspection_status`、`inspection_error`；SSH 执行成功后按 parser 解析 stdout、按 inspection_fields 评估，解析/评估失败为 `crit` 且不影响后续服务器；SSH 失败判定以**退出码非 0** 为准（退出码 0 但 stderr 非空的 shell 启动噪音不判失败，stderr 保留在 `item.stderr` 供报告展示，继续走解析评估），KeyError/无脚本为 `skipped`。`ServerOpsReport` 保留执行计数并提供 `inspection_passed` / `inspection_warned` / `inspection_critical` / `inspection_unassessed` 四项巡检计数，摘要、Markdown、字典输出包含巡检状态与字段结果。

- `app/scripts/ops/ops_report.py` —— 2026-07-22 新增；沈阳不动产运维巡检报告专用模块，含 `OpsSummary` / `OpsAlerts` / `OpsAlertItem` 数据类（综述段落统计口径 + 关键告警条目集合），`compute_ops_summary(server_report, api_report)` / `compute_ops_alerts(server_report, api_report)` 统计，`resolve_server_ip_map(devops_server_service, server_report)` 通过 `devops_server_service.get_connection_config` 反查 IP（`ip` 字段优先，`host` 作为别名兜底；缺失/KeyError/异常时返回 `None`），`build_ops_report_config(...)` 复用 `app/shared/utils/report/word/` 通用 `ReportConfig` 构建报告，`build_ops_email_body(...)` 构造邮件正文文本（不含 IP）。**2026-07-23 扩展告警字段**：`compute_ops_alerts` 接口告警项的 `value` 追加请求路径（如 `HTTP 500 /api/health`），`detail` 按 `接口地址: <path> | 耗时: <ms>ms | <error_message>` 拼接，便于邮件/排障快速定位故障 URL 与延迟；缺失字段跳过对应片段。
- `app/shared/utils/report/word/config.py` —— 2026-07-22 扩展；`SectionConfig.section_type` 新增 `"table"` 字面值（与 `"heading"` / `"paragraph"` / `"page_break"` 并列）；新增 `TableSectionConfig` 通用表格段落配置（`headers` / `rows` / `column_widths` / `header_fill` / `cell_align` / `status_column`）
- `app/shared/utils/report/word/generator.py` —— 2026-07-22 扩展；`_render_section` 分发表格渲染（`section_type="table"` → `_render_table`），按 `status_column` 映射 PASS/WARN/CRIT/未评估 单元格底色（`00B050` / `FFC000` / `C00000` / `808080`），单元格文本加粗
- IP 脱敏边界 —— 2026-07-22 确认；ops Word 报告是唯一展示真实服务器 IP 的场景（IP 仅出现在 docx 附件中），邮件正文、API 列表（`DevOpsServerService.list_public_servers` 走 `_PUBLIC_FIELDS = ("id", "business_name", "server_type", "updated_at")` 白名单）、前端 DevOps 服务器列表（基于上述 API）、日志均不带 IP；`resolve_server_ip_map` 反查失败时报告渲染为 `-`，不中断整体流程

## 统一审计日志（2026-07-29）

统一审计日志由 `app.shared.utils.log_service.LogService.emit(event) -> bool` 作为唯一写入口，覆盖认证、用户、会话、SSH 与系统事件，并通过可信身份覆盖与命令/凭据脱敏保证审计数据安全。

### 日志契约

- **唯一写入口**：`app.shared.utils.log_service.LogService.emit(event) -> bool`。
- **枚举**：`LogType ∈ {auth,user,session,ssh,system}`；`LogResult ∈ {success,failure,blocked,pending,skipped}`；`LogLevel ∈ {info,warning,error}`。
- **线程模型**：`start()` 保存当前事件循环；`emit` 跨线程通过 `loop.call_soon_threadsafe` 调度入队；调度前 `_reserve_lock` 做容量预留，超容立即返回 `False`；`put_nowait` 失败时在 `finally` 中释放预留。
- **脱敏**：`redact_metadata` 使用 `_NORMALIZED_SENSITIVE_KEYS`（`password/token/api_key/secret/api-key/access_key/private_key/mysql_pwd/redis_pwd/cookie/authorization`）；命令键（`command/intercept_reason/decision/intercept_code`）走 `redact_command`。`redact_command` 必须覆盖 `KEY=v`、`KEY="v"`、`KEY='v'`、`KEY: v`、`--key v`、`--key="v"`、`--key='v'`、`-kv`、`-k v`、`Authorization: Bearer` 与 `scheme://user:pass@host`。
- **可信身份与可信 IP**：`AgentContext.log_user_id / log_username / log_ip` 由 `app.routers.agent_router.py`（`request.state.user_id` / `request.client.host`）与 `app.shared.utils.agent.task_scheduler_service.py`（`schedule.created_by_user_id`）双层覆盖客户端/计划 `context_overrides` 的伪造值；命令、Bearer、URL userinfo 凭据禁止在响应与日志中回显。SSH 工具 `SSHTools._emit_log` 通过 `_runtime_ip(runtime)` 读取 `runtime.context['log_ip']` 写入 `LogEvent.ip_address`，最终落库到 `audit_logs.ip_address`。
- **查询 API**：`GET /api/admin/logs` 严格返回 `{items,total,limit,offset}` 信封，仅 admin 可访问，filter 同时走 `query_logs + count_logs`；`GET /api/admin/logs/{log_id}` 返回单条记录及通过 `correlation_id` 关联的 `related_logs`；`log_service` 缺失时返回 503。
- **SSH 拦截类目化**：`CommandInterceptor` 拒绝原因仅以固定类别码 `command_blacklisted` / `command_not_whitelisted` 持久化；原命令仅进入 `command_redacted` 与 `command_hash`；stdout/stderr 仅记录字节数；终态以 `exit_code == 0` 判定。
- **批量执行**：`execute_batch_commands` 必须产生 1 条汇总 + N 条成员，共享同一 UUID `correlation_id`；输入为空或 `None` 时仅产生 1 条 `failure(error_code=invalid_commands)`。
- **DB 模式**：`init_all_tables.sql` 的扩展列、CHECK 约束、索引与 `LogService.init_audit_log_schema` 一致；`memory_only` 模式使用 `LogService._memory_records`；`stop()` flush 残余并 cancel 消费协程。

## 项目架构
app/
├── core/                    # 核心模块
│   ├── server.py           # FastAPI 应用配置（生命周期、中间件、CORS）
│   ├── config/settings.py  # 配置管理
│   ├── database.py         # 数据库连接池
│   ├── prompts.py          # 通用基类系统提示词（BASE_SYSTEM_PROMPT），已包含时间处理策略：当用户问题涉及时间/日期/相对时间（如“今天”“最近N年”“过去N个月”）时，必须首先调用 get_current_time 工具获取当前时间，并将相对时间转换为绝对时间范围后，再写入子任务 prompt（如 query_knowledge），禁止直接传递含相对时间的原始问题
│   ├── concurrency/        # 并发控制模块
│   │   ├── agent_concurrency_queue.py  # 基于内存的 Agent 聊天并发队列
│   │   ├── chat_concurrency_dependency.py  # FastAPI 依赖封装
│   │   └── __init__.py     # 包初始化
│   ├── agent/              # Agent 基类
│   │   ├── stream_event.py          # StreamEvent dataclass（流式事件统一载体）
│   │   └── stream_event_source.py   # StreamEventSource：消费 agent.stream 多模式 chunk → StreamEvent 序列
│   ├── llmcalls/           # LLM 调用封装
│   ├── skills/             # Skill 系统（schema / 加载 / 提示词渲染 / bootstrap / prompt 构造 / load_skill 工具）
│   │   ├── schemas.py      # SkillInfo / SkillsConfig Pydantic 模型
│   │   ├── loader.py       # SkillDiscovery：扫描并解析 SKILL.md
│   │   ├── prompt.py       # render_available_skills_block：渲染 <available_skills> XML 块
│   │   ├── service.py      # SkillsService：skill 注册中心（全局单例 + agent 维度多实例）
│   │   ├── bootstrap.py    # BootstrapProvider：按优先级读取 bootstrap.md 并包裹 <EXTREMELY_IMPORTANT>
│   │   ├── message_transformer.py  # SkillsAwarePrompt：构造含 bootstrap + available_skills 的系统提示词
│   │   ├── tool.py         # load_skill：LangChain @tool 装饰的 skill 加载工具
│   │   └── __init__.py     # 包初始化
│   ├── tools/              # 工具基类和 MCP 适配器
│   └── router.py           # 核心路由（文件上传/下载）
├── features/               # 功能模块（各 Agent）
│   ├── contract_host_agent/    # 合同主办 Agent
│   ├── contract_document_agent/ # 合同文档 Agent
│   ├── contract_approval_agent/ # 合同审批 Agent
│   ├── ~~DevOps_agent/~~         # DevOps Agent 已下线（2026-07-15）— SSH 工具已迁移到 shared/tools/skills/devops/
│   ├── AI_Coding_Check_agent/  # AI 代码检查 Agent
    ├── audit_document_agent/   # 审计文档 Agent
    ├── sandbox_agent/          # 沙箱 Agent（已重构为 subagent 工具模式，见核心工具）
    └── Tagent/                 # T Agent
├── routers/                # 全局管理路由
│   ├── __init__.py           # 包初始化
│   ├── mcp_admin_router.py   # MCP Admin 路由（CRUD + toggle + refresh methods）
│   ├── agent_router.py       # 统一 Agent 路由（，/api/agent/chat|list|agents-md）
│   ├── knowledge_router.py   # 知识库路由
│   ├── tool_admin_router.py  # Tool Admin 路由
│   ├── skill_admin_router.py # Skill Admin 路由
│   ├── email_admin_router.py # 邮件系统 Admin 路由（SMTP 配置 + 策略 CRUD + 测试发送，prefix=/api/admin/email）
│   └── _stream_helper.py     # SSE 流式响应辅助（完整迁移自 map_router，agent_router 与 knowledge_router 复用）
├── shared/                 # 共享模块
│   ├── routers/           # 路由
│   │   ├── auth_router.py    # 认证路由（登录、注册、验证码、refresh、validate）
│   │   ├── session_router.py # 会话管理路由
│   │   ├── user_router.py    # 用户管理路由
│   │   └── file_router.py    # 文件管理路由
│   ├── tools/             # 共享工具（注册表 + 中间件 + MCP 配置）
│   │   ├── __init__.py       # 包初始化
│   │   ├── registry.py       # ToolRegistry + @register_tool 装饰器（按 agent 维度注册工具，供 AgentConfig.get_tools() 查询）
│   │   ├── mcp/              # MCP 服务器配置（config.yaml.example）
│   │   ├── middleware/       # 工具中间件（DockerSandboxBackend / EncodingSafeFileSearch 等）
│   │   ├── channels/         # 多渠道消费者（飞书 / 未来钉钉 / 企微 / Slack 等输出渠道）
│   │   │   ├── base.py           # ChannelConsumer ABC（6 个回调接口）
│   │   │   ├── registry.py       # ChannelRegistry：按 session_id 前缀路由到对应 Consumer
│   │   │   └── feishu/           # 飞书渠道实现
│   │   │       ├── __init__.py           # 包初始化时把 FeishuCardConsumer 注册到 channel_registry
│   │   │       ├── FeishuCardConsumer.py # 飞书 CardKit 同卡片流式 + HITL 同卡片按钮消费者
│   │   │       └── Throttler.py          # 时间窗 + 字符增量双条件节流器
│   │   └── skills/           # 按 agent 维度组织的工具模块（@register_tool 装饰）
│   │       ├── map_agent/    # map_agent 工具（MapTools.py，11 个工具：8 地图 + query_knowledge + generate_report + save_business_info；配套 config/ 子目录承载报告配置）
│   │       └── project/      # project 智能体工具（ProjectTools.py，8 个工具：intent_clarification / project_doc_query / project_doc_outline / project_doc_write / project_doc_workflow / manage_project_log / append_change_log / generate_project_docx）
│   └── utils/             # 工具类
│       ├── auth/          # 认证相关
│       │   ├── Safety.py          # JWT 认证（双 Token：Access + Refresh）
│       │   ├── user_db.py         # 用户数据库操作
│       │   ├── session_db.py      # Session 数据库操作
│       │   ├── refresh_token_db.py # Refresh Token 数据库操作（哈希存储）
│       │   ├── captcha.py         # 验证码生成
│       │   └── audit_log.py       # 审计日志
│       ├── Session/       # Session 缓存
│       ├── files/         # 文件操作
│       │   ├── session_path_manager.py  # session 上传目录日期化管理
│       │   ├── project_path_manager.py  # 项目文件夹路径管理（委托 resolve_project_dir / resolve_project_tmp_dir）
│       │   ├── fileTransfer.py          # 文件清理/列出
│       │   ├── file_upload_handler.py   # 上传处理
│       │   └── pdfToImage.py            # PDF 转图片
│       ├── email/          # 邮件系统（与 FastAPI 解耦，脚本可直接 asyncio.run 调用）
│       │   ├── email_models.py          # EmailServerConfig / EmailPolicy / SendEmailRequest Pydantic 模型
│       │   ├── email_config_service.py  # EmailConfigService（SMTP 配置 CRUD + 策略 CRUD + Fernet 加解密 + @register_schema 建表）
│       │   └── email_service.py         # EmailService（核心发送，smtplib + asyncio.to_thread 异步包装）
│       └── memory/        # 记忆存储（Checkpoint）
├── web/Agent/             # 前端 SPA（Vue 3 + Vite，多入口）
│   ├── index.html         # 主入口（Agent 聊天 + 知识库 Tab）
│   ├── knowledge.html     # 知识库独立页入口
│   ├── portal.html        # 门户导航入口（沈阳市自然资源和规划"一点通"）
│   ├── main.js / knowledge-main.js / portal-main.js  # 三个入口 JS
│   ├── src/
│   │   ├── App.vue        # 主应用根组件（未登录：Login/Register；已登录：Sidebar + ChatArea + InputBox）
│   │   ├── components/ChatArea.vue  # 2026-07-02 修正：标题栏与消息区改为 flex 分栏布局，
│   │   │                              标题栏不再使用 sticky，消息内容不会被标题栏压盖
│   │   ├── KnowledgeApp.vue # 知识库独立页根组件
│   │   ├── PortalApp.vue  # 门户根组件（顶部蓝色导航 + iframe 内嵌 knowledge.html）
│   │   ├── components/    # 业务组件（Sidebar/ChatArea/InputBox/HumanApprovalBox/FileList/FilePreview/...）
│   │   ├── views/         # LoginView、RegisterView
│   │   ├── utils/         # api.js（SSE/auth/session/file）、sseParser.js（thinking/text/timeline/tools）
│   │   ├── styles/        # variables.css（设计 token）、main.css
│   │   └── __tests__/     # Vitest（HumanApprovalBox / api / sseParser）
│   ├── vite.config.js     # 多入口（main/knowledge/portal）+ /api 代理 VITE_API_TARGET
│   ├── vitest.config.js   # 测试配置
│   ├── nginx.conf         # Docker 部署用 Nginx 模板（SSE 反代 + SPA fallback）
│   └── Dockerfile         # 多阶段构建：node:20-alpine 构建 → nginx:alpine 运行
└── main.py               # 应用入口
```

## 通用配置归属隔离（OwnershipScope，2026-07-24 新增）

邮件设置中的发送策略需要按创建者做可见性隔离：admin 见全部策略；普通用户仅见自己创建的策略。同一诉求也落地到「API 接口配置」与「智能体定时任务」，故建立通用 `OwnershipScope` 抽象供各 service 复用，避免每个业务表各自实现一套权限过滤。

### 通用模块

- `app/shared/utils/auth/ownership_scope.py::OwnershipScope` —— frozen dataclass，含 `user_id / is_admin / system` 三字段；提供：
  - `from_request(request)`：从 `request.state.user_id / role` 构造（由 `auth_middleware` 写入）
  - `for_user(user_id, is_admin=False)`：已知用户场景（脚本调用）
  - `system_scope()`：系统内部调用入口（定时任务运行时等绕过隔离场景）
  - `can_access(owner_id) -> bool`：判定当前 scope 是否可访问 `owner_id` 创建的记录（system / admin / owner 三类通过）
  - `sql_filter(column, param_index)` -> `(SQL片段, 参数列表)`：把 scope 翻译为 SQL WHERE 子句（admin / system → `"TRUE"`；普通用户 → `"{column} = $N"`）
- **类型契约**：`can_access(owner_id)` 内部使用 `==` 直接比较，**不做 `int()` 强转**；调用方必须保证 `owner_id` 已是 `int`（或 `None`），非 int 输入（`str` / `float` / `bool` 等）一律返回 `False`。该设计避免 `int("5") == int(5)` 这类类型归一绕过导致的越权风险；DB 字段 `created_by_user_id` 是 `INTEGER`，asyncpg 取出即 `int`，不存在转换需要
- **约定字段命名**：凡需隔离的配置表统一加 `created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE`，与已有 `email_policies` / `api_config_nodes` 列名一致；新表也沿用，避免命名分叉
- **越权访问语义**：service 层缺失与越权统一抛 `*NotFoundError`（不区分"不存在"与"无权限"，避免泄露记录是否存在）；路由层映射 HTTP 404。**例外**：父节点校验（`create_node` / `update_node` 的 parent）翻译为 `ValueError("父节点不存在: <id>")` → HTTP 400，保留前端"父节点不存在"的用户反馈
- **正交关系**：菜单 ACL（`require_admin_or_menu_acl`）仍是入口门（控制"能否调端点"），OwnershipScope 是其之上的数据层过滤（控制"能看到哪些数据"），两者各司其职

### 落地一：邮件发送策略

- `EmailConfigService.list_policies(scope)` / `get_policy(policy_id, scope)` / `update_policy(policy_id, scope, ...)` / `delete_policy(policy_id, scope)` 全部接收 `scope` 参数；返回项附加 `created_by_user_id` 字段供前端 admin 视图展示归属
- 新增 `EmailConfigService.get_policy_internal(policy_id)` —— 系统内部入口，使用 system scope 绕过隔离，供 `TaskSchedulerService._dispatch_script_email` 按 `notify_policy_id` 直查（运行时信任配置期校验）
- `app/routers/email_admin_router.py`：所有 `/policies` 与 `/send-by-policy/{id}` 端点通过 `OwnershipScope.from_request(request)` 构造 scope 传入 service；service 返回 `None` / `delete=False` 时路由返回 404
- `EmailPolicy` Pydantic 模型新增 `created_by_user_id: Optional[int]` 字段
- `init_all_tables.sql`：`email_policies.created_by_user_id` 加索引 `idx_email_policies_created_by_user_id`（list 按用户隔离时高频 WHERE 该列）

### 落地二：API 接口配置（api_config_nodes，2026-07-24）

- `ApiConfigService.get_tree(scope)` —— admin / system 透传全量；普通用户按 `created_by_user_id` 过滤，**父节点不可见的节点 `parent_id` 重写为 `None` 提升为根**，便于前端组树且不泄露隐藏父节点的存在
- `create_node(parent_id, node_type, name, scope)` —— `created_by_user_id = scope.user_id`（缺失抛 `ValueError`）；非 admin 父节点必须是 `scope.can_access(parent)` 通过的 folder，不可见父节点报 `ValueError("父节点不存在")`（400）；api 节点自动建默认 `api_configs` 行
- `update_node(node_id, scope, ...)` / `delete_node(node_id, scope)` / `get_config(node_id, scope)` / `upsert_config(node_id, scope, ...)` / `send_request(node_id, scope)` / `list_runs(node_id, scope, ...)` —— 缺失/越权统一抛 `ApiConfigNotFoundError`（404）；folder 类型不匹配仍 `ValueError`（400）；非空文件夹删除统计**全部**子节点（含他人隐藏子节点）防误删
- 新增 `ApiConfigService.get_node_internal(node_id)` —— 内存缓存轻量查询，不做归属校验，供 `TaskSchedulerService._assert_api_list_access` 系统内部使用
- `app/scripts/api_check.py::run_api_checks` —— 运行时改用 `OwnershipScope.system_scope()` 调用 `get_tree` / `send_request`，绕过隔离（配置期校验已确保 `api_list` 归属）
- `app/routers/api_config_router.py`：所有 8 个端点构造 `OwnershipScope.from_request(request)` 透传 service
- `init_all_tables.sql` 21.1 归属迁移段：位于主事务 COMMIT 之后的独立 `BEGIN/COMMIT`，纯 SQL 顺序语句（`ADD COLUMN IF NOT EXISTS ... REFERENCES users(id)` → `UPDATE` 回填首个 admin（兜底首个用户，仅处理存量 NULL）→ `ALTER COLUMN SET NOT NULL` → `CREATE INDEX idx_api_config_nodes_created_by_user_id`）；全脚本约定不使用 dollar-quoting DO 块 / SAVEPOINT / psql 元命令（如 `\i`），兼容 psql + Navicat / pgAdmin / DBeaver

### 落地三：智能体定时任务（agent_task_schedules，2026-07-24）

`agent_task_schedules.created_by_user_id` 字段已存在但此前无数据层过滤；本次补充：

- `TaskSchedulerService.list_schedules(scope)` —— `scope.sql_filter("created_by_user_id", 1)` 拼 WHERE；admin 全量；普通用户仅自己创建
- `get_schedule(schedule_id, scope)` —— 缺失/越权抛 `TaskScheduleNotFoundError`（404）；新增私有 `get_schedule_internal(schedule_id)`（原 `get_schedule` 主体）供 `execute_schedule` / `update_schedule` / `set_schedule_enabled` / `trigger_schedule` / `_mark_schedule_run_completed` 内部使用
- `update_schedule(schedule_id, payload, scope)` —— 签名增加 `scope` 参数（替换原 `is_admin`）；内部 `get_schedule_internal` + `scope.can_access(owner)` 校验，越权抛 `TaskScheduleNotFoundError`；notify / api 校验沿用现有 schedule owner
- `set_schedule_enabled(schedule_id, enabled, scope)` / `delete_schedule(schedule_id, scope)` / `trigger_schedule(schedule_id, scope)` / `list_runs(schedule_id, scope, limit)` —— 全部加 scope；list_runs 行为由「缺失返回空列表」改为「缺失/越权抛 NotFound」（404）
- `create_schedule(payload, created_by_user_id, is_admin)` —— 签名**不变**（对齐 `EmailConfigService.create_policy` 先例）；新增 `_assert_api_list_access(script_args, schedule_owner_user_id, is_admin)` 校验 `script_args["api_list"]` 每个 id 的归属
- `_assert_api_list_access` —— 镜像 `_assert_notify_policy_access` 模式：缺失/非 list / 非整数字符串 → `TaskScheduleValidationError`；逐 id `api_config_service.get_node_internal` 查节点，不存在/非 api 类型/非 admin 跨用户 → `TaskScheduleValidationError`；`api_config_service` 未注入时 warning 跳过（与 notify_policy 兜底一致）
- `app/routers/task_scheduler_router.py` —— 所有端点构造 `OwnershipScope.from_request(request)` 透传；create 端点从 scope 提取 `scope.user_id or 0` / `scope.is_admin` 显式传入（保留 create 签名不变）；删除 `_request_user_id` / `_request_is_admin` helper
- `init_all_tables.sql`：补 `idx_agent_task_schedules_created_by_user_id` 索引（list 过滤 WHERE 该列）

### 测试

- `app/tests/shared/utils/auth/test_ownership_scope.py` —— 22 用例覆盖 `from_request / for_user / system_scope` 工厂 + `can_access` 判定矩阵（含 admin / system / owner / 越权 / 缺失字段）+ `sql_filter` 透传
- `app/tests/shared/utils/email/test_email_config_service_scope.py` —— 16 用例覆盖 list / get / update / delete 在 admin / user / system scope 下的可见性
- `app/tests/routers/test_email_admin_router_scope.py` —— 13 用例覆盖路由层 404 契约（越权 update / delete / send-by-policy）+ scope 透传
- `app/tests/shared/utils/agent/test_task_scheduler_notify_policy_scope.py` —— 9 用例覆盖 `_assert_notify_policy_access` 判定 + `create_schedule` 跨用户拒绝
- `app/tests/shared/utils/test_api_config_service_scope.py`（2026-07-24 新增）—— 18 用例覆盖 get_tree 过滤/提升、create 父节点归属校验、update/delete/config/send/runs 越权 NotFound、get_node_internal 直查
- `app/tests/routers/test_api_config_router_scope.py`（2026-07-24 新增）—— 11 用例覆盖 scope 透传断言 + 越权 404 契约 + 父节点越权 400 契约
- `app/tests/shared/utils/agent/test_task_scheduler_schedule_scope.py`（2026-07-24 新增）—— 23 用例覆盖 list 过滤、get/update/delete/enable/trigger/runs 越权 NotFound、`_assert_api_list_access` 完整判定矩阵（含 admin bypass / missing node / folder type / invalid element）+ create/update 集成
- 回归保护：现有 `app/tests/shared/utils/email/test_email_config_service.py`（30 例）+ `app/tests/shared/utils/agent/test_task_scheduler_service.py`（30 例）+ `app/tests/routers/test_email_admin_router.py`（30 例）全部通过；原 `fake_email_config_service.get_policy` mock 改为 `get_policy_internal`（dispatch 路径已切换到 system scope）；`ApiConfigService` 既有 28 例 service 单测补 scope 参数；`TaskSchedulerService` set_enabled/trigger 2 例补 scope；api_check + hello_script 的 stub 服务补 `scope=None` 默认参数

#### 执行历史弹窗（TaskSchedulerManager.vue `.task-history-dialog`）

- 数据源：`GET /api/admin/task-schedules/{id}/runs?limit=50`（`web/Agent/src/utils/api.js::fetchTaskRuns`）
- 字段显示：`<span>` 渲染经 `formatRunTime(value)` 本地化
- 时间格式：**绝对时间 `YYYY-MM-DD HH:MM:SS`（24h，零填充，本地时区）**
- 兜底：`null` / 空字符串 / 非法日期 → `-`
- 渲染优先级：`run.created_at` → `run.started_at`
- 不使用 dayjs / date-fns / moment；不依赖后端时间格式调整

## 项目文件夹方案（2026-06-30 新增）

### 设计目标

用户从聊天框下拉框选择"进入项目工作"后：
- 上传的文件落到独立的项目目录（与 session 目录完全隔离）
- 同一项目可被多个 session 共享（多 session 协作）
- 沙箱 / explore / audit 等工具能读取项目目录里的文件
- 历史会话切换时自动恢复项目选择

### 完整语义模型

| 操作 | sessions.project_id | projects.uuid | 物理路径 |
|------|---------------------|---------------|----------|
| 用户新建项目"Daily-work"（无 session） | NULL | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/` |
| session 1111 绑定到项目 1 | 1 | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/`（共享项目目录）|
| session 2222 绑定到项目 1 | 1 | `proj-uuid-a` | `data/project/2026/07/06/proj-uuid-a/`（共享项目目录）|
| session 2222 切回不使用文件夹 | NULL | - | `data/upload/.../2222/` |
| 旧历史会话（无 project） | NULL | - | `data/upload/.../session_id/` |

**关键点**：项目是独立实体，`projects.uuid` 不再与 session_id 绑定；多 session 通过 `sessions.project_id` 关联到同一项目目录。

### 路径查找策略

```python
# session_path_manager.get_session_upload_dir(session_id, project_id=None)
if project_id:
    project = ProjectDB.get_project_by_id(project_id)
    return get_project_upload_dir(project['relative_path'])  # data/project/yyyy/mm/dd/{uuid}/
# 无 project_id：原 session 路径
return data/upload/yyyy/mm/dd/{session_id}/
```

**有 project_id 就用 project_id，没有再用 session_id**——兼容旧 session 逻辑。项目目录按 `projects.relative_path` 解析，不再直接用 `uuid` 推导。

### 关键模块

| 模块 | 职责 |
|------|------|
| `app/shared/utils/project/project_db.py` | ProjectDB 两级缓存（参照 SessionDB 模式） |
| `app/shared/utils/files/project_path_manager.py` | 项目独立目录路径解析 |
| `app/shared/routers/project_router.py` | 项目 CRUD + session 绑定/解绑 API |
| `session_auth_middleware` | 中间件注入 `request.state.project_id` |
| `app/routers/agent_router.py::chat` | 把 project_id 注入 `context_overrides` |
| `AgentContext.project_id` | 工具通过 `runtime.context.get("project_id")` 读取 |
| `app/shared/utils/files/fileTransfer.py` | 2026-07-01 新增：`build_session_file_tree` 构建会话/项目文件树；`resolve_session_file_path` 解析并校验文件路径（防路径遍历）；`_get_preview_mode` / `read_session_file_content` 支持文本/图片/Office/PDF 预览；`delete_session` 同步支持项目目录清理；2026-07-17 加固 `_scan_dir_tree`：listdir 失败返回空 children、单 entry stat 失败 per-entry try/except 跳过
| `app/shared/utils/files/session_path_manager.py` | 2026-07-17 新增 `_to_filesystem_safe(session_id)`：读路径入口把 `:` 替换为 `_`，与飞书 WS 写路径 `_safe_session_marker` 保持等价语义；`get_session_upload_dir` / `get_session_tmp_upload_dir` 入口调用，避免 Windows 上 Path.iterdir 抛 WinError 123
| `app/shared/utils/auth/Safety.py` | 2026-07-17 `SESSION_WHITELIST_PREFIXES` 追加 `/api/core/upload-config`：前端 onMounted 拉取的只读配置，不需要 session 隔离（与 `/api/agent/list` 语义一致）；**不放行整个 `/api/core` 前缀**，避免误伤 uploadfile/merge-chunks 等写接口
| `app/shared/routers/session_router.py::get_session_files_tree` | 2026-07-17 补 `logger.exception` 日志：500 时先打完整 traceback 再 raise，便于运维定位根因

### 工具透传链

`AgentContext.project_id` → 各工具通过 `runtime.context.get("project_id")` 读取 → 透传给 `get_session_upload_dir(session_id, project_id=project_id)`

已透传的工具：
- `SandboxTools.py` —— 沙箱 workspace
- `FilesystemReadTools.py` —— 文件检索
- `file_upload_handler.py` —— 文件处理
- `fileTransfer.py` —— 文件上传/下载/删除
- `pdfToImage.py` —— PDF 转图片
- `audit_document_agent/tools/tools.py` —— 审计 parse_transaction

### 前端集成

| 组件 | 职责 |
|------|------|
| `ProjectDropdown.vue` | 紧挨着 InputBox 上方的下拉框（顶部只读预览 + 3 个动作 + 锁定支持） |
| `SubAgentSuggestionStrip.vue` | InputBox 项目卡下方常驻子智能体胶囊条（2026-07-14 新增）；按 `allowedAgents` 过滤 + 居中展示；点击胶囊 → `emit('select', agent)` 复用 `InputBox.selectAgent` |
| `ProjectDialog.vue` | 双模式弹窗（create / pick）；create 模式点击保存后 emit `created`，弹窗关闭由父组件控制 |
| `App.vue` | `currentProject` 状态机 + handleSessionSwitch 恢复 + newSession 纯前端重置（2026-07-XX 改造）+ `canEditProject` 锁定判定 + `ensureSessionForFirstOp` 按需建 session + `handleProjectCreate` 成功后关闭弹窗并刷新按钮文案 |

### 前端 Session 创建时机改为「首次交互时」（2026-07-XX 改造）

**动机**：原实现中点击「新建任务」按钮或刷新页面都会触发 `/api/session/create`，产生大量"用户未实际交互"的空 session 入库，污染 DB 与侧边栏。

**新规则**：

- **首次进入页面 / 刷新页面**：**不**自动建 session；`sessionId` 保持空字符串，侧边栏无激活项、无"新对话"条目。
- **点击「新建任务」按钮（Sidebar 菜单 / InputBox 的 `@new-chat` 等）**：仅做纯前端页面重置（清 messages / attachments / agentName / sessionTitle / SubAgentDrawer / SessionFileDrawer / approvalMode / `toolStopPending` / `queueStatus`），**不**调 `/api/session/create`。
- **session 的实际创建延后到真正需要后端的入口**：
  1. **首条消息发送**（`handleSendMessage` 在 `chatStream` 前先 `await ensureSessionForFirstOp(projectIdForChat)`）
  2. **发送时存在文件附件**：选择文件本身只进入本地列表，点击发送后 `InputBox::handleSend` 先 `await props.ensureSession(projectIdForUpload)`，再统一上传文件；并发上传由 `createNewSession` 自带的 `isCreatingSession / pendingSessionPromise` 防重锁收敛到 1 次后端调用。2026-07-07 修正：禁止纯附件发送，必须有文本才能触发发送与上传。
  3. **首次斜杠命令**：命令结果走 `emit('send', result.text, [])` 进入 `handleSendMessage` → 命中第 ① 点。

- **项目选择/创建本身不触发 session 创建**（2026-07-06 修正）：项目是独立实体，`App.vue::handleProjectPick` / `handleProjectCreate` / `handleProjectSelectNone` 不再以 `sessionId.value` 是否存在为前提。无 session 时仅更新前端 `currentProject` 状态；有 session 时才调用 `/api/project/session/bind` 或 `/api/project/session/unbind` 同步当前会话的项目关联。未建 session 时若用户发送首条消息 / 上传文件，`ensureSessionForFirstOp(currentProject.id)` 会一并把项目 ID 带到 `/api/session/create`。

**实现要点**：

- `App.vue` 删除原 `ensureSession()`，`onMounted` 仅保留 `checkAuth()`。
- `App.vue` 新增 `ensureSessionForFirstOp(projectId)`：若 `sessionId.value` 已存在则短路返回；否则 `createNewSession('session_id', projectId)` → 同步 `sessionId.value` / `sessionTitle` → `refreshSessionTitle` 异步刷新真实标题 → `sidebarRef.loadSessionList()` 刷新侧边栏。
- `App.vue::handleApprovalSubmit` 加防御性 early-return：缺 `sessionId` 时直接退出（实际不会触发，因为触达 HITL 必然先经历 `handleSendMessage`）。
- `App.vue::handleProjectPick` / `handleProjectCreate` / `handleProjectSelectNone`（2026-07-06 修正）：项目是独立实体，选择/创建/解绑项目不再以 `sessionId.value` 为前提。无 session 时仅更新前端 `currentProject` / `currentAttachments` 状态；有 session 时才调用 `/api/project/session/bind` 或 `/api/project/session/unbind` 同步当前会话的项目关联。创建项目时 `createProject(name)` 不再传入 `session_id` 作为 uuid，由后端独立生成。`handleProjectCreate` 对返回值做防御性读取，成功设置 `currentProject` 后由父组件关闭弹窗，确保按钮文案实时刷新；`handleProjectPick` 对入参做基础校验。
- `App.vue` 模板 `<InputBox :ensure-session="ensureSessionForFirstOp" ... />`。纯文本发送时 `ensureSession` 不在 InputBox 内调用，仍由 `App.vue::handleSendMessage` 负责按需创建 session；仅当 InputBox 内存在待上传文件时才在发送流程中调用 `ensureSession`。
- `InputBox.vue` 新增状态 `isUploading`：发送上传期间禁用发送按钮，避免重复触发。
- `InputBox.vue` 选择文件后仅加入 `selectedFiles`（状态 `pending`），不立即上传；`addFiles` 完成时若存在有效文件即 `emit('project-lock-change', true)`，防止用户在发送前切换项目导致附件挂接到错误 projectId。
- `InputBox.vue::handleSend` 新流程：① 检查必须有文本；② 刷新 token；③ 若存在 `pending` 文件则 `await props.ensureSession(projectIdForUpload)` 创建/获取 session 并挂接 projectId；④ 调用 `startUpload` 统一上传；⑤ 任一文件失败则提示错误并中断发送；⑥ 全部成功后 `emit('send', text, uploadedFiles)` 并清空输入框与文件列表。
- `InputBox.vue::startUpload` 移除内部 `ensureSession` 调用，仅执行分片上传，并返回 `uploadFileInChunks` 的 Promise 以支持 `handleSend` 中 `Promise.all` 等待。
- `InputBox.vue::removeFile` 对 `pending` 文件仅本地移除，不调用 `deleteAttachments`；删除后 `selectedFiles` 为空时 `emit('project-lock-change', false)`。
- `Sidebar.vue` 的 `currentSessionId` 默认值已为 `''`，与历史 session_id 比较时天然不匹配；空 session 时不高亮任何条目，无需额外改动。

**影响面**：

- 后端 `/api/session/create` 接口契约不变；`createNewSession` 自带的防重复锁机制复用。
- `KnowledgeApp.vue` / `KnowledgePage.vue` 维持独立链路（独立 `knowledge_session_id`），本次未在范围内，逻辑保持原状。
- 项目选择器锁定（`canEditProject`）语义扩展：新建任务（messages 空且无成功上传文件）→ 可编辑；首条消息发送成功或存在成功上传文件 → 锁定（详见「项目选择器锁定逻辑」章节）。

### 后端 `/api/agent/list` 加入 Session 白名单（2026-07-XX 配套）

**动机**：前端按需建 session 改造后，`<InputBox onMounted>` 调 `fetchAgentList()`（`GET /api/agent/list`）时 `localStorage.session_id` 为空 → 后端 `session_auth_middleware` 命中 `SESSION_REQUIRED_PREFIXES`（`/api/agent/`）→ 抛 400 "缺少 X-Session-ID 请求头"，导致侧边栏"项目 / 智能体下拉"等首屏交互失效。

**新规则**：

- `app/shared/utils/auth/Safety.py::SESSION_WHITELIST_PREFIXES` 追加 `"/api/agent/list"`（与 `/api/session/list` 同模式：精确前缀匹配）。
- `list_agents` 路由**不依赖 session 隔离**，仅读 `request.state.allowed_agents`（来自 JWT），跳过 X-Session-ID 校验。
- `/api/agent/chat` 仍命中 `SESSION_REQUIRED_PREFIXES`（`/api/agent/`），保持 session 校验不变（按需建 session 的核心保证）。

**实现要点**：

- `app/shared/utils/auth/Safety.py`：`SESSION_WHITELIST_PREFIXES` 列表末尾追加 `"/api/agent/list"` + 注释。
- `app/routers/agent_router.py::list_agents` docstring 补充"不依赖 session_id 隔离"说明。
- `app/tests/routers/test_agent_router.py` 新增 2 个回归测试：
  - `test_list_agents_works_without_session_id`：不带 `X-Session-ID` 头调用 `GET /api/agent/list` → 期望 200。
  - `test_agent_chat_still_requires_session_id`：不带 `X-Session-ID` 头调 `POST /api/agent/chat` → 期望 400，验证白名单精确前缀不会误伤 `chat`。

**影响面**：

- 与 `/api/agent/list` 同语义的 `/api/session/list` / `/api/project/list` 早就走白名单或自然放行，行为对齐。
- 前端 `InputBox::loadAgents()` / `fetchAgentList()` 调用链路不变；冷启动 / 按需建 session 阶段 `GET /api/agent/list` 自动 200，智能体下拉正常工作。

### 项目选择器锁定逻辑（2026-07-01 新增，2026-07-06 扩展）

**规则**：

- 新建会话、`messages` 数组为空且不存在已选文件时 → 项目选择器**可编辑**
- 一旦该会话成功发送过一条消息（或被恢复的历史会话本身有消息）→ 项目选择器**永久锁定**（同一会话再也不能改项目）
- 仅选择文件（未发送）→ 项目选择器**锁定**（2026-07-07 修正：只要 `selectedFiles` 非空即锁定，避免发送前切换项目导致附件挂接到错误 projectId）
- 删除所有已选文件且 `messages` 仍为空 → 项目选择器**恢复可编辑**（2026-07-07 修正：删除后 `selectedFiles` 为空即解锁）
- 切到历史会话时 → 若历史消息数 > 0，**锁定**；若历史为空，**仍可编辑**（允许给从未发过消息的空会话补绑项目）
- 历史会话 `fetchSessionMessages` 失败时 → **默认锁定**（保守策略，避免未知状态下误操作）
- `streaming` 中 → 仍按 `disabled` 短路（与锁定独立，两个维度均可独立触发 disable）

**实现**：

- `App.vue` 新增 `historyLoadFailed = ref(false)`、`projectLockedByUpload = ref(false)` 与派生 `canEditProject = computed(() => isEmptyState.value && !historyLoadFailed.value && !projectLockedByUpload.value)`
- `App.vue::handleSessionSwitch` 入口重置 `historyLoadFailed`，catch 块置 true
- `App.vue::newSession` 重置 `historyLoadFailed` 与 `projectLockedByUpload`
- `App.vue` 模板：`<InputBox :project-locked="!canEditProject" @project-lock-change="projectLockedByUpload = $event" ... />`
- `InputBox.vue` 新增 prop `projectLocked`，透传给 `<ProjectDropdown :locked="projectLocked" />`；新增计算属性 `hasSelectedFiles`（`selectedFiles.length > 0`），并在选择文件时 `emit('project-lock-change', true)`、删除后列表为空时 `emit('project-lock-change', false)`
- `ProjectDropdown.vue` 新增 prop `locked`，与 `disabled` 通过 `effectiveDisabled = computed(() => disabled || locked)` 合并；`toggleDropdown()` 短路 `effectiveDisabled`；按钮 `:disabled="effectiveDisabled"`、class `disabled` 同步
- **视觉**：复用现有 `.disabled` 样式（灰 + not-allowed），不新增图标（设计决策：避免与 streaming 状态视觉混淆，用户可通过 hover tooltip "项目已锁定" 知晓原因）

**测试**（Vitest，全过）：

- `web/Agent/src/components/__tests__/ProjectDropdown.locked.spec.js` — `locked=true` 时按钮 disabled、点击不开下拉、已选项 label 保留可见、`disabled || locked` 任一为 true 都短路
- `web/Agent/src/components/__tests__/InputBox.locked.spec.js` — `projectLocked` prop 透传到 `ProjectDropdown.locked`，默认值 false，与 `isStreaming` 解耦
- `web/Agent/src/components/__tests__/InputBox.upload-lock.spec.js` — 2026-07-07 改造：选择文件后立即 emit `project-lock-change(true)`；仅选文件无文本时 `canSend=false` 且不上传/不创建 session；有文本+文件时发送才调用 `ensureSession`（携带 projectId）、上传文件并 emit `send`；删除全部文件后 emit `project-lock-change(false)`
- `web/Agent/src/components/__tests__/App.project-lock.spec.js` — `canEditProject` 派生：初始 true、恢复历史会话后 false、history 拉取失败默认锁定 false、`newSession` 重置回 true、`projectLocked` 透传到 InputBox；存在已选文件时 `projectLockedByUpload` 为 true 导致 `canEditProject` 为 false

### 前端 chat 请求体显式携带 project_id（2026-07-01 新增）

为消除 chat 时对 `sessions.project_id` 隐式链路的完全依赖，前端在调用 `chatStream` / `knowledgeChatStream` 时把当前项目 ID **显式放进请求 body 的 `context_overrides.project_id` 字段**，与 `newSession` 显式传 `projectId`（`App.vue:301`）的设计保持一致（"显式优于隐式"）。

**前端改动**：

- **`web/Agent/src/utils/api.js`**：`chatStream` / `knowledgeChatStream` 签名扩展 `projectId` 参数（向后兼容，默认 `null`）；body 把原本硬编码的 `geometry_data: {}` 合并进 `context_overrides.geometry_data`（`chatStream`），把 `projectId` 在非 null 时注入 `context_overrides.project_id`。
- **`web/Agent/src/App.vue`**：`handleSendMessage`（行 442）/ `handleApprovalSubmit` resume（行 539）调 `chatStream` 时从 `currentProject.value.id` 取出传入。
- **`web/Agent/src/KnowledgeApp.vue`**：本次未接入（无 `currentProject` ref）；仍依赖 `session_auth_middleware` 注入 `request.state.project_id` 兜底。
- **`web/Agent/src/components/KnowledgeChat.vue`**：本次未修改；调 `knowledgeChatStream` 时不传 `projectId`，等 `knowledge_router.py` 后续改造。

**后端透传路径（2026-07-01 简化）**：

1. 前端 `chatStream` body `context_overrides.project_id` → `ChatRequest.context_overrides`（`agent_router.py:56`）→ `agent_router` 仅做空值过滤（`_EMPTY_VALUES`）后透传 `build_agent_instance`。
2. `agent_config_service.py::build_agent_instance` 通过 `RESERVED_CONTEXT_FIELDS` 过滤 `safe_overrides` 后注入 `context_class(**safe_overrides)`。
3. **2026-07-01 移除 `project_id` 字段后**：`AgentContext` 不再预声明 `project_id`（见下节），`RESERVED_CONTEXT_FIELDS` 也同步移除该键；`project_id` 作为"自定义上下文键"由前端经 `context_overrides` 注入，运行时经 TypedDict dict 落到 `runtime.context.get("project_id")` 供 `SandboxTools` / `FilesystemReadTools` 等工具读取。

**修改文件（2026-07-01）**：

- `web/Agent/src/utils/api.js` —— `chatStream` / `knowledgeChatStream` 扩签名 + body 改造
- `web/Agent/src/App.vue` —— `handleSendMessage` / `handleApprovalSubmit` resume 传 `projectId`
- `app/core/agent/AgentContext.py` —— **删除** `project_id: Optional[int] = None` 字段（含 import 调整）；类文档注释说明 `project_id` 由调用方通过 `context_overrides` 显式注入
- `app/shared/utils/agent/dynamic_schema.py` —— 从 `RESERVED_CONTEXT_FIELDS` 移除 `"project_id"`（不再属于基类保留字段）
- `app/shared/utils/agent/agent_config_service.py::build_agent_instance` —— 回退特殊处理，恢复通用 `context_class(session_id=..., **safe_overrides)` 形式
- `app/routers/agent_router.py::chat` —— 回退 `request.state.project_id` 合并逻辑（删除 `getattr(request.state, "project_id", None)` 与 merged_overrides 合并分支），改纯透传 `chat_request.context_overrides`；保留 `_EMPTY_VALUES` 空值过滤

**未修改（保持兼容）**：

- `app/shared/utils/auth/Safety.py::session_auth_middleware` —— 仍向 `request.state.project_id` 注入值（`app/core/router/file_upload_router.py` 上传/合并分片路由还在用 `request.state.project_id`）
- `app/routers/knowledge_router.py` —— 本次不同步（用户决策）
- `get_session_upload_dir(session_id, project_id=...)` 工具链不变
- `app/routers/file_upload_router.py` —— 上传路径仍依赖 `request.state.project_id`（这是 HTTP 路由层而非 agent runtime 层，链路不同）

**测试覆盖**：

- 前端 Vitest `web/Agent/src/utils/__tests__/api.agent-chat.test.js` 共 10 用例全过（4 旧 + 6 新）
- 后端 pytest `app/tests/routers/test_agent_router.py` 共 30 用例全过（含重写的 `test_chat_context_overrides_project_id_passed_through` / `test_chat_context_overrides_without_project_id_is_empty` / `test_chat_context_project_id_reaches_agent_context_runtime` 三个新语义用例）

**设计原则**：「显式优于隐式」；前端 `context_overrides` 通道作为唯一透传路径，移除 agent runtime 对基类字段的硬编码依赖；任何自定义上下文键（如 `project_id` / `geometry_data` / `audit_root` 等）都通过同一通道注入，符合 `RESERVED_CONTEXT_FIELDS` 的本意（仅过滤与显式 `cls(...)` 构造参数冲突的基类字段）。

### 关键设计决策：为什么删除 AgentContext.project_id

**原状态**：2026-06-30 新增 `project_id: Optional[int] = None` 字段，同时错误归入 `RESERVED_CONTEXT_FIELDS`，导致 `safe_overrides` 过滤永远剥除该键，前端透传失败。

**新设计（2026-07-01）**：
- `AgentContext` 不预声明任何"运行时可能用到的业务字段"（如 `project_id`）；
- 所有运行时业务上下文键均由前端通过 `context_overrides` 显式注入；
- TypedDict 运行时仍允许任意额外键（dict 不受 type 注解限制），所以工具侧 `runtime.context.get("project_id")` 仍能正常工作；
- `RESERVED_CONTEXT_FIELDS` 仅保留真正需要保护的"基类构造参数"（`session_id` 等），不再混入业务字段。

**好处**：
1. 任何新业务键（不限于 `project_id`）都可走同一透传通道，无需修改 AgentContext / RESERVED_CONTEXT_FIELDS / agent_config_service 三处。
2. 前端完全控制透传内容，后端不再做隐式合并/兜底，链路更清晰。
3. 避免"基类字段 + 保留字段集合"双源同步维护的不一致风险（如本次 RESERVED_CONTEXT_FIELDS 与 AgentContext 的 project_id 不一致 bug）。

## 环境变量

- `AUTH_STORAGE_MODE` — 存储模式（postgres/memory）
- `DATABASE_URL` — PostgreSQL 连接字符串
- `PORTAL_REFRESH_TOKEN_TTL_SECONDS` — 门户子 refresh_token 有效期（秒），默认 86400 = 24 小时
- `VITE_API_TARGET` — 前端 Vite 代理目标地址（开发用），默认 `http://localhost:8001`
- ~~`VITE_PORTAL_NAV_CONFIG`~~ — 已废弃，门户导航配置迁移到 `public/app-config.json` 运行时配置
- `AGENT_CHAT_MAX_CONCURRENCY` — Agent 聊天接口最大并发数，超出时进入内存队列等待，默认 3
- **沙箱容器化配置**：
  - `SANDBOX_DOCKER_MODE` — 部署模式 `local` / `socket` / `dind` / `k8s`，默认 `local`
  - `SANDBOX_DOCKER_HOST` — Docker daemon URL，socket 模式必填
  - `SANDBOX_IMAGE` — 沙箱镜像，默认 `python:3.12-alpine`
  - `SANDBOX_MAX_MEMORY_MB` — 容器内存限制（MB），默认 512，下限 64
  - `SANDBOX_MAX_CPU_PERCENT` — 容器 CPU 限制（百分比），默认 100，范围 10-100
  - `SANDBOX_NETWORK_ENABLED` — 是否启用容器网络，默认 `false`
  - `SANDBOX_DEFAULT_TIMEOUT` — 命令默认超时（秒），默认 60
  - `SANDBOX_CONTAINER_WORKSPACE` — 容器内工作目录，默认 `/workspace`
  - `SANDBOX_HOST_WORKSPACE_PREFIX` — 宿主机视角工作目录前缀，socket 模式必填
  - `SANDBOX_K8S_NAMESPACE` — K8s 模式命名空间（占位）
  - `SANDBOX_FALLBACK_TO_LOCAL` — Docker 不可用时是否降级到本地文件系统执行，默认 `false`
- **文件解析（远程解析 + 大小限制）**：
  - `FILE_PARSER_ENABLED` — 是否启用远程解析（`true`/`false`），默认 `false`
  - `FILE_PARSER_SERVER_URL` — 远程解析服务地址，默认 `http://mineru-openai-server:30000`
  - `FILE_PARSER_OUTPUT_FORMAT` — 输出格式 `json` 或 `md`，默认 `json`
  - `FILE_PARSER_API_URL` — 远程解析 API 地址
  - `FILE_PARSER_MAX_RETRIES` — 最大轮询重试次数，默认 60
  - `FILE_PARSER_POLL_INTERVAL` — 轮询间隔（秒），默认 2.0
  - `FILE_PARSER_TIMEOUT` — 请求超时时间（秒），默认 300
  - `FILE_PARSER_MAX_FILE_SIZE` — 上传文件最大大小（**MB，整数**，下限 1），默认 `3`。2026-07-13 新增：前后端共用上传大小上限，原前端硬编码 50MB 已被替换为读取本配置；后端在 `/api/core/uploadfile` 与 `/api/core/merge-chunks` 内做 413 校验；前端通过 `GET /api/core/upload-config` 拉取后做客户端预校验
- **MFA 双因素认证（2026-08-08 新增）**：
  - `MFA_SECRET_KEY` — 浏览器 `/login` TOTP 双因素认证 Fernet 对称密钥，须由 `Fernet.generate_key()` 生成（44 字节 url-safe base64）。缺失或非法时 `lifespan` 无法初始化 `MfaService`，登录 fail-closed 返回 503。
- 其他 LLM API Key 等

## 等保三级安全编码规范

`AGENTS.md` 已纳入 GB/T 22239-2019 应用层面等保三级安全编码规范，作为项目级顶层设计约束。规范覆盖以下 8 个维度，详细规则见 [`AGENTS.md`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/AGENTS.md) 末尾章节：

1. **身份鉴别**：口令复杂度、登录失败锁定、会话超时、双因素认证、HTTPS 传输、用户唯一标识。
2. **访问控制**：最小权限、权限分离、默认拒绝、敏感操作二次授权、`OwnershipScope` 数据层隔离、菜单 ACL 与端点粒度对齐。
3. **安全审计**：统一 `LogService` 入口、审计字段完整、留存≥6 个月、防篡改、命令与凭据脱敏。
4. **入侵防范**：输入白名单校验、XSS/CSP 防护、参数化查询、命令注入防护、文件上传安全、漏洞管理、统一错误响应。
5. **恶意代码防范**：用户内容过滤、前端 SRI、依赖安全审计。
6. **数据保密性**：全站 HTTPS/HSTS、敏感数据加密存储、密钥独立管理、Token 与 Cookie 安全。
7. **剩余信息保护**：服务端会话失效、客户端缓存清理、内存敏感数据清理。
8. **个人信息保护**：最小必要、授权同意、禁止对外提供、用户查询/更正/删除、日志脱敏。

补充检查清单见 [`memory/security-compliance.md`](file:///e:/laboratory/AI/Agents/feature-agent-core-ref/memory/security-compliance.md)。

## 本地 HTTPS 测试（nginx/，2026-08-08 新增）

> 无 Docker 场景下测试 HTTPS 传输 / HSTS / 等保三级 TLS 配置的本地入口。

- **位置**：`nginx/`（Windows nginx 1.30.4 独立发行版，含 `nginx.exe` / `conf/` / `html/` / `logs/`）。
- **入口**：`nginx/conf/nginx.conf`（覆盖默认配置；与 `web/Agent/nginx.conf` 同步 + HTTPS 扩展）。
- **证书**：`nginx/conf/certs/localhost.pem` / `localhost-key.pem`，由 `nginx/mkcert.exe` 签发
  - 主题：`O=mkcert development certificate`、`Issuer=mkcert development CA`
  - 覆盖：`localhost` / `127.0.0.1` / `::1`，有效期 2 年（到 2028-11-08）
  - mkcert 已注册到 Windows 受信根（`mkcert -install`），浏览器访问 https://localhost:8443 显示绿锁无警告
- **端口**：HTTP `8080` → 301 跳转 HTTPS `8443`（避开 80/443 特权端口，本地非管理员即可启动）。
- **同步 `web/Agent/nginx.conf` 内容**：CSP / X-Frame-Options / X-Content-Type-Options / Referrer-Policy / gzip / SPA 路由（`/`、`/knowledge`、`/ops-console`、`/portal`、`/login`）/ **HTML 入口禁缓存（`location ~* \.html$`，`no-cache, no-store, must-revalidate`，块内需显式重复全部安全头；本地版不得保留 `location = /index.html` 精确匹配块——精确匹配优先级高于正则会绕过禁缓存）** / 静态资源 1y 缓存 / `/health`。
- **/api 代理**：直接写死 `http://127.0.0.1:8001`（Windows 无 envsubst，与 Docker 模板 `${VITE_API_TARGET}` 解耦）；保留 SSE 流式（`proxy_buffering off`）+ WebSocket Upgrade + 300s 读超时。
- **TLS 加固（等保三级）**：
  - `ssl_protocols TLSv1.2 TLSv1.3`
  - `ssl_ciphers HIGH:!aNULL:!MD5:!DES:!3DES:!RC4`
  - `ssl_prefer_server_ciphers on`
  - HSTS `max-age=31536000; includeSubDomains`（`always` 标记）
- **Windows 差异（与 Docker 版 nginx.conf）**：移除 `resolver 127.0.0.11`（Docker DNS）；`root` 改用正斜杠绝对路径 `E:/laboratory/AI/Agents/feature-agent-core-ref/web/Agent/dist`（零拷贝，前端重新构建立即生效）；`ssl_certificate` 改用正斜杠绝对路径。
- **`web/Agent/nginx.conf` 保持 HTTP**（Docker 版不提供 TLS；HTTPS 仅在本地测试场景），但禁缓存 / CSP / SPA 路由等通用块两版保持同步。

### 启动 / 停止 / 验证

```powershell
# 前置：mkcert CA 已安装（一次性）
.\nginx\mkcert.exe -install

# 启动（任意目录都可）
Start-Process -FilePath ".\nginx\nginx.exe" `
    -ArgumentList @("-p", "E:\laboratory\AI\Agents\feature-agent-core-ref\nginx", "-c", "conf\nginx.conf") `
    -WindowStyle Hidden

# 语法检查
.\nginx\nginx.exe -t -p "E:\laboratory\AI\Agents\feature-agent-core-ref\nginx" -c "conf\nginx.conf"

# 停止
.\nginx\nginx.exe -s stop -p "E:\laboratory\AI\Agents\feature-agent-core-ref\nginx" -c "conf\nginx.conf"

# 验证（监听 + HTTPS 绿锁）
curl.exe -I -k https://localhost:8443/
curl.exe -k https://localhost:8443/health
```

### 登录 Cookie 安全（推荐）

- 默认 `AUTH_COOKIE_SECURE=false`，HTTPS 下 Cookie 不带 Secure 也能正常发送。
- 本地 HTTPS 测试建议在 `.env` 设 `AUTH_COOKIE_SECURE=true`，让 Cookie 带 Secure 标记（更贴合等保三级数据保密性）。

### HTTPS 模块加载踩坑记录（2026-08-09）

> **症状**：浏览器访问 `https://localhost:8443/` 一直转圈进不去；nginx access.log 只有 `GET /` + `GET /app-config.json` + `POST /api/auth/refresh`，**完全没有 `/assets/main-*.js` / `auth-*.js` 等静态资源请求，也没有 `/api/auth/validate`**。F12 → Network 显示 main bundle 行**根本不发起**（不是 200/404，是没出现）。F12 → Console 报 `Access to script at '…' from origin 'https://localhost:8443' has been blocked by CORS policy: No 'Access-Control-Allow-Origin' header is present.`。

#### 根因

Vite build 产物的 `index.html` 中所有模块脚本都带 `crossorigin=""` 属性：

```html
<script type="module" crossorigin src="/assets/main-*.js"></script>
<link rel="modulepreload" crossorigin href="/assets/auth-*.js">
```

**Chromium 在 HTTPS 上下文下对带 `crossorigin` 的 module 强制 CORS 校验（即使同源也要 ACAO 响应头）**；HTTP 下才放宽。Docker 版 `web/Agent/nginx.conf` 走 80 端口 HTTP，所以历史一直没暴露。

#### 修复契约

1. **必须给所有 JS / CSS / 字体等静态资源显式下发 `Access-Control-Allow-Origin`**（HTTPS 测试场景用 `https://$host:$server_port`；生产环境走真实 origin）。仅 server 级 `add_header` 不够，**任何 `location` 内出现 `add_header` 都会清空父级所有 `add_header`** —— 必须把 ACAO / CSP / HSTS / X-Frame-Options / X-Content-Type-Options / Referrer-Policy **在该 location 内整块显式重复**（参见 `### HTML 入口禁缓存 / 静态资源 1y 缓存` 章节）。
2. **修复后必须让用户硬刷新**（`Ctrl+Shift+R`）：Chromium 对 CORS 失败有 network-level negative cache，普通 reload 不会重试该资源，DevTools Network 也不显示新请求，表现为「我改了配置但用户还说没生效」。标准动作见 `AGENTS.md` R12。
3. **HTTP 与 HTTPS 的浏览器安全约束不同**：CORS 同源严格度 / HSTS preload / Mixed Content / crossorigin module 加载要求 ACAO 等**只对 HTTPS 生效**。Docker HTTP 下能跑不代表 HTTPS 下能跑（违反调试元认知 R5）。新增 HTTPS / 跨协议入口时，**第一时间让用户开 DevTools 取证**而不是自己反复 reload nginx（违反 R11）。

#### 诊断反向证据

- 关键反向证据：`nginx/conf/nginx.conf` 在改 ACAO 之前对 `curl -I https://localhost:8443/assets/main-*.js` 返回 200（curl 不走 crossorigin 流程，看不到 CORS），但浏览器 DevTools Network 面板根本**没有这条请求**。**「curl 200 + 浏览器不发起请求」**就是 HTTPS 下 CORS 失败的反向信号。
- 错误日志侧记：nginx `error.log` 不会记录 CORS 失败（这是浏览器侧拒绝，到不了 nginx），所以只看 nginx 日志看不到，必须看浏览器 Console。

### 本地进程拓扑与 checkpointer 行为契约

- **端口配置点位清单**（三处必须协调一致，改任一处须同步核对）：① `nginx/conf/nginx.conf` → `location /api` 的 `proxy_pass http://127.0.0.1:8001`；② `web/Agent/vite.config.js` → `VITE_API_TARGET` 默认值 `http://localhost:8001`（可被环境变量覆盖）；③ 后端启动命令 `uvicorn app.main:app --port <port>`。另存在 `:9001` IDE debugpy `--reload` 调试实例。
- **双后端进程并存**：`:8001`（`--host 127.0.0.1`，手动启动，是 nginx HTTPS `/api` 与 vite dev 默认代理目标）与 `:9001`（`--host 0.0.0.0 --reload`，IDE debugpy 调试实例）。vite dev（`:5173`）代理目标由 `VITE_API_TARGET` 决定（`vite.config.js` 默认 `http://localhost:8001`）。两个入口行为不一致时，先 `netstat -ano | grep LISTENING` 确认各端口归属进程，再以各自日志中的请求记录判定请求实际命中哪个后端。
- **重启后端前必须确认目标进程 PID**：仅重启其中一个进程不影响另一个；端口被旧进程占用时新进程无法接管。
- **checkpointer 回退契约**（`app/shared/utils/memory/checkpoint.py::get_async_checkpointer`）：`DatabasePool.is_enabled()` 为 True 但 PG 初始化失败（连接超时 / 驱动缺失等）时**回退 MemorySaver**；内存模式下仅能读写当前进程生命周期内的 checkpoint——历史会话（PG 中）读不到、新建会话进程重启即丢。启动正常的标志是日志出现 `使用 PostgreSQL 持久化模式（AsyncPostgresSaver）`；出现 `回退到内存模式` 即处于降级状态。
- **历史消息读取链路**：`GET /api/session/{id}/messages` 优先 `map_agent.graph.aget_state(thread_id=session_id)`，仅当抛异常时才回退 `checkpointer.aget`；`aget_state` 成功但 messages 为空时**不再回退**，直接返回空列表。

