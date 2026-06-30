# -*- coding:utf-8 -*-
"""
FileTransfer 测试

测试 app/shared/utils/files/fileTransfer.py 的日期化路径解析与会话删除逻辑。
"""

from datetime import date
from pathlib import Path

import pytest

from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.files import session_path_manager as spm


class _FakeUploadFile:
    """模拟 FastAPI UploadFile，用于测试上传流程。"""
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content

    async def read(self):
        return self._content


@pytest.fixture
def isolated_spm(tmp_path, monkeypatch):
    """将 session_path_manager 重定向到临时目录，避免污染真实 data/。"""
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    return tmp_path


class TestFileTransferDatedPaths:
    """FileTransfer 日期化路径测试。"""

    @pytest.mark.asyncio
    async def test_upload_files_uses_dated_session_dir(self, isolated_spm):
        """上传文件应保存到 data/upload/yyyy/mm/dd/{session_id}/ 下。"""
        transfer = FileTransfer(upload_dir="data/upload")
        fake_file = _FakeUploadFile("report.docx", b"fake docx content")

        result = await transfer.upload_files([fake_file], "session-ft-001")

        today = date.today()
        expected_dir = isolated_spm / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-ft-001"
        assert expected_dir.exists()
        assert len(result) == 1
        assert result[0]["filename"] == "report"

        saved_files = list(expected_dir.iterdir())
        assert len(saved_files) == 1
        assert saved_files[0].read_bytes() == b"fake docx content"

    def test_get_file_path_resolves_dated_dir(self, isolated_spm):
        """get_file_path 应能根据 session_id 解析到日期化目录。"""
        transfer = FileTransfer(upload_dir="data/upload")
        today = date.today()
        expected_dir = isolated_spm / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-ft-002"
        expected_dir.mkdir(parents=True)
        expected_file = expected_dir / "uuid-123.txt"
        expected_file.write_text("hello", encoding="utf-8")

        resolved = transfer.get_file_path("uuid-123", "session-ft-002")

        assert resolved == expected_file

    @pytest.mark.asyncio
    async def test_delete_session_removes_upload_and_tmp_dirs(self, isolated_spm):
        """delete_session 应同时删除 upload 与 tmp/upload 目录，并清理索引。"""
        transfer = FileTransfer(upload_dir="data/upload")
        today = date.today()
        upload_dir = isolated_spm / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-ft-003"
        tmp_dir = isolated_spm / f"data/tmp/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-ft-003"
        upload_dir.mkdir(parents=True)
        tmp_dir.mkdir(parents=True)
        (upload_dir / "orig.pdf").write_text("orig", encoding="utf-8")
        (tmp_dir / "orig.md").write_text("md", encoding="utf-8")
        spm.register_session_upload_date("session-ft-003")

        deleted = await transfer.delete_session("session-ft-003")

        assert deleted is True
        assert not upload_dir.exists()
        assert not tmp_dir.exists()
        assert spm.resolve_session_date_path("session-ft-003") is None

    @pytest.mark.asyncio
    async def test_delete_session_returns_false_when_missing(self, isolated_spm):
        """upload 与 tmp 目录均不存在时，delete_session 应返回 False。"""
        transfer = FileTransfer(upload_dir="data/upload")

        deleted = await transfer.delete_session("session-ft-999")

        assert deleted is False

    @pytest.mark.asyncio
    async def test_upload_files_with_project_id_routes_to_project_dir(self, isolated_spm, monkeypatch):
        """2026-06-30 新增：传 project_id 时文件应保存到 data/project/{uuid}/ 下。"""
        from app.shared.utils.project import project_db
        from app.shared.utils.project.project_db import ProjectDB

        # 把 project_path_manager 也重定向到 tmp_path
        from app.shared.utils.files import project_path_manager as ppm
        monkeypatch.setattr(ppm, "_get_project_root", lambda: isolated_spm)
        # 准备内存中的 project
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[100] = {
                "id": 100,
                "user_id": 1,
                "name": "test",
                "uuid": "session-uuid-100",
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        transfer = FileTransfer(upload_dir="data/upload")
        fake_file = _FakeUploadFile("report.pdf", b"project content")

        result = await transfer.upload_files(
            [fake_file], "session-1111", project_id=100
        )

        expected_dir = isolated_spm / "data/project/session-uuid-100"
        assert expected_dir.exists()
        assert len(result) == 1
        # 旧 session 目录不应被创建
        assert not (isolated_spm / "data/upload").exists() or not list(
            (isolated_spm / "data/upload").rglob("*session-1111*")
        )

    @pytest.mark.asyncio
    async def test_delete_session_with_project_id_routes_to_project_dir(self, isolated_spm, monkeypatch):
        """2026-06-30 新增：delete_session 传 project_id 时应清理项目目录。"""
        from app.shared.utils.files import project_path_manager as ppm
        from app.shared.utils.project.project_db import ProjectDB

        monkeypatch.setattr(ppm, "_get_project_root", lambda: isolated_spm)
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[200] = {
                "id": 200,
                "user_id": 1,
                "name": "test",
                "uuid": "session-uuid-200",
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        project_dir = isolated_spm / "data/project/session-uuid-200"
        project_dir.mkdir(parents=True)
        (project_dir / "test.txt").write_text("data", encoding="utf-8")

        transfer = FileTransfer(upload_dir="data/upload")
        deleted = await transfer.delete_session("session-1111", project_id=200)

        assert deleted is True
        assert not project_dir.exists()
