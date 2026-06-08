-- 为已部署环境添加 portal_refresh_tokens 表的部分唯一索引
-- 约束：一个用户最多只能有一条未撤销（revoked = FALSE）的 portal refresh_token
-- 适用：PostgreSQL
-- 注意：使用 IF NOT EXISTS，可重复执行不会报错

CREATE UNIQUE INDEX IF NOT EXISTS idx_portal_refresh_tokens_user_id_active
    ON portal_refresh_tokens(user_id)
    WHERE revoked = FALSE;
