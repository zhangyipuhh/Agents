-- =============================================
-- Preview App 生产库建表脚本 v2（防御性升级版）
-- 适用: PostgreSQL 9.6+（ADD COLUMN IF NOT EXISTS 需要 9.6+）
-- 编码: UTF-8
-- 事务: 全部包裹，单次回滚
-- 幂等: 所有 DDL 使用 IF NOT EXISTS，可重复执行
-- v2 变更:
--   * 每张表都拆成 "CREATE 基础列 + ADD COLUMN 防御性补齐扩展列"
--   * 即使老版本代码建的表缺字段，跑一次脚本即可补齐
--   * 覆盖所有代码 INSERT/UPDATE/SELECT 用到的列
-- 来源: 汇总自 app 代码中所有 @register_schema 注册的表
--       + migrations 目录里的 portal_refresh_tokens 迁移
-- 注意: LangGraph checkpointer 表（checkpoints / checkpoint_writes 等）
--       会在应用首次启动时由 AsyncPostgresSaver.setup() 自动建，
--       本脚本不包含。
-- v3 变更（2026-06-24）:
--   * 合并原 fix_map_agent_schema.sql（map_agent state_schema 字段补全）
--   * 统一为"建表 + 数据修复"一体化脚本，运维只需 psql 跑一次即可
--   * 仍然保持全部幂等，重复执行不会破坏已有数据
-- =============================================

BEGIN;

-- ========== 1. users（auth 模块核心表）==========
CREATE TABLE IF NOT EXISTS users (
    id              SERIAL PRIMARY KEY,
    username        VARCHAR(100) UNIQUE NOT NULL,
    password_hash   VARCHAR(255) NOT NULL,
    role            VARCHAR(20)  DEFAULT 'user',
    created_at      TIMESTAMP    DEFAULT NOW(),
    updated_at      TIMESTAMP    DEFAULT NOW()
);
-- 防御性补齐：覆盖代码所有 INSERT/UPDATE/SELECT 用到的扩展列
-- 老版本表只建到 password_hash/role 就停了，跑这步把扩展列补齐
ALTER TABLE users ADD COLUMN IF NOT EXISTS real_name  VARCHAR(20)  DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS phone      VARCHAR(20)  DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS email      VARCHAR(100) DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS department VARCHAR(100) DEFAULT '';
ALTER TABLE users ADD COLUMN IF NOT EXISTS position   VARCHAR(100) DEFAULT '';

-- ========== 2. sessions（会话）==========
CREATE TABLE IF NOT EXISTS sessions (
    session_id      VARCHAR(100) PRIMARY KEY,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username        VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS title          VARCHAR(200) DEFAULT '新对话';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS last_active_at TIMESTAMP    DEFAULT NOW();
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS status         VARCHAR(20)  DEFAULT 'active';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_type     VARCHAR(50)  DEFAULT 'default';
-- 索引
CREATE INDEX IF NOT EXISTS idx_sessions_user_id             ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active_at      ON sessions(last_active_at);
CREATE INDEX IF NOT EXISTS idx_sessions_status              ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id_last_active ON sessions(user_id, last_active_at DESC);

-- ========== 3. conversation_records（对话记录）==========
CREATE TABLE IF NOT EXISTS conversation_records (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    role            VARCHAR(20)  NOT NULL,
    content         TEXT,
    tool_calls      JSONB,
    tool_call_id    VARCHAR(100),
    created_at      TIMESTAMP    DEFAULT NOW()
);
-- 防御性补齐（本表 CREATE 已是完整 7 列，这里兜底，IF NOT EXISTS 不会重复加）
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS session_id   VARCHAR(100);
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS role         VARCHAR(20);
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS content      TEXT;
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS tool_calls   JSONB;
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS tool_call_id VARCHAR(100);
ALTER TABLE conversation_records ADD COLUMN IF NOT EXISTS created_at   TIMESTAMP DEFAULT NOW();
-- 索引
CREATE INDEX IF NOT EXISTS idx_conversation_records_session_id       ON conversation_records(session_id);
CREATE INDEX IF NOT EXISTS idx_conversation_records_session_created ON conversation_records(session_id, created_at);

-- ========== 4. attachments（附件元数据）==========
CREATE TABLE IF NOT EXISTS attachments (
    id              SERIAL PRIMARY KEY,
    session_id      VARCHAR(100) NOT NULL REFERENCES sessions(session_id) ON DELETE CASCADE,
    file_name       VARCHAR(500)  NOT NULL,
    stored_path     VARCHAR(1000) NOT NULL,
    file_type       VARCHAR(20)   NOT NULL,
    file_size       BIGINT        DEFAULT 0,
    mime_type       VARCHAR(100),
    file_id         VARCHAR(100),
    created_at      TIMESTAMP     DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS session_id   VARCHAR(100);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS file_name    VARCHAR(500);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS stored_path  VARCHAR(1000);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS file_type    VARCHAR(20);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS file_size    BIGINT  DEFAULT 0;
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS mime_type    VARCHAR(100);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS file_id      VARCHAR(100);
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS created_at   TIMESTAMP DEFAULT NOW();
-- 索引
CREATE INDEX IF NOT EXISTS idx_attachments_session_id       ON attachments(session_id);
CREATE INDEX IF NOT EXISTS idx_attachments_session_created ON attachments(session_id, created_at);

-- ========== 5. refresh_tokens（主站 RefreshToken）==========
CREATE TABLE IF NOT EXISTS refresh_tokens (
    id              SERIAL PRIMARY KEY,
    token_hash      VARCHAR(255) UNIQUE NOT NULL,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    expires_at      TIMESTAMP NOT NULL,
    created_at      TIMESTAMP DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS token_hash VARCHAR(255);
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS user_id    INTEGER;
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
ALTER TABLE refresh_tokens ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
-- 索引
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_user_id     ON refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_refresh_tokens_expires_at  ON refresh_tokens(expires_at);

-- ========== 6. audit_logs（审计日志）==========
CREATE TABLE IF NOT EXISTS audit_logs (
    id              SERIAL PRIMARY KEY,
    user_id         INTEGER,
    username        VARCHAR(100),
    action          VARCHAR(50) NOT NULL,
    detail          TEXT,
    ip_address      VARCHAR(50),
    created_at      TIMESTAMP DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS user_id    INTEGER;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS username  VARCHAR(100);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS action    VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS detail    TEXT;
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS ip_address VARCHAR(50);
ALTER TABLE audit_logs ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();

-- ========== 7. portal_refresh_tokens（门户子 RefreshToken）==========
CREATE TABLE IF NOT EXISTS portal_refresh_tokens (
    id              SERIAL PRIMARY KEY,
    token_hash      VARCHAR(255) UNIQUE NOT NULL,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username        VARCHAR(100) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    revoked         BOOLEAN   NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS token_hash VARCHAR(255);
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS user_id    INTEGER;
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS username  VARCHAR(100);
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS expires_at TIMESTAMP;
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS revoked    BOOLEAN DEFAULT FALSE;
ALTER TABLE portal_refresh_tokens ADD COLUMN IF NOT EXISTS created_at TIMESTAMP DEFAULT NOW();
-- 索引
CREATE INDEX IF NOT EXISTS idx_portal_refresh_tokens_user_id     ON portal_refresh_tokens(user_id);
CREATE INDEX IF NOT EXISTS idx_portal_refresh_tokens_expires_at  ON portal_refresh_tokens(expires_at);
-- 部分唯一索引：一个用户最多只能有一条未撤销的 portal refresh_token
CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_refresh_tokens_user_id_active
    ON portal_refresh_tokens(user_id)
    WHERE revoked = FALSE;

-- ========== 8. map_business_info（地图业务信息）==========
CREATE TABLE IF NOT EXISTS map_business_info (
    id              SERIAL PRIMARY KEY,
    business_no     VARCHAR(20)  UNIQUE NOT NULL,
    project_name    VARCHAR(200) NOT NULL,
    unit_name       VARCHAR(200) NOT NULL,
    contact_person  VARCHAR(100) NOT NULL,
    contact_phone   VARCHAR(20)  NOT NULL,
    unit_address    VARCHAR(500) NOT NULL,
    session_id      VARCHAR(100) NOT NULL,
    created_at      TIMESTAMP    DEFAULT NOW()
);
-- 防御性补齐
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS business_no    VARCHAR(20);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS project_name   VARCHAR(200);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS unit_name      VARCHAR(200);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS contact_person VARCHAR(100);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS contact_phone  VARCHAR(20);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS unit_address   VARCHAR(500);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS session_id     VARCHAR(100);
ALTER TABLE map_business_info ADD COLUMN IF NOT EXISTS created_at     TIMESTAMP DEFAULT NOW();
-- 索引
CREATE INDEX IF NOT EXISTS idx_map_business_session_id  ON map_business_info(session_id);
CREATE INDEX IF NOT EXISTS idx_map_business_created_at  ON map_business_info(created_at);

-- ========== 9. map_business_no_counter（地图业务编号计数器）==========
CREATE TABLE IF NOT EXISTS map_business_no_counter (
    date_str        VARCHAR(8) PRIMARY KEY,
    current_seq     INTEGER DEFAULT 0
);
-- 防御性补齐
ALTER TABLE map_business_no_counter ADD COLUMN IF NOT EXISTS date_str    VARCHAR(8);
ALTER TABLE map_business_no_counter ADD COLUMN IF NOT EXISTS current_seq INTEGER DEFAULT 0;

-- ============================================================
-- 2026-06-23 统一智能体架构 + MCP 注册界面
-- 新增 5 张表，不修改现有表，幂等可重复执行
-- ============================================================

-- 10. agents 表：智能体运行时配置
CREATE TABLE IF NOT EXISTS agents (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200) NOT NULL,
    description TEXT,
    agents_md_path VARCHAR(500) NOT NULL,
    state_schema JSONB DEFAULT '{}',
    context_schema JSONB DEFAULT '{}',
    mcp_tags JSONB DEFAULT '[]',
    enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 防御性补齐：2026-06-24 新增 config_schema（三层嵌套结构：AgentConfig 字段 + state_fields + context_fields）
-- 与现有 state_schema / context_schema 并存，向后兼容；后续版本稳定后可 DROP COLUMN state_schema/context_schema
ALTER TABLE agents ADD COLUMN IF NOT EXISTS config_schema JSONB DEFAULT '{}';

-- 11. agent_tool_bindings 表：智能体-工具绑定
CREATE TABLE IF NOT EXISTS agent_tool_bindings (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    tool_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_name, tool_name)
);

-- 12. agent_skill_bindings 表：智能体-skill 绑定
CREATE TABLE IF NOT EXISTS agent_skill_bindings (
    id SERIAL PRIMARY KEY,
    agent_name VARCHAR(100) NOT NULL,
    skill_name VARCHAR(100) NOT NULL,
    is_enabled BOOLEAN DEFAULT TRUE,
    sort_order INT DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(agent_name, skill_name)
);

-- 13. mcp_server_configs 表：MCP 服务器配置
CREATE TABLE IF NOT EXISTS mcp_server_configs (
    id SERIAL PRIMARY KEY,
    name VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(200),
    type VARCHAR(20) NOT NULL,
    url VARCHAR(500),
    command JSONB,
    args JSONB DEFAULT '[]'::jsonb,                    -- stdio 参数列表
    env JSONB DEFAULT '{}'::jsonb,                     -- 进程环境变量
    headers JSONB DEFAULT '{}'::jsonb,                 -- HTTP/SSE 自定义头
    timeout INT DEFAULT 5,
    connect_timeout INT DEFAULT 10,                    -- TCP/HTTP 连接超时（秒）
    read_timeout INT DEFAULT 300,
    tags JSONB DEFAULT '[]',
    enabled BOOLEAN DEFAULT TRUE,
    progress_reporting JSONB DEFAULT '{"enabled": false}',
    tool_config JSONB DEFAULT '{"enable_injection": true, "default_param_keys": [], "hidden_param_keys": [], "unwrap_result": false}',
    sampling JSONB DEFAULT '{"enabled": false}',
    methods_synced_at TIMESTAMP,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 14. mcp_server_methods 表：MCP 服务器方法列表
CREATE TABLE IF NOT EXISTS mcp_server_methods (
    id SERIAL PRIMARY KEY,
    server_name VARCHAR(100) NOT NULL,
    method_name VARCHAR(200) NOT NULL,
    enabled BOOLEAN DEFAULT TRUE,
    description TEXT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(server_name, method_name)
);

-- ============================================================
-- 2026-06-24 合并自 fix_map_agent_schema.sql
-- 修复 map_agent state_schema / context_schema 字段不完整
-- 适用：agents 表中已存在 map_agent 记录但 schema 只有 map_zoom
-- 来源：2026-06-24 重构 agent_router 时发现原 seed 脚本漏存字段
-- 幂等：使用 jsonb_set + COALESCE 保留已有键，补充缺失键
-- 说明：本段在整体 BEGIN/COMMIT 事务内执行（无独立 BEGIN/COMMIT），
--       若失败则随主事务一起回滚。
-- ============================================================

-- 14.1 补全 map_agent 的 state_schema 5 个字段
--      原值（重构前）：{"map_zoom": {"type": "int", "default": 10}}
--      新值（修复后）：补全 map_center / map_markers / map_layer / map_polygons
UPDATE agents
SET state_schema = jsonb_set(
        state_schema,
        '{map_center}',
        COALESCE(state_schema->'map_center', '{"type": "dict", "default": {"latitude": 0, "longitude": 0}}'::jsonb)
    ) || jsonb_set(
        state_schema,
        '{map_markers}',
        COALESCE(state_schema->'map_markers', '{"type": "list", "default": []}'::jsonb)
    ) || jsonb_set(
        state_schema,
        '{map_layer}',
        COALESCE(state_schema->'map_layer', '{"type": "str", "default": "standard"}'::jsonb)
    ) || jsonb_set(
        state_schema,
        '{map_polygons}',
        COALESCE(state_schema->'map_polygons', '{"type": "list", "default": []}'::jsonb)
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'map_agent';

-- 14.2 context_schema 保持为 {knowledge_root}（基类保留字段由 dynamic_schema 兜底，
--      不需要在 schema 中重复声明）
--      注：如果当前 context_schema 已经有 knowledge_root，COALESCE 会保留它；
--      如果为 null/空，则保持现状。
UPDATE agents
SET context_schema = COALESCE(context_schema, '{}'::jsonb),
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'map_agent';

-- ============================================================
-- 2026-06-24 agents.config_schema 三层嵌套结构迁移
-- 把现有 state_schema + context_schema 数据合并到 config_schema
-- 三层结构：
--   config_schema = {
--     <AgentConfig 字段>: { type, default },     -- 可选，覆盖 model_type / temperature 等
--     state_fields:   { <字段>: { type, default } },
--     context_fields: { <字段>: { type, default } }
--   }
-- 幂等：使用 COALESCE + jsonb_build_object，可重复执行
-- ============================================================

-- 14.3 迁移：把旧 state_schema + context_schema 合并到 config_schema（仅当 config_schema 为空时）
UPDATE agents
SET config_schema = jsonb_build_object(
        'state_fields',   COALESCE(state_schema,   '{}'::jsonb),
        'context_fields', COALESCE(context_schema, '{}'::jsonb)
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE config_schema = '{}'::jsonb OR config_schema IS NULL;

-- 14.4 兜底：config_schema 已有数据但缺少 state_fields / context_fields 时补齐
UPDATE agents
SET config_schema = config_schema || jsonb_build_object(
        'state_fields',   COALESCE(config_schema->'state_fields',   '{}'::jsonb),
        'context_fields', COALESCE(config_schema->'context_fields', '{}'::jsonb)
    ),
    updated_at = CURRENT_TIMESTAMP
WHERE NOT (config_schema ? 'state_fields') OR NOT (config_schema ? 'context_fields');

-- =============================================
-- 2026-06-24 mcp_server_configs 字段扩展（兼容已建库）
-- 补齐 args / env / headers / connect_timeout 4 列，使 DB 成为 source of truth
-- 幂等：ADD COLUMN IF NOT EXISTS（PostgreSQL 9.6+）
-- =============================================
ALTER TABLE mcp_server_configs
    ADD COLUMN IF NOT EXISTS args JSONB DEFAULT '[]'::jsonb;
ALTER TABLE mcp_server_configs
    ADD COLUMN IF NOT EXISTS env JSONB DEFAULT '{}'::jsonb;
ALTER TABLE mcp_server_configs
    ADD COLUMN IF NOT EXISTS headers JSONB DEFAULT '{}'::jsonb;
ALTER TABLE mcp_server_configs
    ADD COLUMN IF NOT EXISTS connect_timeout INT DEFAULT 10;

-- ============================================================
-- 2026-06-25 Agent 配置缓存 + 工具统一管理架构改造
-- 新增 tools 表 + agents.tool_bindings 字段 + agent_tool_bindings.tool_type 字段
-- 幂等：所有 DDL 使用 IF NOT EXISTS，可重复执行
-- ============================================================

-- 15. tools 表：统一工具元数据注册表
--     用途：将散落在 app/core/tools/ 与 app/features/*/tools/ 下的工具函数元数据
--           统一登记到数据库，供管理界面展示与 Agent 配置缓存查询
CREATE TABLE IF NOT EXISTS tools (
    id                      SERIAL PRIMARY KEY,
    name                    VARCHAR(100) UNIQUE NOT NULL,   -- 工具唯一标识（与 @register_tool 注册名一致）
    display_name            VARCHAR(200),                   -- 展示名称（管理界面用）
    category                VARCHAR(100) NOT NULL,          -- 工具分类（如 filesystem / sandbox / mcp / map 等）
    description             TEXT,                           -- 工具描述（来自 docstring 摘要）
    module_path             VARCHAR(500) NOT NULL,          -- Python 模块路径（如 app.core.tools.SandboxTools）
    file_path               VARCHAR(500) NOT NULL,          -- 源文件相对路径（如 app/core/tools/SandboxTools.py）
    args_schema             JSONB DEFAULT '{}',             -- 参数 schema（Pydantic model 字段描述）
    return_description      TEXT,                           -- 返回值描述
    function_description    TEXT,                           -- 函数完整描述（docstring 全文）
    enabled                 BOOLEAN DEFAULT TRUE,           -- 是否启用
    sort_order              INT DEFAULT 0,                  -- 排序权重
    created_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 索引：按分类查询、按启用状态查询
CREATE INDEX IF NOT EXISTS idx_tools_category ON tools(category);
CREATE INDEX IF NOT EXISTS idx_tools_enabled  ON tools(enabled);

-- 16. agents 表扩展：tool_bindings 字段
--     用途：缓存该智能体当前启用的工具列表快照（JSON 数组）
--           避免每次加载 AgentConfig 时都联表查 agent_tool_bindings
--     结构示例：[{"name": "sandbox", "type": "builtin"}, {"name": "mcp__weather", "type": "mcp"}]
--     数据来源：由 AgentConfigService 在保存配置时同步写入
ALTER TABLE agents ADD COLUMN IF NOT EXISTS tool_bindings JSONB DEFAULT '[]';

-- 17. agent_tool_bindings 表扩展：tool_type 字段
--     用途：区分工具来源类型，便于管理界面分组展示与运行时按类型加载
--     取值：'builtin'（内置 @register_tool 工具）/ 'mcp'（MCP server 工具）/ 'skill'（skill 工具）
--     默认 'builtin'：兼容历史数据（老绑定记录全部视为内置工具）
ALTER TABLE agent_tool_bindings ADD COLUMN IF NOT EXISTS tool_type VARCHAR(20) DEFAULT 'builtin';

-- ============================================================
-- 工具种子数据 (Auto-generated by scripts/seed_tools_from_source.py)
-- 生成时间: 2026-06-25 22:13:44
-- 工具数量: 17
-- 幂等: ON CONFLICT (name) DO NOTHING 可重复执行
-- 重新生成命令: $bytes = [System.IO.File]::ReadAllBytes("scripts/category_map.json"); $env:SEED_CATEGORY_MAP = [System.Text.Encoding]::UTF8.GetString($bytes); $env:PYTHONIOENCODING = "utf-8"; python scripts/seed_tools_from_source.py --output app/migrations/seed_tools.sql
-- ============================================================

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('get_current_time', 'Get Current Time', '基础工具', '获取当前时间，仅在用户询问时间相关问题时调用', 'app.core.tools.BaseTools', 'app/core/tools/BaseTools.py', '{}', NULL, '获取当前时间工具。仅在用户明确询问时间、日期或需要时间上下文时才调用。

返回当前系统时间字符串，格式为 YYYY-MM-DD HH:MM:SS，并附带会话ID。
用于Agent了解当前时间上下文，支持时间敏感的任务处理。

Args:
    runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

Returns:
    str: 格式化的时间字符串，格式 "YYYY-MM-DD HH:MM:SS (session_id: xxx)"', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('load_web_page', 'Load Web Page', '基础工具', '
【网页加载】加载网页URL内容并分块缓存。

**参数**：url - 网页URL或URL列表

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个URL或URL列表，多个URL会统一分块返回一个 cache_id。
', 'app.core.tools.BaseTools', 'app/core/tools/BaseTools.py', '{}', NULL, '网页加载工具

加载指定URL的网页内容，将内容分块后存入存储，返回文件ID。
需要使用 read_cached_chunk 工具逐块读取内容。
支持单个URL或URL列表，多个URL会统一分块返回一个cache_id。

Args:
    url (Union[str, List[str]]): 必填 要加载的网页URL或URL列表
    runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

Returns:
    str: JSON格式结果，包含 file_name 和状态信息', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('open_file', 'Open File', '基础工具', '
【本地文件加载】加载本地文件（PDF/Word/CSV等）并分块缓存。

**参数**：file_path - 文件或文件夹路径，支持相对路径和绝对路径

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个文件路径或路径列表，多个文件会统一分块返回一个 cache_id。
', 'app.core.tools.BaseTools', 'app/core/tools/BaseTools.py', '{}', NULL, '文件加载工具

智能识别文件类型并加载内容，将文档分块后存入存储，返回文件ID。
需要使用 read_cached_chunk 工具逐块读取内容。
支持单个文件路径或路径列表，多个文件会统一分块返回一个cache_id。

Args:
    file_path (Union[str, Path, List[Union[str, Path]]]): 必填 文件或文件夹路径，支持相对路径和绝对路径
    runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

Returns:
    str: JSON格式结果，包含 file_name 和状态信息', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('open_file_by_id', 'Open File By Id', '基础工具', '
【本地文件加载】通过文件ID加载本地文件并分块缓存。

**参数**：file_id - 文件ID或ID列表，用于查找文件路径

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个文件ID或ID列表，多个文件会统一分块返回一个 cache_id。
', 'app.core.tools.BaseTools', 'app/core/tools/BaseTools.py', '{}', NULL, '文件加载工具（通过文件ID）

通过文件ID从 store 中查找文件路径，加载内容后将文档分块存入存储，返回文件ID。
需要使用 read_cached_chunk 工具逐块读取内容。
支持单个文件ID或ID列表，多个文件会统一分块返回一个cache_id。

Args:
    file_id (Union[str, List[str]]): 必填 文件ID或ID列表，用于查找文件路径
    runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

Returns:
    str: JSON格式结果，包含 file_name 和状态信息', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('read_cached_chunk', 'Read Cached Chunk', '基础工具', '
【读取文档块】从缓存中读取文档内容。

**参数**：
- cache_id: 必填，缓存ID，由 open_file 返回
- start_index: 可选，开始块索引（从1开始），不传则顺序读取
- end_index: 可选，结束块索引，不传则顺序读取下一块

**返回值**：
- index: 当前块序号
- name: 进度标识，如 "2/5" 表示第2块/共5块
- content: 块内容
- is_last: 是否最后一块

**使用模式**：
1. 顺序读取（不传范围参数）：每次调用返回下一块，直到 is_last=True
2. 范围读取（传入起止索引）：返回指定范围的块内容，不追踪进度

**重要**：读取文档可能需要多次调用，is_last=True 时表示读完。
', 'app.core.tools.BaseTools', 'app/core/tools/BaseTools.py', '{}', NULL, '', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('explore', 'Explore', '文件读取', 'Launch a new agent to handle complex, multistep file search and reading tasks autonomously.
The explore agent specializes in searching for files by name and content, then reading them.

## When to use
- When you need to search for files by name patterns AND read their content
- When you need to find files containing specific keywords or text
- When the scope of file search may span multiple directories
- For complex file exploration that requires both finding and reading files

## When NOT to use
- If you know the specific file path you need to read, use the read_file tool directly
- If you only need to list directory contents, use the ls tool directly
- If you only need to search for file paths (not read content), use glob_search/grep_search directly
- For tasks that are not related to file searching and reading

## Prompt writing rules (CRITICAL)
The prompt parameter must be a highly detailed task description for the subagent to perform autonomously. You must specify exactly what inf', 'app.core.tools.FilesystemReadTools', 'app/core/tools/FilesystemReadTools.py', '{}', NULL, '启动探索子智能体，读取当前 session 上传目录中的文件并分析。

该工具仅面向当前会话上传目录 `data/upload/{yyyy}/{mm}/{dd}/{session_id}`，知识库检索请使用
`query_knowledge` 工具。

注意：子智能体在该目录下搜索/列出的均为原文件；实际读取内容时，
FilesystemBackend.read 猴补丁会自动映射到 `data/tmp/upload/...` 下对应的 `.md` 文件。

Args:
    prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
            包含搜索目标、预期返回信息、操作约束等。
    runtime: 工具运行时上下文，包含 session_id 与 tool_call_id。

Returns:
    Command: 子智能体的文件搜索与分析结果；若目录为空则返回提示未找到文件的 Command。', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('ask_user_question', 'Ask User Question', '人机交互', '【向用户提问】在需要澄清需求或补充信息的节点暂停执行，等待用户回答。

使用步骤：
1. 判断用户意图是否清晰（如"用什么框架？" → 不清晰）
2. 构造 1-4 个明确的问题（每个问题只问 1 件事）
3. 为每个问题提供 2-4 个选项，**推荐项放第一个并加 (Recommended) 后缀**
   - 如果问题是开放式的（如"请输入项目名称"），传 options=[] + text_only=true
4. 调用本工具，传入结构化 questions 数组

重要约束：
- questions 数组必填，1-4 个
- 每个 question 的 options 0-5 个：
    * AI 业务选项：2-4 个
    * 后端自动追加 1 个虚拟"Other"项，所以最终渲染时最多 5 个
    * 空：纯文本问题，前端显示 textarea 让用户自由输入
- text_only=true：显式标记纯文本问题，跳过 Other 注入
- 推荐项放 options[0]，label 末尾加 "(Recommended)" 后缀
- 多选用 multiple: true

Args:
    questions: 问题列表，每个问题包含 question/header/options/multiple/text_only
    runtime: 工具运行时上下文（LangChain 内部注入）

Returns:
    Command: 包含 pending_question 状态和 ToolMessage 的命令对象
        - pending_question: 待回答问题信息
        - messages: ToolMessage，记录问题已发起', 'app.core.tools.HumanInTheLoopTools', 'app/core/tools/HumanInTheLoopTools.py', '{}', NULL, '【向用户提问】在需要澄清需求或补充信息的节点暂停执行，等待用户回答。

使用步骤：
1. 判断用户意图是否清晰（如"用什么框架？" → 不清晰）
2. 构造 1-4 个明确的问题（每个问题只问 1 件事）
3. 为每个问题提供 2-4 个选项，**推荐项放第一个并加 (Recommended) 后缀**
   - 如果问题是开放式的（如"请输入项目名称"），传 options=[] + text_only=true
4. 调用本工具，传入结构化 questions 数组

重要约束：
- questions 数组必填，1-4 个
- 每个 question 的 options 0-5 个：
    * AI 业务选项：2-4 个
    * 后端自动追加 1 个虚拟"Other"项，所以最终渲染时最多 5 个
    * 空：纯文本问题，前端显示 textarea 让用户自由输入
- text_only=true：显式标记纯文本问题，跳过 Other 注入
- 推荐项放 options[0]，label 末尾加 "(Recommended)" 后缀
- 多选用 multiple: true

Args:
    questions: 问题列表，每个问题包含 question/header/options/multiple/text_only
    runtime: 工具运行时上下文（LangChain 内部注入）

Returns:
    Command: 包含 pending_question 状态和 ToolMessage 的命令对象
        - pending_question: 待回答问题信息
        - messages: ToolMessage，记录问题已发起', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('sandbox', 'Sandbox', '沙箱', 'Launch a sandbox subagent to safely execute code and file operations in an isolated Docker container.
The sandbox agent specializes in running Python/Shell code and performing file operations securely.

## When to use
- When you need to execute user-provided code safely
- When you need to perform data analysis or processing
- When you need to create, read, edit files in an isolated environment
- When the task involves code execution that should not affect the host system

## When NOT to use
- If you only need to read existing files on the host, use read_file directly
- If you only need to search files, use glob_search/grep_search directly
- For tasks that don''t require code execution or file operations

## Prompt writing rules (CRITICAL)
The prompt parameter must be a highly detailed task description for the subagent to perform autonomously. You must specify exactly what code to execute or what file operations to perform.
Do NOT pass the user''s raw message as prompt — formulate a detai', 'app.core.tools.SandboxTools', 'app/core/tools/SandboxTools.py', '{}', NULL, '启动沙箱子智能体，在隔离的 Docker 容器中执行代码和文件操作。

子智能体挂载 DockerSandboxMiddleware（继承 FilesystemMiddleware），
提供完整的沙箱工具集：ls, read_file, write_file, edit_file, glob, grep, execute。

使用 LangGraph MemorySaver checkpointer 管理子智能体会话。

## 2026-06-15 新增：用户停止信号感知

通过 ``app.core.tools._stop_signal`` 取出当前请求的 FastAPI Request，
在 ``child_agent.astream()`` 循环中每 ``_STOP_CHECK_INTERVAL`` 个 chunk 检测一次
``request.is_disconnected()``，发现客户端断开（停止按钮触发）时立即：

1. 跳出 astream 循环
2. 推送 ``tool_stop`` 事件，``data.status = "stopped_by_user"``（前端可识别）
3. 清理 Docker 容器资源（``middleware.cleanup()``）
4. 返回 ``Command`` 包含「子智能体已被用户中止」文本，让父 LLM 知道该子任务被中断

Args:
    prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
            包含要执行的代码、文件操作、预期返回信息等。
    runtime: 工具运行时对象（自动注入）

Returns:
    Command: 包含子智能体执行结果的命令

Raises:
    RuntimeError: Docker 不可用时抛出', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('add_map_marker', 'Add Map Marker', 'map_agent', '在地图上添加标记点', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【添加地图标记】在地图上添加一个标记点。

调用时机：
- 用户说"在地图上标记..."、"添加标记"、"标注位置"时
- 用户说"标记这个位置"、"这里有个点"时
- 需要在地图上标注特定位置时

Args:
    latitude: 纬度，范围 -90 到 90
    longitude: 经度，范围 -180 到 180
    title: 标记标题
    description: 标记描述（可选）
    marker_id: 标记ID（可选，不传则自动生成）
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "marker_added" - 标记已添加
        - marker: 标记信息对象', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('clear_map_markers', 'Clear Map Markers', 'map_agent', '清除地图上所有标记', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【清除所有标记】清除地图上的所有标记点。

调用时机：
- 用户说"清除所有标记"、"清空地图"、"删除所有标记"时
- 用户说"重置地图标记"时
- 需要清空地图上的所有标记时

Args:
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "markers_cleared" - 所有标记已清除
        - cleared_count: 清除的标记数量', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('draw_map_polygon', 'Draw Map Polygon', 'map_agent', '在地图上绘制多边形区域', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【绘制地图多边形】在地图上绘制一个多边形区域。

调用时机：
- 用户说"画一个区域"、"绘制多边形"、"标注范围"时
- 用户说"圈出这块区域"、"标记这个范围"时
- 需要在地图上标注特定区域时

Args:
    coordinates: 多边形顶点坐标列表，每个点包含 latitude 和 longitude
    title: 多边形标题（可选）
    color: 多边形颜色，十六进制格式（可选，默认红色）
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "polygon_drawn" - 多边形已绘制
        - polygon: 多边形信息对象', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('get_map_state', 'Get Map State', 'map_agent', '获取当前地图状态信息', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【获取地图状态】获取当前地图的状态信息。

调用时机：
- 用户说"当前地图状态"、"地图信息"、"查看地图"时
- 用户说"地图中心在哪"、"有多少标记"时
- 需要查看当前地图配置时

Args:
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "state_retrieved" - 状态已获取
        - map_state: 地图状态对象，包含中心点、缩放级别、标记列表等', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('query_knowledge', 'Query Knowledge', 'map_agent', '知识库检索子智能体', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '启动知识库检索子智能体，在配置的知识库目录中搜索并读取文档。

目标知识库路径通过 `runtime.context["knowledge_root"]` 传入，便于不同场景
配置不同的知识库地址。

Args:
    prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
            包含检索目标、预期返回信息、操作约束等。
    runtime: 工具运行时上下文，必须包含 knowledge_root 与 tool_call_id。

Returns:
    Command: 子智能体的知识库检索结果。', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('remove_map_marker', 'Remove Map Marker', 'map_agent', '移除指定的地图标记', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【移除地图标记】从地图上移除指定的标记点。

调用时机：
- 用户说"删除标记"、"移除标记"、"取消标记"时
- 用户说"删除第X个标记"、"移除这个点"时
- 需要移除地图上的特定标记时

Args:
    marker_id: 要移除的标记ID
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "marker_removed" - 标记已移除
        - marker_id: 被移除的标记ID', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('set_map_center', 'Set Map Center', 'map_agent', '设置地图中心点坐标', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【设置地图中心】将地图中心点移动到指定经纬度位置。

调用时机：
- 用户说"定位到某地"、"移动到某位置"、"查看某地"时
- 用户说"地图中心移动到..."、"跳转到..."时
- 需要查看特定地理位置时

Args:
    latitude: 纬度，范围 -90 到 90
    longitude: 经度，范围 -180 到 180
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "center_set" - 中心点已设置
        - center: {"latitude": 纬度, "longitude": 经度}', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('set_map_layer', 'Set Map Layer', 'map_agent', '设置地图显示图层类型', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【设置地图图层】切换地图的显示图层类型。

调用时机：
- 用户说"切换到卫星图"、"显示卫星地图"、"查看卫星视图"时
- 用户说"切换到地形图"、"显示地形"时
- 需要切换地图显示模式时

Args:
    layer_type: 图层类型，可选值：
        - "standard": 标准地图
        - "satellite": 卫星地图
        - "terrain": 地形地图
        - "hybrid": 混合地图（卫星+标注）
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "layer_set" - 图层已设置
        - layer_type: 当前图层类型', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('set_map_zoom', 'Set Map Zoom', 'map_agent', '设置地图缩放级别', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '【设置地图缩放】调整地图的缩放级别。

调用时机：
- 用户说"放大地图"、"缩小地图"、"调整缩放"时
- 用户说"地图缩放到..."、"查看更大范围"时
- 需要调整地图视野范围时

Args:
    zoom_level: 缩放级别，范围 1-20（1=世界视图，20=街道视图）
    runtime: 工具运行时上下文

Returns:
    Command: 包含ToolMessage和状态更新的命令对象
        - status: "zoom_set" - 缩放级别已设置
        - zoom_level: 缩放级别值', TRUE, 0)
ON CONFLICT (name) DO NOTHING;

COMMIT;

-- =============================================
-- 验证：列出本脚本建的所有表
-- =============================================
SELECT table_name
FROM information_schema.tables
WHERE table_schema = 'public'
  AND table_name IN (
    'users', 'sessions', 'conversation_records', 'attachments',
    'refresh_tokens', 'audit_logs', 'portal_refresh_tokens',
    'map_business_info', 'map_business_no_counter',
    'agents', 'agent_tool_bindings', 'agent_skill_bindings',
    'mcp_server_configs', 'mcp_server_methods',
    'tools'
  )
ORDER BY table_name;

-- =============================================
-- 验证：列出 map_agent 修复后的完整 schema
-- （如果 map_agent 记录尚未被 seed_map_agent.py 写入，则查询为空，正常）
-- =============================================
SELECT name,
       jsonb_pretty(state_schema) AS state_schema,
       jsonb_pretty(context_schema) AS context_schema
FROM agents
WHERE name = 'map_agent';
