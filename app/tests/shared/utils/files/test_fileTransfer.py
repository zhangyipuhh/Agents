# -*- coding:utf-8 -*-
"""
FileTransfer 测试

测试 app/shared/utils/files/fileTransfer.py 的日期化路径解析与会话删除逻辑。
"""

from datetime import date
from pathlib import Path

import pytest

from app.core.config import paths as core_paths
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
        """2026-06-30 新增：传 project_id 时文件应保存到 data/project/yyyy/mm/dd/{uuid}/ 下。"""
        from app.shared.utils.project import project_db
        from app.shared.utils.project.project_db import ProjectDB

        # 将项目根目录重定向到临时目录，避免污染真实 data/
        monkeypatch.setattr(core_paths, "_PROJECT_ROOT", str(isolated_spm))
        # 准备内存中的 project，携带日期化 relative_path
        today = date.today()
        relative_path = f"data/project/{today.year}/{today.month:02d}/{today.day:02d}/session-uuid-100"
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[100] = {
                "id": 100,
                "user_id": 1,
                "name": "test",
                "uuid": "session-uuid-100",
                "relative_path": relative_path,
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        transfer = FileTransfer(upload_dir="data/upload")
        fake_file = _FakeUploadFile("report.pdf", b"project content")

        result = await transfer.upload_files(
            [fake_file], "session-1111", project_id=100
        )

        expected_dir = isolated_spm / relative_path
        assert expected_dir.exists()
        assert len(result) == 1
        # 旧 session 目录不应被创建
        assert not (isolated_spm / "data/upload").exists() or not list(
            (isolated_spm / "data/upload").rglob("*session-1111*")
        )

    @pytest.mark.asyncio
    async def test_delete_session_with_project_id_routes_to_project_dir(self, isolated_spm, monkeypatch):
        """2026-06-30 新增：delete_session 传 project_id 时应清理日期化项目目录。"""
        from app.shared.utils.project.project_db import ProjectDB

        # 将项目根目录重定向到临时目录
        monkeypatch.setattr(core_paths, "_PROJECT_ROOT", str(isolated_spm))
        # 准备内存中的 project，携带日期化 relative_path
        today = date.today()
        relative_path = f"data/project/{today.year}/{today.month:02d}/{today.day:02d}/session-uuid-200"
        with ProjectDB._lock:
            ProjectDB._memory_cache.clear()
            ProjectDB._memory_cache[200] = {
                "id": 200,
                "user_id": 1,
                "name": "test",
                "uuid": "session-uuid-200",
                "relative_path": relative_path,
                "created_at": None,
                "updated_at": None,
            }
        monkeypatch.setattr(ProjectDB, "is_enabled", classmethod(lambda cls: False))

        project_dir = isolated_spm / relative_path
        project_dir.mkdir(parents=True)
        (project_dir / "test.txt").write_text("data", encoding="utf-8")

        transfer = FileTransfer(upload_dir="data/upload")
        deleted = await transfer.delete_session("session-1111", project_id=200)

        assert deleted is True
        assert not project_dir.exists()


class TestScanDirTreeRobustness:
    """2026-07-17 新增：_scan_dir_tree 在 Windows / IO 抖动下的鲁棒性。

    复现 2026-07-17 线上事故：
      - 飞书 session_id 含 `:`，Windows 上 Path.iterdir() 抛 OSError [WinError 123]
      - 现状 _scan_dir_tree 内部已 try/except 但仅对子目录递归；
        新增要求：listdir 失败时返回空 children，单 entry stat 失败时跳过该 entry。
    """

    def test_scan_dir_tree_handles_listdir_failure(self, tmp_path):
        """listdir 抛 OSError 时 _scan_dir_tree 应返回 children=[] 而非向上抛。"""
        transfer = FileTransfer(upload_dir="data/upload")

        # 构造一个真实目录，但 monkeypatch 让 iterdir 抛 OSError
        broken_dir = tmp_path / "broken"
        broken_dir.mkdir()

        original_iterdir = Path.iterdir

        def fake_iterdir(self, *args, **kwargs):
            if self == broken_dir:
                raise OSError(123, "文件名、目录名或卷标语法不正确")
            return original_iterdir(self, *args, **kwargs)

        import unittest.mock as mock
        with mock.patch.object(Path, "iterdir", fake_iterdir):
            node = transfer._scan_dir_tree(broken_dir, broken_dir)

        # 应降级为 children=[]，不抛
        assert node["children"] == []
        assert node["name"] == "broken"

    def test_scan_dir_tree_skips_unreadable_entry(self, tmp_path):
        """单个 entry stat 抛 OSError 时应跳过该 entry，继续处理其它 entry。

        实现思路：通过 monkeypatch FileTransfer._scan_dir_tree 内对 entry.is_dir()
        与 entry.stat() 的调用路径，注入抛错逻辑。最稳的做法是：直接验证 _scan_dir_tree
        对真实损坏目录的恢复能力——Windows 上拿到一个损坏/孤立的 reparse point 时，
        stat 会抛 OSError。

        本测试使用 symlink 指向不存在的目标来触发 stat OSError（PermissionError /
        OSError 子类），symlink 解析过程是 Windows 上常见的失败模式。
        """
        import sys
        transfer = FileTransfer(upload_dir="data/upload")

        scan_dir = tmp_path / "mixed"
        scan_dir.mkdir()
        good_file = scan_dir / "good.txt"
        good_file.write_text("ok", encoding="utf-8")

        # 创建悬空 symlink：在 Windows 上若不支持 symlink 则跳过此测试
        broken_link = scan_dir / "broken_link.txt"
        if sys.platform == "win32":
            try:
                broken_link.symlink_to(tmp_path / "nonexistent_target")
            except (OSError, NotImplementedError):
                pytest.skip("Windows 上 symlink 不可用，跳过此测试")
        else:
            broken_link.symlink_to(tmp_path / "nonexistent_target")

        # 在 Windows 上，悬空 symlink 的 stat() 抛 OSError。
        # _scan_dir_tree 应通过 per-entry try/except 跳过，不应 crash。
        node = transfer._scan_dir_tree(scan_dir, scan_dir)

        # 验证：函数正常返回（不抛 OSError），good.txt 在结果中
        file_names = [c["name"] for c in node["children"]]
        assert "good.txt" in file_names

    @pytest.mark.asyncio
    async def test_build_session_file_tree_recovers_from_listdir_failure(self, tmp_path, monkeypatch):
        """build_session_file_tree 在 Windows 路径非法字符下应降级为空根而非 500。"""
        # 重定向项目根到临时目录
        monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
        # 用 register_session_upload_date 让解析能找到日期路径
        from datetime import date
        spm.register_session_upload_date("feishu:p2p:ou_test", date(2026, 7, 17))

        # 预先创建一个**下划线形式**的目录（模拟飞书 WS 已落盘的真实目录）
        real_dir = tmp_path / "data/upload/2026/07/17/feishu_p2p_ou_test"
        real_dir.mkdir(parents=True)
        (real_dir / "创建python.md").write_text("content", encoding="utf-8")

        transfer = FileTransfer(upload_dir="data/upload")

        # 不应抛 OSError，应返回 children 非空（因为核心修复后 _get_session_dir 会走下划线路径）
        tree = await transfer.build_session_file_tree("feishu:p2p:ou_test")
        assert tree["type"] == "folder"
        # 找到原文件节点
        children = tree["children"]
        assert len(children) >= 1
        first_child = children[0]
        assert first_child["children"][0]["name"] == "创建python.md"
