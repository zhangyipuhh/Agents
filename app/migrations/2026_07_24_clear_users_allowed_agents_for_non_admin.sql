-- =====================================================================
-- 2026-07-24 数据修复：清空非 admin 用户的 users.allowed_agents 残留
-- =====================================================================
--
-- 背景：
--   2026-07-24 之前，agent 访问权限由 users.allowed_agents (JSONB) 控制。
--   当「智能体访问」Tab 切换到 user_agent_acl 表后，旧字段并未被清空，
--   仍残留 zyp 等用户的历史授权 ["project"]。
--
--   后果：auth_middleware.authenticate() 历史上读 users.allowed_agents
--   注入 request.state.allowed_agents，导致 zyp 登录后 agent_router
--   仍判定其有权使用 project 等智能体（与新 ACL 实际授权不符）。
--
--   修复：Safety.py 已将数据源切到 user_agent_acl；为彻底消除
--   "旧字段偷偷授权" 的风险，本迁移把所有非 admin 用户的
--   users.allowed_agents 清成 '[]'。admin 用户的 allowed_agents
--   由 ACL bypass 处理（不依赖 user_agent_acl），无需清理。
--
-- 幂等性：可重复执行，结果不变。
-- 回滚：UPDATE users SET allowed_agents = <历史值> WHERE username = ...;
--
-- 执行时机：P0 代码修复完成后立即执行。
-- =====================================================================

UPDATE users
SET allowed_agents = '[]'::jsonb
WHERE role != 'admin';