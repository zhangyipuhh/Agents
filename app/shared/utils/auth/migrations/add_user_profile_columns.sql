-- users 表字段补充迁移脚本
-- 作用：为已存在的旧数据库添加注册页面所需的 5 个用户资料字段
-- 适用：PostgreSQL
-- 注意：使用 IF NOT EXISTS，可重复执行不会报错

ALTER TABLE users
    ADD COLUMN IF NOT EXISTS real_name VARCHAR(20) DEFAULT '',
    ADD COLUMN IF NOT EXISTS phone VARCHAR(20) DEFAULT '',
    ADD COLUMN IF NOT EXISTS email VARCHAR(100) DEFAULT '',
    ADD COLUMN IF NOT EXISTS department VARCHAR(100) DEFAULT '',
    ADD COLUMN IF NOT EXISTS position VARCHAR(100) DEFAULT '';
