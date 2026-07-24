# -*- coding:utf-8 -*-
"""
ApiConfigService 测试模块。

验证 API 接口配置服务的节点树管理、配置 upsert、预期结果断言与请求发送。
使用 FakeDb 模拟 asyncpg 连接池（fetch / fetchrow / execute），
httpx 通过 monkeypatch 替换 AsyncClient，不发起真实网络请求。
"""
import asyncio
from datetime import datetime

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope


# 全部用例使用 admin scope（user_id=1, is_admin=True），保持与原行为一致
# （历史用例假定 service 调用不带权限语义）。按用户隔离的行为在
# test_api_config_service_scope.py 中专项验证。
ADMIN_SCOPE = OwnershipScope.for_user(1, is_admin=True)


class FakeDb:
    """测试用异步 DB，按 SQL 关键字模拟 api_config_* 三表行为。"""

    def __init__(self):
        self.nodes = {}
        self.configs = {}  # node_id -> row
        self.runs = []
        self.next_node_id = 1
        self.next_config_id = 1
        self.next_run_id = 1

    async def fetch(self, query, *args):
        if "FROM api_config_nodes" in query:
            return list(self.nodes.values())
        if "FROM api_configs" in query:
            return list(self.configs.values())
        if "FROM api_check_runs" in query:
            config_id = args[0]
            limit = args[1]
            rows = [r for r in self.runs if r["config_id"] == config_id]
            rows.sort(key=lambda r: r["id"], reverse=True)
            return rows[:limit]
        return []

    async def fetchrow(self, query, *args):
        if "INSERT INTO api_config_nodes" in query:
            row = {
                "id": self.next_node_id,
                "parent_id": args[0],
                "node_type": args[1],
                "name": args[2],
                "sort_order": args[3],
                "created_by_user_id": args[4],
                "created_at": datetime(2026, 7, 20, 10, 0, 0),
                "updated_at": datetime(2026, 7, 20, 10, 0, 0),
            }
            self.nodes[row["id"]] = row
            self.next_node_id += 1
            return row
        if "INSERT INTO api_configs" in query:
            if len(args) == 1:
                # create_node 自动创建默认配置：仅 node_id
                row = {
                    "id": self.next_config_id,
                    "node_id": args[0],
                    "method": "POST",
                    "url": "",
                    "params": [],
                    "headers": [],
                    "body_type": "none",
                    "body_content": "",
                    "form_fields": [],
                    "expectations": [],
                    "created_at": datetime(2026, 7, 20, 10, 0, 0),
                    "updated_at": datetime(2026, 7, 20, 10, 0, 0),
                }
            else:
                # upsert_config：node_id + 8 个字段
                row = {
                    "id": self.next_config_id,
                    "node_id": args[0],
                    "method": args[1],
                    "url": args[2],
                    "params": args[3],
                    "headers": args[4],
                    "body_type": args[5],
                    "body_content": args[6],
                    "form_fields": args[7],
                    "expectations": args[8],
                    "created_at": datetime(2026, 7, 20, 10, 0, 0),
                    "updated_at": datetime(2026, 7, 20, 10, 0, 0),
                }
            existing = self.configs.get(row["node_id"])
            if existing is not None:
                row["id"] = existing["id"]
                row["created_at"] = existing["created_at"]
            else:
                self.next_config_id += 1
            self.configs[row["node_id"]] = row
            return row
        if "UPDATE api_config_nodes" in query:
            node_id = args[0]
            row = self.nodes.get(node_id)
            if row is None:
                return None
            if args[1] is not None:
                row["name"] = args[1]
            if args[2] is not None:
                row["parent_id"] = args[2]
            if args[3] is not None:
                row["sort_order"] = args[3]
            row["updated_at"] = datetime(2026, 7, 20, 11, 0, 0)
            return row
        if "INSERT INTO api_check_runs" in query:
            row = {
                "id": self.next_run_id,
                "config_id": args[0],
                "http_status": args[1],
                "duration_ms": args[2],
                "check_passed": args[3],
                "response_excerpt": args[4],
                "error_message": args[5],
                "created_at": datetime(2026, 7, 20, 12, 0, 0),
            }
            self.runs.append(row)
            self.next_run_id += 1
            return row
        return None

    async def execute(self, query, *args):
        if "DELETE FROM api_config_nodes" in query:
            node_id = args[0]
            if node_id in self.nodes:
                del self.nodes[node_id]
                return "DELETE 1"
            return "DELETE 0"
        return "OK"


def _make_service(db=None):
    """构造 ApiConfigService 实例。

    参数:
        db: FakeDb 实例；None 时传入 FakeDb()。

    返回:
        ApiConfigService: 服务实例。
    """
    from app.shared.utils.api_config_service import ApiConfigService

    return ApiConfigService(db=db if db is not None else FakeDb())


class FakeResponse:
    """测试用 httpx 响应。"""

    def __init__(self, status_code=200, text="{}"):
        self.status_code = status_code
        self.text = text


class FakeAsyncClient:
    """测试用 httpx.AsyncClient 替身，支持成功与异常两种模式。"""

    response = FakeResponse()
    raise_error = None
    last_request = None

    def __init__(self, *args, **kwargs):
        self.timeout = kwargs.get("timeout")

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc_info):
        return False

    async def request(self, method, url, **kwargs):
        type(self).last_request = {"method": method, "url": url, "kwargs": kwargs}
        if type(self).raise_error is not None:
            raise type(self).raise_error
        return type(self).response


@pytest.fixture
def patched_httpx(monkeypatch):
    """把 service 模块内的 httpx.AsyncClient 替换为 FakeAsyncClient。

    参数:
        monkeypatch: pytest monkeypatch fixture。

    返回:
        FakeAsyncClient: 替身类，可通过类属性配置响应或异常。
    """
    FakeAsyncClient.response = FakeResponse()
    FakeAsyncClient.raise_error = None
    FakeAsyncClient.last_request = None
    monkeypatch.setattr(
        "app.shared.utils.api_config_service.httpx.AsyncClient",
        FakeAsyncClient,
    )
    return FakeAsyncClient


# =============================================================================
# P0: 导入与节点创建
# =============================================================================

def test_api_config_service_importable():
    """测试 api_config_service 模块可导入且包含 ApiConfigService。"""
    from app.shared.utils import api_config_service

    assert hasattr(api_config_service, "ApiConfigService")


def test_create_folder_node_at_root():
    """测试在根节点下创建文件夹节点，写入内存与 DB。"""
    service = _make_service()

    node = asyncio.run(service.create_node(None, "folder", "支付网关", ADMIN_SCOPE))

    assert node["id"] == 1
    assert node["parent_id"] is None
    assert node["node_type"] == "folder"
    assert service._nodes[1]["name"] == "支付网关"
    assert service._nodes[1]["created_by_user_id"] == 1


def test_create_api_node_auto_creates_default_config():
    """测试创建 api 类型节点时自动创建默认 api_configs 行。"""
    service = _make_service()

    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    node = asyncio.run(service.create_node(folder["id"], "api", "查询接口", ADMIN_SCOPE))

    assert node["node_type"] == "api"
    config = service._configs[node["id"]]
    assert config["method"] == "POST"
    assert config["url"] == ""
    assert config["body_type"] == "none"
    assert service._db.configs[node["id"]]["node_id"] == node["id"]


def test_create_node_with_missing_parent_raises_value_error():
    """测试 parent_id 指向不存在节点时抛 ValueError("父节点不存在")。

    与「越权访问父节点」统一为相同错误（ValueError），避免泄露节点是否
    对他用户存在；路由层映射 HTTP 400。
    """
    service = _make_service()

    with pytest.raises(ValueError, match="父节点不存在"):
        asyncio.run(service.create_node(999, "folder", "孤儿", ADMIN_SCOPE))


def test_create_node_under_api_parent_raises_value_error():
    """测试父节点不是 folder 时抛 ValueError。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(service.create_node(api_node["id"], "api", "子接口", ADMIN_SCOPE))


def test_create_node_invalid_type_raises_value_error():
    """测试非法 node_type 抛 ValueError。"""
    service = _make_service()

    with pytest.raises(ValueError):
        asyncio.run(service.create_node(None, "link", "坏节点", ADMIN_SCOPE))


# =============================================================================
# P1: 节点更新与防环
# =============================================================================

def test_update_node_rename():
    """测试 update_node 修改名称并同步内存与 DB。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "旧名", ADMIN_SCOPE))

    updated = asyncio.run(service.update_node(folder["id"], ADMIN_SCOPE, name="新名"))

    assert updated["name"] == "新名"
    assert service._nodes[folder["id"]]["name"] == "新名"


def test_update_node_move_into_own_descendant_raises_value_error():
    """测试把文件夹移动到自己的后代下形成环时抛 ValueError。"""
    service = _make_service()
    root = asyncio.run(service.create_node(None, "folder", "根", ADMIN_SCOPE))
    child = asyncio.run(service.create_node(root["id"], "folder", "子", ADMIN_SCOPE))
    grandchild = asyncio.run(service.create_node(child["id"], "folder", "孙", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(service.update_node(root["id"], ADMIN_SCOPE, parent_id=grandchild["id"]))


def test_update_node_move_to_self_raises_value_error():
    """测试把节点移动到自己下面时抛 ValueError。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "根", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(service.update_node(folder["id"], ADMIN_SCOPE, parent_id=folder["id"]))


def test_update_node_missing_raises_not_found():
    """测试更新不存在节点抛 ApiConfigNotFoundError。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = _make_service()

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.update_node(999, ADMIN_SCOPE, name="不存在"))


# =============================================================================
# P1: 节点删除
# =============================================================================

def test_delete_non_empty_folder_raises_value_error():
    """测试删除非空文件夹抛 ValueError('文件夹非空，拒绝删除')。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    with pytest.raises(ValueError, match="文件夹非空"):
        asyncio.run(service.delete_node(folder["id"], ADMIN_SCOPE))


def test_delete_api_node_cascades_config():
    """测试删除 api 节点时内存中的配置一并删除。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    asyncio.run(service.delete_node(api_node["id"], ADMIN_SCOPE))

    assert api_node["id"] not in service._nodes
    assert api_node["id"] not in service._configs


def test_delete_missing_node_raises_not_found():
    """测试删除不存在节点抛 ApiConfigNotFoundError。"""
    from app.shared.utils.api_config_service import ApiConfigNotFoundError

    service = _make_service()

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.delete_node(999, ADMIN_SCOPE))


# =============================================================================
# P1: 配置 upsert 校验
# =============================================================================

def test_upsert_config_success():
    """测试合法配置 upsert 成功并同步内存。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    config = asyncio.run(
        service.upsert_config(
            api_node["id"],
            ADMIN_SCOPE,
            method="PUT",
            url="https://example.com/api",
            params=[{"name": "a", "value": "1", "description": ""}],
            headers=[{"name": "X-Token", "value": "t", "description": ""}],
            body_type="json",
            body_content='{"k": "v"}',
            form_fields=[],
            expectations=[{"type": "status_code", "operator": "eq", "value": 200}],
        )
    )

    assert config["method"] == "PUT"
    assert config["url"] == "https://example.com/api"
    assert service._configs[api_node["id"]]["body_type"] == "json"


def test_upsert_config_invalid_method_raises_value_error():
    """测试非法 method 抛 ValueError。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(
            service.upsert_config(
                api_node["id"],
                ADMIN_SCOPE,
                method="GET",
                url="https://example.com",
                params=[],
                headers=[],
                body_type="none",
                body_content="",
                form_fields=[],
                expectations=[],
            )
        )


def test_upsert_config_invalid_body_type_raises_value_error():
    """测试非法 body_type 抛 ValueError。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(
            service.upsert_config(
                api_node["id"],
                ADMIN_SCOPE,
                method="POST",
                url="https://example.com",
                params=[],
                headers=[],
                body_type="graphql",
                body_content="",
                form_fields=[],
                expectations=[],
            )
        )


def test_upsert_config_invalid_expectation_type_raises_value_error():
    """测试 expectations 中含非法 type 时抛 ValueError。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(
            service.upsert_config(
                api_node["id"],
                ADMIN_SCOPE,
                method="POST",
                url="https://example.com",
                params=[],
                headers=[],
                body_type="none",
                body_content="",
                form_fields=[],
                expectations=[{"type": "regex", "value": ".*"}],
            )
        )


def test_get_config_on_folder_raises_value_error():
    """测试对 folder 节点调用 get_config 抛 ValueError（不是 api 类型）。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))

    with pytest.raises(ValueError):
        asyncio.run(service.get_config(folder["id"], ADMIN_SCOPE))


# =============================================================================
# P1: 预期结果断言
# =============================================================================

def test_evaluate_expectations_status_code_eq():
    """测试 status_code eq 断言的通过与失败。"""
    from app.shared.utils.api_config_service import ApiConfigService

    rules = [{"type": "status_code", "operator": "eq", "value": 200}]

    ok = ApiConfigService._evaluate_expectations(rules, 200, "")
    fail = ApiConfigService._evaluate_expectations(rules, 500, "")

    assert ok[0]["passed"] is True
    assert fail[0]["passed"] is False


def test_evaluate_expectations_body_contains():
    """测试 body_contains 子串断言。"""
    from app.shared.utils.api_config_service import ApiConfigService

    rules = [{"type": "body_contains", "value": "success"}]

    ok = ApiConfigService._evaluate_expectations(rules, 200, '{"msg":"success"}')
    fail = ApiConfigService._evaluate_expectations(rules, 200, '{"msg":"fail"}')

    assert ok[0]["passed"] is True
    assert fail[0]["passed"] is False


def test_evaluate_expectations_json_field_exists_and_eq():
    """测试 json_field 断言支持点号路径下钻 dict 与 list 索引。"""
    from app.shared.utils.api_config_service import ApiConfigService

    body = '{"data": {"items": [{"id": 42}]}}'
    exists_rule = [{"type": "json_field", "path": "data.items.0.id", "operator": "exists"}]
    eq_rule = [{"type": "json_field", "path": "data.items.0.id", "operator": "eq", "value": 42}]
    miss_rule = [{"type": "json_field", "path": "data.missing", "operator": "exists"}]

    assert ApiConfigService._evaluate_expectations(exists_rule, 200, body)[0]["passed"] is True
    assert ApiConfigService._evaluate_expectations(eq_rule, 200, body)[0]["passed"] is True
    assert ApiConfigService._evaluate_expectations(miss_rule, 200, body)[0]["passed"] is False


def test_evaluate_expectations_json_field_invalid_json_fails():
    """测试响应体非 JSON 时 json_field 断言失败。"""
    from app.shared.utils.api_config_service import ApiConfigService

    rules = [{"type": "json_field", "path": "data.id", "operator": "exists"}]
    result = ApiConfigService._evaluate_expectations(rules, 200, "not json")

    assert result[0]["passed"] is False


# =============================================================================
# P1: 请求发送
# =============================================================================

def test_send_request_success(patched_httpx):
    """测试 send_request 成功路径：断言通过、响应截断、运行记录落库。"""
    patched_httpx.response = FakeResponse(status_code=200, text="x" * 5000)
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))
    asyncio.run(
        service.upsert_config(
            api_node["id"],
            ADMIN_SCOPE,
            method="POST",
            url="https://example.com/api",
            params=[{"name": "a", "value": "1", "description": ""}],
            headers=[{"name": "X-Token", "value": "t", "description": ""}],
            body_type="json",
            body_content='{"k": "v"}',
            form_fields=[],
            expectations=[{"type": "status_code", "operator": "eq", "value": 200}],
        )
    )

    result = asyncio.run(service.send_request(api_node["id"], ADMIN_SCOPE))

    assert result["http_status"] == 200
    assert result["check_passed"] is True
    assert len(result["response_body"]) == 4000
    assert result["run_id"] == 1
    assert result["assertion_results"][0]["passed"] is True
    assert result["error_message"] == ""
    assert service._db.runs[0]["http_status"] == 200
    assert service._db.runs[0]["check_passed"] is True
    # query params 与 json body 正确组装
    req = patched_httpx.last_request
    assert req["kwargs"]["params"] == {"a": "1"}
    assert req["kwargs"]["json"] == {"k": "v"}


def test_send_request_json_fallback_to_raw_text(patched_httpx):
    """测试 body_type=json 但 body_content 非法 JSON 时按 raw text 发送。"""
    patched_httpx.response = FakeResponse(status_code=200, text="ok")
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))
    asyncio.run(
        service.upsert_config(
            api_node["id"],
            ADMIN_SCOPE,
            method="POST",
            url="https://example.com/api",
            params=[],
            headers=[],
            body_type="json",
            body_content="{bad json",
            form_fields=[],
            expectations=[],
        )
    )

    asyncio.run(service.send_request(api_node["id"], ADMIN_SCOPE))

    req = patched_httpx.last_request
    assert req["kwargs"]["content"] == "{bad json"
    assert "json" not in req["kwargs"]


def test_send_request_network_error_records_run(patched_httpx):
    """测试网络异常时 http_status=None、check_passed=False 且记录落库。"""
    patched_httpx.raise_error = RuntimeError("connection refused")
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    result = asyncio.run(service.send_request(api_node["id"], ADMIN_SCOPE))

    assert result["http_status"] is None
    assert result["check_passed"] is False
    assert "connection refused" in result["error_message"]
    assert service._db.runs[0]["http_status"] is None
    assert service._db.runs[0]["check_passed"] is False
    assert "connection refused" in service._db.runs[0]["error_message"]


def test_list_runs_returns_history(patched_httpx):
    """测试 list_runs 返回调用历史并按时间倒序。"""
    patched_httpx.response = FakeResponse(status_code=200, text="ok")
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    api_node = asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    asyncio.run(service.send_request(api_node["id"], ADMIN_SCOPE))
    asyncio.run(service.send_request(api_node["id"], ADMIN_SCOPE))
    runs = asyncio.run(service.list_runs(api_node["id"], ADMIN_SCOPE))

    assert len(runs) == 2
    assert runs[0]["id"] > runs[1]["id"]


# =============================================================================
# P2: 预加载与降级
# =============================================================================

def test_preload_all_loads_nodes_and_configs():
    """测试 preload_all 把 DB 中的节点与配置载入内存。"""
    service = _make_service()
    folder = asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
    asyncio.run(service.create_node(folder["id"], "api", "接口", ADMIN_SCOPE))

    fresh = _make_service(db=service._db)
    fresh._nodes.clear()
    fresh._configs.clear()
    asyncio.run(fresh.preload_all())

    assert len(fresh._nodes) == 2
    assert len(fresh._configs) == 1


def test_db_none_graceful_degradation():
    """测试 db=None 时 preload no-op、读返回空、写抛 RuntimeError。"""
    from app.shared.utils.api_config_service import ApiConfigService

    service = ApiConfigService(db=None)

    asyncio.run(service.preload_all())
    assert asyncio.run(service.get_tree(ADMIN_SCOPE)) == []
    with pytest.raises(RuntimeError):
        asyncio.run(service.create_node(None, "folder", "分组", ADMIN_SCOPE))
