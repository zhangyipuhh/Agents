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
-- v4 变更（2026-07-10）:
--   * 移除 \i app/migrations/seed_project_skills.sql（psql 元命令，GUI 不支持）
--   * 将原 seed_project_skills.sql 的全部 INSERT 直接内联到本脚本底部，
--     兼容 psql 命令行 + 任意 GUI 工具（pgAdmin / Navicat / DBeaver）
--   * 删除独立的 app/migrations/seed_project_skills.sql（已废弃）
--   * 应用启动时仍由 app/migrations/seed_project_agent.py::seed_project_skills 自动写入，
--     本脚本内联部分只是把"手动初始化数据库、不启动应用"场景的依赖折叠进来
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
ALTER TABLE users ADD COLUMN IF NOT EXISTS allowed_agents JSONB DEFAULT '[]';

-- ========== 1.5. projects（项目元数据，2026-06-30 新增）==========
-- 项目文件夹方案：用户从聊天框下拉框选择"新建空白项目"或"使用现有文件夹"
--   * uuid：项目的逻辑标识 = 创建时的 session_id（可保证全局唯一）
--   * 用户隔离：通过 user_id 限定可见范围
--   * 物理路径：<项目根>/data/project/{uuid}/ （原文件）与 <项目根>/data/tmp/project/{uuid}/ （解析md）
CREATE TABLE IF NOT EXISTS projects (
    id          SERIAL PRIMARY KEY,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    name        VARCHAR(200) NOT NULL,
    uuid        VARCHAR(64)  UNIQUE NOT NULL,
    created_at  TIMESTAMP    DEFAULT NOW(),
    updated_at  TIMESTAMP    DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_projects_user_id ON projects(user_id);
ALTER TABLE projects ADD COLUMN IF NOT EXISTS relative_path VARCHAR(500);

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
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS status          VARCHAR(20)  DEFAULT 'active';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_type      VARCHAR(50)  DEFAULT 'default';
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS agent_display_name VARCHAR(200) DEFAULT '';
-- 2026-06-30 新增：会话关联的项目 ID（一对多：多会话可共用同一项目）
--   * 引用 projects(id)，projects 表已在 1.5 段创建
--   * ON DELETE SET NULL：项目被删除时会话自动解除关联，文件保留
ALTER TABLE sessions ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL;

-- sessions 表索引
CREATE INDEX IF NOT EXISTS idx_sessions_user_id ON sessions(user_id);
CREATE INDEX IF NOT EXISTS idx_sessions_last_active_at ON sessions(last_active_at);
CREATE INDEX IF NOT EXISTS idx_sessions_status ON sessions(status);
CREATE INDEX IF NOT EXISTS idx_sessions_user_id_last_active ON sessions(user_id, last_active_at DESC);
CREATE INDEX IF NOT EXISTS idx_sessions_project_id ON sessions(project_id);

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
-- 2026-06-30 新增：附件冗余存储所属项目 ID，便于按项目聚合查询
--   * 不强制 NOT NULL：旧附件无 project_id（兼容存量数据）
--   * ON DELETE SET NULL：项目被删除时附件记录保留，project_id 置 NULL
ALTER TABLE attachments ADD COLUMN IF NOT EXISTS project_id INTEGER REFERENCES projects(id) ON DELETE SET NULL;

CREATE INDEX IF NOT EXISTS idx_attachments_session_id       ON attachments(session_id);
CREATE INDEX IF NOT EXISTS idx_attachments_session_created ON attachments(session_id, created_at);
CREATE INDEX IF NOT EXISTS idx_attachments_project_id       ON attachments(project_id);

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

-- 12. mcp_server_configs 表：MCP 服务器配置
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

-- 14.2 context_schema 兜底（map_agent 历史上曾有 knowledge_root 字段，
--      已于 2026-06-29 重构为 KNOWLEDGE_DIR 常量，此处仅确保 schema 非空）
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
-- 重新生成命令: python scripts/seed_tools_from_source.py --output app/migrations/seed_tools.sql
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
  ('query_knowledge', 'Query Knowledge', 'map_agent', '知识库检索子智能体', 'app.shared.tools.skills.map_agent.MapTools', 'app/shared/tools/skills/map_agent/MapTools.py', '{}', NULL, '启动知识库检索子智能体，在项目统一的知识库目录（KNOWLEDGE_DIR）中搜索并读取文档。

目标知识库路径由 `app.core.config.paths.KNOWLEDGE_DIR` 统一管理。

Args:
    prompt: 详细任务描述。父 LLM 应将用户问题改写为高度详细的任务描述，
            包含检索目标、预期返回信息、操作约束等。
    runtime: 工具运行时上下文，仅需 tool_call_id。

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

-- ============================================================
-- 2026-06-29 Skill 管理 + 智能体 skill 绑定字段扩展
-- 新增 skills 表、agents.skill_bindings JSONB 字段及种子数据
-- 幂等：所有 DDL 使用 IF NOT EXISTS，种子使用 ON CONFLICT (name) DO NOTHING
-- ============================================================

-- 18. skills 表：统一 skill 元数据注册表
--     用途：将 app/skills/ 与 .agents/skills/ 下的 SKILL.md 元数据
--           统一登记到数据库，供管理界面展示与 Agent skill 绑定查询
CREATE TABLE IF NOT EXISTS skills (
    id              SERIAL PRIMARY KEY,
    name            VARCHAR(100) UNIQUE NOT NULL,
    display_name    VARCHAR(200) DEFAULT '',
    category        VARCHAR(100) DEFAULT '',
    description     TEXT DEFAULT '',
    location        VARCHAR(1000) NOT NULL,
    base_dir        VARCHAR(1000) NOT NULL,
    content         TEXT DEFAULT '',
    enabled         BOOLEAN DEFAULT TRUE,
    sort_order      INT DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 索引：按分类查询、按启用状态查询
CREATE INDEX IF NOT EXISTS idx_skills_category ON skills(category);
CREATE INDEX IF NOT EXISTS idx_skills_enabled  ON skills(enabled);

-- 19. agents 表扩展：skill_bindings 字段
--     用途：缓存该智能体当前启用的 skill 列表快照（JSON 数组）
--     结构示例：[{"name": "hgsc", "enabled": true, "sort_order": 0}]
ALTER TABLE agents ADD COLUMN IF NOT EXISTS skill_bindings JSONB DEFAULT '[]';

-- ============================================================
-- Skill 种子数据
-- 来源：app/skills/<name>/SKILL.md frontmatter + 去 frontmatter 正文
-- 幂等：ON CONFLICT (name) DO NOTHING 可重复执行
-- ============================================================

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'bdc_query',
    'bdc_query',
    '',
    '',
    'app/skills/bdc_query/SKILL.md',
    'app/skills/bdc_query',
    $SKILL_BDC_QUERY_BODY$

    $SKILL_BDC_QUERY_BODY$,
    TRUE,
    0
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'hgsc',
    'hgsc',
    '',
    '合规性审查（Compliance Review）与项目预审（Project Pre-review）工作流，包括业务信息收集、保存、质量检测分析、报告生成。',
    'app/skills/hgsc/SKILL.md',
    'app/skills/hgsc',
    $SKILL_HGSC_BODY$
## Workflow
When handling compliance review or approval-related requests, you act as a **Compliance Reviewer**. You must strictly follow the steps and requirements defined in this prompt. Do NOT request any files, materials, or information from the user that are not explicitly required by the Workflow below. For questions unrelated to compliance review, respond normally.

### 合规性审查
1. When collecting information for the `save_business_info` tool, follow this EXACT order:
   - **Step 1**: Check the current conversation context for the required information (project name, construction unit, contact person, phone, address). Collect any information found in the context.
   - **Step 2**: **ALWAYS** use the `explore` tool to search attachments for the required information, regardless of whether the context already contains some or all of it. This is to verify and supplement the context information.
   - When using `explore`, instruct it to return ONLY the specific fields needed for `save_business_info`. Do NOT output full attachment content, summaries, file types, or extensions.
   - Merge the information from context and attachments. If there are conflicts, prefer the information from attachments.
   - **Step 3**: **Before calling `save_business_info`, ALWAYS use `ask_user_question` to confirm the accuracy and completeness of the collected information with the user**, regardless of whether the information comes from the conversation context or attachments.
   - Only if information is still missing after checking both context and attachments, use `ask_user_question` to ask the user for the missing information.
2. After the user confirms the information is accurate, use the `save_business_info` tool to persist the business information. This step is mandatory, refer to the tool parameters for required fields. When asking, use one tab to include all information that needs to be saved.
3. Invoke the `quality_inspection_analysis` tool and await the results.
4. Once the analysis completes, review the results and use `ask_user_question` to ask if the user wants to generate a report. If confirmed, call `generate_report`； if declined, inform the user they can request it later by typing "export report".

## Task Examples
### Example 1: Compliance Review
- User: Analyze the compliance review results for Project A.
- Tool Call: quality_inspection_analysis with analysis_categories=["合规性审查"]
- Response Format:
  - Categorize the tool output (e.g., farmland area, forest area)
  - State clearly if no occupancy

### Example 2: Project Pre-review
- User: Analyze the pre-review results for Project A.
- Tool Call: quality_inspection_analysis with analysis_categories=["项目预审"]
- Response Format: Same as above

## Output Requirements
- Structure the tool output by categories
- Be concise and direct
- Provide improvement or adjustment suggestions
- NEVER mention file types, file extensions, or attachment formats in responses
- When referencing attachment content, only state the extracted key information, not the source file details
    $SKILL_HGSC_BODY$,
    TRUE,
    0
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'knowledge_ydt',
    'knowledge_ydt',
    '',
    'Use when the user asks a question that requires querying the knowledge base, especially when attachments or uploaded files may contain constraints, clauses, or query content.',
    'app/skills/knowledge_ydt/SKILL.md',
    'app/skills/knowledge_ydt',
    $SKILL_KNOWLEDGE_YDT_BODY$
# 知识库查询工作流

## 概述

本 skill 指导智能体完成一次规范的知识库查询。核心原则：**先判断意图，再决定是否需要读取附件，最后调用 `query_knowledge` 获取结果并按要求格式返回。**

## 执行步骤

### 步骤 1：识别用户意图

判断用户的问题属于以下哪一类：

- **事实查询**：用户只想知道某个政策、条款、数据、流程、规定的原文或现状。例如：
  - "建设用地规划许可证的有效期是多久？"
  - "某文件的第 X 条内容是什么？"
- **辅助决策**：用户希望基于知识库内容做出判断、选择或建议。例如：
  - "这个项目是否符合规划要求？"
  - "我应该选择哪种审批路径？"

### 步骤 2：判断是否需要从附件/上传文件中获取信息

分析用户问题和当前对话上下文：

- **需要附件信息**：当问题涉及具体项目、合同、条款、约束条件，且这些关键信息可能存在于用户上传的文件中时。**不要直接向用户索要文件**，应使用 `explore` 工具从当前 session 的上传目录中主动提取。
  - 使用 `explore` 时，任务描述要明确：需要提取哪些字段、条款或约束条件。
  - `explore` 只能读取当前 session 已上传的文件；禁止返回文件类型、扩展名、文件路径等元信息，只返回提取出的关键内容。
- **不需要附件信息**：当问题仅依赖知识库中的公共政策、法规、流程文档即可回答时，跳过 `explore`。

### 步骤 3：处理相对时间（如适用）

若用户问题中包含相对时间表达（例如"最近3年"、"过去一年"、"2024年至今"、"上月"、"本周"等），在构造 `query_knowledge` 查询前必须执行以下操作：

1. 调用 `get_current_time` 工具获取当前系统时间。
2. 基于当前时间，将用户表达的相对时间转换为**绝对时间范围**（例如当前日期为 2026-06-29 时，"最近3年"应转换为 "2023-06-29 至 2026-06-29"）。
3. 在后续传递给 `query_knowledge` 的 `prompt` 中，必须显式写明：
   - 当前日期
   - 计算后的绝对时间范围
   - 原始用户问题
4. 禁止将包含相对时间的原始问题直接传递给 `query_knowledge`，必须先行解析。

### 步骤 4：构造 `query_knowledge` 查询

- 如果步骤 2 使用了 `explore`，将提取出的关键信息与会话上下文中的相关信息合并，构造为清晰、详细的查询任务，调用 `query_knowledge`。
- 如果步骤 2 不需要附件，直接基于对话上下文中的信息构造查询任务，调用 `query_knowledge`。
- `query_knowledge` 的 `prompt` 必须包含：查询目标、已知约束/上下文、期望返回的信息类型、是否需要原文引用。若涉及时间范围，必须包含步骤 3 计算出的绝对时间范围。

### 步骤 5：返回结果

根据步骤 1 识别的意图返回：

- **事实查询**：直接返回知识库中的原文或事实内容，保持准确、完整。如果查询结果为空，可结合预训练知识回答，但必须标注 `"基于预训练知识回答"`。
- **辅助决策**：返回明确的决策结论，并列出决策依据。决策依据必须引用知识库中的相关条款、政策或数据，禁止无依据的主观判断。

## 输出要求

- 回答语言与用户问题保持一致。
- 引用知识库内容时，只陈述关键信息，不暴露文件路径、文件类型、扩展名或附件来源。
- 若 `query_knowledge` 返回为空且无法结合预训练知识给出合理回答，应使用 `ask_user_question` 询问用户是否需要补充信息，而不是编造答案。

## 常见错误

- **错误**：用户问题明显涉及附件条款，却直接调用 `query_knowledge` 而跳过 `explore`。
  - **修正**：必须先通过 `explore` 提取附件中的约束、条款、查询内容，再构造查询。
- **错误**：用户问题包含"最近N年"等相对时间，未调用 `get_current_time` 就直接传递给 `query_knowledge`。
  - **修正**：必须先获取当前时间并转换为绝对时间范围，再写入 `query_knowledge` 的 prompt。
- **错误**：辅助决策类问题只给出结论，没有列出依据。
  - **修正**：必须显式返回"决策依据"部分，并引用知识库内容。
- **错误**：在回答中提及附件文件名、扩展名或路径。
  - **修正**：只输出提取出的业务信息，不输出任何文件元信息。
    $SKILL_KNOWLEDGE_YDT_BODY$,
    TRUE,
    0
)
ON CONFLICT (name) DO NOTHING;

-- ============================================================
-- 2026-06-30 skill location/base_dir 改为相对项目根的 POSIX 路径
-- 历史数据迁移：把已存在的 Windows 绝对路径转换为相对路径（POSIX 形式）
-- 幂等：WHERE 限定只更新仍为绝对路径的行，避免覆盖已迁移的相对路径数据
-- 触发条件：location LIKE '%\\%' 表示当前是 Windows 风格路径（含反斜杠）
-- ============================================================

UPDATE skills
SET location = 'app/skills/bdc_query/SKILL.md',
    base_dir = 'app/skills/bdc_query',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'bdc_query'
  AND location LIKE '%\%';

UPDATE skills
SET location = 'app/skills/hgsc/SKILL.md',
    base_dir = 'app/skills/hgsc',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'hgsc'
  AND location LIKE '%\%';

UPDATE skills
SET location = 'app/skills/knowledge_ydt/SKILL.md',
    base_dir = 'app/skills/knowledge_ydt',
    updated_at = CURRENT_TIMESTAMP
WHERE name = 'knowledge_ydt'
  AND location LIKE '%\%';

-- ============================================================
-- 2026-07-10 兼容修复：内联原 seed_project_skills.sql 的全部 INSERT
--   * 原方案用 \i 元命令引用独立 SQL 文件，仅 psql 命令行支持
--   * pgAdmin / Navicat / DBeaver 等 GUI 工具不识别 \i ，
--     会抛「语法错误 在 "\" 或附近的」并终止整个 BEGIN 事务
--   * 修复方式：把 seed_project_skills.sql 的全部内容直接合并到本脚本里
--   * 幂等：ON CONFLICT (name) DO UPDATE 可重复执行
--   * 注意：应用启动时仍会由 seed_project_agent.py::seed_project_skills 再次写入，
--     本段只是把"手动初始化数据库"场景的依赖从外部文件折叠进来
-- 来源：app/skills/project-doc-*/SKILL.md 与 app/skills/intent-clarification/SKILL.md
-- 等价内容由 scripts/generate_project_skills_seed.py 同步生成
-- ============================================================

-- >>> BEGIN_INLINE_SEED_PROJECT_SKILLS

-- ============================================================
-- 2026-07-02 新增：project 智能体依赖的 skills 种子数据
-- 来源：app/skills/project-doc-*/SKILL.md 与 app/skills/intent-clarification/SKILL.md
-- 幂等：ON CONFLICT (name) DO UPDATE 可重复执行
-- ============================================================

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-overview',
    '',
    '',
    'Use when any conversation involves software-engineering project documents (策划表/requirements/design/plans/test/acceptance/deployment) — this skill is the model''s entry point to the project-doc suite, listing all 7 child skills and how to dispatch them. Auto-loaded by models at conversation start when project-doc context detected.',
    'app/skills/project-doc-overview/SKILL.md',
    'app/skills/project-doc-overview',
    $SKILL_PROJECT_PROJECT_DOC_OVERVIEW_BODY$
## Keywords (关键词)

- 套件总览 (suite-overview)
- 元说明 (meta-description)
- 7个skill (seven-skills)
- 调度决策树 (dispatch-decision-tree)
- 场景分流 (scenario-dispatch)
- 流程规范 (workflow-standard)
- 入口文档 (entry-document)
- 不瞎编 (no-fabrication)

# Project Doc Overview (Suite Meta Description · For Model)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

All skills in this suite strictly forbid fabrication during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

See `../intent-clarification/references/no_fabrication.md` and the `<HARD-GATE: NO FABRICATION>` section in `../intent-clarification/SKILL.md` for details.

---

## Scenario Dispatch (Required · First Step)

```dot
digraph dispatch {
    "User question" [shape=box]；
    "Question type?" [shape=diamond]；
    "Technical document" [shape=box, color=red, style="rounded,filled", fillcolor="#fff5f5"]；
    "Management document" [shape=box, color=blue, style="rounded,filled", fillcolor="#f0f8ff"]；
    "Factual query" [shape=box, color=green, style="rounded,filled", fillcolor="#f0fff0"]；
    "Advisory" [shape=box, color=purple, style="rounded,filled", fillcolor="#f8f0ff"]；

    "User question" -> "Question type?"；
    "Question type?" -> "Technical document\n→ A0.technical_doc\n→ Must ask doc_type + C.environment" [label="Write technical document"]；
    "Question type?" -> "Management document\n→ A0.administrative\n→ D.document_attr" [label="Write management document"]；
    "Question type?" -> "Factual query\n→ A0.factual_query\n→ A.intent (fact)" [label="Query facts"]；
    "Question type?" -> "Advisory\n→ A0.advisory\n→ A.intent (decision) + three-layer framework" [label="Get advice"]；
}
```

> **Target reader**: **The model**. After loading this skill, the model should be able to automatically:
> - Know what each of the 7 skills in the suite does and when to invoke them
> - Know that **all "ask the user" actions must first invoke `intent-clarification`**
> - Know the `.project` directory structure and log conventions
> - Know how to orchestrate typical flows

## Purpose

This suite is used to manage **software-engineering project documents** (策划表, requirements, design, plans, test, acceptance, deployment, training, etc.).
This skill is the **model-read** entry document, not a user document.

Core principle: **Deterministic things are done by scripts； things requiring judgment/confirmation are done by the LLM**.

## Suite Roster (7 skills)

| Skill | YAML Description (Concise) | When to Invoke |
|---|---|---|
| `intent-clarification` | Unified clarification protocol: scan project materials → show existing info → ask user → log | **Any** scenario needing user confirmation (re-entrant during flow) |
| `project-doc-hub` | Dispatch entry: accept "project + document" requests → clarify → dispatch to query/outline/write/data | The first step of any "project + document" request |
| `project-doc-query` | Answer project facts/consultation: facts from 策划表/requirements/plans/contracts/emails + decision advisory | User asks "what's in the project", "when is the review" |
| `project-doc-outline` | Generate chapter outlines for 10 document types (no body) | User wants "see outline first" or during hub orchestration |
| `project-doc-write` | Fill body based on existing materials + generate decision advisory (no draft/— placeholder) | User wants "write complete document" |
| `project-doc-workflow` | 4-step pipeline checklist (query→outline→write→save-to-disk) | End-to-end automation scenarios |
| `data-skill` | Business file OCR → SQLite ingestion + self-healing verification (**Independent sub-suite**) | User wants to "ingest" data |

Full YAML descriptions see `references/skill_yaml_descriptions.md`.

## Hard Rule: Every User-Facing Question Goes Through `intent-clarification`

When the model needs to ask the user at any time:
- Project root, target document type, intent (query/generate/update)
- Fact vs decision, project-related vs industry-general
- Hardware/software/network/deployment/security level/localization/system architecture/localization list
- Document status / role signoff table
- Proactively ask when data is missing

**Must** first invoke `intent-clarification`, **forbidden** to ask inline within SKILL.md / reference.

## Process Files Location (Key: All Process Files Under .project/)

```
<用户工作根>/.project/<项目号>/          ← Sibling to project directory (e.g., <工作根>/.project/202410-C0008/)
├── project_log.md                     ← Main operation log (1 entry appended per skill flow end)
├── clarification_log.md               ← Clarification log (1 entry appended per Q/A)
├── drafts/                            ← Intermediate drafts
└── session_<YYYY-MM-DD>.md            ← Session log (optional)
```

**Do NOT** create or modify files inside any skill for runtime records.

## Dispatch Decision Tree

```
User says something related to "project + document"
  │
  ├─ Involves "ingest/OCR/SQLite" → data-skill (Independent sub-suite)
  │
  ├─ Involves "generate/update/write document"
  │   ├─ hub path
  │   │   ├─ Pure query → hub → project-doc-query
  │   │   ├─ Outline only → hub → project-doc-outline
  │   │   └─ Complete document → hub → project-doc-workflow → query→outline→write
  │   └─ Direct to a specific sub-skill (user has specified)
  │
  └─ Involves "ask the user" → Any skill first invokes intent-clarification
```

## Anti-Patterns (Strictly Forbidden for the Model)

| Anti-Pattern | Consequence |
|---|---|
| Directly invoking query/outline/write/data without calling intent-clarification | 5 inconsistent clarifications, repeated questions |
| Asking "what is the project root" inline within SKILL.md | Violates unified protocol |
| Skipping clarification and giving "should/suggest" directly | Violates HARD-GATE |
| Model inventing its own "question phrasing" to bypass intent-clarification | Protocol failure |
| Repeatedly asking the same question across skills | Should read `.project/<项目号>/clarification_log.md` |
| Writing process files under skill/references/ | Violates "process files externalized" principle |
| Skipping append to `.project/<项目号>/project_log.md` | Main log missing |

## Typical Flows

See `references/typical_flows.md` for details.

### Flow A: User Asks "What's in the Project"
1. project-doc-overview (current skill)
2. → intent-clarification (get project root + intent + scope)
3. → project-doc-query → use `explore(...)` to read project files → answer
4. → append operation record to `.project/<项目号>/project_log.md`

### Flow B: User Says "Write a Test Plan"
1. project-doc-overview
2. → intent-clarification (project root + document type + intent)
3. → project-doc-outline
4. → intent-clarification (environment/technology/compliance 10 technical points)
5. → project-doc-write
6. → intent-clarification (data integrity)
7. → Invoke "the skill that operates Word" to convert to .docx
8. → Append change record to `.project/<项目号>/06_变更及暂停/变更记录.md`
9. → append operation record to `.project/<项目号>/project_log.md`

### Flow C: Re-asking During Flow (Clarification is Re-entrant)
Any sub-skill encountering a new question at any step → invoke intent-clarification → log → continue.

    $SKILL_PROJECT_PROJECT_DOC_OVERVIEW_BODY$,
    TRUE,
    0
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-hub',
    '',
    '',
    'Use when the user wants to create, query, or update software-engineering project deliverables (Implementation Plan / Requirements Specification / High-Level Design / Detailed Design / Test Plan / Test Report / Acceptance Report / Implementation & Deployment / Training Plan etc.) under a project root such as <项目根> — acts as the entry point that dispatches to project-doc-query/outline/write/workflow',
    'app/skills/project-doc-hub/SKILL.md',
    'app/skills/project-doc-hub',
    $SKILL_PROJECT_PROJECT_DOC_HUB_BODY$
## Keywords (关键词)

- 项目文档 (project-document)
- 调度入口 (dispatch-entry)
- 软件工程 (software-engineering)
- 项目管理 (project-management)
- 分流调度 (dispatch-routing)
- 多框架 (multi-framework)
- 4步流水线 (four-step-pipeline)
- 售前方案 (pre-sales-proposal)

# Project Doc Hub (Project Management Skill V1 · Main Entry Point)

> **Stage Positioning**: The current suite is at **V1 Basic Capability Version**, and will continue to expand in the future (PMP/PRINCE2/Systems Analyst multi-framework overlay, see "Future Extensions" in each sub-skill).

## Overview

Accepts user requests related to "software-engineering project documents" and serves as the main entry dispatching to:

1. `project-doc-query` — Answers "what's in the project / when to deliver / review milestones" questions
2. `project-doc-outline` — Generates chapter outlines conforming to software-engineering standards based on the target document type
3. `project-doc-write` — Strictly fills the outline based on project materials + generates decision advisory
4. `project-doc-workflow` — Orchestrates the 4-step pipeline checklist

> **Note**: This skill is the **dispatch layer**, it does not directly write documents； document writing is completed in `project-doc-write`.

---

## Trigger Conditions (When to use)

- User mentions "project" + "document" + "generate/query/update" intent (e.g., "write a test plan", "implementation plan outline", "when is the review")
- User provides a project root path (e.g., `<项目根>`)
- User uses this suite's terminology ("project process documents", "策划表", "implementation plan", "high-level design", etc.)

---

## Core Flow (Dispatch · 2026-06-XX Reinforcement)

```
Step 1  Accept request
   ↓
Step 2  Clarification (Dispatch first, then ask · 5 dimensions · Fixed order)
   ↓ (If no project specified, list all projects under root directory and let user choose)
Step 2-a  [New · Required] intent-clarification · E.intent_detail (4-Choice-1 Creation Mode)
   ├─ E1 Generate based on existing materials → proceed to query to load materials
   ├─ E2 Brand-new independent generation  → skip query； must go through C.environment including 5 business materials
   ├─ E3 Incremental update of existing document → proceed to query to load existing docx
   └─ E4 Mimic writing from other project → let user specify reference project, load that docx
   ↓
Step 2-b  intent-clarification · A.intent 5 sub-items (doc_type/project_root/action_intent etc.)
   ↓
Step 2-c  Branch on E dispatch result: C.environment / D.document_attr
   ├─ E1/E3/E4 → C.environment 10 technical points (fill as needed)
   ├─ E2      → C.environment 10 technical points + 5 business materials (**All 5 business materials required**)
   └─ Writing administrative document → D.document_attr
   ↓
Step 2-d  [2026-06-XX New] Pre-Sales Proposal 5-item all-required validation (Required when E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 3
   ├─ Any item unfilled → [X3 Exit] return 5-item required checklist + (a) supplement / (b) hold
   └─ After X3 exit **do not** enter Step 3, **do not** load outline, **do not** write body
   ↓
Step 3  Load and activate corresponding sub-skill
   ├─ Query/consultation only → project-doc-query
   ├─ Outline only     → project-doc-outline
   │   ├─ E1/E3/E4 → outline version A (implementation-detail oriented)
   │   └─ E2      → outline version B (value-proposition oriented, see outline_pre_sales_proposal.md)
   ├─ Generate document   → project-doc-workflow (auto-chain query→outline→write)
   │   ├─ E1/E3/E4 → query → outline A → write regular
   │   └─ E2      → skip query → outline B → write Step 3.B new branch
   └─ Update document   → project-doc-write (incremental mode)
   ↓
Step 4  Collect output location confirmation (project directory vs intermediate draft)
   ↓
Step 5  Report output paths
```

### Future Extension: X2 Company Sales Archive Library (To Be Implemented · 2026-06-XX Reserved Interface)

**Goal**: When the company sales archive library is available, the X2 path can be taken under E2 Pre-Sales Proposal (auto-extract needed materials).

**Interface Reserved**:
- Library path: `<TBD · to be specified by company>` (Recommended: `<company archive root>/sales_archive/<industry>/<client>/<project>/`)
- Library-invoking method: `<TBD>` (Recommended: use `explore(...)` for unified file loading)
- Extraction field mapping: #11-15 business materials ↔ corresponding fields in sales archive
- Status: **Not implemented** in this round； if library is available in the future, `project-doc-hub` in Step 2-c will auto-detect library existence and dispatch to X2

**Current Default Behavior**: Library does not exist → auto-degrade to X1 or X3
```

---

## Key File Loading Method (Rigid Constraint)

- **All file-reading actions MUST use** `explore(...)` to read project files/attachments
- Forbidden to write one-off scripts in `tmp/` or absolute path root directories to read files
- Forbidden to bypass `explore(...)` by directly using "open() by extension"

---

## Mandatory Clarification Items (Call intent-clarification Before Talking to User)

**Forbidden** to ask inline within hub SKILL.md. **Must** invoke `intent-clarification` skill (see `../intent-clarification/SKILL.md` + `../project-doc-query/references/intent.md` for details).

### Step 0: Scenario Dispatch (Required · First Step)

**The first thing to do when a user question comes in**: identify the scenario type.

| Scenario | User Phrasing Characteristic | Required Question Dimensions (**Fixed Order**) |
|---|---|---|
| `A0.technical_doc` | "Write XX plan/design/test/deployment/training" | **1. E.intent_detail (4-Choice-1 Creation Mode)** → 2. A.intent (doc_type) → 3. C.environment (10 technical points + 5 business materials for E2 scenario) |
| `A0.administrative` | "Change record / weekly report / meeting minutes" | 1. E.intent_detail → 2. A.intent (doc_type) → 3. D.document_attr |
| `A0.factual_query` | "When / Who / How many / Where" | A.intent (fact/decision) |
| `A0.advisory` | "Suggest / Should / Which / How to choose" | A.intent (decision) + three-layer framework |

**Key points**:

- Technical document scenarios **must first ask E.intent_detail** (4-Choice-1 Creation Mode), then ask A.intent 5 sub-items
- E2 brand-new independent generation scenarios **must** additionally ask the 5 business material sub-items of C.environment
- Must not skip E.intent_detail to directly ask doc_type

### Step 1: 5 intent Dimension Sub-items + E.intent_detail (New)

Clarification items total 6 sub-items (including newly added E):

**A.intent (5 sub-items, in order)**:
1. Fact/Decision (intent_fact_or_decision)
2. Scope (scope_project_or_industry)
3. Project root directory (project_root)
4. Target document type (doc_type)
5. Action (action_intent: query / generate / update / delete)

**E.intent_detail (New · Required when action_intent = generate/update)**:
- 4-Choice-1 Creation Mode: E1 Based on existing materials / **E2 Brand-new independent** / E3 Incremental update / E4 Mimic other
- See `../intent-clarification/references/intent_detail.md` for details

---

## Output Location Convention

| Output         | Location                                                         |
| ------------ | ------------------------------------------------------------ |
| Final formal document | `<项目根>/03_技术文档及评审/<corresponding subdirectory>/<document name>.md`      |
| Change record     | `<项目根>/06_变更及暂停/变更记录.md` (append)               |
| Intermediate draft  | `<工作根>/.aiassistive/output/<项目号>/<document name>_草稿.md` |

---

## ⚠️ Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Writing Code)

**Forbidden** to skip clarification or violate the clarification order in the following scenarios:

- ❌ action_intent = "generate" but E.intent_detail not asked (don't know if it's "based on materials" or "brand-new") → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 5 business materials not asked → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 10 technical points not asked → considered an anti-pattern
- ❌ Pre-Sales Proposal / external material scenario but still writing "specific fields/interfaces/table structure" → considered an anti-pattern
- ❌ Only when user asks "why didn't you ask" do you go back and ask clarification → considered an anti-pattern (should be asked in the first clarification)
- ❌ Skipping E.intent_detail to directly ask doc_type → considered an anti-pattern (order reversed)

### ⚠️ Differentiated Anti-Pattern Redline by Document Type (2026-06-XX Second Reinforcement · Read Before Writing Code)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to have "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder (Q3 decision)
- ❌ **Forbidden** to use "**To Be Supplemented (待补)**：<field name>" as placeholder
- ❌ **Forbidden** to continue writing when any of the 5 business materials is unfilled (All 5 required, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any of 5 items unfilled → still taking X1 path to write outline → considered an anti-pattern
- ✅ User **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ User fills in all 5 business materials → take the X1 path to write the complete proposal

#### C. Administrative Documents (Weekly Reports / Meeting Minutes / Change Records)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal with any of 5 items unfilled and **continuing** to take X1 path to write outline → considered an anti-pattern
- ❌ Pre-Sales Proposal with a chapter outline full of "To Be Supplemented (待补)" → considered an anti-pattern
- ❌ Pre-Sales Proposal using "Example content" or "Industry general" as placeholder → considered an anti-pattern
- ❌ Mechanically applying "To Be Supplemented (待补)" to Pre-Sales Proposal → considered an anti-pattern

---

## Future Extensions (Reserved, Not Implemented)

- Program/Portfolio Management (PgMP/MSP)
- Agile Dual-Track (Scrum/SAFe)
- Quantitative Project Management (QPM/CMMI)
- AI-Assisted Decision Making (based on historical project databases)

---

## Resource References

- Project root directory and subdirectory mapping table: `references/project_root_index.md`
- 策划表 subtag description template: `references/planning_sheet_subtag_template.md`
- Decision advisory template: `references/decision_advisory_template.md`
- **Meta description skill (each skill in the suite introduction)**: `../project-doc-overview/SKILL.md`
- **Unified clarification protocol**: `../intent-clarification/SKILL.md`
  - intent 5 sub-items: `../project-doc-query/references/intent.md`
  - environment 10 technical points: `../project-doc-outline/references/tech_*.md`
- .project log management: append operation records to `.project/<项目号>/project_log.md` and clarification rows to `.project/<项目号>/clarification_log.md`

    $SKILL_PROJECT_PROJECT_DOC_HUB_BODY$,
    TRUE,
    1
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-query',
    '',
    '',
    'Use when the user asks questions about a software-engineering project''s documents, milestones, deliverables, review schedule, or wants PMO-level advisory — applies three-layer framework overlay (PMP framework layer + PRINCE2 implementation layer + Systems Analyst practice layer) and forces intent-clarification (fact vs decision) before answering',
    'app/skills/project-doc-query/SKILL.md',
    'app/skills/project-doc-query',
    $SKILL_PROJECT_PROJECT_DOC_QUERY_BODY$
## Keywords (关键词)

- 事实查询 (factual-query)
- 决策建议 (decision-advisory)
- PMP框架 (pmp-framework)
- PRINCE2 (prince2)
- 系统分析师 (systems-analyst)
- 三层框架 (three-layer-framework)
- 评审计划 (review-plan)
- 框架叠加 (framework-overlay)

# Project Doc Query (Query / Consultation)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: This skill is currently at **V1 Basic Capability Version**, will be extended to Program/Agile/Quantitative Management in the future.

---

## ⚠️ Anti-Pattern Redline (Read Before Writing Code · 2026-06-11 Reinforcement)

**Forbidden** to use in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly reading xlsm/xlsx
- ❌ `from docx import Document` directly reading docx
- ❌ `from pypdf import PdfReader` directly reading pdf
- ❌ `import csv` / `import json` / `import email` directly reading csv/json/eml

**Must** be changed to invoke `explore(...)` for reading project files/attachments.

### Quick Entry (To Avoid Writing One-Off Scripts)

| Pain Point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need to search within file content | Use `explore(file_path="<path>", keyword="<keyword>")` |
| Need structured output | `explore(...)` returns readable text； process it directly |

**Code violating this constraint is considered an anti-pattern** and should be rewritten to call `explore(...)`.

---

## Overview

Provides answers for two types of questions about software-engineering projects: **facts/data** and **decision advisory**, applying the **PMP + PRINCE2 + Systems Analyst three-layer framework overlay**.

Before answering, **must** first do "intent clarification" (fact vs decision)； the answer **must** explicitly mark the framework used.

---

## Trigger Conditions

- User asks "what's in the project / when to deliver / who's responsible / how are reviews arranged"
- User asks "what should this document contain / how to determine test coverage / how to handle risks"
- User wants PMO-level advisory

---

## Rigid Constraints

1. **Clarification must go through intent-clarification**: When this skill starts, **must** invoke `intent-clarification` skill (see references/intent.md for details). **Forbidden** to ask "fact/decision" or "project root" inline within SKILL.md.
2. **Mandatory framework tag**: First line of each answer outputs `【Framework: {PMP|PRINCE2|Systems Analyst} · {Framework Layer|Implementation Layer|Practice Layer}】`.
3. **Traceable evidence**: All fact-type answers must attach "project evidence" — 策划表 subtag name + document path + row/cell.
4. **Three-layer framework overlay** (mutually non-conflicting):
   - **PMP Framework Layer**: 5 Process Groups / 10 Knowledge Areas (provides "management system panorama")
   - **PRINCE2 Implementation Layer**: 7 Principles / 7 Themes / 7 Processes (provides "how to do it specifically")
   - **Systems Analyst Practice Layer**: 5 Major Modules (System Planning/Requirements Analysis/System Design/Test & Maintenance/Informatization) (provides "software engineering practice")
5. **Strictly forbid fabrication**: All numbers, dates, people names in answers must come from project materials； invoke `intent-clarification` for the data dimension when materials are missing.

---

## Core Flow

```
Step 1  Invoke intent-clarification skill (clarify intent + project root + scope)
   ├─ 5 sub-items see references/intent.md
   └─ Re-ask when necessary during flow (clarification is re-entrant)
   ↓
Step 2  Load project materials per directory conventions (use `explore(...)` to read files)
   ↓
Step 3  If fact/data: directly give data + evidence
         If decision: select framework → reference framework cheat sheet → give advice (with project evidence)
   ↓
Step 4  Mark framework tag + data source
   ↓
Step 5  Append operation record to `.project/<项目号>/project_log.md`
```

---

## Framework Selection Decision Tree

| Scenario | Priority Framework | Layers |
|---|---|---|
| Review/deliverable arrangement | PMP · Framework Layer (Schedule Management) | + PRINCE2 Implementation Layer (Management Stage Boundaries) |
| Scope/change control | PRINCE2 · Implementation Layer (Change Theme) | + PMP (Scope/Change/Integration) |
| Quality/test | Systems Analyst · Practice Layer (Test & Maintenance) | + PMP (Quality Management) + PRINCE2 (Quality Theme) |
| Risk | PMP · Framework Layer (Risk Management) | + PRINCE2 (Risk Theme) |
| Resource/cost | PMP · Framework Layer (Resource/Cost) | + PRINCE2 (Business Case Theme) |
| Requirements analysis | Systems Analyst · Practice Layer (Requirements Analysis) | + PMP (Scope) |
| Architecture/design | Systems Analyst · Practice Layer (System Design) | + PMP (Scope/Schedule) |
| Implementation/deployment | Systems Analyst · Practice Layer (Implementation O&M) | + PMP (Executing) + PRINCE2 (Delivery Theme) |
| Closing/acceptance | PMP · Framework Layer (Closing Process Group) | + PRINCE2 (Continued Business Validation) |

---

## Key File Loading Method

- **All file-reading actions MUST use** `explore(...)` to read project files/attachments
- PDF / eml extracted text < 100 characters is considered a scanned document → prompt user to provide a readable version

---

## Resource References

- Process clarification (intent 5 sub-items, scheduled by intent-clarification): `references/intent.md`
- Framework cheat sheets: `references/framework_pmp_quick_reference.md`, `references/framework_prince2_quick_reference.md`, `references/framework_systems_analyst_quick_reference.md`
- Framework selection decision tree: `references/framework_selection_decision_tree.md`
- 策划表 field cheat sheet: `references/planning_sheet_field_quick_reference.md`
- Document type directory cheat sheet: `references/document_type_directory_quick_reference.md`
- Review plan extraction method: `references/review_plan_extraction_method.md`
- Meta description (each skill in the suite introduction): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Future Extensions (Reserved)

- Program/Portfolio (PgMP/MSP)
- Agile Dual-Track (Scrum/SAFe)
- Quantitative Management (QPM/CMMI)
- AI-Assisted Decision Making (based on historical project databases)

    $SKILL_PROJECT_PROJECT_DOC_QUERY_BODY$,
    TRUE,
    2
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-outline',
    '',
    '',
    'Use when the user wants a chapter outline (no body content) for any of the 10 supported software-engineering deliverable types (Pre-Sales Proposal / Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan) — picks the corresponding reference template and applies software-engineering standard chapter structure',
    'app/skills/project-doc-outline/SKILL.md',
    'app/skills/project-doc-outline',
    $SKILL_PROJECT_PROJECT_DOC_OUTLINE_BODY$
## Keywords (关键词)

- 文档大纲 (document-outline)
- 章节结构 (chapter-structure)
- 10种文档 (ten-document-types)
- 售前方案 (pre-sales-proposal)
- 实施细节 (implementation-detail)
- 价值主张 (value-proposition)
- 软件工程规范 (software-engineering-standard)
- 创作模式 (creation-mode)

# Project Doc Outline (Document Outline)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: V1 Basic Capability Version.

## Overview

Selects the corresponding reference template by target document type, outputs **chapter-level outline** (without body content).

The outline must conform to software-engineering standards (GB/T 8564, ISO/IEC/IEEE 42010, ISO 21500), and **must not contain any fabricated body content**.

---

## Trigger Conditions

- User says "write a test plan outline"
- User says "what chapters should an implementation plan have"
- User provides target document type + needs "see outline first"

## Not Applicable

- User wants "complete document" (switch to `project-doc-write`)
- User only asks "what documents does the project have" (switch to `project-doc-query`)

---

## Rigid Constraints

1. **Outline ≠ Body**: Only output chapter titles (level 1/2), do not write body
2. **Chapter numbering convention**: Level 1: 1, 2, 3； Level 2: 1.1, 1.2； Level 3: 1.1.1 (when necessary)
3. **Each chapter must explain**: purpose (what problem this chapter solves) + required sub-sections (if any spec)
4. **Reference template source**: Default extracts chapters from `<项目根>/03_技术文档及评审/01_实施方案/*.docx`； if empty, fall back to 02 Requirements → 03 High-Level
5. **Extraction method**: Use `explore(...)` to read existing docx files and extract chapter structure
6. **Environment/Technology/Compliance clarification required**: Before writing the outline, **must** invoke `intent-clarification` (C.environment dimension, 10 technical point references: tech_hardware.md / tech_software.md / tech_database.md / tech_network.md / tech_deployment.md / tech_third_party_ops.md / tech_security_level.md / tech_localization.md / tech_architecture.md / tech_localization_list.md)
   - Even if user has uploaded materials, **still must ask** and completely cite the original + mark source file + line number, let user confirm "whether to write based on existing info"
   - User answers "TBD/待定" → re-ask "whether to stop outline generation / provide detailed information"
   - Asking result is recorded to `.project/<项目号>/clarification_log.md`
   - Skipping this step and directly writing the outline is considered an anti-pattern

---

## Supported 10 Document Types

| # | Type | Reference Template |
|---|---|---|
| 1 | Pre-Sales Proposal | `references/outline_pre_sales_proposal.md` |
| 2 | Requirements Specification | `references/outline_requirements_specification.md` |
| 3 | High-Level Design Specification | `references/outline_high_level_design_specification.md` |
| 4 | Detailed Design Specification | `references/outline_detailed_design_specification.md` |
| 5 | Implementation Plan | `references/outline_implementation_plan.md` |
| 6 | Test Plan | `references/outline_test_plan.md` |
| 7 | Test Report | `references/outline_test_report.md` |
| 8 | Acceptance Report | `references/outline_acceptance_report.md` |
| 9 | Implementation & Deployment Plan | `references/outline_implementation_deployment_plan.md` |
| 10 | Training Plan | `references/outline_training_plan.md` |
| — | Other Process Documents | `references/outline_other_process_documents.md` |

---

## Core Flow (2026-06-XX Second Reinforcement · Dispatch by E.intent_detail · With X3 Exit)

```
Step 0  [Required · Fixed order] Invoke intent-clarification
   ├─ Step 0-a  E.intent_detail (4-Choice-1 Creation Mode) —— Required
   ├─ Step 0-b  A.intent (doc_type) —— Required
   └─ Step 0-c  C.environment
       ├─ E1/E3/E4 → 10 technical points (fill as needed)
       └─ E2      → 10 technical points + **5 business materials required** (see tech_value_proposition.md)
   ↓
Step 0-d  [2026-06-XX New · Pre-Sales Proposal 5-item all-required validation] (Required when E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 0-e
   ├─ Any item unfilled → [X3 Exit] return 5-item required checklist + (a) supplement / (b) hold
   │   └─ After X3 exit **do not** enter subsequent Step 1-6, **do not** load outline, **do not** write body
   └─ E2 + other doc_type → take original "all 5 items required" constraint (**do not** force X3 exit, **do not** forbid "To Be Supplemented (待补)" placeholder)
   ↓
Step 0-e  [Select version by E]
   ├─ E1/E3/E4 → take corresponding reference template's "Version A"
   └─ E2      → 走对应 reference 模板的"版本 B"（如 outline_pre_sales_proposal.md 版本 B）
   ↓
Step 1  Receive target document type + Creation Mode (E)
   ↓
Step 2  Load corresponding reference template (select version by E)
   ↓
Step 3  (Optional) Extract format template from existing similar docx in project (use `explore(...)`)
   ├─ E1/E3/E4 → read docx in project and extract chapter structure
   └─ E2      → skip (no project materials)； optional "reference industry-general docx"
   ↓
Step 4  Output "chapter-level" outline (no body)
   ├─ E1/E3/E4 → implementation-detail oriented
   ├─ E2 + Pre-Sales Proposal → value-proposition oriented (embed "Customer Value" + "Relative Advantage" at end of each chapter)； **"To Be Supplemented (待补)" placeholder not allowed**
   └─ E2 + other doc_type → value-proposition oriented； "To Be Supplemented (待补)" placeholder **only** used when user has explicitly agreed
   ↓
Step 5  Mark "Purpose" and "Required sub-section" hints at end of each chapter
   ├─ E1/E3/E4 → data source marking
   ├─ E2 + Pre-Sales Proposal → data source marking (**not** using "**To Be Supplemented (待补)**" placeholder)
   └─ E2 + other doc_type → data source marking / "**To Be Supplemented (待补)**" placeholder (when user has explicitly agreed)
   ↓
Step 6  Append operation record to `.project/<项目号>/project_log.md`
```

### Future Extension: X2 Company Sales Archive Library (To Be Implemented · 2026-06-XX Reserved Interface)

**Goal**: When the company sales archive library is available, the X2 path can be taken under E2 Pre-Sales Proposal (auto-extract needed materials → take X1 path to write complete proposal, **do not** trigger X3 exit).

**Interface Reserved**:
- Library path: `<TBD · to be specified by company>` (Recommended: `<company archive root>/sales_archive/<industry>/<client>/<project>/`)
- Library-invoking method: `<TBD>` (Recommended: use `explore(...)` for unified file loading)
- Extraction field mapping: #11-15 business materials ↔ corresponding fields in sales archive
- Status: **Not implemented** in this round； if library is available in the future, this skill in Step 0-d will auto-detect library existence and dispatch

**Current Default Behavior**: Library does not exist → auto-degrade to X1 (user provides) or X3 (exit)

---

## Resource References

- 10 outline references: `references/outline_*.md`
- 10 technical point references (scheduled by intent-clarification): `references/tech_*.md`
- Meta description (each skill in the suite introduction): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Anti-Pattern Redline (Rigid Constraint · 2026-06-11 Reinforcement · Read Before Writing Code)

**Forbidden** to use in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly reading xlsm/xlsx
- ❌ `from docx import Document` directly reading docx (for chapter extraction)
- ❌ `import csv` / `import json` directly reading csv/json

**Must** be changed to invoke `explore(...)` for reading project files/attachments:

| Scenario | Tool |
|---|---|
| Extract chapters from in-project docx as format template | `explore(file_path="<path>")` |
| Read other project files | `explore(file_path="<path>")` |

### Quick Entry (To Avoid Writing One-Off Scripts)

| Pain Point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need structured output | Process `explore(...)` result directly |

**Code violating this constraint is considered an anti-pattern** and should be rewritten to call `explore(...)`.

---

## ⚠️ Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Writing Code)

**Forbidden** to skip clarification or violate the clarification order in the following scenarios:

- ❌ action_intent = "generate" but E.intent_detail not asked (don't know if it's "based on materials" or "brand-new") → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 5 business materials not asked → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 10 technical points not asked → considered an anti-pattern
- ❌ E2 Pre-Sales Proposal scenario not selecting outline Version B (mistakenly using Version A) → considered an anti-pattern
- ❌ Pre-Sales Proposal / external material scenario but still writing "specific fields/interfaces/table structure" → considered an anti-pattern
- ❌ Only when user asks "why didn't you ask" do you go back and ask clarification → considered an anti-pattern (should be asked in the first clarification)
- ❌ Skipping E.intent_detail to directly ask doc_type → considered an anti-pattern (order reversed)
- ❌ All 5 business materials as "To Be Supplemented (待补)" and still writing body → considered an anti-pattern (violates `<HARD-GATE: NO FABRICATION>`)

### ⚠️ Differentiated Anti-Pattern Redline by Document Type (2026-06-XX Second Reinforcement · Read Before Writing Code)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to have "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder
- ❌ **Forbidden** to use "**To Be Supplemented (待补)**：<field name>" as placeholder
- ❌ **Forbidden** to continue writing when any of the 5 business materials is unfilled (All 5 required, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any of 5 items unfilled → still taking X1 path to write outline → considered an anti-pattern
- ✅ User **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ User fills in all 5 business materials → take the X1 path to write the complete proposal

#### C. Administrative Documents (Weekly Reports / Meeting Minutes / Change Records)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal with any of 5 items unfilled and **continuing** to take X1 path to write outline → considered an anti-pattern
- ❌ Pre-Sales Proposal with a chapter outline full of "To Be Supplemented (待补)" → considered an anti-pattern
- ❌ Pre-Sales Proposal using "Example content" or "Industry general" as placeholder → considered an anti-pattern
- ❌ Mechanically applying "To Be Supplemented (待补)" to Pre-Sales Proposal → considered an anti-pattern

---

## Future Extensions

- Industry-specific (Government/Finance/Healthcare) outline versions
- Auto-derive project phase document structure from 策划表 WBS

    $SKILL_PROJECT_PROJECT_DOC_OUTLINE_BODY$,
    TRUE,
    3
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-write',
    '',
    '',
    'Use when the user has an approved outline and wants the document body filled in based strictly on existing project artifacts (planning sheet / requirements / contract / plan / weekly report etc.) — generates decision-and-opinion from real project data deltas, never invents content, asks user when info is missing',
    'app/skills/project-doc-write/SKILL.md',
    'app/skills/project-doc-write',
    $SKILL_PROJECT_PROJECT_DOC_WRITE_BODY$
## Keywords (关键词)

- 填充正文 (body-filling)
- 决策与意见 (decision-advisory)
- 严禁虚构 (no-fabrication)
- 数据完整性 (data-integrity)
- 净化规则 (purification-rule)
- word落盘 (word-save)
- 变更记录 (change-log)
- 售前方案 (pre-sales-proposal)

# Project Doc Write (Body Filling + Decision Advisory)

## Hard Rule: No Fabrication

**This skill must NEVER fabricate** any of the following at any stage of execution:
- Person names / dates / numbers / tool names / role signoff table / document status / framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` on the relevant dimension
2. User answers "TBD" / "待定" → re-ask "stop or provide detailed info"
3. User did not specify → **do not write**, **do not auto-fill defaults**

**Strictly forbidden "placeholder for later"**:
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **Pending-fill**: <field-name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md`.

> **Stage**: V1 base capability.

## Overview

On the chapter outline output by `project-doc-outline`, **strictly based on existing project artifacts** fill in the body, and generate "Decision and Opinion" based on the delta between actual values and baseline values from planning sheet / contract / weekly report.

> **Core principle: mechanical work is done by tools； judgments are made by the LLM.**
> Reading planning sheet subtags, extracting docx chapters — all "mechanical work" goes through `explore(...)`； body writing and decision advisory are done by the model.

---

## Trigger Conditions

- User already has an outline (generated by hub or provided by outline)
- User requires "write a complete document based on existing project artifacts"
- User requires "complete/update a document"

---

## Rigid Constraints

1. **Strictly no fabrication**: every body section must have project evidence. Missing evidence → **actively ask** the user.
2. **Format template**: by default extract chapters from `<项目根>/03_技术文档及评审/01_实施方案/*.docx` as the format template.
3. **Decision and Opinion source**: `references/decision_advisory_generation_rule.md` + `references/no_fabrication_redline_checklist.md`.
4. **Multi-framework overlay**: every decision-and-opinion entry must be tagged `【Framework: {PMP|PRINCE2|Systems Analyst} · {layer}】`.
5. **Change log mandatory**: after each document write, **must** append a record to `<项目根>/06_变更及暂停/变更记录.md` (in the canonical planning sheet subtag format).
6. **Read files via `explore(...)`**: forbidden to write one-off scripts in `tmp/` or `D:\` root. Use `explore(file_path="<path>")` to read project files/attachments.
7. **Scanned document detection**: PDFLoader extracts < 100 characters → treat as scanned → ask user to provide a readable version.
8. **TOC mandatory**: every generated .md document **must** contain a `## Table of Contents` section listing 1-3 level heading links (markdown static layer).
9. **Content purification**: when writing body, follow `references/document_content_purification_rule.md` — do not write "Draft for review", do not write "Prepared by/Reviewed by/Approved by" (when planning sheet has not specified), do not write "—" placeholders, do not write empty quotes, do not write tools not mentioned in project artifacts.
10. **Sections without data**: use `**Pending-fill**: [specific explanation]` pattern, do not write "—" placeholders； before writing, use `references/data_integrity_query_template.md` to actively ask the user.
11. **word save-to-disk**: after writing .md **must** convert to .docx via "word operation skill" (e.g. docx-skill) and save to project directory. write **does not** implement markdown → docx itself, **does not** hard-code third-party skill paths. See `references/word_save_to_disk_workflow.md`.

---

## Core Workflow (2026-06-XX Second Reinforcement — By E.intent_detail Branching — With X3 Exit)

```
Step 1  Receive outline (from outline) + E.intent_detail branch identifier
   ↓
Step 1.0  [2026-06-XX New · Pre-Sales Proposal 5-Item All-Required Check] (E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 2
   ├─ Any one not filled → [X3 Exit] return 5-item checklist + (a) supplement / (b) suspend
   │   └─ After X3 exit, **do not** enter Step 2-7, **do not** write body
   └─ Other doc_type → original flow
   ↓
Step 2  Load project artifacts (DocumentLoader)
   ├─ E1/E3/E4 → load project artifacts (planning sheet / requirements / contract etc.)
   └─ E2      → skip project artifact loading (none available)； directly load value_proposition_template.md
   ↓
Step 3  [Key · By E branching] Fill in order of chapters
   ↓
Step 3.0  Judge E.intent_detail branch
   ├─ E1/E3/E4 → Step 3.A Regular Branch
   └─ E2      → Step 3.B New Branch
   ↓
Step 3.A Regular Branch (E1/E3/E4 · Based on artifacts)
   ├─ Content has evidence → write directly
   ├─ Content no evidence → invoke intent-clarification (B.data dimension) **continue to ask user** (D4 decision)
   ├─ User answers concrete content → write on the spot
   ├─ User answers "mark pending first" / "fill in later" → mark "**Pending-fill**: <field-name>" placeholder
   ├─ User answers "not providing for now" → skip that section
   ├─ Data-driven section without data → same as above via B.data
   ├─ Role signoff table / document status → invoke intent-clarification (D.document_attr dimension)
   └─ Content exceeds spec → notify out-of-scope, ask whether to keep
   ↓
Step 3.B New Branch (E2 · 2026-06-XX Second Reinforcement)
   ├─ 3.B.0 [2026-06-XX New] Pre-check: all 5 business materials filled
   │    ├─ Any one not filled → [X3 Exit] **do not** enter 3.B.1-3.B.7
   │    └─ All filled → enter 3.B.1
   ├─ 3.B.1 Load value proposition template (references/value_proposition_template.md)
   ├─ 3.B.2 Fill by outline Version B (value-proposition-oriented, **no implementation details**)
   ├─ 3.B.3 Each chapter structure = Solution Points + **Customer Value** + **Relative Advantage** + **Data Source** (**no** "Pending-fill" section)
   ├─ 3.B.4 [2026-06-XX Modified] **Forbidden** "**Pending-fill**: <field-name>" placeholders (pre-sales proposal is a finished document)
   ├─ 3.B.5 Do not write "how exactly" — only write "why this is the best approach"
   ├─ 3.B.6 Strictly forbidden: "specific fields / interfaces / table structures / duration numbers / team member names / empty quotes"
   └─ 3.B.7 Industry-specific fields (4.1-4.4 chapter names) dynamically replaced by E2 clarification item 12
   ↓
Step 4  Generate "Decision and Opinion" chapter (references/decision_advisory_template.md)
   ├─ E1/E3/E4 → regular decision advisory
   └─ E2 + Pre-Sales Proposal → **do not** generate "Decision and Opinion" chapter (pre-sales proposal has no such chapter)
   ↓
Step 5  Scanned document detection (references/scanned_doc_handling_rule.md)
   ↓
Step 6  Content purification self-check (references/document_content_purification_rule.md)
   ├─ Remove "Draft for review / Draft" status tags
   ├─ Remove "Prepared by / Reviewed by / Approved by" role table (when planning sheet has not specified)
   ├─ Remove "—" placeholder → change to "**Pending-fill**" section (A/C type) / delete entire section (B type, trigger X3 re-review)
   ├─ Remove empty quotes ("advanced/reliable/easy-to-use/secure/scalable" stacked without evidence)
   ├─ [2026-06-XX New] Differentiated purification by document type:
   │    ├─ A type (internal process): "**Pending-fill**: <field-name>" section **retained** (user has explicitly agreed)
   │    ├─ **B type (pre-sales proposal): "**Pending-fill**" section must be deleted** + trigger X3 re-review (violates "pre-sales proposal is a finished document" principle)
   │    └─ C type (administrative): "**Pending-fill**: <field-name>" section **retained** (user has explicitly agreed)
   ├─ E2 extra: remove "specific fields / interfaces / table structures / duration numbers / team member names"
   └─ Remove tools / terms not mentioned in project artifacts
   ↓
Step 7  Output (project directory final save + AIAssistive\output\ draft)
   ├─ 7.1 Save .md to project directory
   ├─ 7.2 [Key] Check whether "word operation skill" is in the current skill library
   │       ├─ Exists → 7.3
   │       └─ Not exists → notify user to install docx-skill, skip 7.3
   ├─ 7.3 Invoke word skill to convert to .docx (apply styles from references/word_format_template_rule.md)
   ├─ 7.4 Save draft to AIAssistive\output\
   └─ 7.5 Append change record (references/change_record_append_format.md)
```

---

## Resource References

- Format template extraction method: `references/implementation_plan_format_template_extraction.md`
- Software engineering document chapter filling spec: `references/software_engineering_doc_section_filling_spec.md`
- Decision advisory generation rule: `references/decision_advisory_generation_rule.md`
- No-fabrication redline checklist: `references/no_fabrication_redline_checklist.md`
- **Word format template rules** (hard-coded, cover / font / line spacing / header-footer / TOC): `references/word_format_template_rule.md`
- **Word save-to-disk workflow** (Step 7 detailed, with docx-skill self-check): `references/word_save_to_disk_workflow.md`
- **Document content purification rules** (do not write "Draft/— placeholder/Prepared by" etc. useless content): `references/document_content_purification_rule.md`
- **Data integrity reference** (Step 4.2.5 active asking, dispatched by intent-clarification):
  - `references/data_missing_section.md`
  - `references/numeric_field_missing.md`
- **Document attribute reference** (role signoff table / document status):
  - `references/role_signoff.md`
  - `references/doc_status.md`
- Meta description (each skill intro): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Coding)

**Forbidden** in the following scenarios to skip clarification or violate clarification order:

- ❌ action_intent = "Generate" but no E.intent_detail asked (do not know "based on artifacts" or "new") → anti-pattern
- ❌ E2 new scenario but did not go through C.environment 5 business materials → anti-pattern
- ❌ E2 new scenario but did not go through C.environment 10 technical points → anti-pattern
- ❌ E2 pre-sales proposal scenario did not go through Step 3.B new branch (mistakenly went Step 3.A regular) → anti-pattern
- ❌ Pre-sales proposal / external material scenario but still writing "specific fields/interfaces/table structures" → anti-pattern
- ❌ User asks "why didn't you ask" then going back to supplement clarification → anti-pattern (should have asked during first clarification)
- ❌ Skipping E.intent_detail to ask doc_type directly → anti-pattern (order reversed)
- ❌ 5 business materials all "Pending-fill" still writing body → anti-pattern (violates `<HARD-GATE: NO FABRICATION>`)

### Anti-Pattern Redline Differentiated by Document Type (2026-06-XX Second Reinforcement · Read Before Coding)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **must** invoke intent-clarification to continue asking user (D4 decision)
- ❌ Missing materials → **do not** ask, directly mark "Pending-fill" placeholder → anti-pattern
- ✅ User **explicitly says "mark pending first"** → allow "**Pending-fill**: <field-name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to use "**Pending-fill**" placeholder (pre-sales proposal is a finished document)
- ❌ **Forbidden** to use "example content / industry generic template / company typical scale" placeholder
- ❌ **Forbidden** to use "**Pending-fill**: <field-name>" as placeholder
- ❌ **Forbidden** to continue writing when any of 5 business materials is not filled (all 5 mandatory, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any 5-item not filled → still going Step 3.B to write body → anti-pattern
- ❌ E2 + Pre-Sales Proposal Step 6 purification self-check when "**Pending-fill**" section not deleted → anti-pattern
- ✅ User **cannot provide materials** → **direct X3 exit**: return X3 refuse-write template + 5-item mandatory checklist
- ✅ User completes 5 business materials → go Step 3.B to write complete proposal

#### C. Administrative Documents (Weekly Report / Minutes / Change Record)
- ✅ Missing materials → **must** invoke intent-clarification to continue asking user (D4 decision)
- ❌ Missing materials → **do not** ask, directly mark "Pending-fill" placeholder → anti-pattern
- ✅ User **explicitly says "mark pending first"** → allow "**Pending-fill**: <field-name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal any 5-item not filled yet **continues** to go Step 3.B to write body → anti-pattern
- ❌ Pre-Sales Proposal written with a body full of "Pending-fill" → anti-pattern
- ❌ Pre-Sales Proposal uses "example content" or "industry generic" placeholder → anti-pattern
- ❌ Mechanically applying "Pending-fill" to pre-sales proposal → anti-pattern

#### Step 6 Purification Self-Check Anti-Patterns
- ❌ A type document "**Pending-fill**: <field-name>" section **mistakenly deleted** (user has explicitly agreed to retain) → anti-pattern
- ❌ B type document "**Pending-fill**" section **not deleted** (pre-sales proposal is a finished document) → anti-pattern
- ❌ Purification self-check list does not distinguish A/B/C 3 types → anti-pattern

---

## Anti-Pattern Redline (Rigid Constraint · 2026-06-11 Reinforcement · Read Before Coding)

**Forbidden** in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly read xlsm/xlsx
- ❌ `from docx import Document` directly read docx
- ❌ `from pypdf import PdfReader` directly read pdf
- ❌ `import csv` / `import json` / `import email` directly read csv/json/eml

**Must** be changed to call `explore(...)` for reading project files/attachments:

| Scenario | Tool |
|---|---|
| Read any file | `explore(file_path="<path>")` |
| Extract docx chapters as format template | `explore(file_path="<path>")` |
| Extract word style baseline | `explore(file_path="<path>")` |

### Quick Entry (Avoid Writing One-Off Scripts)

| Pain point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need structured output | Process `explore(...)` result directly |

**Violations of this constraint are anti-patterns** and should be rewritten as `explore(...)` calls.

---

## Future Extensions

- Auto-derive templates from historical same-type documents
- AI decision advisory scoring (linked with program/PMO database)
- Multi-language version generation

    $SKILL_PROJECT_PROJECT_DOC_WRITE_BODY$,
    TRUE,
    4
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-workflow',
    '',
    '',
    'Use when generating a software-engineering project deliverable end-to-end (from initial user request to final document on disk) — orchestrates the 4-step pipeline (hub → query → outline → write) and provides the work-skill checklist',
    'app/skills/project-doc-workflow/SKILL.md',
    'app/skills/project-doc-workflow',
    $SKILL_PROJECT_PROJECT_DOC_WORKFLOW_BODY$
## Keywords (关键词)

- 端到端工作流 (end-to-end-workflow)
- 4步流水线 (four-step-pipeline)
- hub-query-outline-write (hub-query-outline-write)
- 检查清单 (checklist)
- 落盘规范 (save-to-disk-spec)
- 变更记录 (change-log)
- work-skill (work-skill)
- 不瞎编 (no-fabrication)

# Project Doc Workflow (End-to-End Workflow)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: V1 Basic Capability Version.

## Overview

Orchestrates the requests accepted by `project-doc-hub` into an executable checklist following the 4-step pipeline (query → outline → write → save-to-disk + change record), **guiding the work skill (executing agent) to execute in order**.

> **Core principle: Deterministic things are done by scripts； things requiring judgment are done by the LLM.**

---

## Trigger Conditions

- User wants to "generate a complete project document from 0"
- User wants to "write a complete document based on existing project materials"
- Not applicable: query only / outline only / update only (these go to a single sub-skill)

---

## 4-Step Pipeline

```
┌────────────────────────────────────────┐
│  Step 1  project-doc-hub (Accept + Clarify)   │
│  - Invoke intent-clarification for intent dimension │
│  - Get project root + document type + intent        │
│  - Let user choose when there are multiple projects │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 2  project-doc-query (Material Extraction)    │
│  - Load 策划表 xlsm → extract milestones/review plan  │
│  - Load project root → list existing similar docx   │
│  - Extract docx chapters as format template          │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 3  project-doc-outline (Generate Outline)  │
│  - Invoke intent-clarification for environment dimension │
│  - Pick reference template by document type           │
│  - Output "chapter-level" outline (no body)          │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 4  project-doc-write (Fill + Decisions)  │
│  - Invoke intent-clarification for data/document_attr dimension │
│  - Strictly fill body based on existing project materials          │
│  - Actively ask user when materials are missing                  │
│  - Generate "Decision & Advisory" (with [Framework] tags)     │
│  - Append change record                          │
│  - Append operation record to `.project/<项目号>/project_log.md` │
│  - Output to project directory + intermediate draft               │
└────────────────────────────────────────┘
```

---

## Work Skill Execution Checklist

The executing agent must complete each item in order, after each item change `□` to `☑`:

```
□ Step 1 hub
   □ 1.1 List all projects under root directory
   □ 1.2 User selects project (or already provided)
   □ 1.3 User selects target document type
   □ 1.4 User states intent (generate/update/query)
   □ 1.5 User confirms output location

□ Step 2 query
   □ 2.1 Load 策划表 xlsm (via `explore(...)`)
   □ 2.2 Extract milestones/review plan/P&L analysis/risk register
   □ 2.3 List existing similar docx in project (if any)
   □ 2.4 Extract docx chapters as format template (if any, via `explore(...)`)
   □ 2.5 Scan detection (PDF)

□ Step 3 outline
   □ 3.1 Load outline_*.md reference template
   □ 3.2 Output chapter-level outline
   □ 3.3 User confirms outline

□ Step 4 write
   □ 4.1 Fill chapters in order
   □ 4.2 Mark data source for each chapter
   □ 4.3 Actively ask user when materials are missing (do not fabricate)
   □ 4.4 Generate "Decision & Advisory" chapter (with [Framework] + [Strength] + [Data Source])
   □ 4.5 Self-check no-fabrication redline
   □ 4.6 Content purification self-check (remove "draft/— placeholder/compile-review" boilerplate, see write/references/document_content_purification_rule.md)
   □ 4.7 Append change record to <项目根>/06_变更及暂停/变更记录.md
   □ 4.8 Output final document to project directory (.md + .docx)
        ├─ 4.8.1 Save .md to project directory
        ├─ 4.8.2 [Invoke word skill to convert to .docx] — Model self-checks whether current skill library has "a skill that operates Word" (docx-skill / word-skill / docx-generator etc.)
        │        ├─ Exists → Invoke that skill to convert to .docx
        │        └─ Not exists → Prompt user to install docx-skill, only save .md
        ├─ 4.8.3 Save intermediate draft to AIAssistive\output\
   □ 4.9 Report output paths
```

---

## Key Execution Constraints

1. **Must follow Step order**: Cannot skip Step 1 clarification
2. **Each Step must complete before moving to next**: Especially Step 2's material extraction
3. **Step 4.3 is the core constraint**: Must ask when materials are missing, cannot make own decisions
4. **Step 4.6 is mandatory output**: Change record must be written
5. **Dual output**: Project directory (formal) + .aiassistive/output/ (intermediate draft)

---

## Resource References

- End-to-end workflow detailed description: `references/end_to_end_workflow.md`
- Output file naming convention: `references/output_file_naming_convention.md`

---

## Future Extensions

- Multi-document concurrent generation (parallel via subagent)
- Integration with PMO database (auto-fill historical project data)
- Automatic review email generation

    $SKILL_PROJECT_PROJECT_DOC_WORKFLOW_BODY$,
    TRUE,
    5
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'intent-clarification',
    '',
    '',
    'Use whenever any project-doc skill (query/outline/write/workflow/data-skill) needs to confirm something with the user — unified protocol: scan project artifacts first, show prior answers, cite source+line, handle ''TBD/待定'' by re-asking. Re-entrant: can be invoked from any step, not just the start.',
    'app/skills/intent-clarification/SKILL.md',
    'app/skills/intent-clarification',
    $SKILL_PROJECT_INTENT_CLARIFICATION_BODY$
## Keywords (关键词)

- 意图澄清 (intent-clarification)
- 询问协议 (clarification-protocol)
- 多维度分流 (multi-dimension-dispatch)
- 强制澄清 (mandatory-clarification)
- 日志持久化 (log-persistence)
- 待定处理 (pending-handling)
- 项目级澄清 (project-level-clarification)
- 反模式红线 (anti-pattern-redline)

# Intent Clarification (Project-Level Clarification Protocol · For Model)

> **Target reader**: **The model** (not the user). After loading this skill, the model should be able to automatically:
> - Know that any "ask the user" action must first invoke this skill
> - Know where clarification logs are stored (`.project/<project_id>/`, **NOT inside the skill**)
> - Know the 4 major question scenarios (intent/data/environment/document_attr)
> - Know it is re-entrant (can be invoked at any time during the flow)

<HARD-GATE>
Do NOT write any outline / document / answer without first invoking this skill and completing clarification. Each clarification produces a row in `<用户工作根>/.project/<project_id>/clarification_log.md` (NOT inside the skill).
</HARD-GATE>

<HARD-GATE: NO FABRICATION>
Do NOT fabricate ANY content under ANY circumstance. When a fact is missing from project materials:
1. Mark as "**To Be Supplemented (待补)**：<specific field name>" (NEVER "—" / "TBD" / "待定" used alone)
2. Cite source field: "No project material supports this (无项目资料支撑)"
3. Append row to `<用户工作根>/.project/<project_id>/clarification_log.md` using file write tools
4. NEVER write a guess, even a plausible one

This applies to:
- People names (if 策划表 does not list "张三", do not write "张三")
- Dates (if 策划表 does not list "2025-12-31", do not write it)
- Numbers (test case count / duration / cost with no evidence → "**To Be Supplemented (待补)**")
- Tool names (if the project does not mention "ZenTao (禅道)" / "Git" / "DingTalk (钉钉)", do not write them)
- Role signoff (no specific name → stay silent, do not write)
- Doc status (user did not say → stay silent, do not write "Draft for Review (评审稿)")
- Framework tags (PMP/PRINCE2/Systems Analyst tags must be accurate)

When in doubt: ASK, don't WRITE.
</HARD-GATE: NO FABRICATION>

---

<HARD-GATE: Differentiated "To Be Supplemented (待补)" Handling by Document Type · 2026-06-XX Second Reinforcement>

> The semantics of "To Be Supplemented (待补)" placeholder are **classified by document type**. **Not** every document type can use the "To Be Supplemented (待补)" placeholder.

### A. Internal Process Documents (Allow "To Be Supplemented (待补)" Placeholder, but Must Ask User First)

**Applies to**: Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan

- When materials are missing → **Must first** invoke `intent-clarification` taking the B.data dimension (D4 decision) to ask the user
- User provides specific content → write it directly
- User answers "To Be Supplemented (待补)" / "Mark as To Be Supplemented for now" / "I will fill it in later" → allowed to use "**To Be Supplemented (待补)**：<field name>" placeholder
- User answers "Will not provide" / "Do not write this chapter" → skip that chapter
- **Forbidden**: When materials are missing, **not** asking the user, and directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern

### B. External Marketing Materials (**Forbidden to use "To Be Supplemented (待补)" Placeholder**) · 2026-06-XX New Rule

**Applies to**: Pre-Sales Proposal (售前方案) (the only currently applicable type)

- ❌ **Forbidden** to use "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document for external submission)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder
- ❌ **Forbidden** to continue writing the body when any of the 5 business materials (#11-15) is unfilled
- ✅ When user **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ After user fills in all 5 business materials → take the X1 path to write the complete proposal
- See `references/intent_detail.md` section "E2 Pre-Sales Proposal 3-Choice-1 Decision" for details

### C. Administrative Documents (Allow "To Be Supplemented (待补)" Placeholder, but Must Ask User First)

**Applies to**: Weekly Reports / Meeting Minutes / Change Records

- When materials are missing → **Must first** invoke `intent-clarification` taking the B.data dimension to ask the user
- User provides specific content → write it directly
- User answers "To Be Supplemented (待补)" / "Mark as To Be Supplemented for now" → allowed to use "**To Be Supplemented (待补)**：<field name>" placeholder
- **Forbidden**: When materials are missing, **not** asking the user, and directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern

### Anti-Patterns (Strictly Forbidden for All Type B Documents)

- ❌ Type B documents containing "**To Be Supplemented (待补)**" placeholder → must be deleted and trigger X3 exit
- ❌ Type B documents continuing to write the body when any of the 5 business materials is unfilled
- ❌ Type B documents using "Example content" or "Industry general" as placeholder
- ❌ Type A/C documents **not** asking the user when materials are missing, and directly marking "To Be Supplemented (待补)"
- ❌ Mechanically applying "To Be Supplemented (待补)" to Type B documents

### Decision Matrix Quick Reference

| Document Type | When Materials Missing | When User Answers "To Be Supplemented (待补)" | When User Answers "Will Not Provide" |
|---|---|---|---|
| A. Internal Process Documents | Must ask | Allowed "**To Be Supplemented (待补)**：<field name>" | Skip that chapter |
| **B. External Marketing Materials** | **Exit X3** | **Exit X3** | **Exit X3** |
| C. Administrative Documents | Must ask | Allowed "**To Be Supplemented (待补)**：<field name>" | Skip that chapter |

</HARD-GATE: Differentiated "To Be Supplemented (待补)" Handling by Document Type>

---

## Step 0: Scenario Dispatch (Required · First Step)

**The first thing to do when a user question comes in**: identify the scenario type.

| Scenario | User Phrasing Characteristic | Required Question Dimensions (**Fixed Order**) |
|---|---|---|
| `A0.technical_doc` | "Write XX plan/design/test/deployment/training" | **1. E.intent_detail (4-Choice-1 Creation Mode)** → 2. A.intent (doc_type) → 3. C.environment (10 technical points + 5 business materials for E2 scenario) |
| `A0.administrative` | "Change record / weekly report / meeting minutes" | 1. E.intent_detail → 2. A.intent (doc_type) → 3. D.document_attr |
| `A0.factual_query` | "When / Who / How many / Where" | A.intent (fact/decision) (E.intent_detail not applicable) |
| `A0.advisory` | "Suggest / Should / Which / How to choose" | A.intent (decision) + three-layer framework (E.intent_detail not applicable) |

**If unable to identify**: actively ask the user "Do you want to write a document / query facts / get advice?"

**Key points**:

- Technical document scenarios **must first ask E.intent_detail** (4-Choice-1 Creation Mode), then ask A.intent 5 sub-items, finally ask C.environment
- Brand-new independent generation (E2) scenarios **must** additionally ask the 5 business material sub-items of C.environment (see `references/tech_value_proposition.md`)
- Must not skip E.intent_detail to directly ask doc_type； must not skip E.intent_detail when action_intent = "Generate"
- 5 question dimensions (intent/data/environment/document_attr/intent_detail) are named alphabetically, **E.intent_detail is the newly added highest-priority dimension**

## Where to Log (Key: All Process Files Are Outside the Skill)

**Runtime records MUST go to** (not placed inside the skill):

```
<用户工作根>/.project/<project_id>/          ← Sibling to project directory
├── project_log.md         ← Main operation log (1 entry appended per skill flow end)
├── clarification_log.md   ← Clarification log (1 entry appended per Q/A)
├── drafts/                ← Intermediate drafts (drafts from the write flow)
└── session_<YYYY-MM-DD>.md ← Session log (optional)
```

**Do NOT** create or modify files inside the skill itself for runtime records.

## When to Invoke

- **At the start of any skill flow** that needs user input (project root, doc type, intent)
- **At any step** when a new question emerges (missing data, ambiguous requirement, environmental constraint)
- **When prior answer in log** is ambiguous or outdated
- **NOT for trivial one-word confirmations** that the user has already implicitly given

## Checklist

1. **Identify dimension** — see `references/clarification_dimensions_checklist.md` (4 scenarios: intent / data / environment / document_attr)
2. **Read existing log** at `<用户工作根>/.project/<project_id>/clarification_log.md`
   - Prior answer exists → show it + ask "confirm or update"
3. **Scan project artifacts** for evidence (策划表/contract/requirements) using `explore(...)`
   - If found → cite file + line + show excerpt
4. **Ask user** using the dimension-specific template
5. **Handle "TBD/待定"** — re-ask: "stop or provide details"
6. **Append row to log** to `<用户工作根>/.project/<project_id>/clarification_log.md` using file write tools
7. **Return value** to calling skill
8. **After skill flow ends** — append to `<用户工作根>/.project/<project_id>/project_log.md` using file write tools

## 5 Dimensions (2026-06-XX Reinforcement · Added E.intent_detail)

| Scenario | Sub-items | Reference template |
|---|---|---|
| A. Process Clarification (intent) | 5 sub-items (see file) | `../project-doc-query/references/intent.md` |
| B. Data Integrity (data) | Chapters with no data / numeric fields missing | `../project-doc-write/references/data_missing_section.md`<br>`../project-doc-write/references/numeric_field_missing.md` |
| C. Environment/Technology/Compliance/Business (environment) | **10 technical points + 5 business materials (Required for E2)** | `../project-doc-outline/references/tech_*.md` (10 files)<br>`../project-doc-outline/references/tech_value_proposition.md` (5 business materials) |
| D. Document Attributes (document_attr) | Role signoff / Document status | `../project-doc-write/references/role_signoff.md`<br>`../project-doc-write/references/doc_status.md` |
| **E. Creation Mode (intent_detail) · New** | **4-Choice-1 Generation/Writing Mode (E1/E2/E3/E4)** | **`./references/intent_detail.md`** |

## Key Principles

1. **One dimension per call** - Don't bundle intent + data + env
2. **Multiple choice preferred** - 4 options max
3. **Show prior first** - Avoid re-asking
4. **Cite source+line** - When from artifacts
5. **TBD/待定 is not an answer** - Re-ask: stop or provide
6. **Persist to log** - All Q/A in `<用户工作根>/.project/<project_id>/clarification_log.md`
7. **Re-entrant** - Can be called from any step
8. **All files outside skill** - Process files all in `.project/<project_id>/`, **NOT inside the skill**

## Anti-Patterns

| Anti-Pattern | Consequence |
|---|---|
| Asking inline within SKILL.md without invoking this skill | 5 inconsistent clarifications |
| Skipping clarification and giving "should/suggest" directly | Violates HARD-GATE |
| Treating "TBD/待定" as a valid answer and continuing | Incomplete outline causes rework later |
| Not recording clarification results | Repeated questions across skills |
| Bundling multiple dimensions in one ask | Answers interfere with each other |
| Writing process files under skill/references/ | Violates "process files externalized" principle |

## After Clarification

After the calling skill receives the return value:
- Use the return value to continue
- Do not ask the same dimension again (unless user explicitly says "ask again")
- Inform subsequent skills of the path to clarification_log.md
- After the flow ends, append to `<用户工作根>/.project/<project_id>/project_log.md` using file write tools

    $SKILL_PROJECT_INTENT_CLARIFICATION_BODY$,
    TRUE,
    6
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;
-- <<< END_INLINE_SEED_PROJECT_SKILLS


-- ========== 16. message_feedback（2026-07-02 新增：AI 回复的赞/踩反馈入库）==========
-- 用户对 AI 回复的赞/踩评价持久化表。
--   * 赞（feedback_type='like'）直接入库，不要求任何附加内容
--   * 踩（feedback_type='dislike'）弹窗收集 problem_type / problem_description / expected_answer
--   * user_id 通过 auth_middleware 注入到 request.state.user_id；session_id/message_id 由前端传入
--   * ON DELETE CASCADE：用户被删除时其全部反馈记录一并删除
CREATE TABLE IF NOT EXISTS message_feedback (
    id                   SERIAL PRIMARY KEY,
    user_id              INTEGER       NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    session_id           VARCHAR(100)  NOT NULL,
    message_id           VARCHAR(64)   NOT NULL,
    feedback_type        VARCHAR(16)   NOT NULL,
    problem_type         VARCHAR(32)   DEFAULT NULL,
    problem_description  TEXT          DEFAULT NULL,
    expected_answer      TEXT          DEFAULT NULL,
    message_content      TEXT          DEFAULT NULL,
    ai_reply             TEXT          DEFAULT NULL,
    agent_name           VARCHAR(64)   DEFAULT NULL,
    user_agent           VARCHAR(255)  DEFAULT NULL,
    created_at           TIMESTAMP     NOT NULL DEFAULT NOW(),
    CONSTRAINT message_feedback_type_chk CHECK (feedback_type IN ('like', 'dislike'))
);

-- 防御性清理：同一用户同一消息的反馈只保留最新一条（id 最大），否则后续唯一索引会失败
DELETE FROM message_feedback a
WHERE EXISTS (
    SELECT 1 FROM message_feedback b
    WHERE b.user_id = a.user_id
      AND b.session_id = a.session_id
      AND b.message_id = a.message_id
      AND b.id > a.id
);

-- 唯一约束：同一用户对同一条消息只能有一种反馈，确保赞/踩互斥
CREATE UNIQUE INDEX IF NOT EXISTS idx_message_feedback_user_session_message
    ON message_feedback(user_id, session_id, message_id);

CREATE INDEX IF NOT EXISTS idx_message_feedback_user_id     ON message_feedback(user_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_session_id  ON message_feedback(session_id);
CREATE INDEX IF NOT EXISTS idx_message_feedback_type        ON message_feedback(feedback_type);
CREATE INDEX IF NOT EXISTS idx_message_feedback_created_at  ON message_feedback(created_at DESC);

-- ========== 17. agent_task_schedules / agent_task_runs（智能体定时任务）==========
-- 应用内调度器的任务定义与执行历史。数据库是任务定义真相源；服务启动时加载 enabled 任务。
-- 所有 DDL 使用 IF NOT EXISTS / IF NOT EXISTS（索引），幂等可重复执行。
CREATE TABLE IF NOT EXISTS agent_task_schedules (
    id                    SERIAL PRIMARY KEY,
    name                  VARCHAR(200) NOT NULL,
    description           TEXT DEFAULT NULL,
    agent_name            VARCHAR(100) NOT NULL REFERENCES agents(name) ON DELETE CASCADE,
    prompt                TEXT NOT NULL,
    cron_expression       VARCHAR(100) NOT NULL,
    timezone              VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
    enabled               BOOLEAN NOT NULL DEFAULT TRUE,
    created_by_user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    context_overrides     JSONB DEFAULT '{}',
    max_concurrent_runs   INT NOT NULL DEFAULT 1,
    last_run_at           TIMESTAMP DEFAULT NULL,
    next_run_at           TIMESTAMP DEFAULT NULL,
    created_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at            TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_task_schedules_max_concurrent_chk CHECK (max_concurrent_runs >= 1)
);

CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_agent_name  ON agent_task_schedules(agent_name);
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_enabled     ON agent_task_schedules(enabled);
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_next_run_at ON agent_task_schedules(next_run_at);
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_created_by_user_id
    ON agent_task_schedules(created_by_user_id);

CREATE TABLE IF NOT EXISTS agent_task_runs (
    id               SERIAL PRIMARY KEY,
    schedule_id      INTEGER NOT NULL REFERENCES agent_task_schedules(id) ON DELETE CASCADE,
    session_id       VARCHAR(100) DEFAULT NULL,
    agent_name       VARCHAR(100) NOT NULL,
    prompt_snapshot  TEXT NOT NULL,
    status           VARCHAR(32) NOT NULL DEFAULT 'pending',
    trigger_type     VARCHAR(32) NOT NULL DEFAULT 'scheduled',
    scheduled_at     TIMESTAMP DEFAULT NULL,
    started_at       TIMESTAMP DEFAULT NULL,
    finished_at      TIMESTAMP DEFAULT NULL,
    duration_ms      INTEGER DEFAULT NULL,
    output_text      TEXT DEFAULT NULL,
    error_message    TEXT DEFAULT NULL,
    created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT agent_task_runs_status_chk CHECK (status IN ('pending', 'running', 'success', 'failed', 'skipped')),
    CONSTRAINT agent_task_runs_trigger_type_chk CHECK (trigger_type IN ('scheduled', 'manual'))
);

CREATE INDEX IF NOT EXISTS idx_agent_task_runs_schedule_id ON agent_task_runs(schedule_id);
CREATE INDEX IF NOT EXISTS idx_agent_task_runs_status      ON agent_task_runs(status);
CREATE INDEX IF NOT EXISTS idx_agent_task_runs_created_at  ON agent_task_runs(created_at DESC);

-- 17.1 扩展：支持脚本作为调度目标（2026-07-16 新增）
--   * target_type 区分 'agent' / 'script'，默认 'agent' 保证旧记录向后兼容
--   * script_name 脚本任务时引用 app/scripts/ 中注册的脚本名
--   * script_args JSONB 注入脚本参数
--   * agent_name / prompt 放松为可空（脚本任务时为 NULL）
--   * CHECK 约束确保两种任务类型的字段一致性
ALTER TABLE agent_task_schedules ADD COLUMN IF NOT EXISTS target_type VARCHAR(16) NOT NULL DEFAULT 'agent';
ALTER TABLE agent_task_schedules ADD COLUMN IF NOT EXISTS script_name VARCHAR(100) DEFAULT NULL;
ALTER TABLE agent_task_schedules ADD COLUMN IF NOT EXISTS script_args JSONB DEFAULT '{}'::jsonb;
ALTER TABLE agent_task_schedules ALTER COLUMN agent_name DROP NOT NULL;
ALTER TABLE agent_task_schedules ALTER COLUMN prompt DROP NOT NULL;
ALTER TABLE agent_task_schedules DROP CONSTRAINT IF EXISTS agent_task_schedules_target_type_chk;
ALTER TABLE agent_task_schedules ADD CONSTRAINT agent_task_schedules_target_type_chk
    CHECK (target_type IN ('agent', 'script'));
ALTER TABLE agent_task_schedules DROP CONSTRAINT IF EXISTS agent_task_schedules_target_payload_chk;
ALTER TABLE agent_task_schedules ADD CONSTRAINT agent_task_schedules_target_payload_chk
    CHECK (
        (target_type = 'agent' AND agent_name IS NOT NULL AND prompt IS NOT NULL)
        OR
        (target_type = 'script' AND script_name IS NOT NULL)
    );
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_target_type ON agent_task_schedules(target_type);
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_script_name ON agent_task_schedules(script_name);

-- 17.3 扩展：定时任务邮件通知（脚本任务可选启用）
--   * notify_enabled 启用邮件通知后，脚本执行完成时自动按 notify_policy_id 模板渲染并发送邮件
--   * notify_policy_id 引用 email_policies(id)；删除策略时自动置 NULL，避免任务被级联删除
ALTER TABLE agent_task_schedules
    ADD COLUMN IF NOT EXISTS notify_enabled BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE agent_task_schedules
    ADD COLUMN IF NOT EXISTS notify_policy_id INTEGER
        DEFAULT NULL REFERENCES email_policies(id) ON DELETE SET NULL;
CREATE INDEX IF NOT EXISTS idx_agent_task_schedules_notify_policy
    ON agent_task_schedules(notify_policy_id);

-- 17.2 扩展：agent_task_runs 同步加 target_type / script_name，便于执行历史区分
ALTER TABLE agent_task_runs ADD COLUMN IF NOT EXISTS target_type VARCHAR(16) NOT NULL DEFAULT 'agent';
ALTER TABLE agent_task_runs ADD COLUMN IF NOT EXISTS script_name VARCHAR(100) DEFAULT NULL;
ALTER TABLE agent_task_runs DROP CONSTRAINT IF EXISTS agent_task_runs_target_type_chk;
ALTER TABLE agent_task_runs ADD CONSTRAINT agent_task_runs_target_type_chk
    CHECK (target_type IN ('agent', 'script'));

-- ========== 18. devops_servers（DevOps SSH 服务器配置，2026-07-15 新增）==========
-- DevOpsServerService 的运行时配置真实数据源：
--   * business_name 唯一，作为 upsert 键（与 YAML 中的 name/host 别名规范化为统一字段）
--   * password_encrypted 使用 Fernet 对称加密（base64），由 DevOpsServerService 在
--     scan_and_upsert 阶段写入；读取时通过 credential_key 解密
--   * blacklist / whitelist 是 list[str]（存为 jsonb），CommandInterceptor 重建时按
--     精确 / 前缀 / 正则 三类分别编译
--   * server_type 仅 'windows' / 'linux'，由 CHECK 约束兜底
--   * 扫描时校验：port 1-65535；每服务器名单必须为 list；业务名唯一
-- 幂等：所有 DDL / CHECK / INDEX 使用 IF NOT EXISTS，可重复执行
CREATE TABLE IF NOT EXISTS devops_servers (
    id                 SERIAL PRIMARY KEY,
    business_name      VARCHAR(200) UNIQUE NOT NULL,
    ip                 VARCHAR(64)  NOT NULL,
    port               INTEGER      NOT NULL,
    username           VARCHAR(100) NOT NULL,
    password_encrypted BYTEA        NOT NULL,
    server_type        VARCHAR(16)  NOT NULL DEFAULT 'linux',
    blacklist          JSONB        DEFAULT '[]'::jsonb,
    whitelist          JSONB        DEFAULT '[]'::jsonb,
    created_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    updated_at         TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
    -- 2026-07-22 新增：巡检脚本 / 解析器 / 字段规则列。
    -- inspection_fields JSONB 元素定义为 list[dict]，每个 dict 形如：
    --   {key, name_zh, unit, direction, warn, crit}
    -- 详细字段契约见 app/shared/utils/inspection/parser.py::normalize_inspection_fields
    -- 与 data/devops/servers.yaml.example 注释。
    inspection_script TEXT NULL,
    inspection_parser VARCHAR(16) DEFAULT 'json',
    inspection_fields JSONB DEFAULT '[]'::jsonb,
    CONSTRAINT devops_servers_server_type_chk CHECK (server_type IN ('linux', 'windows')),
    CONSTRAINT devops_servers_port_range_chk  CHECK (port BETWEEN 1 AND 65535)
);
-- 防御性补齐（覆盖代码所有 INSERT/UPDATE/SELECT 用到的列）
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS business_name      VARCHAR(200);
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS ip                 VARCHAR(64);
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS port               INTEGER;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS username           VARCHAR(100);
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS password_encrypted BYTEA;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS server_type        VARCHAR(16);
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS blacklist          JSONB DEFAULT '[]'::jsonb;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS whitelist          JSONB DEFAULT '[]'::jsonb;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS created_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS updated_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP;
-- 18.2 巡检脚本（2026-07-22 新增）
-- inspection_script TEXT: 固定巡检脚本(bash / powershell，YAML | 字面块)
-- inspection_parser VARCHAR(16): 解析器类型，默认 'json'；可选 'kv' | 'csv' | 'raw'
-- inspection_fields JSONB: list[dict]，每条规则 schema：
--   {key, name_zh, unit, direction, warn, crit}
-- 契约详见 app/shared/utils/inspection/parser.py::normalize_inspection_fields。
-- ALTER TABLE ADD COLUMN IF NOT EXISTS 全部使用，可重复执行（幂等）。
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS inspection_script TEXT DEFAULT NULL;
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS inspection_parser VARCHAR(16) DEFAULT 'json';
ALTER TABLE devops_servers ADD COLUMN IF NOT EXISTS inspection_fields JSONB DEFAULT '[]'::jsonb;
-- CHECK 约束：单独 ALTER，避免与已有数据冲突；IF NOT EXISTS 兼容老 PG
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conname = 'devops_servers_inspection_parser_chk'
    ) THEN
        ALTER TABLE devops_servers
            ADD CONSTRAINT devops_servers_inspection_parser_chk
            CHECK (inspection_parser IN ('json', 'kv', 'csv', 'raw'));
    END IF;
END$$;
-- 索引：按 server_type 过滤 / 按 updated_at 排序
CREATE INDEX IF NOT EXISTS idx_devops_servers_server_type ON devops_servers(server_type);
CREATE INDEX IF NOT EXISTS idx_devops_servers_updated_at  ON devops_servers(updated_at DESC);

-- 18.1 工具元数据：DevOpsServerService 的 3 个 @tool（execute_command / batch / logs）
--     元数据由 ToolRegistryService 在启动时通过源码扫描发现；这里登记到 DB 便于
--     Tool Admin 界面展示（不创建任何 Agent / agent_tool_bindings / seed 脚本）。
--     参数 schema 显式不含 runtime（LangChain ToolRuntime 由框架运行时自动注入）。
INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('execute_command', 'Execute SSH Command', 'devops', '在已配置的远程服务器上执行单条命令（Linux/bash 或 Windows/powershell）。', 'app.shared.tools.skills.devops.SSHTools', 'app/shared/tools/skills/devops/SSHTools.py', '{"properties": {"command": {"type": "string"}, "business_name": {"type": "string"}, "timeout": {"type": "integer", "default": 30}}, "required": ["command", "business_name"]}', NULL, 'execute_command：在远程服务器执行单条命令。', TRUE, 0)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    module_path = EXCLUDED.module_path,
    file_path = EXCLUDED.file_path,
    args_schema = EXCLUDED.args_schema,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('execute_batch_commands', 'Execute SSH Batch Commands', 'devops', '在已配置的远程服务器上批量执行多条命令；任一条被策略拦截即整批拒绝。', 'app.shared.tools.skills.devops.SSHTools', 'app/shared/tools/skills/devops/SSHTools.py', '{"properties": {"commands": {"type": "array", "items": {"type": "string"}}, "business_name": {"type": "string"}, "timeout": {"type": "integer", "default": 30}}, "required": ["commands", "business_name"]}', NULL, 'execute_batch_commands：批量 SSH 命令执行。', TRUE, 0)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    module_path = EXCLUDED.module_path,
    file_path = EXCLUDED.file_path,
    args_schema = EXCLUDED.args_schema,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO tools (name, display_name, category, description, module_path, file_path, args_schema, return_description, function_description, enabled, sort_order) VALUES
  ('get_system_logs', 'Get System Logs', 'devops', '获取远程服务器系统日志（tail），返回成功摘要，不含连接配置。', 'app.shared.tools.skills.devops.SSHTools', 'app/shared/tools/skills/devops/SSHTools.py', '{"properties": {"business_name": {"type": "string"}, "log_type": {"type": "string", "default": "syslog"}, "lines": {"type": "integer", "default": 100}}, "required": ["business_name"]}', NULL, 'get_system_logs：系统日志获取。', TRUE, 0)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    module_path = EXCLUDED.module_path,
    file_path = EXCLUDED.file_path,
    args_schema = EXCLUDED.args_schema,
    updated_at = CURRENT_TIMESTAMP;

-- ========== 19. email_server_configs（邮件服务器配置，2026-07-16 新增）==========
-- 全局唯一的 SMTP 出口配置；密码字段 password_encrypted 使用 Fernet 对称加密
-- （复用 DEVOPS_CREDENTIAL_KEY），明文密码仅在内存中流转
CREATE TABLE IF NOT EXISTS email_server_configs (
    id                SERIAL PRIMARY KEY,
    host              VARCHAR(200) NOT NULL,
    port              INTEGER NOT NULL DEFAULT 465,
    use_ssl           BOOLEAN NOT NULL DEFAULT TRUE,
    username          VARCHAR(200) NOT NULL,
    password_encrypted TEXT NOT NULL,
    sender_name       VARCHAR(200) DEFAULT '',
    enabled           BOOLEAN NOT NULL DEFAULT TRUE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 单行启用约束：全局仅允许一条 enabled=TRUE 配置
CREATE UNIQUE INDEX IF NOT EXISTS idx_email_server_configs_enabled
    ON email_server_configs(enabled) WHERE enabled = TRUE;

-- 19.1 扩展：企业邮箱兼容字段（2026-07-18 新增，方案 Z）
-- force_plain：跳过 STARTTLS，仅 use_ssl=False 时生效；支持 25 端口明文 SMTP
-- verify_ssl：是否校验 SMTP 服务器 TLS 证书；企业自签证书时可设为 False
ALTER TABLE email_server_configs
    ADD COLUMN IF NOT EXISTS force_plain BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE email_server_configs
    ADD COLUMN IF NOT EXISTS verify_ssl BOOLEAN NOT NULL DEFAULT TRUE;

-- ========== 20. email_policies / email_policy_recipients（邮件发送策略）==========
-- 策略仅包含收件人集合（用户确认）；策略与 users 多对多关系
-- 调用方（脚本/定时任务/手动）通过 policy_id 调用 EmailService 发送邮件
-- 归属隔离（2026-07-24 起）：
--   * created_by_user_id 作为归属字段，遵循 OwnershipScope 通用方案
--   * admin 可见全部策略；普通用户仅可见自己创建的策略
--   * 定时任务通过 notify_policy_id 关联策略，校验策略归属 task 创建人
CREATE TABLE IF NOT EXISTS email_policies (
    id                SERIAL PRIMARY KEY,
    name              VARCHAR(200) NOT NULL,
    description       TEXT DEFAULT '',
    created_by_user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
-- 归属字段索引：按用户隔离 list 时频繁 WHERE created_by_user_id = $1
CREATE INDEX IF NOT EXISTS idx_email_policies_created_by_user_id
    ON email_policies(created_by_user_id);

CREATE TABLE IF NOT EXISTS email_policy_recipients (
    policy_id   INTEGER NOT NULL REFERENCES email_policies(id) ON DELETE CASCADE,
    user_id     INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    PRIMARY KEY (policy_id, user_id)
);
CREATE INDEX IF NOT EXISTS idx_email_policy_recipients_user_id ON email_policy_recipients(user_id);

-- 20.1 扩展：邮件主题/正文模板（含 {{var}} 占位符）
-- 定时任务执行完成后用模板渲染主题与正文，再通过 EmailService 发送。
-- 留空字符串时：subject_template 用策略名；body_template 用脚本返回的 body。
ALTER TABLE email_policies
    ADD COLUMN IF NOT EXISTS subject_template VARCHAR(500) NOT NULL DEFAULT '';
ALTER TABLE email_policies
    ADD COLUMN IF NOT EXISTS body_template TEXT NOT NULL DEFAULT '';

-- ========== 21. api_config_nodes / api_configs / api_check_runs（API接口配置）==========
-- 树形节点（folder / api）+ 每个 api 节点的请求配置 + 调用历史。
-- 所有 DDL 使用 IF NOT EXISTS，幂等可重复执行。
-- 归属隔离（2026-07-24 起）：
--   * created_by_user_id 作为归属字段，遵循 OwnershipScope 通用方案
--   * admin 可见全部节点；普通用户仅可见自己创建的节点（父节点不可见时提升为根）
--   * 创建/移动节点的父节点必须是 admin 或本人拥有的 folder
--   * 存量节点回填到首个 admin（兜底首个用户），避免迁移期间 NULL 阻塞隔离
CREATE TABLE IF NOT EXISTS api_config_nodes (
    id                  SERIAL PRIMARY KEY,
    parent_id           INTEGER NULL REFERENCES api_config_nodes(id) ON DELETE CASCADE,
    node_type           VARCHAR(16) NOT NULL CHECK (node_type IN ('folder', 'api')),
    name                VARCHAR(255) NOT NULL,
    sort_order          INTEGER NOT NULL DEFAULT 0,
    created_by_user_id  INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_config_nodes_parent ON api_config_nodes(parent_id);
-- 21.1 块之后才追加 idx_api_config_nodes_created_by_user_id（依赖 21.1 段落的 ADD COLUMN，
-- 在存量库上必须先加列再建索引，否则 CREATE INDEX 报「字段不存在」）

CREATE TABLE IF NOT EXISTS api_configs (
    id            SERIAL PRIMARY KEY,
    node_id       INTEGER NOT NULL UNIQUE REFERENCES api_config_nodes(id) ON DELETE CASCADE,
    method        VARCHAR(8) NOT NULL DEFAULT 'POST' CHECK (method IN ('POST', 'PUT')),
    url           TEXT NOT NULL DEFAULT '',
    params        JSONB NOT NULL DEFAULT '[]',
    headers       JSONB NOT NULL DEFAULT '[]',
    body_type     VARCHAR(32) NOT NULL DEFAULT 'none'
                  CHECK (body_type IN ('none', 'json', 'xml', 'text', 'form-data', 'x-www-form-urlencoded')),
    body_content  TEXT NOT NULL DEFAULT '',
    form_fields   JSONB NOT NULL DEFAULT '[]',
    expectations  JSONB NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS api_check_runs (
    id               SERIAL PRIMARY KEY,
    config_id        INTEGER NOT NULL REFERENCES api_configs(id) ON DELETE CASCADE,
    http_status      INTEGER NULL,
    duration_ms      INTEGER NULL,
    check_passed     BOOLEAN NOT NULL DEFAULT FALSE,
    response_excerpt TEXT NOT NULL DEFAULT '',
    error_message    TEXT NOT NULL DEFAULT '',
    created_at       TIMESTAMPTZ DEFAULT NOW()
);
CREATE INDEX IF NOT EXISTS idx_api_check_runs_config ON api_check_runs(config_id, created_at DESC);

-- 21.1 块推迟到 COMMIT 之后执行（见文件末尾 21.1 段），避免 21.1 失败回滚整个事务

-- ========== 22. user_menu_acl（用户-菜单授权，2026-07-23 新增）==========
-- 按用户粒度控制可见菜单（一级 + 二级）。
--   * user_id + menu_id 联合唯一，防止重复授权
--   * created_by_user_id 记录授权人，删除授权人不影响授权
--   * 应用启动时由 MenuPermissionService.preload_all() 全量加载到内存
CREATE TABLE IF NOT EXISTS user_menu_acl (
    id                  SERIAL PRIMARY KEY,
    user_id             INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    menu_id             VARCHAR(64) NOT NULL,
    created_at          TIMESTAMP DEFAULT NOW(),
    created_by_user_id  INTEGER REFERENCES users(id) ON DELETE SET NULL,
    UNIQUE (user_id, menu_id)
);
CREATE INDEX IF NOT EXISTS idx_user_menu_acl_user_id ON user_menu_acl(user_id);
CREATE INDEX IF NOT EXISTS idx_user_menu_acl_menu_id ON user_menu_acl(menu_id);

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
    'agents', 'agent_tool_bindings',
    'mcp_server_configs', 'mcp_server_methods',
    'tools', 'skills',
    'message_feedback',
    'agent_task_schedules', 'agent_task_runs',
    'devops_servers',
    'email_server_configs', 'email_policies', 'email_policy_recipients',
    'api_config_nodes', 'api_configs', 'api_check_runs',
    'user_menu_acl'
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

-- =============================================
-- 21.1 扩展：api_config_nodes 归属字段（2026-07-24 新增）
-- 移到主事务（COMMIT 之后）执行，独立 BEGIN/COMMIT 包裹，SAVEPOINT 隔离失败：
--   * ADD COLUMN IF NOT EXISTS + FK；新装 DB 在 CREATE TABLE 已直接定义 NOT NULL，本段 ALTER no-op
--   * UPDATE 回填到首个 admin（兜底首个用户），仅处理存量 NULL 行（依赖 users 已有数据）
--   * SET NOT NULL：要求 users 表至少有 1 行（生产必满足）；若有 NULL 残留，内层
--     EXCEPTION 捕获并 RAISE NOTICE 跳过；外层 EXCEPTION 兜底 ROLLBACK 整段
--   * CREATE INDEX 在 ADD COLUMN 之后建（依赖 created_by_user_id 已存在）
--   * 整段使用 IF NOT EXISTS，幂等可重复执行；21.1 失败不会影响主事务已 commit 的内容
-- =============================================
BEGIN;
SAVEPOINT api_config_nodes_ownership_migration;
DO $$
BEGIN
    ALTER TABLE api_config_nodes
        ADD COLUMN IF NOT EXISTS created_by_user_id INTEGER REFERENCES users(id) ON DELETE CASCADE;
    UPDATE api_config_nodes
    SET created_by_user_id = COALESCE(
        (SELECT id FROM users WHERE role = 'admin' ORDER BY id ASC LIMIT 1),
        (SELECT id FROM users ORDER BY id ASC LIMIT 1)
    )
    WHERE created_by_user_id IS NULL
      AND EXISTS (SELECT 1 FROM users LIMIT 1);
    BEGIN
        ALTER TABLE api_config_nodes ALTER COLUMN created_by_user_id SET NOT NULL;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'api_config_nodes.created_by_user_id SET NOT NULL 跳过（仍有 NULL）: %', SQLERRM;
    END;
    CREATE INDEX IF NOT EXISTS idx_api_config_nodes_created_by_user_id
        ON api_config_nodes(created_by_user_id);
EXCEPTION WHEN OTHERS THEN
    ROLLBACK TO SAVEPOINT api_config_nodes_ownership_migration;
    RAISE NOTICE '21.1 块整体失败已回滚到 SAVEPOINT：%', SQLERRM;
END $$;
RELEASE SAVEPOINT api_config_nodes_ownership_migration;
COMMIT;
