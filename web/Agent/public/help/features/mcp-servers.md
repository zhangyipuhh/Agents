# MCP 服务器管理

MCP（Model Context Protocol）服务器管理模块负责**配置第三方 MCP 服务**与**在智能体中启用 MCP 工具**。MCP 是 Anthropic 提出的开放标准，兼容 OpenAI 风格的 `tool_calls` 调用。

## 前置条件

- **MCP server 进程运行**（stdio 模式）或 **MCP server 服务地址可达**（sse 模式）
- 已在「智能体管理」添加 binding（`tool_type=mcp`）
- admin 角色（路由 `require_admin` router 级，2026-09-12 渗透整改）
- MCP 版本契约：`mcp==1.27.2`（详见 `requirements.txt` + `mcpClient/pyproject.toml`）

## MCP 版本契约（2026-09-11 校准）

| 项 | 版本 | 说明 |
|---|---|---|
| `mcp` | `==1.27.2` | Python SDK 锁版本 |
| `langchain-mcp-adapters` | `==0.3.2` | LangChain 适配器 |
| Python | `3.12.7` | 项目主版本 |

> ⚠️ **禁止 mcp 2.x**：其 `client.experimental` 顶层 import 因 tasks 扩展 SEP-2663 未完成，`mcp.types` 不导出 `TASK_STATUS_COMPLETED` 等常量，抛 `ImportError`。

## 架构

### 表设计

- `mcp_server_configs`：MCP 服务器配置（name / enabled / transport / command / args / url）
- `mcp_server_methods`：MCP 方法列表（server_name / method_name / display_name / description / enabled）

### 运行时

- `MCPToolsRegistry` 单例（`app/core/tools/mcp_registry.py`）
- 进程内缓存 `_server_configs`（lifespan 加载 + 热加载同步）
- `is_server_enabled(name)` 是**唯一真相源**

## 配置字段

### MCP server 配置

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `name` | ✓ | 字符串（唯一） | server 标识 |
| `display_name` | | 字符串 | 展示名（中文） |
| `enabled` | | bool，默认 true | **闸门**（2026-09-14 起为唯一真相源） |
| `transport` | | `stdio` / `sse` | 传输协议 |
| `command` | stdio 模式 | 字符串 | 启动命令（如 `python` / `node`） |
| `args` | stdio 模式 | JSON list | 命令参数 |
| `url` | sse 模式 | URL | SSE 服务地址 |

### MCP method 配置

每个 server 可有多个 method（每个 method 对应一个工具）：

| 字段 | 说明 |
|---|---|
| `server_name` | 关联 server |
| `method_name` | 方法名（用于 LLM 工具调用） |
| `display_name` | 展示名 |
| `description` | 方法描述 |
| `enabled` | 是否启用该方法 |

## 添加 MCP server

### API
`POST /api/admin/mcp/servers` body：

```json
{
  "name": "amap",
  "display_name": "高德地图",
  "enabled": true,
  "transport": "stdio",
  "command": "python",
  "args": ["-m", "amap_mcp_server"]
}
```

### 设置后效果

- `mcp_server_configs` 表新增行
- `MCPToolsRegistry._server_configs` 缓存更新（热加载）
- admin 可在 UI 看到「工具列表」

## 启用 / 禁用 server

### API
- `POST /api/admin/mcp/servers/{name}/toggle` body `{"enabled": true/false}`

### 效果（2026-09-14 关键修复）

> ✅ **`mcp_server_configs.enabled` 是 MCP 工具加载的**唯一真相源**。**

- 禁用 server 后，`AgentConfigService._load_tools` MCP 分支前置守卫拒绝加载
- 即使 `agents.tool_bindings` 中有 `tool_type=mcp` 条目，**system 禁用时不生效**
- admin 选了 binding 但没生效 → **不是 bug**，是按设计意图
- 生效需 admin 在「MCP 服务器管理」同时把对应 server 启用

## 启用 method

### API
- `POST /api/admin/mcp/servers/{name}/methods/{method}/toggle`
- `POST /api/admin/mcp/servers/{name}/methods/refresh`（重新发现 method 列表）

### 效果
- `mcp_server_methods.enabled` 字段更新
- LLM 工具列表立即生效

## 在智能体中绑定 MCP 工具

### 步骤

1. 进入「智能体管理」→ 选中目标智能体
2. 「工具绑定」标签 → 选择 `tool_type=mcp`
3. 选择 `server.method` 复合名（如 `amap.search`）
4. 点击「保存」

### 生效条件（必须全部满足）

1. ✅ MCP server `enabled=true`
2. ✅ MCP method `enabled=true`
3. ✅ `agents.tool_bindings` 含 `tool_type=mcp` 条目且 `enabled=true`

任一缺失则**不生效**。

## MCP 客户端调用流程

1. LLM 决策调 `amap.search(...)` 工具
2. LangChain `AgentConfigService._load_tools` 按 binding 加载
3. `_get_tools_with_server_async` 守卫：`is_server_enabled('amap')` → True
4. `streamable_http_client` 连接 MCP server
5. 调用 `search` method → 返回结果
6. 注入 ToolMessage 返回 LLM

## 常见问题

### MCP server 连接失败？
**错误文案**：`ConnectTimeout` 或 `connection refused`

**排查**：
1. 检查 `command` / `args`（stdio 模式）是否启动正常
2. 检查 `url`（sse 模式）是否可访问
3. 检查 MCP server 日志
4. 验证 MCP 版本契约（`mcp==1.27.2`）

### 工具调用后无响应？
**排查**：
1. 检查 method 是否 `enabled=true`
2. 检查 method name 是否拼写正确
3. 查看 LLM 日志是否有 `tool_call` 失败

### admin 选了 binding 但 server 没启用？
**排查**：
1. 进入「MCP 服务器管理」启用对应 server
2. 触发 `refresh_methods` 重新发现

### Docker 镜像 mcp 版本错配？
**错误文案**：`ImportError: cannot import name 'TASK_STATUS_COMPLETED' from 'mcp.types'`

**修复**：
- `requirements.txt` 锁 `mcp==1.27.2`（不要升 2.x）
- `mcpClient/pyproject.toml` 锁 `mcp>=1.24,<2.0`
- Docker 重建需 `docker builder prune -af` 清缓存

## 相关章节

- [智能体管理](/help/features/agent-management) — tool_bindings 配置
- [基本设置 → 网络与集成](/help/features/basic-settings#网络与集成) — MCP 相关配置
- [常见问题](/help/faq) — 高频问题