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
    timeout INT DEFAULT 5,
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
    'mcp_server_configs', 'mcp_server_methods'
  )
ORDER BY table_name;
