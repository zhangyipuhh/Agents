# -*- coding:utf-8 -*-
"""
ProjectDB 单元测试（2026-06-30 新增）

测试 app/shared/utils/project/project_db.py 的：
  * create_project
  * list_user_projects
  * get_project_by_id
  * get_project_by_uuid

由于 ProjectDB 主要在 PG 模式下工作，测试在 Memory 模式下覆盖基础逻辑分支。
"""

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
        """Memory 模式：create_project 返回含 id 的字典。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        project = ProjectDB.run = None  # placeholder
        # 直接调内部方法
        import asyncio

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

    def test_create_project_raises_on_missing_params(self, fresh_project_db, monkeypatch):
        """缺少必填参数应抛 ValueError。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            return await ProjectDB.create_project(user_id=0, name="", uuid="x")

        with pytest.raises(ValueError):
            asyncio.run(_run())

    def test_create_project_duplicate_uuid_idempotent(self, fresh_project_db, monkeypatch):
        """uuid 重复时 Memory 模式不会真正去重（仅 DB 模式生效）。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            p1 = await ProjectDB.create_project(user_id=1, name="A", uuid="dup-uuid")
            p2 = await ProjectDB.create_project(user_id=1, name="B", uuid="dup-uuid")
            return p1, p2

        p1, p2 = asyncio.run(_run())
        # Memory 模式下两条都成功，id 不同
        assert p1 is not None
        assert p2 is not None
        assert p1["id"] != p2["id"]


class TestProjectDBList:
    """list_user_projects 测试。"""

    def test_list_user_projects_filters_by_user(self, fresh_project_db, monkeypatch):
        """应只返回指定 user 的项目。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            await ProjectDB.create_project(user_id=1, name="U1-Project", uuid="u1-1")
            await ProjectDB.create_project(user_id=1, name="U1-Project2", uuid="u1-2")
            await ProjectDB.create_project(user_id=2, name="U2-Project", uuid="u2-1")
            return await ProjectDB.list_user_projects(user_id=1)

        result = asyncio.run(_run())
        assert len(result) == 2
        assert all(p["user_id"] == 1 for p in result)

    def test_list_user_projects_empty(self, fresh_project_db, monkeypatch):
        """空时返回空列表。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            return await ProjectDB.list_user_projects(user_id=999)

        result = asyncio.run(_run())
        assert result == []


class TestProjectDBGetById:
    """get_project_by_id 测试。"""

    def test_get_existing_project(self, fresh_project_db, monkeypatch):
        """存在的项目应能正确查询。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1")
            return await ProjectDB.get_project_by_id(p["id"], user_id=1)

        result = asyncio.run(_run())
        assert result is not None
        assert result["name"] == "test"

    def test_get_project_user_mismatch(self, fresh_project_db, monkeypatch):
        """user_id 不匹配时返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            p = await ProjectDB.create_project(user_id=1, name="test", uuid="uuid-1")
            return await ProjectDB.get_project_by_id(p["id"], user_id=2)

        result = asyncio.run(_run())
        assert result is None

    def test_get_nonexistent_project(self, fresh_project_db, monkeypatch):
        """不存在的项目 ID 返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            return await ProjectDB.get_project_by_id(9999)

        result = asyncio.run(_run())
        assert result is None


class TestProjectDBGetByUuid:
    """get_project_by_uuid 测试。"""

    def test_get_by_uuid(self, fresh_project_db, monkeypatch):
        """通过 uuid 查找项目。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            await ProjectDB.create_project(user_id=1, name="test", uuid="unique-uuid")
            return await ProjectDB.get_project_by_uuid("unique-uuid")

        result = asyncio.run(_run())
        assert result is not None
        assert result["uuid"] == "unique-uuid"

    def test_get_by_uuid_empty(self, fresh_project_db, monkeypatch):
        """空 uuid 返回 None。"""
        import asyncio

        async def _run():
            return await ProjectDB.get_project_by_uuid("")

        result = asyncio.run(_run())
        assert result is None

    def test_get_by_uuid_not_found(self, fresh_project_db, monkeypatch):
        """不存在的 uuid 返回 None。"""
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))
        import asyncio

        async def _run():
            return await ProjectDB.get_project_by_uuid("nonexistent-uuid")

        result = asyncio.run(_run())
        assert result is None
