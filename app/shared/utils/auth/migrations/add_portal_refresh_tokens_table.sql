-- portal_refresh_tokens 表（门户子 refresh_token 存储）
-- 用途：第三方 iframe 通过 postMessage 拿到子 refresh_token 后，反复用它换 access_token。
-- 子 token 与正常 refresh_token 等效，但独立存储便于撤销与审计。
-- 适用：PostgreSQL
-- 注意：使用 IF NOT EXISTS，可重复执行不会报错

CREATE TABLE IF NOT EXISTS portal_refresh_tokens (
    id              SERIAL PRIMARY KEY,
    token_hash      VARCHAR(255) UNIQUE NOT NULL,
    user_id         INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    username        VARCHAR(100) NOT NULL,
    expires_at      TIMESTAMP NOT NULL,
    revoked         BOOLEAN NOT NULL DEFAULT FALSE,
    created_at      TIMESTAMP NOT NULL DEFAULT NOW()
);

-- 索引：按 user_id 查询（撤销某用户所有子 token）
CREATE INDEX IF NOT EXISTS idx_portal_refresh_tokens_user_id
    ON portal_refresh_tokens(user_id);

-- 索引：按过期时间清理
CREATE INDEX IF NOT EXISTS idx_portal_refresh_tokens_expires_at
    ON portal_refresh_tokens(expires_at);

-- 部分唯一索引：一个用户最多只能有一条未撤销的 portal refresh_token
CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_refresh_tokens_user_id_active
    ON portal_refresh_tokens(user_id)
    WHERE revoked = FALSE;
