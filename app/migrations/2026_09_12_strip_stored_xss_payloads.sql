-- 2026_09_12_strip_stored_xss_payloads.sql
-- 渗透测试存量 XSS 载荷一次性清理（数据层，无 schema 变更）。
-- 适用环境：被渗透测试写入过载荷的部署库（如 124.95.179.91:9000 对应库）。
-- 执行方式：psql / Navicat 手动执行；幂等，可重复执行。
-- 注意：执行后必须重启后端进程（ProjectDB._memory_cache / SessionDB 内存缓存
--       持有旧值，重启后从 DB 重载）。
-- username 列只出报告不自动改：它是登录标识，改名将导致用户无法登录。

BEGIN;

-- 预检（可选先执行）：评估影响行数
-- SELECT id, username, real_name, department, position FROM users
--  WHERE real_name ~ '<[^>]*>' OR department ~ '<[^>]*>' OR position ~ '<[^>]*>';
-- SELECT id, name FROM projects WHERE name ~ '<[^>]*>';
-- SELECT session_id, title FROM sessions WHERE title ~ '<[^>]*>';
-- SELECT id, username FROM users WHERE username ~ '<[^>]*>';  -- 仅报告，不更新

UPDATE users SET
  real_name  = regexp_replace(real_name,  '<[^>]*>', '', 'g'),
  department = regexp_replace(department, '<[^>]*>', '', 'g'),
  position   = regexp_replace(position,   '<[^>]*>', '', 'g'),
  updated_at = CURRENT_TIMESTAMP
WHERE real_name ~ '<[^>]*>'
   OR department ~ '<[^>]*>'
   OR position   ~ '<[^>]*>';

UPDATE projects
   SET name = regexp_replace(name, '<[^>]*>', '', 'g')
 WHERE name ~ '<[^>]*>';

UPDATE sessions
   SET title = regexp_replace(title, '<[^>]*>', '', 'g')
 WHERE title ~ '<[^>]*>';

COMMIT;

-- 验证：三条均应返回 0 行
-- SELECT COUNT(*) FROM users
--  WHERE real_name ~ '<[^>]*>' OR department ~ '<[^>]*>' OR position ~ '<[^>]*>';
-- SELECT COUNT(*) FROM projects WHERE name ~ '<[^>]*>';
-- SELECT COUNT(*) FROM sessions WHERE title ~ '<[^>]*>';
