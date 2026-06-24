# -*- coding:utf-8 -*-
"""
Agent Admin Router 测试模块

验证 /api/admin/agents/* 完整 CRUD 接口：
- GET    /api/admin/agents                          列出
- GET    /api/admin/agents/{name}                   详情
- POST   /api/admin/agents                          新增
- DELETE /api/admin/agents/{name}                   删除
- PUT    /api/admin/agents/{name}/enabled           启用/禁用
- GET    /api/admin/agents/check-name               唯一性
- POST   /api/admin/agents/validate-md-path         路径校验
- GET    /api/admin/agents/field-templates          字段模板
- PUT    /api/admin/agents/{name}/config-schema     全量替换
- POST   /api/admin/agents/{name}/config-schema/field
- DELETE /api/admin/agents/{name}/config-schema/field
"""
import pytest


# ============================================================
# P0 导入 / 路由注册测试
# ============================================================

def test_agent_admin_router_importable():
    """测试 agent_admin_router 模块可导入。"""
    from app.routers import agent_admin_router
    assert hasattr(agent_admin_router, "router")


def test_all_endpoints_registered(client):
    """测试所有 admin 端点已注册。"""
    routes = [r.path for r in client.app.routes]
    expected = [
        "/api/admin/agents",
        "/api/admin/agents/check-name",
        "/api/admin/agents/validate-md-path",
        "/api/admin/agents/field-templates",
        "/api/admin/agents/{name}",
        "/api/admin/agents/{name}/enabled",
        "/api/admin/agents/{name}/config-schema",
        "/api/admin/agents/{name}/config-schema/field",
    ]
    # PUT /config-schema/field 与 POST / DELETE 共享同一 path，已包含在上面的 path 中
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# ============================================================
# 字段模板 + 唯一性 + 路径校验（无需 DB）
# ============================================================

def test_field_templates_returns_list(client, admin_headers):
    """GET /api/admin/agents/field-templates 返回 AgentConfig 字段模板列表。"""
    response = client.get("/api/admin/agents/field-templates", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    # 字段模板包含 temperature
    field_names = [t["field_name"] for t in data]
    assert "temperature" in field_names
    # 不包含保留字段
    assert "state_class" not in field_names
    assert "checkpointer" not in field_names


def test_validate_md_path_for_existing_file(client, admin_headers, tmp_path):
    """POST /api/admin/agents/validate-md-path 检查已存在的文件。"""
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("# test agent")
    response = client.post(
        "/api/admin/agents/validate-md-path",
        headers=admin_headers,
        json={"path": str(md_file)},
    )
    assert response.status_code == 200
    assert response.json()["exists"] is True


def test_validate_md_path_for_missing_file(client, admin_headers):
    """POST /api/admin/agents/validate-md-path 检查不存在的文件。"""
    response = client.post(
        "/api/admin/agents/validate-md-path",
        headers=admin_headers,
        json={"path": "/non/existent/path/AGENTS.md"},
    )
    assert response.status_code == 200
    assert response.json()["exists"] is False


# ============================================================
# CRUD 测试（mock DB）
# ============================================================

def test_list_agents_returns_db_rows(client, admin_headers):
    """GET /api/admin/agents 返回 db.fetch 结果。"""
    from unittest.mock import AsyncMock

    fake_rows = [
        {
            "name": "map_agent",
            "display_name": "地图智能体",
            "description": "",
            "agents_md_path": "agents/map_agent/AGENTS.md",
            "state_schema": "{}",
            "context_schema": "{}",
            "config_schema": {
                "state_fields": {"map_zoom": {"type": "int", "default": 10}},
                "context_fields": {},
            },
            "mcp_tags": ["map"],
            "enabled": True,
            "sort_order": 0,
            "created_at": None,
            "updated_at": None,
        }
    ]

    async def fake_fetch(*args, **kwargs):
        return fake_rows

    # 2026-06-24 重构后 list_agents 改走 service，需先注入 _db 再挂 fetch
    service = client.app.state.agent_config_service
    if service._db is None:
        from unittest.mock import MagicMock
        service._db = MagicMock()
    service._db.fetch = fake_fetch

    response = client.get("/api/admin/agents", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert data[0]["name"] == "map_agent"


def test_get_agent_returns_full_config(client, admin_headers):
    """GET /api/admin/agents/{name} 返回包含 agent_config_overrides 的完整配置。"""
    from unittest.mock import AsyncMock

    fake_row = {
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": "{}",
        "context_schema": "{}",
        "config_schema": {
            "temperature": {"type": "float", "default": 0.5},
            "state_fields": {"map_zoom": {"type": "int", "default": 10}},
            "context_fields": {},
        },
        "mcp_tags": ["map"],
        "enabled": True,
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    }

    async def fake_fetchrow(*args, **kwargs):
        return fake_row

    # 2026-06-24 重构后 get_agent 改走 service，需先注入 _db 再挂 fetchrow
    service = client.app.state.agent_config_service
    if service._db is None:
        from unittest.mock import MagicMock
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get("/api/admin/agents/map_agent", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()
    assert data["name"] == "map_agent"
    # agent_config_overrides 包含 temperature
    assert data["agent_config_overrides"]["temperature"] == 0.5


def test_create_agent_success(client, admin_headers, tmp_path):
    """POST /api/admin/agents 新增智能体（合法 payload）。"""
    from unittest.mock import AsyncMock, MagicMock

    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("# new agent")

    fake_db = MagicMock()
    call_count = {"n": 0}
    async def fake_fetchrow(*args, **kwargs):
        call_count["n"] += 1
        # 第一次调用：SELECT 检查 name 是否存在 → 返回 None
        # 第二次调用：INSERT ... RETURNING * → 返回 row
        if call_count["n"] == 1:
            return None
        return {"name": "new_agent", "config_schema": "{}"}
    fake_db.fetchrow = fake_fetchrow

    # 同时覆盖 app.state.db 和 service._db
    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.post(
        "/api/admin/agents",
        headers=admin_headers,
        json={
            "name": "new_agent",
            "display_name": "新智能体",
            "description": "",
            "agents_md_path": str(md_file),
            "config_schema": {
                "temperature": {"type": "float", "default": 0.7},
                "state_fields": {},
                "context_fields": {},
            },
        },
    )
    assert response.status_code == 201


def test_create_agent_invalid_name_400(client, admin_headers, tmp_path):
    """POST /api/admin/agents 非法 name 格式返回 400。"""
    md_file = tmp_path / "AGENTS.md"
    md_file.write_text("# x")

    response = client.post(
        "/api/admin/agents",
        headers=admin_headers,
        json={
            "name": "Invalid Name!",
            "display_name": "X",
            "agents_md_path": str(md_file),
        },
    )
    # Pydantic 校验失败（pattern 不匹配）通常返回 422；
    # service 层校验返回 400。这里至少应非 201/200。
    assert response.status_code in (400, 422)


def test_create_agent_missing_md_file_400(client, admin_headers):
    """POST /api/admin/agents AGENTS.md 不存在返回 400。"""
    response = client.post(
        "/api/admin/agents",
        headers=admin_headers,
        json={
            "name": "valid_agent",
            "display_name": "Valid",
            "agents_md_path": "/non/existent/AGENTS.md",
        },
    )
    assert response.status_code == 400


def test_delete_agent_returns_204(client, admin_headers):
    """DELETE /api/admin/agents/{name} 成功删除返回 204。"""
    from unittest.mock import AsyncMock, MagicMock

    fake_db = MagicMock()
    async def fake_fetchrow(*args, **kwargs):
        return {"name": "to_delete"}
    async def fake_execute(*args, **kwargs):
        return None
    fake_db.fetchrow = fake_fetchrow
    fake_db.execute = fake_execute

    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.delete("/api/admin/agents/to_delete", headers=admin_headers)
    assert response.status_code == 204


def test_set_agent_enabled(client, admin_headers):
    """PUT /api/admin/agents/{name}/enabled 切换 enabled。"""
    from unittest.mock import AsyncMock, MagicMock

    fake_db = MagicMock()
    async def fake_fetchrow(*args, **kwargs):
        return {"name": "x", "enabled": False}
    fake_db.fetchrow = fake_fetchrow

    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.put(
        "/api/admin/agents/x/enabled",
        headers=admin_headers,
        json={"enabled": False},
    )
    assert response.status_code == 200


def test_add_field_to_state_fields(client, admin_headers):
    """POST /api/admin/agents/{name}/config-schema/field 添加 state 字段。"""
    from unittest.mock import AsyncMock, MagicMock

    fake_db = MagicMock()
    call_count = {"n": 0}
    async def fake_fetchrow(*args, **kwargs):
        call_count["n"] += 1
        # 第一次调用返回现有 config_schema；后续返回 UPDATE 结果
        if call_count["n"] == 1:
            return {"name": "x", "config_schema": {
                "state_fields": {},
                "context_fields": {},
            }}
        return {"name": "x", "config_schema": {
            "state_fields": {"new_field": {"type": "int", "default": 0}},
            "context_fields": {},
        }}
    fake_db.fetchrow = fake_fetchrow

    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.post(
        "/api/admin/agents/x/config-schema/field",
        headers=admin_headers,
        json={
            "section": "state_fields",
            "field_name": "new_field",
            "field_def": {"type": "int", "default": 0},
        },
    )
    assert response.status_code == 200


def test_add_field_invalid_section_400(client, admin_headers):
    """POST /api/admin/agents/{name}/config-schema/field 非法 section 返回 400。"""
    response = client.post(
        "/api/admin/agents/x/config-schema/field",
        headers=admin_headers,
        json={
            "section": "invalid_section",
            "field_name": "new_field",
            "field_def": {"type": "int", "default": 0},
        },
    )
    assert response.status_code == 400


def test_non_admin_access_403(client, user_headers):
    """非 admin 用户访问 /api/admin/agents 返回 403。"""
    response = client.get("/api/admin/agents", headers=user_headers)
    assert response.status_code == 403


def test_unauthenticated_access_403(client):
    """未登录访问 /api/admin/agents 返回 403（require_admin 拦截）。"""
    response = client.get("/api/admin/agents")
    # FastAPI HTTPBearer 缺失时通常 403 而非 401
    assert response.status_code in (401, 403)


def test_update_field_success(client, admin_headers):
    """PUT /api/admin/agents/{name}/config-schema/field 直接修改已存在字段。"""
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    call_count = {"n": 0}
    async def fake_fetchrow(*args, **kwargs):
        call_count["n"] += 1
        # 第一次调用返回现有 config_schema；后续返回 UPDATE 结果
        if call_count["n"] == 1:
            return {"name": "x", "config_schema": {
                "state_fields": {"existing": {"type": "int", "default": 0}},
                "context_fields": {},
            }}
        return {"name": "x", "config_schema": {
            "state_fields": {"existing": {"type": "int", "default": 42}},
            "context_fields": {},
        }}
    fake_db.fetchrow = fake_fetchrow

    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.put(
        "/api/admin/agents/x/config-schema/field",
        headers=admin_headers,
        json={
            "section": "state_fields",
            "field_name": "existing",
            "field_def": {"type": "int", "default": 42},
        },
    )
    assert response.status_code == 200


def test_delete_nonexistent_field_returns_200(client, admin_headers):
    """DELETE /config-schema/field 幂等删除：字段不存在时返回 200 而非 400。"""
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    async def fake_fetchrow(*args, **kwargs):
        return {"name": "x", "config_schema": {
            "state_fields": {},
            "context_fields": {},
        }}
    fake_db.fetchrow = fake_fetchrow

    client.app.state.db = fake_db
    client.app.state.agent_config_service._db = fake_db

    response = client.delete(
        "/api/admin/agents/x/config-schema/field?section=state_fields&field_name=not_exist",
        headers=admin_headers,
    )
    assert response.status_code == 200


def test_get_agent_returns_decoded_config_schema(client, admin_headers):
    """GET /api/admin/agents/{name} 在 DB 返回 JSONB 字符串时仍能返回 JSON 对象。"""
    from unittest.mock import AsyncMock, MagicMock

    fake_row = {
        "name": "map_agent",
        "display_name": "地图智能体",
        "description": "",
        "agents_md_path": "agents/map_agent/AGENTS.md",
        "state_schema": '{}',
        "context_schema": '{}',
        "config_schema": '{"max_tokens": {"type": "int", "default": 20000}}',
        "mcp_tags": '["map"]',
        "enabled": True,
        "sort_order": 0,
        "created_at": None,
        "updated_at": None,
    }

    async def fake_fetchrow(*args, **kwargs):
        return fake_row

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get("/api/admin/agents/map_agent", headers=admin_headers)
    assert response.status_code == 200
    data = response.json()

    # 关键断言：config_schema 必须是对象，而不是字符串
    assert isinstance(data["config_schema"], dict)
    assert data["config_schema"]["max_tokens"]["default"] == 20000
    # agent_config_overrides 应正确提取
    assert data["agent_config_overrides"]["max_tokens"] == 20000
    # mcp_tags 也必须是数组
    assert data["mcp_tags"] == ["map"]