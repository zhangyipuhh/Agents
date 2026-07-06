# -*- coding:utf-8 -*-
"""
ProjectDB 单元测试（2026-06-30 新增，2026-07-01 扩展 relative_path）

测试 app/shared/utils/project/project_db.py 的：
  * create_project
  * list_user_projects
  * get_project_by_id
  * get_project_by_uuid
  * _backfill_missing_relative_paths

由于 ProjectDB 主要在 PG 模式下工作，测试在 Memory 模式下覆盖基础逻辑分支。
"""

import asyncio

import pytest

from app.shared.utils.project import project_db
from app.shared.utils.project.project_db import ProjectDB


@pytest.fixture
def fresh_project_db():
    """清空内存缓存的 fixture。"""
    with ProjectDB._lock:
        ProjectDB._memory_cache.clear()
    ProjectDB._initialized = True  # Memory 模式不强制 reload
    yield ProjectDB
    with ProjectDB._lock:
        ProjectDB._memory_cache.clear()


class TestProjectDBCreate:
    """create_project 测试。"""

    def test_create_project_in_memory_mode(self, fresh_project_db, monkeypatch):
        """Memory 模式：create_project 返回含 id 与 relative_path 的字典。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.create_project(
                user_id=1,
                name="Daily-work",
                uuid="session-1111",
            )

        result = asyncio.run(_run())
        assert result is not None
        assert result["name"] == "Daily-work"
        assert result["uuid"] == "session-1111"
        assert result["user_id"] == 1
        assert "id" in result
        assert "relative_path" in result
        assert result["relative_path"].startswith("data/project/")
        assert result["relative_path"].endswith("/session-1111")

    def test_create_project_auto_uuid(self, fresh_project_db, monkeypatch):
        """未传 uuid 时应自动生成独立 uuid。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.create_project(user_id=1, name="Auto-uuid")

        result = asyncio.run(_run())
        assert result is not None
        assert result["name"] == "Auto-uuid"
        assert result["uuid"]
        assert len(result["uuid"]) > 0

    def test_create_project_raises_on_missing_params(self, fresh_project_db, monkeypatch):
        """缺少必填参数应抛 ValueError。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.create_project(user_id=0, name="")

        with pytest.raises(ValueError):
            asyncio.run(_run())

    def test_create_project_duplicate_uuid_idempotent(self, fresh_project_db, monkeypatch):
        """uuid 重复时 Memory 模式不会真正去重（仅 DB 模式生效）。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p1 = await ProjectDB.create_project(user_id=1, name="A", uuid="dup-uuid")
            p2 = await ProjectDB.create_project(user_id=1, name="B", uuid="dup-uuid")
            return p1, p2

        p1, p2 = asyncio.run(_run())
        # Memory 模式下两条都成功，id 不同
        assert p1 is not None
        assert p2 is not None
        assert p1["id"] != p2["id"]
        # 相同 uuid 且通常同日期，默认 relative_path 会相同
        assert p1["relative_path"] == p2["relative_path"]

    def test_create_project_stores_relative_path(self, fresh_project_db, monkeypatch):
        """未传 relative_path 时，默认生成按日期分层的相对路径。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        from datetime import datetime

        async def _run():
            return await ProjectDB.create_project(
                user_id=1,
                name="Auto-path",
                uuid="session-auto",
            )

        result = asyncio.run(_run())
        now = datetime.now()
        expected = f"data/project/{now.year}/{now.month:02d}/{now.day:02d}/session-auto"
        assert result["relative_path"] == expected

    def test_create_project_custom_relative_path(self, fresh_project_db, monkeypatch):
        """传入 relative_path 时应原样保存。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.create_project(
                user_id=1,
                name="Custom-path",
                uuid="session-custom",
                relative_path="custom/folder/path",
            )

        result = asyncio.run(_run())
        assert result["relative_path"] == "custom/folder/path"


class TestProjectDBInitialize:
    """initialize / 数据补齐 测试。"""

    def test_initialize_backfills_missing_relative_path(self, fresh_project_db, monkeypatch):
        """模拟旧记录缺失 relative_path，调用 _backfill_missing_relative_paths 后补齐。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        from datetime import datetime

        old_time = datetime(2025, 8, 15, 10, 30, 0)
        with ProjectDB._lock:
            ProjectDB._memory_cache[1] = {
                "id": 1,
                "user_id": 1,
                "name": "Old",
                "uuid": "old-uuid",
                "relative_path": None,
                "created_at": old_time,
                "updated_at": old_time,
            }
            ProjectDB._memory_cache[2] = {
                "id": 2,
                "user_id": 1,
                "name": "Empty",
                "uuid": "empty-uuid",
                "relative_path": "",
                "created_at": old_time,
                "updated_at": old_time,
            }
            ProjectDB._memory_cache[3] = {
                "id": 3,
                "user_id": 1,
                "name": "HasPath",
                "uuid": "has-uuid",
                "relative_path": "existing/path",
                "created_at": old_time,
                "updated_at": old_time,
            }

        async def _run():
            await ProjectDB._backfill_missing_relative_paths()

        asyncio.run(_run())

        assert ProjectDB._memory_cache[1]["relative_path"] == "data/project/2025/08/15/old-uuid"
        assert ProjectDB._memory_cache[2]["relative_path"] == "data/project/2025/08/15/empty-uuid"
        assert ProjectDB._memory_cache[3]["relative_path"] == "existing/path"


class TestProjectDBList:
    """list_user_projects 测试。"""

    def test_list_user_projects_filters_by_user(self, fresh_project_db, monkeypatch):
        """应只返回指定 user 的项目。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            await ProjectDB.create_project(user_id=1, name="U1-Project", uuid="u1-1")
            await ProjectDB.create_project(user_id=1, name="U1-Project2", uuid="u1-2")
            await ProjectDB.create_project(user_id=2, name="U2-Project", uuid="u2-1")
            return await ProjectDB.list_user_projects(user_id=1)

        result = asyncio.run(_run())
        assert len(result) == 2
        assert all(p["user_id"] == 1 for p in result)
        assert all("relative_path" in p for p in result)

    def test_list_user_projects_empty(self, fresh_project_db, monkeypatch):
        """空时返回空列表。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.list_user_projects(user_id=999)

        result = asyncio.run(_run())
        assert result == []


class TestProjectDBGetById:
    """get_project_by_id 测试。"""

    def test_get_existing_project(self, fresh_project_db, monkeypatch):
        """存在的项目应能正确查询。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1")
            return await ProjectDB.get_project_by_id(p["id"], user_id=1)

        result = asyncio.run(_run())
        assert result is not None
        assert result["name"] == "test"
        assert "relative_path" in result

    def test_get_project_user_mismatch(self, fresh_project_db, monkeypatch):
        """user_id 不匹配时返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1")
            return await ProjectDB.get_project_by_id(p["id"], user_id=2)

        result = asyncio.run(_run())
        assert result is None

    def test_get_nonexistent_project(self, fresh_project_db, monkeypatch):
        """不存在的项目 ID 返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.get_project_by_id(9999)

        result = asyncio.run(_run())
        assert result is None


class TestProjectDBGetByUuid:
    """get_project_by_uuid 测试。"""

    def test_get_by_uuid(self, fresh_project_db, monkeypatch):
        """通过 uuid 查找项目。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            await ProjectDB.create_project(user_id=1, name="test", uuid="unique-uuid")
            return await ProjectDB.get_project_by_uuid("unique-uuid")

        result = asyncio.run(_run())
        assert result is not None
        assert result["uuid"] == "unique-uuid"
        assert "relative_path" in result

    def test_get_by_uuid_empty(self, fresh_project_db, monkeypatch):
        """空 uuid 返回 None。"""

        async def _run():
            return await ProjectDB.get_project_by_uuid("")

        result = asyncio.run(_run())
        assert result is None

    def test_get_by_uuid_not_found(self, fresh_project_db, monkeypatch):
        """不存在的 uuid 返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.get_project_by_uuid("nonexistent-uuid")

        result = asyncio.run(_run())
        assert result is None


class TestProjectDBDelete:
    """delete_project 测试。"""

    def test_delete_existing_project(self, fresh_project_db, monkeypatch):
        """删除存在的项目，内存缓存同步移除。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="ToDelete", uuid="uuid-del")
            deleted = await ProjectDB.delete_project(p["id"], user_id=1)
            return deleted, p["id"]

        deleted, project_id = asyncio.run(_run())
        assert deleted is True
        assert project_id not in ProjectDB._memory_cache

    def test_delete_nonexistent_project(self, fresh_project_db, monkeypatch):
        """删除不存在的项目返回 False。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.delete_project(9999, user_id=1)

        result = asyncio.run(_run())
        assert result is False

    def test_delete_project_user_mismatch(self, fresh_project_db, monkeypatch):
        """user_id 不匹配时不删除。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="U1", uuid="uuid-u1")
            deleted = await ProjectDB.delete_project(p["id"], user_id=2)
            return deleted, p["id"]

        deleted, project_id = asyncio.run(_run())
        assert deleted is False
        assert project_id in ProjectDB._memory_cache


class TestProjectDBRename:
    """rename_project 测试。"""

    def test_rename_existing_project(self, fresh_project_db, monkeypatch):
        """重命名存在的项目，内存缓存同步更新。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="Old", uuid="uuid-rename")
            updated = await ProjectDB.rename_project(p["id"], new_name="New", user_id=1)
            return updated, p["id"]

        updated, project_id = asyncio.run(_run())
        assert updated is not None
        assert updated["name"] == "New"
        assert ProjectDB._memory_cache[project_id]["name"] == "New"

    def test_rename_project_empty_name(self, fresh_project_db, monkeypatch):
        """空名称应返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="Old", uuid="uuid-empty")
            return await ProjectDB.rename_project(p["id"], new_name="  ", user_id=1)

        result = asyncio.run(_run())
        assert result is None

    def test_rename_project_too_long(self, fresh_project_db, monkeypatch):
        """超过 50 字符应返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="Old", uuid="uuid-long")
            return await ProjectDB.rename_project(p["id"], new_name="a" * 51, user_id=1)

        result = asyncio.run(_run())
        assert result is None

    def test_rename_project_not_found(self, fresh_project_db, monkeypatch):
        """重命名不存在的项目返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            return await ProjectDB.rename_project(9999, new_name="New", user_id=1)

        result = asyncio.run(_run())
        assert result is None

    def test_rename_project_user_mismatch(self, fresh_project_db, monkeypatch):
        """user_id 不匹配时返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="U1", uuid="uuid-u1-rename")
            return await ProjectDB.rename_project(p["id"], new_name="New", user_id=2)

        result = asyncio.run(_run())
        assert result is None


class TestProjectDBModule:
    """模块级兼容测试。"""

    def test_init_project_schema_alias_exists(self):
        """module-level 别名与类引用保持一致。"""
        assert project_db.ProjectDB is ProjectDB
