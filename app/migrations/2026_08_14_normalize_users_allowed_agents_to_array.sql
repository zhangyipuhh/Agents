-- 2026-08-14 修复：把 users.allowed_agents 中类型为 string / object / number 等
-- 非 array 的脏数据规整为合法 JSONB array '[]'，避免 lifespan 启动时
-- jsonb_array_elements_text 抛 "cannot extract elements from a scalar"。
--
-- 触发场景：早期代码 / 手动 UPDATE 把字符串 '[]' 直接写入 JSONB 列，
-- PostgreSQL 静默存为 jsonb string（"[]"），合法但语义破坏。
-- 案例：ZYP 用户 (id=2) allowed_agents 存为 jsonb string '"[]"'，
-- migrate_from_users_allowed_agents() 的 jsonb_array_elements_text 调用
-- 抛 InvalidParameterValueError，整个 lifespan 启动迁移失败。
--
-- 幂等性：WHERE 条件限制只在非 array 行才更新，重复执行无副作用。
-- 回滚：UPDATE users SET allowed_agents = '"[]"'::jsonb WHERE id=2;
--      （仅 ZYP 一行；未来若需保留历史脏数据可手动执行）

UPDATE users
SET allowed_agents = '[]'::jsonb
WHERE jsonb_typeof(allowed_agents) <> 'array';