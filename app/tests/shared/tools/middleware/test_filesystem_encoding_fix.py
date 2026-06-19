# -*- coding:utf-8 -*-
"""
Filesystem Encoding Fix 测试

测试 app/shared/tools/middleware/filesystem_encoding_fix 模块的 read 猴补丁：
- deepagents FilesystemMiddleware 传入的是以 "/" 开头的虚拟绝对路径
- 猴补丁通过临时转换 self.cwd 把虚拟路径解析到 data/tmp/upload/...
- 扩展名统一替换为 .md
- md 文件不存在时返回 not found 且错误信息使用原路径
- 读取后 self.cwd 恢复
"""

from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.shared.tools.middleware import filesystem_encoding_fix as fix
from app.shared.utils.files import session_path_manager as spm


class _FakeBackend:
    """模拟 FilesystemBackend 实例，提供 cwd、virtual_mode 与 _resolve_path。"""
    def __init__(self, cwd: Path, virtual_mode: bool = True):
        self.cwd = cwd
        self.virtual_mode = virtual_mode

    def _resolve_path(self, key: str) -> Path:
        """复刻 deepagents FilesystemBackend._resolve_path 在 virtual_mode=True 下的行为。"""
        if self.virtual_mode:
            vpath = key if key.startswith("/") else "/" + key
            if ".." in vpath or vpath.startswith("~"):
                raise ValueError("Path traversal not allowed")
            return (self.cwd / vpath.lstrip("/")).resolve()

        path = Path(key)
        if path.is_absolute():
            return path
        return (self.cwd / path).resolve()


@pytest.fixture
def patched_read(tmp_path, monkeypatch):
    """返回可直接调用的 _patched_read，并隔离项目根目录。"""
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    return fix._patched_read


class TestPatchedRead:
    """_patched_read 单元测试。"""

    def test_read_virtual_path_maps_to_tmp_md(self, tmp_path, patched_read):
        """/file.docx 在 cwd=data/upload/... 时应解析到 data/tmp/upload/.../file.md。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "file.md").write_text("# Markdown content", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/file.docx")

        assert result.error is None
        assert result.file_data is not None
        assert result.file_data["content"] == "# Markdown content"

    def test_read_virtual_subdir_maps_to_tmp_md(self, tmp_path, patched_read):
        """/reports/annual.pdf 应解析到 data/tmp/upload/.../reports/annual.md。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc/reports"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "annual.md").write_text("Annual report", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/reports/annual.pdf")

        assert result.error is None
        assert result.file_data["content"] == "Annual report"

    def test_read_returns_not_found_with_original_path(self, tmp_path, patched_read):
        """md 文件不存在时，应返回 not found 且错误信息使用原始虚拟路径。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        backend = _FakeBackend(upload_dir)
        original_path = "/missing.docx"
        result = patched_read(backend, original_path)

        assert result.error is not None
        assert original_path in result.error
        assert ".md" not in result.error

    def test_read_md_virtual_path_is_idempotent(self, tmp_path, patched_read):
        """/readme.md 应直接读取对应的 .md 文件。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "readme.md").write_text("Already markdown", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/readme.md")

        assert result.error is None
        assert result.file_data["content"] == "Already markdown"

    def test_read_offset_limit(self, tmp_path, patched_read):
        """验证 offset 与 limit 切片生效。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "lines.md").write_text("line1\nline2\nline3\nline4\n", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/lines.docx", offset=1, limit=2)

        assert result.error is None
        assert result.file_data["content"] == "line2\nline3\n"

    def test_read_restores_original_cwd(self, tmp_path, patched_read):
        """读取完成后必须恢复原始 self.cwd。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "file.md").write_text("content", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        patched_read(backend, "/file.docx")

        assert backend.cwd == upload_dir

    def test_read_does_not_double_convert_tmp_cwd(self, tmp_path, patched_read):
        """self.cwd 已在 data/tmp/ 下时，不应重复替换为 data/tmp/tmp/。"""
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "file.md").write_text("From tmp", encoding="utf-8")

        backend = _FakeBackend(tmp_dir)
        result = patched_read(backend, "/file.docx")

        assert result.error is None
        assert result.file_data["content"] == "From tmp"
        assert backend.cwd == tmp_dir


class TestApplyFix:
    """apply_fix 注册行为测试。"""

    def test_apply_fix_registers_read_patch(self, monkeypatch):
        """apply_fix 应将 FilesystemBackend.read 替换为 _patched_read。"""
        fake_fs_module = MagicMock()
        fake_fs_module.FilesystemBackend.read = lambda self, x: x
        monkeypatch.setattr(fix, "fs_module", fake_fs_module)

        fix.apply_fix()

        assert fake_fs_module.FilesystemBackend.read is fix._patched_read
