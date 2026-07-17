# -*- coding:utf-8 -*-
"""
Session 路径管理器测试

测试 app/shared/utils/files/session_path_manager 模块的路径解析、索引注册与删除逻辑。
"""

import json
from datetime import date
from pathlib import Path

import pytest

from app.shared.utils.files import session_path_manager as spm


@pytest.fixture
def fresh_manager(tmp_path, monkeypatch):
    """提供一个隔离的 session_path_manager 环境。

    将项目根目录重定向到临时目录，避免污染真实 data/ 目录。
    """
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    # 清空内存中的索引缓存（通过直接操作索引文件实现隔离）
    index_path = tmp_path / "data/upload/session_index.json"
    if index_path.exists():
        index_path.unlink()
    yield tmp_path


class TestSessionPathManager:
    """Session 路径管理器测试套件。"""

    def test_register_and_resolve_date_path(self, fresh_manager):
        """注册日期索引后应能正确解析。"""
        spm.register_session_upload_date("session-001", date(2026, 6, 19))
        assert spm.resolve_session_date_path("session-001") == "2026/06/19"

    def test_get_upload_dir_creates_and_registers(self, fresh_manager):
        """create=True 时应创建目录并写入索引。"""
        upload_dir = spm.get_session_upload_dir("session-002", create=True)
        today = date.today()
        expected = fresh_manager / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-002"
        assert upload_dir == expected
        assert upload_dir.exists()
        assert spm.resolve_session_date_path("session-002") == f"{today.year}/{today.month:02d}/{today.day:02d}"

    def test_get_tmp_dir_matches_upload_date(self, fresh_manager):
        """tmp 目录应与 upload 目录日期一致。"""
        spm.register_session_upload_date("session-003", date(2026, 1, 2))
        tmp_dir = spm.get_session_tmp_upload_dir("session-003", create=True)
        expected = fresh_manager / "data/tmp/upload/2026/01/02/session-003"
        assert tmp_dir == expected
        assert tmp_dir.exists()

    def test_get_upload_dir_fallback_to_old_path(self, fresh_manager):
        """索引不存在且未找到日期目录时，应兜底到旧路径。"""
        upload_dir = spm.get_session_upload_dir("session-004", create=False)
        expected = fresh_manager / "data/upload/session-004"
        assert upload_dir == expected

    def test_remove_session_upload_date(self, fresh_manager):
        """移除索引后解析应返回 None。"""
        spm.register_session_upload_date("session-005", date(2026, 6, 19))
        assert spm.resolve_session_date_path("session-005") == "2026/06/19"
        spm.remove_session_upload_date("session-005")
        assert spm.resolve_session_date_path("session-005") is None

    def test_find_session_date_path_by_walk(self, fresh_manager):
        """索引缺失时，通过遍历应能找到已存在的日期目录。"""
        session_dir = fresh_manager / "data/upload/2026/06/19/session-006"
        session_dir.mkdir(parents=True)
        assert spm.resolve_session_date_path("session-006") == "2026/06/19"

    def test_default_session_id(self, fresh_manager):
        """空 session_id 应回退到 default。"""
        upload_dir = spm.get_session_upload_dir("", create=True)
        assert upload_dir.name == "default"

    def test_get_upload_dir_with_project_id_routes_to_project_dir(self, fresh_manager, monkeypatch):
        """2026-06-30 新增：传 project_id 时应走项目目录，忽略 session_id。"""
        from app.shared.utils.project.project_db import ProjectDB
        from app.core.config import paths as core_paths

        # 同步重定向项目根到临时目录
        monkeypatch.setattr(core_paths, "_PROJECT_ROOT", str(fresh_manager))
        # 准备内存中的 project
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[10] = {
                "id": 10,
                "user_id": 1,
                "name": "test",
                "uuid": "session-9999",
                "relative_path": "data/project/2026/07/01/session-9999",
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        upload_dir = spm.get_session_upload_dir(
            "session-1111", create=True, project_id=10
        )
        # 应走项目目录而非 session 目录
        assert upload_dir == fresh_manager / "data/project/2026/07/01/session-9999"
        assert upload_dir.exists()

    def test_get_upload_dir_project_id_not_found_falls_back(self, fresh_manager, monkeypatch):
        """project_id 在内存中不存在时，fallback 到 session 路径。"""
        from app.shared.utils.project.project_db import ProjectDB

        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        # 传不存在的 project_id
        upload_dir = spm.get_session_upload_dir(
            "session-1111", create=True, project_id=99999
        )
        # 应 fallback 到 session 目录
        today = date.today()
        expected = fresh_manager / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-1111"
        assert upload_dir == expected

    def test_get_tmp_upload_dir_with_project_id(self, fresh_manager, monkeypatch):
        """2026-06-30 新增：tmp 目录也支持 project_id 路由。"""
        from app.shared.utils.project.project_db import ProjectDB
        from app.core.config import paths as core_paths

        monkeypatch.setattr(core_paths, "_PROJECT_ROOT", str(fresh_manager))
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[20] = {
                "id": 20,
                "user_id": 1,
                "name": "test",
                "uuid": "session-8888",
                "relative_path": "data/project/2026/07/01/session-8888",
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        tmp_dir = spm.get_session_tmp_upload_dir(
            "session-1111", create=True, project_id=20
        )
        assert tmp_dir == fresh_manager / "data/tmp/project/2026/07/01/session-8888"
        assert tmp_dir.exists()


class TestFilesystemSafeSessionId:
    """2026-07-17 新增：飞书 session_id 含 `:`，需要做文件系统安全转换。"""

    def test_to_filesystem_safe_replaces_colons(self):
        """冒号必须替换为下划线。"""
        assert spm._to_filesystem_safe("feishu:p2p:ou_0a4bb") == "feishu_p2p_ou_0a4bb"

    def test_to_filesystem_safe_keeps_uuid_unchanged(self):
        """普通 UUID 不含冒号，转换应 no-op。"""
        assert spm._to_filesystem_safe("550e8400-e29b-41d4-a716-446655440000") == \
               "550e8400-e29b-41d4-a716-446655440000"

    def test_to_filesystem_safe_handles_empty(self):
        """空值应回退到 default（与 get_session_upload_dir 旧行为一致）。"""
        assert spm._to_filesystem_safe("") == "default"
        assert spm._to_filesystem_safe(None) == "default"

    def test_get_upload_dir_collapses_feishu_colons(self, fresh_manager):
        """飞书 session_id 在路径上应自动转为下划线形式，避免 Windows WinError 123。

        复现 2026-07-17 线上事故：data/upload/2026/07/17/feishu:p2p:ou_xxx
        在 Windows 上 iterdir() 抛 OSError，引发文件树 500。
        """
        spm.register_session_upload_date(
            "feishu:p2p:ou_0a4bb8715bc1c45f5024a2bfc4a56261",
            date(2026, 7, 17),
        )
        upload_dir = spm.get_session_upload_dir(
            "feishu:p2p:ou_0a4bb8715bc1c45f5024a2bfc4a56261",
            create=False,
        )
        # 路径中不应再包含 `:`，应是下划线形式
        assert "feishu:p2p:ou_" not in str(upload_dir)
        assert str(upload_dir).endswith(
            "feishu_p2p_ou_0a4bb8715bc1c45f5024a2bfc4a56261"
        )
        assert upload_dir == fresh_manager / \
            "data/upload/2026/07/17/feishu_p2p_ou_0a4bb8715bc1c45f5024a2bfc4a56261"

    def test_get_tmp_upload_dir_collapses_feishu_colons(self, fresh_manager):
        """tmp 目录也应做同样的转换。"""
        spm.register_session_upload_date(
            "feishu:p2p:ou_abc",
            date(2026, 7, 17),
        )
        tmp_dir = spm.get_session_tmp_upload_dir(
            "feishu:p2p:ou_abc",
            create=True,
        )
        assert "feishu:p2p:ou_abc" not in str(tmp_dir)
        assert str(tmp_dir).endswith("feishu_p2p_ou_abc")
        assert tmp_dir.exists()
