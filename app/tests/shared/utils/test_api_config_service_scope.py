# -*- coding:utf-8 -*-
"""
ApiConfigService 按用户隔离（OwnershipScope）测试模块。

验证:
- get_tree 按 scope 过滤;非 admin 看不到他人节点;父节点不可见时提升为根
- create_node 写入 created_by_user_id;非 admin 父节点不可见报 ValueError("父节点不存在")
- update_node / delete_node / get_config / upsert_config / send_request / list_runs
  对越权节点统一抛 ApiConfigNotFoundError(404 语义)
- get_node_internal 不做归属校验,供调度器内部使用
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from app.shared.utils.api_config_service import (
    ApiConfigNotFoundError,
    ApiConfigService,
)
from app.shared.utils.auth.ownership_scope import OwnershipScope


# ==== FakeDb（最小化） =======================================================

class FakeDb:
    """测试用 FakeDb：仅支持本测试用到的 INSERT / UPDATE / DELETE / fetch。"""

    def __init__(self):
        self.nodes = {}
        self.configs = {}
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
                "created_at": datetime(2026, 7, 24, 10, 0, 0),
                "updated_at": datetime(2026, 7, 24, 10, 0, 0),
            }
            self.nodes[row["id"]] = row
            self.next_node_id += 1
            return row
        if "INSERT INTO api_configs" in query:
            row = {
                "id": self.next_config_id,
                "node_id": args[0],
                "method": "POST",
                "url": "",
                "params": "[]",
                "headers": "[]",
                "body_type": "none",
                "body_content": "",
                "form_fields": "[]",
                "expectations": "[]",
                "created_at": datetime(2026, 7, 24, 10, 0, 0),
                "updated_at": datetime(2026, 7, 24, 10, 0, 0),
            }
            self.configs[row["node_id"]] = row
            self.next_config_id += 1
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
            row["updated_at"] = datetime(2026, 7, 24, 11, 0, 0)
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
                "created_at": datetime(2026, 7, 24, 12, 0, 0),
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


def _make_service_with_db() -> tuple:
    """返回 (service, db) 便于直接构造特定节点结构。"""
    db = FakeDb()
    service = ApiConfigService(db=db)
    return service, db


def _seed_two_users_tree(service: ApiConfigService) -> Dict[str, int]:
    """构造 user_A 与 user_B 的混合节点树。

    返回 id 字典供断言使用::

        {
            "folder_admin": 1, "folder_user_a": 2, "folder_user_b": 3,
            "api_user_a_root": 4, "api_user_b_in_b": 5,
            "api_user_a_in_a": 6,
        }
    """
    admin_scope = OwnershipScope.for_user(1, is_admin=True)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)
    user_b_scope = OwnershipScope.for_user(99, is_admin=False)

    folder_admin = asyncio.run(
        service.create_node(None, "folder", "admin_folder", admin_scope)
    )
    folder_user_a = asyncio.run(
        service.create_node(None, "folder", "a_folder", user_a_scope)
    )
    folder_user_b = asyncio.run(
        service.create_node(None, "folder", "b_folder", user_b_scope)
    )
    api_user_a_root = asyncio.run(
        service.create_node(None, "api", "a_api_root", user_a_scope)
    )
    api_user_b_in_b = asyncio.run(
        service.create_node(folder_user_b["id"], "api", "b_api", user_b_scope)
    )
    api_user_a_in_a = asyncio.run(
        service.create_node(folder_user_a["id"], "api", "a_api", user_a_scope)
    )
    return {
        "folder_admin": folder_admin["id"],
        "folder_user_a": folder_user_a["id"],
        "folder_user_b": folder_user_b["id"],
        "api_user_a_root": api_user_a_root["id"],
        "api_user_b_in_b": api_user_b_in_b["id"],
        "api_user_a_in_a": api_user_a_in_a["id"],
    }


# ==== get_tree ==============================================================

def test_get_tree_admin_sees_all_nodes():
    """admin get_tree 返回全部节点。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    nodes = asyncio.run(service.get_tree(admin_scope))

    visible_ids = {n["id"] for n in nodes}
    assert visible_ids == set(ids.values())


def test_get_tree_user_sees_only_own_nodes():
    """普通用户 get_tree 仅返回自己创建的节点。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    nodes = asyncio.run(service.get_tree(user_a_scope))

    visible_ids = {n["id"] for n in nodes}
    assert visible_ids == {ids["folder_user_a"], ids["api_user_a_root"], ids["api_user_a_in_a"]}


def test_get_tree_promotes_orphans_to_root():
    """普通用户视角下:父节点不可见时,子节点 parent_id 重写为 None(提升为根)。

    模拟 admin 把 user_A 的节点移动到 admin_folder 下后,user_A 看不到
    admin_folder,但仍能看自己的节点(此时 parent_id 应为 None)。
    """
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    # admin 把 user_A 的根 api 移动到 admin_folder 下
    asyncio.run(
        service.update_node(
            ids["api_user_a_root"], admin_scope,
            parent_id=ids["folder_admin"],
        )
    )

    nodes = asyncio.run(service.get_tree(user_a_scope))
    by_id = {n["id"]: n for n in nodes}
    # api_user_a_root 应在 user_A 视图中以 root 出现（parent_id=None）
    assert by_id[ids["api_user_a_root"]]["parent_id"] is None
    # folder_user_a / api_user_a_in_a 仍正常保留父节点
    assert by_id[ids["api_user_a_in_a"]]["parent_id"] == ids["folder_user_a"]


def test_get_tree_system_scope_sees_all():
    """system scope 绕过隔离,用于脚本运行时。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    sys_scope = OwnershipScope.system_scope()

    nodes = asyncio.run(service.get_tree(sys_scope))

    assert {n["id"] for n in nodes} == set(ids.values())


# ==== create_node ===========================================================

def test_create_node_writes_created_by_user_id():
    """create_node 写入 scope.user_id 作为归属人。"""
    service, db = _make_service_with_db()
    user_scope = OwnershipScope.for_user(42, is_admin=False)

    node = asyncio.run(service.create_node(None, "folder", "我的分组", user_scope))

    assert db.nodes[node["id"]]["created_by_user_id"] == 42


def test_create_node_under_other_users_folder_raises_value_error():
    """非 admin 在他人 folder 下创建节点抛 ValueError(报"父节点不存在",不泄露)。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ValueError, match="父节点不存在"):
        asyncio.run(
            service.create_node(ids["folder_user_b"], "api", "越权", user_a_scope)
        )


def test_create_node_user_id_none_raises_value_error():
    """scope.user_id 缺失时抛 ValueError,无法写入归属人。"""
    service, _ = _make_service_with_db()
    anonymous_scope = OwnershipScope.for_user(0, is_admin=False)  # None 模拟

    # 用 None user_id 构造;scope.sql_filter 把 None 视作非 admin 但 user_id 缺失
    # 直接构造 dataclass(user_id=None)
    bad_scope = OwnershipScope(user_id=None, is_admin=False)
    with pytest.raises(ValueError):
        asyncio.run(service.create_node(None, "folder", "x", bad_scope))


# ==== update_node / delete_node ==============================================

def test_update_node_other_user_raises_not_found():
    """非 admin 更新他人节点抛 ApiConfigNotFoundError(404 语义,不泄露)。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(
            service.update_node(ids["api_user_b_in_b"], user_a_scope, name="x")
        )


def test_update_node_move_under_other_user_folder_raises_value_error():
    """非 admin 把节点移到他人 folder 抛 ValueError(报"父节点不存在")。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ValueError, match="父节点不存在"):
        asyncio.run(
            service.update_node(
                ids["api_user_a_root"], user_a_scope,
                parent_id=ids["folder_user_b"],
            )
        )


def test_delete_node_other_user_raises_not_found():
    """非 admin 删除他人节点抛 ApiConfigNotFoundError。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.delete_node(ids["folder_user_b"], user_a_scope))


def test_delete_node_non_empty_counts_all_children_including_hidden():
    """非 admin 删除 folder 时统计全部子节点(含他人隐藏子节点),防误删。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    admin_scope = OwnershipScope.for_user(1, is_admin=True)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    # admin 把 user_B 的节点移动到 user_A 的 folder 下
    asyncio.run(
        service.update_node(
            ids["api_user_b_in_b"], admin_scope,
            parent_id=ids["folder_user_a"],
        )
    )

    # user_A 看 folder_user_a 没有子节点(因为 user_B 的节点被隔离);
    # 但删除时仍因"非空"被拒,防止误删隐藏内容
    with pytest.raises(ValueError, match="文件夹非空"):
        asyncio.run(service.delete_node(ids["folder_user_a"], user_a_scope))


# ==== get_config / upsert_config / send_request / list_runs ===================

def test_get_config_other_user_raises_not_found():
    """非 admin 读他人 api 节点配置抛 ApiConfigNotFoundError。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.get_config(ids["api_user_b_in_b"], user_a_scope))


def test_upsert_config_other_user_raises_not_found():
    """非 admin upsert 他人 api 节点配置抛 ApiConfigNotFoundError。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(
            service.upsert_config(
                ids["api_user_b_in_b"], user_a_scope,
                method="POST", url="x",
                params=[], headers=[], body_type="none",
                body_content="", form_fields=[], expectations=[],
            )
        )


def test_send_request_other_user_raises_not_found():
    """非 admin 调用他人接口 send_request 抛 ApiConfigNotFoundError。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.send_request(ids["api_user_b_in_b"], user_a_scope))


def test_list_runs_other_user_raises_not_found():
    """非 admin 查他人调用历史抛 ApiConfigNotFoundError。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)
    user_a_scope = OwnershipScope.for_user(42, is_admin=False)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.list_runs(ids["api_user_b_in_b"], user_a_scope))


def test_get_config_missing_node_raises_not_found():
    """缺失节点(无论是否 admin)统一抛 ApiConfigNotFoundError,与越权不可区分。"""
    service, _ = _make_service_with_db()
    admin_scope = OwnershipScope.for_user(1, is_admin=True)

    with pytest.raises(ApiConfigNotFoundError):
        asyncio.run(service.get_config(9999, admin_scope))


# ==== get_node_internal =====================================================

def test_get_node_internal_returns_node_without_scope_check():
    """get_node_internal 不做归属校验,直接返回缓存节点(系统内部使用)。"""
    service, _ = _make_service_with_db()
    ids = _seed_two_users_tree(service)

    # 不论归属,都能查到
    node = service.get_node_internal(ids["api_user_b_in_b"])
    assert node is not None
    assert node["id"] == ids["api_user_b_in_b"]

    # 不存在的 id 返回 None
    assert service.get_node_internal(9999) is None


def test_get_node_internal_works_when_db_none():
    """db=None 时 get_node_internal 返回空缓存结果而不抛错。"""
    service = ApiConfigService(db=None)

    assert service.get_node_internal(1) is None