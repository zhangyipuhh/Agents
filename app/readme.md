# App 文件夹说明

## 项目概述
本文件夹包含智能体服务应用程序的核心代码和资源文件。

## 程序入口
- **main.py**：应用程序的启动入口，负责初始化 FastAPI 应用、注册路由并启动服务器

## 目录结构

### core/
- **用途**：核心框架模块
- **说明**：包含智能体框架、配置管理、LLM调用、工具系统等核心基础设施

#### core/agent/
- 智能体核心模块，包含 AgentConfig、AgentContext、agent.py 等

#### core/config/
- 配置管理模块，包含 config.py、settings.py 等

#### core/llmcalls/
- LLM 调用模块，支持多种大语言模型
- 支持：anthropic、deepseek、ollama、openai 等

#### core/tools/
- 工具系统核心模块
- 包含 BaseTools、mcp_registry、mcp_tool_adapter、mcp_wrapper 等
- 支持 MCP (Model Context Protocol) 工具集成

#### core/dependencies.py
- 依赖注入模块

#### core/server.py
- FastAPI 服务器创建模块

### shared/
- **用途**：共享模块，为各个功能模块提供通用支持
- **说明**：包含路由、工具和通用工具类

#### shared/routers/
- 公共路由模块
- auth_router.py：认证路由
- file_router.py：文件操作路由
- session_router.py：会话管理路由

#### shared/tools/mcp/
- MCP 配置文件目录
- config.yaml.example：MCP 配置示例

#### shared/utils/
- 通用工具类集合

##### shared/utils/Session/
- 会话管理工具，包含 SessionCache.py

##### shared/utils/auth/
- 认证相关工具
- Safety.py：安全相关工具
- createpassword.py：密码创建工具

##### shared/utils/files/
- 文件处理工具集合
- DocumentLoader.py：文档加载器
- loader/：文件加载器子模块
  - CSVLoader.py
  - JSONLoader.py
  - MarkdownLoader.py
  - PDFLoader.py
  - TextLoader.py
  - WebLoader.py
  - WordLoader.py
- fileTransfer.py：文件传输工具
- file_upload_handler.py：文件上传处理器
- pdfToImage.py：PDF 转图片工具
- pdf_untils.py：PDF 工具
- web_untils.py：网页工具
- word_untils.py：Word 工具

##### shared/utils/memory/
- 记忆存储模块
- checkpoint.py：检查点管理
- document_memory_store.py：文档记忆存储
- key_value_memory_store.py：键值记忆存储

##### shared/utils/store_schema.py
- 存储模式定义

### features/
- **用途**：功能智能体模块
- **说明**：包含各种业务领域的智能体实现
- **DevOps 智能体已于 2026-07-15 下线**：SSH 工具集迁至 `app/shared/tools/skills/devops/`，配置管理迁至 `app/shared/utils/devops_server_service.py`，admin 接口由 `app/routers/devops_server_admin_router.py` 提供（`/api/admin/devops-servers` 与 `/api/admin/devops-servers/scan`）。

#### features/Tagent/
- T 智能体（基础文本智能体）

#### features/audit_document_agent/
- 文档审核智能体
- 用于文档内容和合规性审核

#### features/contract_approval_agent/
- 合同审批智能体
- 合同审批流程管理

#### features/contract_document_agent/
- 合同文档智能体
- 合同文档处理和生成

#### features/contract_host_agent/
- 合同主持智能体
- 包含 HtAgent.py 和 contract_router

#### features/map_agent/
- 地图智能体
- 提供地图相关服务

#### features/search_database/
- 数据库搜索智能体

#### features/stream_Agent/
- 流式智能体
- 支持流式响应和处理

### test/
- **用途**：测试文件存储目录
- **说明**：存放功能测试和智能体测试相关的代码文件