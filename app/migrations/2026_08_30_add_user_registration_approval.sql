-- ============================================================
-- 2026-08-30 注册审批 + IP 白名单
-- 等保三级 §7.1.3 访问控制 a/e:注册提交后账号进入 pending_approval,
-- 管理员审批通过后才能登录。配套 IP 白名单闸门在中间件层。
-- ============================================================

BEGIN;

-- ========== users 表新增 4 列 ==========
-- status:active(已激活) / pending_approval(待审批) / rejected(已拒绝) / disabled(已禁用)
-- 历史用户默认 active,向后兼容。
ALTER TABLE users ADD COLUMN IF NOT EXISTS status VARCHAR(32) NOT NULL DEFAULT 'active';
ALTER TABLE users ADD COLUMN IF NOT EXISTS status_reason TEXT NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_by_user_id INTEGER NULL
    REFERENCES users(id) ON DELETE SET NULL;
ALTER TABLE users ADD COLUMN IF NOT EXISTS approved_at TIMESTAMP NULL;

-- CHECK 约束
ALTER TABLE users DROP CONSTRAINT IF EXISTS users_status_chk;
ALTER TABLE users ADD CONSTRAINT users_status_chk
    CHECK (status IN ('active', 'pending_approval', 'rejected', 'disabled'));

-- 索引(待审批列表查询加速)
CREATE INDEX IF NOT EXISTS idx_users_status ON users(status);

-- ========== 新表 registration_approval_logs ==========
-- 审批操作独立审计表,与 audit_logs 并存便于专项查询
CREATE TABLE IF NOT EXISTS registration_approval_logs (
    id                  SERIAL PRIMARY KEY,
    target_user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    target_username     VARCHAR(100) NOT NULL,
    target_register_ip  VARCHAR(64) NULL,
    action              VARCHAR(16) NOT NULL,
    reason              TEXT NULL,
    operator_user_id    INTEGER NULL REFERENCES users(id) ON DELETE SET NULL,
    operator_username   VARCHAR(100) NOT NULL,
    created_at          TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT registration_approval_logs_action_chk
        CHECK (action IN ('approve', 'reject'))
);

CREATE INDEX IF NOT EXISTS idx_registration_approval_logs_target
    ON registration_approval_logs(target_user_id);
CREATE INDEX IF NOT EXISTS idx_registration_approval_logs_created_at
    ON registration_approval_logs(created_at DESC);

COMMIT;
