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
