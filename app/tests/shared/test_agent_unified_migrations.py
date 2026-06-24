# -*- coding:utf-8 -*-
"""
统一智能体架构数据库迁移测试模块

验证 2026_06_23_agent_unified 迁移脚本包含 5 张新表的 CREATE TABLE 语句。
"""
import pytest
from pathlib import Path


def _read_migration_sql() -> str:
    """读取 init_all_tables.sql 全文。

    Returns:
        str: 迁移脚本内容

    Raises:
        FileNotFoundError: 迁移文件不存在时抛出
    """
    migration_path = Path(__file__).parent.parent.parent / "migrations" / "init_all_tables.sql"
    return migration_path.read_text(encoding="utf-8")


def test_agents_table_exists_in_migration():
    """测试迁移脚本包含 agents 表创建语句。"""
    sql = _read_migration_sql()
    assert "CREATE TABLE IF NOT EXISTS agents" in sql
    assert "agents_md_path" in sql
    assert "state_schema" in sql
    assert "context_schema" in sql


def test_agent_tool_bindings_table_exists():
    """测试迁移脚本包含 agent_tool_bindings 表。"""
    sql = _read_migration_sql()
    assert "CREATE TABLE IF NOT EXISTS agent_tool_bindings" in sql
    assert "UNIQUE(agent_name, tool_name)" in sql


def test_agent_skill_bindings_table_exists():
    """测试迁移脚本包含 agent_skill_bindings 表。"""
    sql = _read_migration_sql()
    assert "CREATE TABLE IF NOT EXISTS agent_skill_bindings" in sql
    assert "UNIQUE(agent_name, skill_name)" in sql


def test_mcp_server_configs_table_exists():
    """测试迁移脚本包含 mcp_server_configs 表。

    覆盖：
    - 基础字段：methods_synced_at / tool_config
    - 2026-06-24 新增字段：args / env / headers / connect_timeout
    - 幂等 ALTER：ADD COLUMN IF NOT EXISTS
    """
    sql = _read_migration_sql()
    assert "CREATE TABLE IF NOT EXISTS mcp_server_configs" in sql
    assert "methods_synced_at" in sql
    assert "tool_config" in sql
    # 2026-06-24 新增 4 列（CREATE TABLE 内）
    assert "args JSONB" in sql
    assert "env JSONB" in sql
    assert "headers JSONB" in sql
    assert "connect_timeout INT" in sql
    # 幂等 ALTER（兼容已建库）
    assert "ADD COLUMN IF NOT EXISTS args" in sql
    assert "ADD COLUMN IF NOT EXISTS env" in sql
    assert "ADD COLUMN IF NOT EXISTS headers" in sql
    assert "ADD COLUMN IF NOT EXISTS connect_timeout" in sql


def test_mcp_server_methods_table_exists():
    """测试迁移脚本包含 mcp_server_methods 表。"""
    sql = _read_migration_sql()
    assert "CREATE TABLE IF NOT EXISTS mcp_server_methods" in sql
    assert "UNIQUE(server_name, method_name)" in sql
