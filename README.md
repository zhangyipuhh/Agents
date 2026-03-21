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

```
Agents/
├── app/
│   ├── MainServer.py          # 应用入口，FastAPI 服务配置
│   ├── agents/                 # 智能体模块
│   │   ├── Mainagent.py       # 主智能体
│   │   ├── agent/             # 智能体基础组件
│   │   ├── config/            # 配置管理
│   │   ├── llmcalls/          # LLM 调用封装
│   │   ├── states/            # 状态管理
│   │   ├── tools/             # 工具集
│   │   ├── continues/         # 条件判断逻辑
│   │   └── subgraphs/         # 子智能体
│   │       ├── ApprovalAgent/ # 审批智能体
│   │       ├── Doc_Agent/     # 文档处理智能体
│   │       ├── audit_contract_clause/ # 合同条款审计
│   │       ├── audit_document/ # 文档审计
│   │       ├── readFile/      # 文件读取
│   │       └── search_database/ # 数据库搜索
│   ├── routers/               # API 路由
│   │   ├── agent_router.py    # 智能体 API
│   │   ├── auth_router.py     # 认证 API
│   │   ├── contract_router.py # 合同 API
│   │   ├── file_router.py     # 文件 API
│   │   └── session_router.py  # 会话 API
│   ├── utils/                 # 工具模块
│   │   ├── auth/              # 认证工具
│   │   ├── files/             # 文件处理工具
│   │   ├── memory/            # 记忆存储
│   │   └── Session/           # 会话缓存
│   ├── html/                  # 前端页面
│   └── test/                  # 测试文件
└── requirements.txt           # 依赖清单
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

在 `app/agents/config/config.py` 中配置 LLM 参数：

```python
LLM_CONFIG = {
    "model_type": "openai",      # 可选: openai, deepseek, ollama
    "model_name": "gpt-4",
    "api_key": "your-api-key",
    "base_url": "https://api.openai.com/v1"
}
```

### 启动服务

```bash
# 直接运行
python -m app.MainServer

# 或使用 uvicorn
uvicorn app.MainServer:app --host 0.0.0.0 --port 8000
```

服务启动后访问：
- API 文档: http://localhost:8000/docs
- ReDoc 文档: http://localhost:8000/redoc

## 核心模块

### 主智能体 (MainAgent)

主智能体是系统的核心协调者，负责：
- 构建和管理 LangGraph 状态图工作流
- 绑定和管理工具集
- 协调子智能体的调用
- 处理流式响应输出

```python
from app.agents.Mainagent import MainAgent

# 创建智能体实例
agent = await MainAgent.create()

# 执行任务
result = agent.CreateAgent()
```

### 子智能体

| 智能体 | 功能描述 |
|--------|----------|
| ApprovalAgent | 审批流程处理，支持多轮对话和状态管理 |
| DocAgent | 文档处理，支持多种文档格式的解析和理解 |
| HtAgent | 合同审批，专门处理自然资源业务合同审批 |
| audit_document | 文档审计，检查文档合规性 |
| readFile | 文件读取，支持 PDF/Word/CSV/JSON 等格式 |
| search_database | 数据库搜索，提供数据查询能力 |

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

1. 在 `app/agents/subgraphs/` 创建智能体目录
2. 实现智能体类，继承基础配置
3. 定义工具和状态
4. 在 `MainAgent` 中注册子图

### 添加新工具

1. 在 `app/agents/tools/` 中定义工具函数
2. 使用 `@tool` 装饰器声明工具
3. 在 `MainTools` 类中注册工具

```python
from langchain.tools import tool

@tool
def my_tool(param: str) -> str:
    """工具描述"""
    return result
```

### 配置管理

配置文件位于 `app/agents/config/config.py`，支持：
- LLM 模型配置
- 提示词模板配置
- 工具参数配置

## 作者

张镒谱

## 许可证

MIT License
