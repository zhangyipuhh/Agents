# mcpClient

```
 _____ _____ ____  __  __   ___ ____   ____
|_   _| ____|  _ \|  \/  | |_ _|  _ \ / ___|
  | | |  _| | |_) | |\/| |  | || |_) | |
  | | | |___|  _ <| |  | |  | ||  _ <| |___
  |_| |_____|_| \_\_|  |_| |___|_| \_\\____|
```

MCP 中转站服务。

## 安装

### 环境要求
- Python 3.10+
- Node.js 18+（如需使用 stdio 类型的 MCP 服务器）

### 安装步骤

```bash
# 1. 进入项目目录
cd mcpClient

# 2. 创建虚拟环境（推荐）
python -m venv venv

# 3. 激活虚拟环境
# Windows:
venv\Scripts\activate
# macOS/Linux:
source venv/bin/activate

# 4. 安装依赖
pip install -e ../app/  # 安装 app 包
pip install -e .         # 通过 pyproject.toml 安装 mcpClient 及全部依赖
```

> 说明：`pip install -e .` 会读取当前目录的 `pyproject.toml`，自动安装 `dependencies` 中列出的所有依赖包。如需同时安装开发依赖，使用 `pip install -e ".[dev]"`。

## 快速开始

```bash
# 配置 .env 文件
cp .env.example .env

# 启动服务
python -m mcpClient.main
```

## 安装组件（配置 MCP 服务器）

在 `config.yaml` 中添加 MCP 服务器配置即可安装组件。支持以下四种类型：

### 1. stdio 类型（本地命令）

通过命令行启动的 MCP 服务器，需先安装对应运行时（如 Node.js、Python、Docker）。

```yaml
mcp_servers:
  filesystem:
    type: stdio
    command: "npx"           # 或 "uvx", "docker", "python" 等
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    env:                      # 可选：环境变量
      HOME: "/home/user"
    timeout: 120
```

常用 stdio 组件安装示例：

```bash
# 文件系统组件（需 Node.js）
npx -y @modelcontextprotocol/server-filesystem /tmp

# GitHub 组件（需 Node.js）
npx -y @modelcontextprotocol/server-github

# PostgreSQL 组件（需 Node.js）
npx -y @modelcontextprotocol/server-postgres postgresql://localhost/mydb

# Python 组件（需 uv/uvx）
uvx mcp-server-sqlite --db-path /path/to/db.sqlite
```

### 2. http / streamable_http 类型（HTTP 远程服务）

连接已部署的 HTTP 接口型 MCP 服务器。

```yaml
mcp_servers:
  github:
    type: http
    url: "https://api.github.com/mcp"
    headers:
      Authorization: "Bearer ${GITHUB_TOKEN}"
    timeout: 120
```

### 3. sse 类型（Server-Sent Events）

连接 SSE 流式接口的 MCP 服务器。

```yaml
mcp_servers:
  sse-server:
    type: sse
    url: "http://localhost:3000/sse"
    headers:
      X-API-Key: "${API_KEY}"
    timeout: 60
    sse_read_timeout: 300
```

### 4. websocket 类型

连接 WebSocket 接口的 MCP 服务器。

```yaml
mcp_servers:
  ws-server:
    type: websocket
    url: "ws://localhost:3001/ws"
    headers:
      Authorization: "Bearer ${TOKEN}"
    timeout: 60
```

### 配置说明

- `${ENV_VAR}` 支持环境变量插值，需在 `.env` 文件中定义对应变量
- `timeout`：连接超时时间（秒）
- `sse_read_timeout`：SSE 读取超时时间（秒），sse 类型专用
- `env`：stdio 类型专用，传递给子进程的环境变量

完整配置示例：

```yaml
mcp_servers:
  filesystem:
    type: stdio
    command: "npx"
    args: ["-y", "@modelcontextprotocol/server-filesystem", "/tmp"]
    timeout: 120

  github:
    type: http
    url: "https://api.github.com/mcp"
    headers:
      Authorization: "Bearer ${GITHUB_TOKEN}"
    timeout: 120
```
