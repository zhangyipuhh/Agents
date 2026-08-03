# -*- coding:utf-8 -*-
"""
UserServerService 测试模块（2026-07-24 新增）。

覆盖：
- list_nodes 按 scope 过滤；父节点不可见时提升为根
- create_node 写入 created_by_user_id；server 必须 source_devops_server_id；
  folder 必须 None；父节点必须可见且为 folder 类型
- update_node / delete_node 越权抛 UserServerNodeNotFoundError
- delete_node 非空 folder 抛 UserServerNodeNotEmptyError
- get_node_config folder → 元数据；server → JOIN devops_servers 详情
- import_from_devops_servers 按 business_name 匹配，dedupe，fold 校验
"""
import asyncio
from datetime import datetime
from typing import Any, Dict, List, Optional

import pytest

from app.shared.utils.auth.ownership_scope import OwnershipScope
from app.shared.utils.user_server_service import (
    NODE_TYPES,
    UserServerNodeNotEmptyError,
    UserServerNodeNotFoundError,
    UserServerService,
)


# ==== FakeDb（最小化） =======================================================


class FakeDb:
    """测试用 FakeDb：仅支持本测试用到的 INSERT / UPDATE / DELETE / fetch。"""

    def __init__(self):
        self.nodes: Dict[int, Dict[str, Any]] = {}
        self.next_node_id = 1

    async def fetch(self, query: str, *args: Any) -> List[Dict[str, Any]]:
        if "FROM user_server_nodes" in query:
            return list(self.nodes.values())
        return []

    async def fetchrow(self, query: str, *args: Any) -> Optional[Dict[str, Any]]:
        if "INSERT INTO user_server_nodes" in query:
            parent_id, node_type, name, sort_order, source_id, created_by = args
            row = {
                "id": self.next_node_id,
                "parent_id": parent_id,
                "node_type": node_type,
                "name": name,
                "sort_order": sort_order,
                "source_devops_server_id": source_id,
                "created_by_user_id": created_by,
                "created_at": datetime(2026, 7, 24, 10, 0, 0),
                "updated_at": datetime(2026, 7, 24, 10, 0, 0),
            }
            self.nodes[row["id"]] = row
            self.next_node_id += 1
            return row
        if "UPDATE user_server_nodes" in query:
            node_id, name, parent_id, sort_order = args
            row = self.nodes.get(node_id)
            if row is None:
                return None
            if name is not None:
                row["name"] = name
            if parent_id is not None:
                row["parent_id"] = parent_id
            if sort_order is not None:
                row["sort_order"] = sort_order
            row["updated_at"] = datetime(2026, 7, 24, 11, 0, 0)
            return row
        return None

    async def execute(self, query: str, *args: Any) -> str:
        if "DELETE FROM user_server_nodes" in query:
            node_id = args[0]
            self.nodes.pop(node_id, None)
            return "DELETE 1"
        return ""


class FakeDevopsService:
    """最小化的 DevOpsServerService stub。"""

    def __init__(self, public_servers=None, server_exists_map=None, detail_map=None):
        self._public = public_servers or []
        self._exists = server_exists_map or {}
        self._details = detail_map or {}

    def list_public_servers(self) -> List[Dict[str, Any]]:
        return self._public

    async def server_exists(self, server_id: int) -> bool:
        return self._exists.get(server_id, False)

    def get_server_detail(self, server_id: int) -> Optional[Dict[str, Any]]:
        return self._details.get(server_id)


# ==== Fixtures ===============================================================


def _make_service(db=None, devops=None) -> UserServerService:
    return UserServerService(db=db, devops_server_service=devops)


def _admin_scope() -> OwnershipScope:
    return OwnershipScope.for_user(user_id=1, is_admin=True)


def _user_scope(uid: int) -> OwnershipScope:
    return OwnershipScope.for_user(user_id=uid, is_admin=False)


# ==== P0: 导入 / 节点类型 ====================================================


def test_user_server_service_importable():
    """UserServerService 可导入。"""
    assert UserServerService is not None


def test_node_types_constant():
    """NODE_TYPES = ('folder', 'server')。"""
    assert NODE_TYPES == ("folder", "server")


# ==== P1: list_nodes ========================================================


def test_list_nodes_admin_returns_all():
    """admin 透传全量节点。"""
    db = FakeDb()
    service = _make_service(db=db)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "folder", "name": "A",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": None},
        2: {"id": 2, "parent_id": 1, "node_type": "server", "name": "B",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": 100},
        3: {"id": 3, "parent_id": None, "node_type": "folder", "name": "C",
            "created_by_user_id": 2, "sort_order": 0, "source_devops_server_id": None},
    }
    nodes = service.list_nodes(_admin_scope())
    assert len(nodes) == 3


def test_list_nodes_user_filter_only_own():
    """普通用户仅看自己 created_by_user_id 的节点。"""
    db = FakeDb()
    service = _make_service(db=db)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "folder", "name": "A",
            "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None},
        2: {"id": 2, "parent_id": None, "node_type": "folder", "name": "B",
            "created_by_user_id": 20, "sort_order": 0, "source_devops_server_id": None},
    }
    nodes = service.list_nodes(_user_scope(uid=10))
    assert len(nodes) == 1
    assert nodes[0]["created_by_user_id"] == 10


def test_list_nodes_invisible_parent_promotes_to_root():
    """父节点对当前用户不可见时，节点 parent_id 重写为 None。"""
    db = FakeDb()
    service = _make_service(db=db)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "folder", "name": "A_他人",
            "created_by_user_id": 20, "sort_order": 0, "source_devops_server_id": None},
        2: {"id": 2, "parent_id": 1, "node_type": "server", "name": "B_自己",
            "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 100},
    }
    nodes = service.list_nodes(_user_scope(uid=10))
    # 仅 B 可见；B 的 parent_id=1 不在可见集合中 → 提升为根
    assert len(nodes) == 1
    assert nodes[0]["id"] == 2
    assert nodes[0]["parent_id"] is None


def test_list_nodes_server_attach_business_and_type_admin():
    """2026-07-26：admin list_nodes 对 server 节点附带 business_name / server_type。

    字段来自 devops_server_service.list_public_servers() 内存 join。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[
        {"id": 100, "business_name": "服务器A", "server_type": "linux", "updated_at": "2026-07-26"},
        {"id": 101, "business_name": "服务器B", "server_type": "windows", "updated_at": "2026-07-26"},
    ])
    service = _make_service(db=db, devops=devops)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "folder", "name": "分组",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": None},
        2: {"id": 2, "parent_id": 1, "node_type": "server", "name": "本地别名",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": 100},
        3: {"id": 3, "parent_id": None, "node_type": "server", "name": "服务器B",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": 101},
    }
    nodes = service.list_nodes(_admin_scope())
    # 找到 server 节点
    s2 = next(n for n in nodes if n["id"] == 2)
    s3 = next(n for n in nodes if n["id"] == 3)
    folder = next(n for n in nodes if n["id"] == 1)
    # server 节点附带 canonical 字段（来源 devops_servers，与节点 name 无关）
    assert s2["business_name"] == "服务器A"
    assert s2["server_type"] == "linux"
    assert s3["business_name"] == "服务器B"
    assert s3["server_type"] == "windows"
    # folder 节点不附带
    assert "business_name" not in folder
    assert "server_type" not in folder


def test_list_nodes_server_attach_user_scope():
    """2026-07-26：普通用户 list_nodes 同样对 server 节点附带 canonical 字段。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[
        {"id": 100, "business_name": "服务器A", "server_type": "linux", "updated_at": "2026-07-26"},
    ])
    service = _make_service(db=db, devops=devops)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "server", "name": "本地别名",
            "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 100},
        2: {"id": 2, "parent_id": None, "node_type": "server", "name": "他人服务器",
            "created_by_user_id": 20, "sort_order": 0, "source_devops_server_id": 101},
    }
    nodes = service.list_nodes(_user_scope(uid=10))
    # 仅自己节点 1 可见
    assert len(nodes) == 1
    assert nodes[0]["id"] == 1
    assert nodes[0]["business_name"] == "服务器A"
    assert nodes[0]["server_type"] == "linux"


def test_list_nodes_server_devops_deleted_leaves_fields_absent():
    """2026-07-26：server 节点引用的 devops_servers 不存在时，附加字段保持缺失。

    外键 CASCADE 通常会先删除引用节点，但保留防御：缺源时跳过附加，
    节点 dict 不含 business_name / server_type。前端 maskServers
    按"无 business_name 一律剔除"的口径过滤掉。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[])  # 空，源行已被删
    service = _make_service(db=db, devops=devops)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "server", "name": "幽灵",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": 999},
    }
    nodes = service.list_nodes(_admin_scope())
    assert len(nodes) == 1
    # 字段缺失（不是 None）—— 与未注入 devops_server_service 的行为一致
    assert "business_name" not in nodes[0]
    assert "server_type" not in nodes[0]


def test_list_nodes_server_no_devops_service_leaves_fields_absent():
    """2026-07-26：devops_server_service 未注入时 server 节点不附加字段。

    devops_index 为空 → 跳过附加，保持列表节点原状（无 business_name / server_type）。"""
    db = FakeDb()
    service = _make_service(db=db, devops=None)
    service._nodes = {
        1: {"id": 1, "parent_id": None, "node_type": "server", "name": "服务器A",
            "created_by_user_id": 1, "sort_order": 0, "source_devops_server_id": 100},
    }
    nodes = service.list_nodes(_admin_scope())
    assert len(nodes) == 1
    assert "business_name" not in nodes[0]
    assert "server_type" not in nodes[0]


# ==== P1: create_node ======================================================


def test_create_folder_node_ok():
    """创建 folder 节点成功。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    node = asyncio.run(
        service.create_node(parent_id=None, node_type="folder", name="我的文件夹", scope=scope)
    )
    assert node["node_type"] == "folder"
    assert node["name"] == "我的文件夹"
    assert node["created_by_user_id"] == 10
    assert node["source_devops_server_id"] is None
    assert 1 in service._nodes


def test_create_server_node_requires_source():
    """server 节点必须传 source_devops_server_id。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="必须指定 source_devops_server_id"):
        asyncio.run(
            service.create_node(parent_id=None, node_type="server", name="S", scope=scope)
        )


def test_create_folder_node_rejects_source():
    """folder 节点不能传 source_devops_server_id。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="不能引用 devops_servers"):
        asyncio.run(
            service.create_node(
                parent_id=None, node_type="folder", name="F", scope=scope,
                source_devops_server_id=999
            )
        )


def test_create_node_invalid_type():
    """非法 node_type → ValueError。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="node_type 必须是"):
        asyncio.run(
            service.create_node(parent_id=None, node_type="invalid", name="X", scope=scope)
        )


def test_create_node_empty_name():
    """空 name → ValueError。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="节点名称不能为空"):
        asyncio.run(
            service.create_node(parent_id=None, node_type="folder", name="", scope=scope)
        )


def test_create_node_invisible_parent_raises():
    """父节点不可见时 → ValueError('父节点不存在')。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    # 父节点 100 由他人创建
    service._nodes[100] = {
        "id": 100, "parent_id": None, "node_type": "folder", "name": "他人",
        "created_by_user_id": 20, "sort_order": 0, "source_devops_server_id": None,
    }
    with pytest.raises(ValueError, match="父节点不存在"):
        asyncio.run(
            service.create_node(parent_id=100, node_type="folder", name="F", scope=scope)
        )


def test_create_node_parent_must_be_folder():
    """父节点不是 folder → ValueError。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    service._nodes[100] = {
        "id": 100, "parent_id": None, "node_type": "server", "name": "Server",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 50,
    }
    with pytest.raises(ValueError, match="父节点必须是 folder 类型"):
        asyncio.run(
            service.create_node(parent_id=100, node_type="folder", name="F", scope=scope)
        )


def test_create_server_node_validates_devops_exists():
    """server 节点创建时校验 devops_servers 行存在。"""
    db = FakeDb()
    devops = FakeDevopsService(server_exists_map={100: True})
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    node = asyncio.run(
        service.create_node(
            parent_id=None, node_type="server", name="S", scope=scope,
            source_devops_server_id=100
        )
    )
    assert node["node_type"] == "server"
    assert node["source_devops_server_id"] == 100


def test_create_server_node_devops_not_exists_raises():
    """server 节点引用的 devops_servers 不存在 → ValueError。"""
    db = FakeDb()
    devops = FakeDevopsService(server_exists_map={100: False})
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="devops_servers 行不存在"):
        asyncio.run(
            service.create_node(
                parent_id=None, node_type="server", name="S", scope=scope,
                source_devops_server_id=100
            )
        )


# ==== P1: update_node ======================================================


def test_update_node_ok():
    """更新节点名称。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    db.nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "folder", "name": "旧名",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
    }
    service._nodes[1] = dict(db.nodes[1])
    node = asyncio.run(service.update_node(1, scope, name="新名"))
    assert node["name"] == "新名"


def test_update_node_other_user_raises():
    """越权更新 → UserServerNodeNotFoundError。"""
    db = FakeDb()
    service = _make_service(db=db)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "folder", "name": "X",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
    }
    with pytest.raises(UserServerNodeNotFoundError):
        asyncio.run(service.update_node(1, _user_scope(uid=20), name="X"))


# ==== P1: delete_node ======================================================


def test_delete_node_ok():
    """删除空 folder 节点。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "folder", "name": "X",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
    }
    asyncio.run(service.delete_node(1, scope))
    assert 1 not in service._nodes


def test_delete_node_not_empty_raises():
    """非空 folder → UserServerNodeNotEmptyError。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "folder", "name": "X",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
    }
    service._nodes[2] = {
        "id": 2, "parent_id": 1, "node_type": "folder", "name": "Y",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
    }
    with pytest.raises(UserServerNodeNotEmptyError, match="文件夹非空"):
        asyncio.run(service.delete_node(1, scope))


# ==== P1: get_node_config ==================================================


def test_get_node_config_folder():
    """folder 节点详情 = 元数据。"""
    db = FakeDb()
    service = _make_service(db=db)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "folder", "name": "F",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": None,
        "created_at": "2026-07-24T10:00:00Z", "updated_at": "2026-07-24T10:00:00Z",
    }
    detail = asyncio.run(service.get_node_config(1, scope))
    assert detail["node_type"] == "folder"
    assert detail["name"] == "F"


def test_get_node_config_server_joins_devops():
    """server 节点详情 = JOIN devops_servers 取白名单字段（2026-08-03 改造）。

    详情不再返回 inspection_script / inspection_parser / inspection_fields 三列原文，
    改为返回 inspection_script_id / inspection_script_name /
    inspection_script_display_name（service 层通过 InspectionScriptService 解析）。
    """
    db = FakeDb()
    devops = FakeDevopsService(detail_map={
        100: {
            "id": 100, "business_name": "服务器A", "server_type": "linux",
            "updated_at": "2026-08-03T11:00:00Z",
            "whitelist": ["ls", "pwd"],
            "inspection_script_id": 11,
            "inspection_script_name": "linux-bash",
            "inspection_script_display_name": "Linux Bash 巡检",
        }
    })
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "server", "name": "服务器A",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 100,
    }
    detail = asyncio.run(service.get_node_config(1, scope))
    assert detail["node_type"] == "server"
    assert detail["business_name"] == "服务器A"
    assert detail["server_type"] == "linux"
    assert detail["whitelist"] == ["ls", "pwd"]
    assert detail["inspection_script_id"] == 11
    assert detail["inspection_script_name"] == "linux-bash"
    assert detail["inspection_script_display_name"] == "Linux Bash 巡检"
    # 关键：脚本原文 / 解析器 / 字段规则不在详情中（改走 inspection_script_admin_router）
    for forbidden in (
        "inspection_script", "inspection_parser", "inspection_fields",
        "ip", "port", "username", "password", "password_encrypted",
    ):
        assert forbidden not in detail


def test_get_node_config_server_devops_deleted_raises():
    """server 节点引用的 devops_servers 已被删除 → ValueError。"""
    db = FakeDb()
    devops = FakeDevopsService(detail_map={})  # 空，视为已删除
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "server", "name": "S",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 100,
    }
    with pytest.raises(ValueError, match="已被删除"):
        asyncio.run(service.get_node_config(1, scope))


# ==== P1: import_from_devops_servers ========================================


def test_import_basic_success():
    """基本导入：parent=None, business_names=['A', 'B']。"""
    db = FakeDb()
    devops = FakeDevopsService(
        public_servers=[
            {"id": 100, "business_name": "A", "server_type": "linux", "updated_at": "2026-07-24"},
            {"id": 101, "business_name": "B", "server_type": "linux", "updated_at": "2026-07-24"},
        ],
        server_exists_map={100: True, 101: True},
    )
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    result = asyncio.run(
        service.import_from_devops_servers(parent_id=None, business_names=["A", "B"], scope=scope)
    )
    assert result["imported"] == 2
    assert result["skipped"] == 0
    assert result["failed"] == 0
    assert len(result["node_ids"]) == 2


def test_import_unknown_business_name_counts_as_failed():
    """business_name 在 devops_servers 中找不到 → failed。"""
    db = FakeDb()
    devops = FakeDevopsService(
        public_servers=[
            {"id": 100, "business_name": "A", "server_type": "linux", "updated_at": "2026-07-24"},
        ],
        server_exists_map={100: True},
    )
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    result = asyncio.run(
        service.import_from_devops_servers(
            parent_id=None, business_names=["A", "不存在的"], scope=scope
        )
    )
    assert result["imported"] == 1
    assert result["failed"] == 1


def test_import_dedup_same_user_same_parent_skipped():
    """同一用户对同一 devops_server 在同 parent_id 下重复导入 → skipped。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[
        {"id": 100, "business_name": "A", "server_type": "linux", "updated_at": "2026-07-24"},
    ])
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    # 预置：用户 10 已在 parent=None 下导入了 A
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "server", "name": "A",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 100,
    }
    result = asyncio.run(
        service.import_from_devops_servers(parent_id=None, business_names=["A"], scope=scope)
    )
    assert result["imported"] == 0
    assert result["skipped"] == 1


def test_import_no_devops_service_raises():
    """未注入 DevOpsServerService → RuntimeError。"""
    db = FakeDb()
    service = _make_service(db=db, devops=None)
    scope = _user_scope(uid=10)
    with pytest.raises(RuntimeError, match="DevOpsServerService 未注入"):
        asyncio.run(
            service.import_from_devops_servers(
                parent_id=None, business_names=["A"], scope=scope
            )
        )


def test_import_empty_business_names_raises():
    """空 business_names 列表 → ValueError。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[])
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    with pytest.raises(ValueError, match="business_names 不能为空"):
        asyncio.run(
            service.import_from_devops_servers(parent_id=None, business_names=[], scope=scope)
        )


def test_import_parent_must_be_folder():
    """parent 节点不是 folder → ValueError。"""
    db = FakeDb()
    devops = FakeDevopsService(public_servers=[
        {"id": 100, "business_name": "A", "server_type": "linux", "updated_at": "2026-07-24"},
    ])
    service = _make_service(db=db, devops=devops)
    scope = _user_scope(uid=10)
    service._nodes[1] = {
        "id": 1, "parent_id": None, "node_type": "server", "name": "Other",
        "created_by_user_id": 10, "sort_order": 0, "source_devops_server_id": 200,
    }
    with pytest.raises(ValueError, match="父节点必须是 folder"):
        asyncio.run(
            service.import_from_devops_servers(parent_id=1, business_names=["A"], scope=scope)
        )


# ==== P0: db=None 降级 ====================================================


def test_db_none_preload_is_noop():
    """db=None 时 preload_all no-op。"""
    service = UserServerService(db=None, devops_server_service=None)
    asyncio.run(service.preload_all())
    # 不抛异常即可


def test_db_none_read_returns_empty_list():
    """db=None 时 list_nodes 返空（不读内存——内存也是空）。"""
    service = UserServerService(db=None, devops_server_service=None)
    nodes = service.list_nodes(_admin_scope())
    assert nodes == []


def test_db_none_write_raises():
    """db=None 时 create_node 抛 RuntimeError('数据库未启用')。"""
    service = UserServerService(db=None, devops_server_service=None)
    with pytest.raises(RuntimeError, match="数据库未启用"):
        asyncio.run(
            service.create_node(
                parent_id=None, node_type="folder", name="F", scope=_user_scope(uid=10)
            )
        )
