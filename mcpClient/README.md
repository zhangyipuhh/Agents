# mcpClient

```
 _____ _____ ____  __  __   ___ ____   ____
|_   _| ____|  _ \|  \/  | |_ _|  _ \ / ___|
  | | |  _| | |_) | |\/| |  | || |_) | |
  | | | |___|  _ <| |  | |  | ||  _ <| |___
  |_| |_____|_| \_\_|  |_| |___|_| \_\\____|
```

MCP 中转站服务。

## 快速开始

```bash
# 安装依赖
pip install -e ../app/  # 安装 app 包
pip install -r requirements.txt

# 配置 .env 文件
cp .env.example .env

# 启动服务
python -m mcpClient.main
```

## 配置

编辑 `config.yaml` 配置 MCP 服务器：

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
