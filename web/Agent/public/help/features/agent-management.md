# 智能体管理

智能体管理模块负责**注册 / 配置 / 启停**所有 Agent。Agent 是 LangGraph + LangChain 1.x 的核心抽象，每个 Agent 包含 system_prompt、tool_bindings、skill_bindings 三层。

## 前置条件

- **admin 角色**（路由 `require_admin` router 级）
- **AGENTS.md 文件必须先存在**（项目根 `agents/<name>/AGENTS.md`，如 `agents/project/AGENTS.md`）
- 内容包含 system prompt + 工具约束说明（参考已有 11 个内置 Agent）

## 新增智能体

### API 端点
`POST /api/admin/agents`（`app/routers/agent_admin_router.py::create_agent`）

### 请求体字段

| 字段 | 必填 | 取值 | 说明 |
|---|---|---|---|
| `name` | ✓ | 正则 `^[a-z0-9_]+$`，3~50 字符 | 智能体唯一标识 |
| `display_name` | ✓ | 1~200 字符 | 展示名称（中文） |
| `description` | | ≤ 500 字符 | 智能体描述 |
| `agents_md_path` | ✓ | 1~500 字符，路径必须真实存在 | AGENTS.md 文件绝对路径 |
| `config_schema` | | 嵌套 dict | root / state_fields / context_fields 三层 |
| `mcp_tags` | | List[str] | MCP 标签列表（用于匹配 server） |
| `enabled` | | bool，默认 true | 是否启用 |
| `sort_order` | | int，默认 0 | 排序权重 |

### 校验逻辑
- name 必须符合正则 `^[a-z0-9_]+$`
- name 必须唯一（`check_name_unique` 预校验）
- `agents_md_path` 必须真实存在（`Path.is_file()`）
- `config_schema` 必须能通过 `parse_config_schema` 解析

### 设置后效果

| 层级 | 效果 |
|---|---|
| DB | `agents` 表新增行（含 `name` / `display_name` / `description` / `config_schema` JSONB / `tool_bindings` JSONB / `mcp_tags` JSONB / `enabled` / `sort_order`） |
| 内存 | `AgentConfigService._cache` 进程内缓存自动刷新 |
| 路由 | `GET /api/admin/agents` 列表立即包含新 Agent |
| 用户可见 | 在「权限管理 → 智能体访问」被授权后，普通用户登录即可看到 |

## 工具绑定

### 数据结构

`agents.tool_bindings` JSONB 字段：

```json
[
  {
    "tool_name": "get_current_time",
    "tool_type": "builtin",
    "enabled": true,
    "sort_order": 0
  },
  {
    "tool_name": "amap.search",
    "tool_type": "mcp",
    "enabled": true,
    "sort_order": 1
  },
  {
    "tool_name": "project-doc-hub",
    "tool_type": "skill",
    "enabled": true,
    "sort_order": 2
  }
]
```

### 字段语义

| 字段 | 取值 | 说明 |
|---|---|---|
| `tool_name` | 字符串 | builtin=函数名（如 `get_current_time`）/ mcp=`server.method` 复合名 / skill=技能名 |
| `tool_type` | `builtin` / `mcp` / `skill` | 工具来源类型 |
| `enabled` | bool | 是否启用该绑定 |
| `sort_order` | int | 排序权重（越小越靠前） |

### 绑定生效

- **下次 chat 时** `AgentConfigService._load_tools` 延迟加载（高优先级）
- 写 DB 后 `service.update_tool_bindings` 自动 `_refresh_cache(name)` 把 `tools` 置 None
- 不会中断已在执行的会话，但**新消息**会使用新工具集

### MCP 绑定额外条件（2026-09-14 起）

> ⚠️ **`mcp_server_configs.enabled` 是 MCP 工具加载的唯一真相源**。

- `tool_type=mcp` 条目**仅在** `mcp_server_configs.enabled=true` 时生效
- admin 选了 binding 但 server 未启用 → **不是 bug**，按设计意图
- 生效需 admin 在「MCP 服务器管理」同时把对应 server 启用

## 技能绑定

`agents.skill_bindings` JSONB 字段：

```json
[
  {
    "skill_name": "project-doc-hub",
    "enabled": true,
    "sort_order": 0
  }
]
```

### 技能注册表位置
- `app/skills/<skill-name>/SKILL.md`（项目级全局 skill）
- `app/features/<agent>/skills/<skill-name>/SKILL.md`（子智能体维度专属 skill）

### 加载规则
- bootstrap 优先级链（从高到低）：
  1. `app/features/<agent>/config/bootstrap.md`（子智能体）
  2. `settings.skills_bootstrap_path`（用户自定义全局）
  3. `app/core/skills/bootstrap.md`（系统默认）
  4. 代码内置 `_FALLBACK_TOOL_MAPPING`（最后兜底）

## 启用 / 禁用

### API
- `PUT /api/admin/agents/{name}/enabled` body `{"enabled": true/false}`

### 效果
- `agents.enabled` 字段更新
- `AgentConfigService._cache` 同步刷新
- 禁用的 Agent 在主会话下拉列表中**不显示**
- 历史会话中的该 Agent 消息仍可恢复，但不计入 allowed_agents

## 删除智能体

### API
`DELETE /api/admin/agents/{name}`（返回 204）

### 效果
- 级联清理 `tool_bindings` / `skill_bindings`（**仅清空 JSONB，不删除 AGENTS.md 文件**）
- 保留历史会话（消息元数据不丢，但 agent_name 仍指向已删除的 name）

> ⚠️ **不可恢复**。删除前请确认 AGENTS.md 文件已备份。

## config_schema 三层结构

| 层级 | 路径 | 说明 |
|---|---|---|
| root | `config_schema.*` | AgentConfig 字段覆盖（如 `temperature` / `max_tokens` / `parallel_tool_calls`） |
| state_fields | `config_schema.state_fields.*` | AgentState 自定义字段（运行时持久化到 checkpoint） |
| context_fields | `config_schema.context_fields.*` | AgentContext 自定义字段（仅运行时，不持久化） |

### 字段定义语法

```json
{
  "temperature": {"type": "float", "default": 0.7},
  "max_tokens": {"type": "int", "default": 4096},
  "parallel_tool_calls": {"type": "bool", "default": null},
  "context_fields": {
    "user_role":": {"type": "str", "default": ""},
    "project_id": {"type": "Optional[str]", "default": null}
  }
}
```

### 字段模板来源

`GET /api/admin/agents/field-templates?section=root|state_fields|context_fields` 返回模板列表（含 `field_name` / `type` / `default`），供前端「添加字段」弹窗使用。

## 常见问题

### name 校验失败？
**错误文案**：`name must match regex ^[a-z0-9_]+$`

**修复**：仅允许小写字母 + 数字 + 下划线，长度 3~50。

### AGENTS.md 路径不存在？
**错误文案**：`FileNotFoundError: AGENTS.md not found`

**修复**：先在 `agents/<name>/AGENTS.md` 创建文件，确保 `Path.is_file()` 返回 True。

### config_schema 字段类型错误？
**错误文案**：`ValueError: invalid field type`

**修复**：参考 `app/shared/utils/agent/dynamic_schema.py::RESERVED_CONFIG_FIELDS` 与字段模板。

### MCP 工具不生效？
**排查**：
1. 检查 `mcp_server_configs.enabled=true`
2. 检查 binding 中 `tool_name` 格式为 `server.method`
3. 重启服务（lifespan 加载）

### 修改 config_schema 后没生效？
**排查**：
- config_schema 变更下次 chat 才生效
- 已在执行的会话需要新开会话

## 相关章节

- [权限管理](/help/features/permission-management) — 智能体 ACL
- [MCP 服务器管理](/help/features/mcp-servers) — MCP 工具来源
- [基本设置 → LLM 模型](/help/features/basic-settings#llm-模型) — 模型配置