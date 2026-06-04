# AI Agents 智能体系统

基于 **LangGraph** 和 **LangChain** 框架开发的企业级智能体系统，采用 FastAPI 作为 Web 框架，支持多种 LLM 模型，提供合同审批、文档处理等专业智能体服务。

## 核心特性

- 🤖 **多智能体架构** - 主智能体协调多个专业子智能体协同工作
- 🔄 **流式响应** - 基于 SSE (Server-Sent Events) 的实时输出
- 💬 **多轮对话** - 支持会话状态管理和上下文记忆
- 📄 **文档处理** - 支持 PDF、Word、CSV、JSON 等多种格式
- 🔐 **安全认证** - JWT 认证 + Session 会话管理
- 🔌 **多 LLM 支持** - OpenAI、DeepSeek、Ollama 等多种模型

## 技术栈

| 类别 | 技术 |
|------|------|
| Web 框架 | FastAPI + Uvicorn |
| 智能体框架 | LangGraph + LangChain |
| LLM 支持 | OpenAI / DeepSeek / Ollama |
| 认证授权 | PyJWT |
| 文档处理 | PyMuPDF / python-docx / pypdf |
| 异步支持 | aiofiles |

## 项目结构

项目采用三层架构设计，清晰分离核心、功能和共享模块：

```
Agents/
├── .env.example              # 环境变量配置模板
├── .gitignore                # Git 忽略规则
├── readme.md                 # 项目说明文档
├── requirements.txt          # 依赖清单
├── app/
│   ├── core/                 # 核心模块
│   │   ├── agent/            # 智能体基础组件
│   │   │   ├── AgentConfig.py    # 智能体配置基类
│   │   │   ├── AgentContext.py   # 智能体上下文基类
│   │   │   └── agent.py          # 智能体基类
│   │   ├── config/           # 配置管理
│   │   │   ├── __init__.py
│   │   │   └── config.py         # 全局配置
│   │   ├── llmcalls/         # LLM 调用封装
│   │   │   ├── __init__.py
│   │   │   ├── deepseek.py       # DeepSeek 模型
│   │   │   ├── model_factory.py  # 模型工厂
│   │   │   ├── ollama.py         # Ollama 模型
│   │   │   └── openai.py         # OpenAI 模型
│   │   ├── tools/            # 基础工具
│   │   │   └── BaseTools.py      # 工具基类
│   │   └── server.py             # 服务配置
│   ├── features/             # 功能模块
│   │   ├── Tagent/           # T 智能体
│   │   │   ├── config/
│   │   │   │   ├── TagentConfig.py
│   │   │   │   └── TagentContext.py
│   │   │   ├── tools/
│   │   │   │   └── Ttools.py
│   │   │   └── Tagent.py
│   │   ├── audit_document_agent/ # 文档审计智能体
│   │   │   ├── tools/
│   │   │   │   └── tools.py
│   │   │   └── agent.py
│   │   ├── contract_approval_agent/ # 合同审批智能体
│   │   │   └── ApprovalAgent/
│   │   │       ├── config/
│   │   │       │   ├── ApprovalAgentConfig.py
│   │   │       │   ├── ApprovalAgentContext.py
│   │   │       │   └── config.py
│   │   │       ├── tools/
│   │   │       │   └── ApprovalAgentTools.py
│   │   │       └── ApprovalAgent.py
│   │   ├── contract_document_agent/ # 文档处理智能体
│   │   │   ├── config/
│   │   │   │   ├── DocAgentConfig.py
│   │   │   │   └── DocAgentContext.py
│   │   │   ├── tools/
│   │   │   │   └── DocTools.py
│   │   │   └── DocAgent.py
│   │   ├── contract_host_agent/ # 合同主机智能体
│   │   │   ├── config/
│   │   │   │   ├── HtAgentConfig.py
│   │   │   │   └── HtAgentContext.py
│   │   │   ├── tools/
│   │   │   │   └── HtTools.py
│   │   │   ├── HtAgent.py
│   │   │   ├── client.py
│   │   │   └── contract_router.py
│   │   ├── search_database/  # 数据库搜索智能体
│   │   │   └── agent.py
│   │   └── stream_Agent/     # 流式主智能体
│   │       ├── config/
│   │       │   ├── config.py
│   │       │   ├── maincontinues.py
│   │       │   └── mainstates.py
│   │       ├── tools/
│   │       │   ├── maintools.py
│   │       │   └── mcpservers.py
│   │       ├── Mainagent.py
│   │       └── agent_router.py
│   ├── shared/               # 共享模块
│   │   ├── routers/          # API 路由
│   │   │   ├── auth_router.py    # 认证 API
│   │   │   ├── file_router.py    # 文件 API
│   │   │   └── session_router.py # 会话 API
│   │   └── utils/            # 工具模块
│   │       ├── Session/
│   │       │   └── SessionCache.py
│   │       ├── auth/
│   │       │   ├── Safety.py
│   │       │   └── createpassword.py
│   │       ├── files/
│   │       │   ├── loader/       # 文档加载器
│   │       │   │   ├── CSVLoader.py
│   │       │   │   ├── JSONLoader.py
│   │       │   │   ├── MarkdownLoader.py
│   │       │   │   ├── PDFLoader.py
│   │       │   │   ├── TextLoader.py
│   │       │   │   ├── WebLoader.py
│   │       │   │   └── WordLoader.py
│   │       │   ├── DocumentLoader.py
│   │       │   ├── fileTransfer.py
│   │       │   ├── file_upload_handler.py
│   │       │   ├── pdfToImage.py
│   │       │   └── word_untils.py
│   │       └── memory/
│   │           ├── checkpoint.py
│   │           ├── document_memory_store.py
│   │           └── key_value_memory_store.py
│   ├── test/                 # 测试文件
│   ├── __init__.py
│   └── main.py               # 应用入口
└── web/
    └── html/                 # 前端页面
        ├── clnt/
        │   └── htagent.html
        └── Agent.html
```

## 快速开始

### 环境要求

- Python 3.10+
- pip 或 uv 包管理器

### 安装步骤

```bash
# 克隆项目
git clone <repository-url>
cd Agents

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate     # Windows

# 安装依赖
pip install -r requirements.txt
```

### 配置说明

项目使用环境变量管理敏感配置：

1. 复制配置模板：
```bash
cp .env.example .env
```

2. 编辑 `.env` 文件，填入真实配置：
```env
# 大模型配置
model_type="openai"
model_name="gpt-4"
model_api_key="your-api-key"
model_api_base="https://api.openai.com/v1"
model_temperature=0.2

# 视觉模型配置（可选）
model_type_vision="openai"
model_name_vision="gpt-4-vision"
model_api_key_vision="your-api-key"
model_api_base_vision="https://api.openai.com/v1"
```

| 配置项 | 说明 |
|--------|------|
| `model_type` | 模型类型：openai / deepseek / ollama |
| `model_name` | 模型名称 |
| `model_api_key` | API 密钥 |
| `model_api_base` | API 地址 |
| `is_multimodal` | 是否支持多模态 |

> ⚠️ **注意**：`.env` 文件包含敏感信息，已添加到 `.gitignore`，不会被提交到 Git。

### 启动服务

```bash
# 直接运行
python -m app.main

# 或使用 uvicorn
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- ReDoc 文档: http://localhost:8000/redoc

### Docker 部署

推荐使用 Docker Compose 进行容器化部署：

```bash
# 1. 复制环境变量配置模板
cp .env.example .env

# 2. 编辑 .env 文件，配置必要的环境变量
#    - model_api_key: 大模型 API 密钥
#    - DATABASE_URL: 数据库连接字符串（可选）

# 3. 拉取并启动所有服务
docker-compose up -d

# 4. 查看服务状态
docker-compose ps

# 5. 查看服务日志
docker-compose logs -f agents
```

服务启动后：
- 主应用 API：http://localhost:9001
- 前端页面：http://localhost:10000

### 停止服务

```bash
docker-compose down
```

### 开发模式说明

- `agents` 服务中的 `./app` 目录已挂载到容器，修改宿主机代码后立即生效
- 如需重新构建镜像： `docker-compose up -d --build`

## 核心模块

### 架构设计

项目采用三层架构：

| 层级 | 目录 | 职责 |
|------|------|------|
| 核心层 | `app/core/` | 智能体基类、配置管理、LLM 调用封装、基础工具 |
| 功能层 | `app/features/` | 各类专业智能体实现 |
| 共享层 | `app/shared/` | API 路由、工具函数、会话管理、文件处理 |

### 主智能体 (MainAgent)

主智能体位于 `app/features/stream_Agent/Mainagent.py`，是系统的核心协调者，负责：

- 构建和管理 LangGraph 状态图工作流
- 绑定和管理工具集
- 协调子智能体的调用
- 处理流式响应输出

```python
from app.features.stream_Agent.Mainagent import MainAgent

# 创建智能体实例
agent = await MainAgent.create()

# 执行任务
result = agent.CreateAgent()
```

### 子智能体

| 智能体 | 目录 | 功能描述 |
|--------|------|----------|
| ApprovalAgent | `features/contract_approval_agent/` | 审批流程处理，支持多轮对话和状态管理 |
| DocAgent | `features/contract_document_agent/` | 文档处理，支持多种文档格式的解析和理解 |
| HtAgent | `features/contract_host_agent/` | 合同审批，专门处理自然资源业务合同审批 |
| Tagent | `features/Tagent/` | 通用智能体，提供基础对话能力 |
| audit_document_agent | `features/audit_document_agent/` | 文档审计，检查文档合规性 |
| search_database | `features/search_database/` | 数据库搜索，提供数据查询能力 |

## API 文档

### 主要接口

| 方法 | 路径 | 描述 |
|------|------|------|
| POST | `/api/auth/login` | 用户登录认证 |
| POST | `/api/session/create` | 创建会话 |
| DELETE | `/api/session/delete` | 删除会话 |
| POST | `/api/file/upload` | 文件上传 |
| POST | `/api/contract/audit` | 合同审批 |

### 智能体对话接口

```bash
POST /api/agent/chat
Content-Type: application/json

{
    "message": "请帮我分析这份合同"
}
```

响应为 SSE 流式输出，包含智能体的思考过程和最终回答。

## 开发指南

### 添加新智能体

1. 在 `app/features/` 创建智能体目录
2. 实现智能体类，继承 `app/core/agent/` 中的基类
3. 在 `config/` 子目录定义配置和上下文
4. 在 `tools/` 子目录定义工具
5. 在 `MainAgent` 中注册子图

### 添加新工具

1. 在智能体的 `tools/` 目录中定义工具函数
2. 使用 `@tool` 装饰器声明工具
3. 继承 `BaseTools` 基类

```python
from langchain.tools import tool

@tool
def my_tool(param: str) -> str:
    """工具描述"""
    return result
```

### 配置管理

全局配置文件位于 `app/core/config/config.py`，支持：
- LLM 模型配置
- 提示词模板配置
- 工具参数配置

各智能体独立配置位于 `app/features/<agent_name>/config/` 目录。

## 作者

张镒谱

## 许可证

MIT License
