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
        "/api/admin/agents/{name}/tool-bindings",
    ]
    # PUT /config-schema/field 与 POST / DELETE 共享同一 path，已包含在上面的 path 中
    for path in expected:
        assert path in routes, f"路由未注册: {path}"


# ============================================================
# 字段模板 + 唯一性 + 路径校验（无需 DB）
# ============================================================

def test_field_templates_returns_list(client, admin_headers):
    """GET /api/admin/agents/field-templates 默认返回 AgentConfig 字段模板列表。"""
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


def test_field_templates_state_fields_returns_list(client, admin_headers):
    """GET /api/admin/agents/field-templates?section=state_fields 返回 AgentState 字段模板。"""
    response = client.get(
        "/api/admin/agents/field-templates?section=state_fields",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    field_names = [t["field_name"] for t in data]
    assert "error_limit" in field_names
    assert "limit" in field_names
    # 不应包含运行时必需字段 messages
    assert "messages" not in field_names


def test_field_templates_context_fields_returns_list(client, admin_headers):
    """GET /api/admin/agents/field-templates?section=context_fields 返回 AgentContext 字段模板。"""
    response = client.get(
        "/api/admin/agents/field-templates?section=context_fields",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data, list)
    assert len(data) > 0
    field_names = [t["field_name"] for t in data]
    assert "session_id" in field_names
    assert "namespace" in field_names
    assert "store_id" in field_names


def test_field_templates_invalid_section_400(client, admin_headers):
    """GET /api/admin/agents/field-templates?section=invalid 返回 400。"""
    response = client.get(
        "/api/admin/agents/field-templates?section=invalid",
        headers=admin_headers,
    )
    assert response.status_code == 400


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


def test_update_agent_basic_info_success(client, admin_headers):
    """PUT /api/admin/agents/{name} 成功更新 display_name 和 description。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码或返回值不符合预期时抛出
    """
    from unittest.mock import MagicMock

    async def fake_fetchrow(*args, **kwargs):
        return {
            "name": "x", "display_name": "新名称", "description": "新描述",
            "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
            "config_schema": {}, "mcp_tags": [], "tool_bindings": [],
            "enabled": True,
        }

    async def fake_fetch(*args, **kwargs):
        return []

    fake_db = MagicMock()
    fake_db.fetchrow = fake_fetchrow
    fake_db.fetch = fake_fetch

    client.app.state.db = fake_db
    service = client.app.state.agent_config_service
    service._db = fake_db
    service._loader.load = MagicMock(return_value="prompt")

    response = client.put(
        "/api/admin/agents/x",
        headers=admin_headers,
        json={"display_name": "新名称", "description": "新描述"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["display_name"] == "新名称"
    assert data["description"] == "新描述"


def test_update_agent_basic_info_not_found_404(client, admin_headers):
    """PUT /api/admin/agents/{name} agent 不存在返回 404。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码不符合预期时抛出
    """
    from unittest.mock import MagicMock

    async def fake_fetchrow(*args, **kwargs):
        return None

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.put(
        "/api/admin/agents/nonexistent",
        headers=admin_headers,
        json={"display_name": "名称", "description": "描述"},
    )
    assert response.status_code == 404


def test_update_agent_basic_info_missing_display_name_422(client, admin_headers):
    """PUT /api/admin/agents/{name} 缺少 display_name 返回 422。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码不符合预期时抛出
    """
    response = client.put(
        "/api/admin/agents/x",
        headers=admin_headers,
        json={"description": "只有描述"},
    )
    assert response.status_code == 422


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


# ============================================================
# 工具绑定 (tool-bindings) 端点测试
# ============================================================

def test_get_tool_bindings_returns_list(client, admin_headers):
    """GET /api/admin/agents/{name}/tool-bindings 返回工具绑定列表。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    from unittest.mock import MagicMock

    fake_row = {
        "tool_bindings": [
            {"tool_name": "search", "tool_type": "builtin",
             "enabled": True, "sort_order": 0},
            {"tool_name": "map_mcp", "tool_type": "mcp",
             "enabled": False, "sort_order": 1},
        ]
    }

    async def fake_fetchrow(*args, **kwargs):
        return fake_row

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get(
        "/api/admin/agents/map_agent/tool-bindings", headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "map_agent"
    assert isinstance(data["tool_bindings"], list)
    assert len(data["tool_bindings"]) == 2
    assert data["tool_bindings"][0]["tool_name"] == "search"
    assert data["tool_bindings"][1]["tool_type"] == "mcp"


def test_get_tool_bindings_returns_empty_list(client, admin_headers):
    """GET /api/admin/agents/{name}/tool-bindings 无绑定时返回空列表。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    from unittest.mock import MagicMock

    async def fake_fetchrow(*args, **kwargs):
        return {"tool_bindings": []}

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get(
        "/api/admin/agents/empty_agent/tool-bindings", headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "empty_agent"
    assert data["tool_bindings"] == []


def test_get_tool_bindings_agent_not_found_404(client, admin_headers):
    """GET /api/admin/agents/{name}/tool-bindings agent 不存在返回 404。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码不符合预期时抛出
    """
    from unittest.mock import MagicMock

    async def fake_fetchrow(*args, **kwargs):
        return None

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get(
        "/api/admin/agents/nonexistent/tool-bindings", headers=admin_headers,
    )
    assert response.status_code == 404


def test_get_tool_bindings_decodes_jsonb_string(client, admin_headers):
    """GET /api/admin/agents/{name}/tool-bindings 在 DB 返回 JSONB 字符串时正确解码。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 解码结果不符合预期时抛出
    """
    from unittest.mock import MagicMock

    async def fake_fetchrow(*args, **kwargs):
        # asyncpg 未注册 JSONB codec 时返回字符串
        return {"tool_bindings": '[{"tool_name": "x", "tool_type": "builtin"}]'}

    service = client.app.state.agent_config_service
    if service._db is None:
        service._db = MagicMock()
    service._db.fetchrow = fake_fetchrow

    response = client.get(
        "/api/admin/agents/x/tool-bindings", headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert isinstance(data["tool_bindings"], list)
    assert data["tool_bindings"][0]["tool_name"] == "x"


def test_update_tool_bindings_success(client, admin_headers):
    """PUT /api/admin/agents/{name}/tool-bindings 成功更新工具绑定列表。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    # update_tool_bindings 调用 fetchrow（UPDATE RETURNING *），
    # 随后 _refresh_cache → _load_from_db 再次调用 fetchrow + fetch
    updated_row = {
        "name": "map_agent", "display_name": "地图智能体", "description": "",
        "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [],
        "tool_bindings": [
            {"tool_name": "search", "tool_type": "builtin",
             "enabled": True, "sort_order": 0},
        ],
        "enabled": True,
    }

    async def fake_fetchrow(*args, **kwargs):
        return updated_row

    async def fake_fetch(*args, **kwargs):
        return []

    fake_db.fetchrow = fake_fetchrow
    fake_db.fetch = fake_fetch

    client.app.state.db = fake_db
    service = client.app.state.agent_config_service
    service._db = fake_db
    # _refresh_cache → _load_from_db 会调用 loader.load(agents_md_path)，
    # 真实 loader 会读文件抛 FileNotFoundError，此处 mock 为返回固定 prompt
    service._loader.load = MagicMock(return_value="prompt")

    response = client.put(
        "/api/admin/agents/map_agent/tool-bindings",
        headers=admin_headers,
        json={
            "bindings": [
                {"tool_name": "search", "tool_type": "builtin",
                 "enabled": True, "sort_order": 0},
            ]
        },
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "map_agent"
    assert isinstance(data["tool_bindings"], list)
    assert data["tool_bindings"][0]["tool_name"] == "search"


def test_update_tool_bindings_empty_list_clears_bindings(client, admin_headers):
    """PUT /api/admin/agents/{name}/tool-bindings 传空列表清空所有绑定。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 返回值不符合预期时抛出
    """
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    updated_row = {
        "name": "x", "display_name": "X", "description": "",
        "agents_md_path": "x.md", "state_schema": {}, "context_schema": {},
        "config_schema": {}, "mcp_tags": [], "tool_bindings": [],
        "enabled": True,
    }

    async def fake_fetchrow(*args, **kwargs):
        return updated_row

    async def fake_fetch(*args, **kwargs):
        return []

    fake_db.fetchrow = fake_fetchrow
    fake_db.fetch = fake_fetch

    client.app.state.db = fake_db
    service = client.app.state.agent_config_service
    service._db = fake_db
    # _refresh_cache → _load_from_db 会调用 loader.load(agents_md_path)，
    # 真实 loader 会读文件抛 FileNotFoundError，此处 mock 为返回固定 prompt
    service._loader.load = MagicMock(return_value="prompt")

    response = client.put(
        "/api/admin/agents/x/tool-bindings",
        headers=admin_headers,
        json={"bindings": []},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["tool_bindings"] == []


def test_update_tool_bindings_agent_not_found_404(client, admin_headers):
    """PUT /api/admin/agents/{name}/tool-bindings agent 不存在返回 404。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码不符合预期时抛出
    """
    from unittest.mock import MagicMock

    fake_db = MagicMock()
    # UPDATE ... RETURNING * 在 agent 不存在时返回 None
    async def fake_fetchrow(*args, **kwargs):
        return None

    async def fake_fetch(*args, **kwargs):
        return []

    fake_db.fetchrow = fake_fetchrow
    fake_db.fetch = fake_fetch

    client.app.state.db = fake_db
    service = client.app.state.agent_config_service
    service._db = fake_db
    # agent 不存在时 update_tool_bindings 直接抛 AgentNotFoundError，
    # 不会进入 _refresh_cache，但防御性 mock loader 避免意外调用
    service._loader.load = MagicMock(return_value="prompt")

    response = client.put(
        "/api/admin/agents/nonexistent/tool-bindings",
        headers=admin_headers,
        json={"bindings": []},
    )
    assert response.status_code == 404


def test_update_tool_bindings_invalid_payload_422(client, admin_headers):
    """PUT /api/admin/agents/{name}/tool-bindings 非法 payload（缺 tool_name）返回 422。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 状态码不符合预期时抛出
    """
    response = client.put(
        "/api/admin/agents/x/tool-bindings",
        headers=admin_headers,
        json={"bindings": [{"tool_type": "builtin"}]},  # 缺少 tool_name
    )
    assert response.status_code == 422


# ============================================================
# 可绑定工具列表 (available-tools) 端点测试
# ============================================================
# 端点签名：GET /api/admin/agents/{name}/available-tools
# 返回结构：{"agent_name": str, "builtin": [...], "mcp": [...]}
# - builtin 项：name / display_name / category / description / module_path /
#   file_path / file_basename
# - mcp 项：server_name / server_display_name / method_name / display_name /
#   description / tool_name("server.method") / enabled
# ============================================================


def test_available_tools_returns_builtin_and_mcp(client, admin_headers):
    """GET /api/admin/agents/{name}/available-tools 返回 200 且含 builtin/mcp 字段。

    端点合并 ToolRegistryService.list_tools() 与 McpConfigService.list_servers() +
    list_methods() 的结果，供前端「工具绑定」面板使用。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 响应结构不符合预期时抛出
    """
    from unittest.mock import AsyncMock

    fake_tools = [
        {
            "name": "get_current_time",
            "display_name": "获取当前时间",
            "category": "utility",
            "description": "返回当前时间字符串",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
            "args_schema": {},
            "return_description": "str",
            "function_description": "获取当前时间",
            "enabled": True,
        },
    ]
    fake_servers = [
        {
            "name": "amap",
            "display_name": "高德地图",
            "type": "sse",
            "url": "https://example.com/sse",
            "enabled": True,
            "tags": ["map"],
        },
    ]
    fake_methods = [
        {
            "method_name": "search",
            "display_name": "地点搜索",
            "description": "根据关键词搜索 POI",
            "enabled": True,
        },
    ]

    tool_service = client.app.state.tool_service
    tool_service.list_tools = AsyncMock(return_value=fake_tools)
    mcp_service = client.app.state.mcp_config_service
    mcp_service.list_servers = AsyncMock(return_value=fake_servers)
    mcp_service.list_methods = AsyncMock(return_value=fake_methods)

    response = client.get(
        "/api/admin/agents/map_agent/available-tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert data["agent_name"] == "map_agent"
    assert isinstance(data["builtin"], list)
    assert isinstance(data["mcp"], list)
    assert len(data["builtin"]) == 1
    assert len(data["mcp"]) == 1
    # 验证 builtin 项关键字段
    assert data["builtin"][0]["name"] == "get_current_time"
    # 验证 mcp 项关键字段
    assert data["mcp"][0]["server_name"] == "amap"
    assert data["mcp"][0]["method_name"] == "search"


def test_available_tools_includes_file_basename_for_builtin(client, admin_headers):
    """GET .../available-tools builtin 项的 file_basename 从 file_path 提取。

    端点期望对 file_path='app/core/tools/BaseTools.py' 提取
    file_basename='BaseTools'，前端用于展示「BaseTools.get_current_time」形式。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: file_basename 不正确时抛出
    """
    from unittest.mock import AsyncMock

    fake_tools = [
        {
            "name": "get_current_time",
            "display_name": "获取当前时间",
            "category": "utility",
            "description": "返回当前时间",
            "module_path": "app.core.tools.BaseTools",
            "file_path": "app/core/tools/BaseTools.py",
            "args_schema": {},
            "return_description": "str",
            "function_description": "获取当前时间",
            "enabled": True,
        },
    ]
    tool_service = client.app.state.tool_service
    tool_service.list_tools = AsyncMock(return_value=fake_tools)
    mcp_service = client.app.state.mcp_config_service
    mcp_service.list_servers = AsyncMock(return_value=[])
    mcp_service.list_methods = AsyncMock(return_value=[])

    response = client.get(
        "/api/admin/agents/any_agent/available-tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["builtin"]) == 1
    builtin_item = data["builtin"][0]
    assert builtin_item["file_path"] == "app/core/tools/BaseTools.py"
    # 关键断言：file_basename 应为 "BaseTools"（去除 .py 后缀）
    assert builtin_item["file_basename"] == "BaseTools"
    # 其他字段也正确返回
    assert builtin_item["name"] == "get_current_time"
    assert builtin_item["display_name"] == "获取当前时间"
    assert builtin_item["category"] == "utility"
    assert builtin_item["module_path"] == "app.core.tools.BaseTools"


def test_available_tools_uses_server_dot_method_composite_name_for_mcp(client, admin_headers):
    """GET .../available-tools mcp 项的 tool_name 格式为 'server.method'。

    端点构造复合 tool_name='server_name.method_name'，用于保存到
    agents.tool_bindings 时作为唯一标识（与 builtin 工具区分命名空间）。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: tool_name 格式不符合预期时抛出
    """
    from unittest.mock import AsyncMock

    fake_servers = [
        {
            "name": "amap",
            "display_name": "高德地图",
            "type": "sse",
            "url": "https://example.com/sse",
            "enabled": True,
            "tags": [],
        },
    ]
    fake_methods = [
        {
            "method_name": "search",
            "display_name": "地点搜索",
            "description": "搜索 POI",
            "enabled": True,
        },
        {
            "method_name": "route",
            "display_name": "路径规划",
            "description": "规划路径",
            "enabled": True,
        },
    ]
    tool_service = client.app.state.tool_service
    tool_service.list_tools = AsyncMock(return_value=[])
    mcp_service = client.app.state.mcp_config_service
    mcp_service.list_servers = AsyncMock(return_value=fake_servers)
    mcp_service.list_methods = AsyncMock(return_value=fake_methods)

    response = client.get(
        "/api/admin/agents/any_agent/available-tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    assert len(data["mcp"]) == 2
    tool_names = {item["tool_name"] for item in data["mcp"]}
    # 关键断言：tool_name 必须为 "server.method" 复合名
    assert "amap.search" in tool_names
    assert "amap.route" in tool_names
    # 每项还应包含 server_name / method_name / server_display_name
    for item in data["mcp"]:
        assert item["server_name"] == "amap"
        assert item["server_display_name"] == "高德地图"
        assert item["method_name"] in {"search", "route"}
        assert item["enabled"] is True


def test_available_tools_excludes_disabled_mcp_servers(client, admin_headers):
    """GET .../available-tools MCP server enabled=FALSE 时不返回其 methods。

    端点对 list_servers() 返回的每个 server 检查 enabled 字段；enabled=FALSE
    的 server 整体跳过，不展开其 methods（保持工具列表最小可用集）。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 禁用 server 未被过滤时抛出
    """
    from unittest.mock import AsyncMock

    fake_servers = [
        {
            "name": "amap",
            "display_name": "高德地图",
            "type": "sse",
            "url": "https://example.com/sse",
            "enabled": True,
            "tags": [],
        },
        {
            "name": "disabled_server",
            "display_name": "已禁用",
            "type": "stdio",
            "command": ["python", "-m", "fake"],
            "enabled": False,
            "tags": [],
        },
    ]
    # 即使禁用 server 的 list_methods 被调用，endpoints 应不调用；
    # 若被意外调用，返回空列表，断言会失败
    fake_methods_enabled = [
        {
            "method_name": "search",
            "display_name": "搜索",
            "description": "搜索 POI",
            "enabled": True,
        },
    ]

    async def list_methods_separator(server_name):
        # 若端点对 disabled_server 调用了 list_methods，立即失败以提示 bug
        assert server_name != "disabled_server", (
            f"端点不应查询禁用 server '{server_name}' 的 methods"
        )
        return fake_methods_enabled

    tool_service = client.app.state.tool_service
    tool_service.list_tools = AsyncMock(return_value=[])
    mcp_service = client.app.state.mcp_config_service
    mcp_service.list_servers = AsyncMock(return_value=fake_servers)
    mcp_service.list_methods = AsyncMock(side_effect=list_methods_separator)

    response = client.get(
        "/api/admin/agents/any_agent/available-tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # mcp 列表只应包含 amap 的方法，disabled_server 整个被排除
    assert len(data["mcp"]) == 1
    assert data["mcp"][0]["server_name"] == "amap"
    assert data["mcp"][0]["tool_name"] == "amap.search"
    # 验证 disabled_server 的 tool_name 不存在
    tool_names = [item["tool_name"] for item in data["mcp"]]
    assert "disabled_server.search" not in tool_names


def test_available_tools_excludes_disabled_mcp_methods(client, admin_headers):
    """GET .../available-tools MCP method enabled=FALSE 时不返回该 method。

    端点对每个 server 调用 list_methods() 后逐个 method 检查 enabled 字段；
    enabled=FALSE 的 method 被跳过，enabled=TRUE 的正常返回。

    参数:
        client: FastAPI TestClient
        admin_headers: admin 认证头

    返回:
        None

    异常:
        AssertionError: 禁用 method 未被过滤时抛出
    """
    from unittest.mock import AsyncMock

    fake_servers = [
        {
            "name": "amap",
            "display_name": "高德地图",
            "type": "sse",
            "url": "https://example.com/sse",
            "enabled": True,
            "tags": [],
        },
    ]
    fake_methods = [
        {
            "method_name": "search",
            "display_name": "搜索",
            "description": "搜索 POI",
            "enabled": True,
        },
        {
            "method_name": "disabled_method",
            "display_name": "已禁用方法",
            "description": "暂不开放",
            "enabled": False,
        },
    ]

    tool_service = client.app.state.tool_service
    tool_service.list_tools = AsyncMock(return_value=[])
    mcp_service = client.app.state.mcp_config_service
    mcp_service.list_servers = AsyncMock(return_value=fake_servers)
    mcp_service.list_methods = AsyncMock(return_value=fake_methods)

    response = client.get(
        "/api/admin/agents/any_agent/available-tools",
        headers=admin_headers,
    )
    assert response.status_code == 200
    data = response.json()
    # mcp 列表只应包含 enabled=TRUE 的 search，disabled_method 被排除
    assert len(data["mcp"]) == 1
    assert data["mcp"][0]["method_name"] == "search"
    assert data["mcp"][0]["tool_name"] == "amap.search"
    # 验证 disabled_method 未出现在列表中
    method_names = [item["method_name"] for item in data["mcp"]]
    assert "disabled_method" not in method_names
