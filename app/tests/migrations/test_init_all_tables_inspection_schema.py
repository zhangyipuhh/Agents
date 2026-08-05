# -*- coding:utf-8 -*-
"""init_all_tables.sql 巡检脚本目标 schema 静态契约测试。"""

from pathlib import Path


INIT_SQL_PATH = Path(__file__).resolve().parents[2] / "migrations" / "init_all_tables.sql"
LEGACY_COLUMNS = (
    "inspection_script",
    "inspection_parser",
    "inspection_fields",
)


def _load_init_sql() -> str:
    """读取初始化 SQL。

    Returns:
        str: UTF-8 编码的初始化 SQL 全文。

    Raises:
        OSError: 文件无法读取时抛出。
    """
    return INIT_SQL_PATH.read_text(encoding="utf-8")


def _drop_position(sql: str) -> int:
    """定位第一个旧列 DROP COLUMN 的位置。

    Args:
        sql: 初始化 SQL 全文。

    Returns:
        int: 第一个 ``ALTER TABLE devops_servers DROP COLUMN IF EXISTS inspection_script;``
        的字符索引。

    Raises:
        AssertionError: 文本中找不到 DROP 语句时抛出。
    """
    marker = "ALTER TABLE devops_servers DROP COLUMN IF EXISTS inspection_script;"
    assert marker in sql, "init_all_tables.sql 必须包含目标 DROP COLUMN 段"
    return sql.index(marker)


def test_inspection_script_schema_and_foreign_key_are_defined_before_legacy_drop():
    """脚本库表与外键必须在旧列删除前定义。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 任意 DDL 顺序不符合目标 schema 时抛出。
    """
    sql = _load_init_sql()
    drop_position = _drop_position(sql)
    table_position = sql.index("CREATE TABLE IF NOT EXISTS inspection_scripts")
    foreign_key_position = sql.index(
        "inspection_script_id  INTEGER NULL REFERENCES inspection_scripts(id) ON DELETE SET NULL"
    )

    assert table_position < foreign_key_position < drop_position


def test_init_sql_explicitly_drops_all_legacy_inspection_columns():
    """目标新 schema 必须直接删除全部旧巡检列。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 任一旧列未显式删除时抛出。
    """
    sql = _load_init_sql()

    for column in LEGACY_COLUMNS:
        marker = f"ALTER TABLE devops_servers DROP COLUMN IF EXISTS {column};"
        assert marker in sql, f"init_all_tables.sql 必须显式删除旧列 {column}"


def test_drop_comment_contains_external_migration_instructions():
    """DROP 段之前必须给出迁移前置说明。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 迁移前置说明缺失时抛出。
    """
    sql = _load_init_sql()
    drop_position = _drop_position(sql)
    comment_segment = sql[max(0, drop_position - 1800):drop_position]

    required_phrases = (
        "外部一次性迁移",
        "回填",
        "inspection_script_id",
        "丢失旧巡检数据",
    )
    missing = [phrase for phrase in required_phrases if phrase not in comment_segment]
    assert not missing, (
        "DROP 段之前的注释必须包含迁移前置说明，缺失: "
        f"{missing}; 当前片段前 600 字符: {comment_segment[:600]!r}"
    )


# ============================================================================
# 2026-08-05 静态契约:agents JSONB 字段双层编码脏数据修复段(14.5)
# 验证 init_all_tables.sql 包含必要的修复 SQL + 防御补丁。
# 端到端执行需要真实 DB(MCP 只读无法跑 UPDATE),但本测试只验证 SQL 文本契约。
# ============================================================================


def test_init_all_tables_has_jsonb_double_encode_repair_v6_comment():
    """脚本头部必须包含 v6 变更说明,标注 14.5 修复段。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    # 文件开头 v5 注释段含 "v5 变更",v6 注释应紧跟其后
    assert "v6 变更(2026-08-05)" in sql, (
        "init_all_tables.sql 头部必须包含 v6 变更说明段,"
        "让运维看到 14.5 修复的目的与触发日期"
    )
    assert "14.5" in sql, "v6 注释必须引用 14.5 节段号"
    assert "双层编码" in sql or "json.dumps" in sql, (
        "v6 注释必须说明根因(双层 json.dumps 与 asyncpg codec 冲突)"
    )


def test_init_all_tables_has_14_4_defensive_where_clause():
    """14.4 节 WHERE 子句必须包含 jsonb_typeof(object) 防御。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    # 14.4 节原文:WHERE jsonb_typeof(config_schema) = 'object' AND ...
    assert "WHERE jsonb_typeof(config_schema) = 'object'" in sql, (
        "14.4 节 WHERE 必须加 jsonb_typeof='object' 防御,"
        "避免 array/string 与 object 合并后产生 array 元素"
    )


def test_init_all_tables_has_14_5_state_schema_repair():
    """14.5.1 节必须还原 state_schema 的 string 类型 JSONB。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    assert "14.5.1 state_schema" in sql, "14.5.1 注释段缺失"
    assert "jsonb_typeof(state_schema) = 'string'" in sql, (
        "14.5.1 SQL 必须检测 string 类型才能触发还原"
    )
    assert "(state_schema #>> '{}')::jsonb" in sql, (
        "14.5.1 SQL 必须用 #>> 提取字符串字面量后再 cast jsonb 还原"
    )


def test_init_all_tables_has_14_5_context_schema_repair():
    """14.5.2 节必须还原 context_schema 的 string 类型 JSONB。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    assert "14.5.2 context_schema" in sql, "14.5.2 注释段缺失"
    assert "jsonb_typeof(context_schema) = 'string'" in sql
    assert "(context_schema #>> '{}')::jsonb" in sql


def test_init_all_tables_has_14_5_tool_bindings_repair():
    """14.5.3 节必须还原 tool_bindings 的 string 类型 JSONB → array。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    assert "14.5.3 tool_bindings" in sql, "14.5.3 注释段缺失"
    assert "jsonb_typeof(tool_bindings) = 'string'" in sql
    # tool_bindings 还原必须 fallback 到 [] 而非 {}
    assert "'[]'::jsonb" in sql, "tool_bindings 解析失败时应 fallback 到空 array"


def test_init_all_tables_has_14_5_skill_bindings_repair():
    """14.5.4 节必须还原 skill_bindings 的 string 类型 JSONB → array。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    assert "14.5.4 skill_bindings" in sql, "14.5.4 注释段缺失"
    assert "jsonb_typeof(skill_bindings) = 'string'" in sql


def test_init_all_tables_14_5_repair_is_idempotent():
    """14.5 段 WHERE 子句保证幂等:已修过的 object/array 数据不会再次被覆盖。

    Returns:
        None: 断言通过时无返回值。
    """
    sql = _load_init_sql()
    # 每段都以 "WHERE jsonb_typeof(...) = 'string' OR ... IS NULL" 结尾
    # 这种条件下 object / array 类型不会被选中,实现幂等
    assert sql.count("jsonb_typeof(state_schema) = 'string'") >= 1
    assert sql.count("jsonb_typeof(context_schema) = 'string'") >= 1
    assert sql.count("jsonb_typeof(tool_bindings) = 'string'") >= 1
    assert sql.count("jsonb_typeof(skill_bindings) = 'string'") >= 1
    # 关键:不要把 "UPDATE agents SET state_schema = " 这种 SQL 写成无 WHERE,
    # 否则会无差别覆盖所有行(破坏幂等)
    assert "UPDATE agents SET state_schema = state_schema" not in sql, (
        "14.5.1 不应写成无差别的 SET state_schema = state_schema,"
        "必须带 WHERE jsonb_typeof = 'string' 防御"
    )


def test_init_sql_does_not_use_unloadable_drop_gate_helper():
    """init_all_tables.sql 不应再引用无法兼容新旧 schema 的 _devops_drop_gate。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 文本中仍残留失效 gate 标识符时抛出。
    """
    sql = _load_init_sql()
    assert "_devops_drop_gate" not in sql, (
        "init_all_tables.sql 不应再出现失效的 _devops_drop_gate 标识符。"
        "该 gate 通过 information_schema 包裹 SELECT 仍会在 PostgreSQL 解析阶段 "
        "校验列名存在性，无法同时兼容新旧 schema。删除并改由人工迁移契约承担。"
    )


def test_drop_segment_does_not_claim_runtime_fail_fast_semantics():
    """DROP 段不应再声明运行时 fail-fast 行为。

    Returns:
        None: 断言通过时无返回值。

    Raises:
        AssertionError: 注释仍声称 fail-fast 行为时抛出。
    """
    sql = _load_init_sql()
    drop_position = _drop_position(sql)
    comment_segment = sql[max(0, drop_position - 1800):drop_position]

    assert "fail-fast" not in comment_segment.lower(), (
        "DROP 段注释不应再声称 fail-fast 行为；该语义已下沉到人工迁移 + 回填契约。"
    )
