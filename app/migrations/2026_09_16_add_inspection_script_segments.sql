-- ===== 17.5.1 inspection_script_segments(巡检脚本分段,2026-09-16 新增)=====
-- 单体巡检脚本拆分为有序分段(cpu / memory / disk-usage / disk-io),SSH 单连接
-- 循环执行后按 D1 合并语义拼回完整 JSON;inspection_scripts 为组头,本表为分段体。
-- 约束:
--   * FK ON DELETE CASCADE:组删除时自动清理分段(防止悬挂引用)
--   * UNIQUE(script_id, segment_key):分段键在组内唯一,upsert 走 ON CONFLICT
--   * segment_key CHECK:小写字母数字+下划线短横线,长度 1-64,首字符必须字母数字
--   * idx_script_id:按组快速拉取该组全部分段(preload_all / _reload_segments)
CREATE TABLE IF NOT EXISTS inspection_script_segments (
    id           SERIAL PRIMARY KEY,
    script_id    INTEGER NOT NULL REFERENCES inspection_scripts(id) ON DELETE CASCADE,
    segment_key  VARCHAR(64) NOT NULL,
    display_name VARCHAR(200) NOT NULL DEFAULT '',
    sort_order   INTEGER NOT NULL DEFAULT 0,
    script       TEXT NOT NULL,
    enabled      BOOLEAN NOT NULL DEFAULT TRUE,
    created_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT inspection_script_segments_key_chk
        CHECK (segment_key ~ '^[a-z0-9][a-z0-9_\-]{0,63}$'),
    CONSTRAINT inspection_script_segments_uq UNIQUE (script_id, segment_key)
);

CREATE INDEX IF NOT EXISTS idx_inspection_script_segments_script_id
    ON inspection_script_segments(script_id);
