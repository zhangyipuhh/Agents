# -*- coding:utf-8 -*-
"""
Filesystem Encoding Fix 测试

测试 app/shared/tools/middleware/filesystem_encoding_fix 模块的 read/write 猴补丁：
- deepagents FilesystemMiddleware 传入的是以 "/" 开头的虚拟绝对路径
- read 补丁对 pdf/docx/xlsx/md/txt 扩展名临时映射到 data/tmp/upload/... 的 .md 缓存
- read 补丁对非文档类扩展名直接读取 self.cwd 下的原文件
- write 补丁对 pdf/docx/xlsx/md/txt 扩展名同步写入 data/tmp/... 的 .md 镜像
- 读取后 self.cwd 恢复
"""

import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.shared.utils.files import session_path_manager as spm


# 全局 conftest 与 routers/conftest 都会把 filesystem_encoding_fix mock 为仅含 apply_fix 的 stub，
# 但本测试需要验证真实实现。为了避免 sys.modules 被其它 conftest 覆盖导致拿到 mock，
# 这里直接从源文件加载真实模块，不依赖 sys.modules 中的条目。
_fix_path = (
    Path(__file__).resolve().parents[4]
    / "shared"
    / "tools"
    / "middleware"
    / "filesystem_encoding_fix.py"
)
_spec = importlib.util.spec_from_file_location(
    "app.shared.tools.middleware.filesystem_encoding_fix", _fix_path
)
fix = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fix)


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


@pytest.fixture
def patched_write(tmp_path, monkeypatch):
    """返回可直接调用的 _patched_write，并隔离项目根与 paths._PROJECT_ROOT。"""
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    monkeypatch.setattr("app.core.config.paths._PROJECT_ROOT", str(tmp_path))
    return fix._patched_write


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
        """/reports/annual.pdf 应解析到 data/tmp/upload/.../reports/annual.md，并返回 base64 编码内容。"""
        import base64

        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc/reports"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "annual.md").write_text("Annual report", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/reports/annual.pdf")

        assert result.error is None
        assert result.file_data["encoding"] == "base64"
        decoded = base64.b64decode(result.file_data["content"]).decode("utf-8")
        assert decoded == "Annual report"

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

    def test_read_non_text_extension_returns_base64(self, tmp_path, patched_read):
        """原始路径为 .pdf 等非文本扩展名时，返回的 content 应为 base64 编码，encoding 为 base64。"""
        import base64

        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        markdown_text = "# PDF converted to markdown\nSome content."
        (tmp_dir / "report.md").write_text(markdown_text, encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/report.pdf")

        assert result.error is None
        assert result.file_data is not None
        assert result.file_data["encoding"] == "base64"
        # 验证 content 是合法的 base64 编码字符串
        decoded = base64.b64decode(result.file_data["content"]).decode("utf-8")
        assert decoded == markdown_text

    def test_read_text_extension_returns_plain_text(self, tmp_path, patched_read):
        """原始路径为 .txt 等文本扩展名时，返回的 content 仍为纯文本，encoding 为 utf-8。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        tmp_dir.mkdir(parents=True)
        plain_text = "Plain text content."
        (tmp_dir / "notes.md").write_text(plain_text, encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/notes.txt")

        assert result.error is None
        assert result.file_data is not None
        assert result.file_data["encoding"] == "utf-8"
        assert result.file_data["content"] == plain_text

    def test_read_non_doc_extension_reads_original(self, tmp_path, patched_read):
        """非文档类扩展名（如 .py）应直接读取 self.cwd 下的原文件，不重定向到 .md。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)
        (upload_dir / "script.py").write_text("print('hello')", encoding="utf-8")

        backend = _FakeBackend(upload_dir)
        result = patched_read(backend, "/script.py")

        assert result.error is None
        assert result.file_data is not None
        assert result.file_data["encoding"] == "utf-8"
        assert result.file_data["content"] == "print('hello')"

    def test_read_project_date_path_maps_to_tmp_md(self, tmp_path, patched_read):
        """项目文件夹日期化路径 data/project/yyyy/mm/dd/{uuid}/ 能自然映射到 data/tmp/project/..."""
        project_dir = tmp_path / "data/project/2026/07/01/project-uuid"
        tmp_dir = tmp_path / "data/tmp/project/2026/07/01/project-uuid"
        tmp_dir.mkdir(parents=True)
        (tmp_dir / "doc.md").write_text("Project doc markdown", encoding="utf-8")

        backend = _FakeBackend(project_dir)
        result = patched_read(backend, "/doc.txt")

        assert result.error is None
        assert result.file_data is not None
        assert result.file_data["content"] == "Project doc markdown"


class TestPatchedWrite:
    """_patched_write 单元测试。"""

    def test_write_doc_extension_creates_md_mirror(self, tmp_path, patched_write, monkeypatch):
        """写 .docx 时同步生成 data/tmp/.../.md 镜像。"""
        from deepagents.backends.protocol import WriteResult

        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)

        def _fake_orig_write(self, file_path, content):
            p = self._resolve_path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return WriteResult(path=file_path)

        monkeypatch.setattr(fix, "_orig_write", _fake_orig_write)
        backend = _FakeBackend(upload_dir)

        result = patched_write(backend, "/report.docx", "# Report\ncontent")

        assert result.error is None
        assert result.path == "/report.docx"
        assert (upload_dir / "report.docx").read_text(encoding="utf-8") == "# Report\ncontent"

        md_mirror = tmp_path / "data/tmp/upload/2026/06/19/session-abc/report.md"
        assert md_mirror.exists()
        assert md_mirror.read_text(encoding="utf-8") == "# Report\ncontent"

    def test_write_non_doc_extension_no_mirror(self, tmp_path, patched_write, monkeypatch):
        """写 .py 时不生成 .md 镜像。"""
        from deepagents.backends.protocol import WriteResult

        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)

        def _fake_orig_write(self, file_path, content):
            p = self._resolve_path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return WriteResult(path=file_path)

        monkeypatch.setattr(fix, "_orig_write", _fake_orig_write)
        backend = _FakeBackend(upload_dir)

        result = patched_write(backend, "/script.py", "print('hello')")

        assert result.error is None
        assert (upload_dir / "script.py").read_text(encoding="utf-8") == "print('hello')"

        md_mirror = tmp_path / "data/tmp/upload/2026/06/19/session-abc/script.md"
        assert not md_mirror.exists()


class _FakeMiddleware:
    """模拟 EncodingSafeFileSearchMiddleware 实例，提供 _validate_and_resolve_path。"""
    def __init__(self, root_path: Path, max_file_size_mb: int = 10):
        self.root_path = root_path.resolve()
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

    def _validate_and_resolve_path(self, path: str) -> Path:
        """复刻 EncodingSafeFileSearchMiddleware._validate_and_resolve_path。"""
        if not path.startswith("/"):
            path = "/" + path
        if ".." in path or "~" in path:
            raise ValueError("Path traversal not allowed")
        relative = path.lstrip("/")
        full_path = (self.root_path / relative).resolve()
        try:
            full_path.relative_to(self.root_path)
        except ValueError:
            raise ValueError(f"Path outside root directory: {path}") from None
        return full_path


@pytest.fixture
def patched_python_search(tmp_path, monkeypatch):
    """返回可直接调用的 _patched_python_search，并隔离项目根目录。"""
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)
    # 设置原始回退函数，用于测试回退场景
    fix._orig_python_search = lambda self, pattern, base_path, include: {"/fallback": [(1, "fallback")]}
    return fix._patched_python_search


class TestPatchedPythonSearch:
    """_patched_python_search 单元测试。"""

    def test_grep_maps_to_tmp_md(self, tmp_path, patched_python_search):
        """原始目录下有 file.pdf，tmp 目录下有 file.md（含匹配文本），验证能搜到匹配且返回 /file.pdf。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)
        tmp_dir.mkdir(parents=True)
        (upload_dir / "file.pdf").write_text("", encoding="utf-8")
        (tmp_dir / "file.md").write_text("hello world\nmatch line\n", encoding="utf-8")

        middleware = _FakeMiddleware(upload_dir)
        results = patched_python_search(middleware, "match", "/", None)

        assert "/file.pdf" in results
        assert len(results["/file.pdf"]) == 1
        assert results["/file.pdf"][0] == (2, "match line")

    def test_grep_include_filter_on_original_name(self, tmp_path, patched_python_search):
        """include 过滤在原始文件名上生效，只返回匹配的原始文件。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)
        tmp_dir.mkdir(parents=True)
        (upload_dir / "a.pdf").write_text("", encoding="utf-8")
        (upload_dir / "b.txt").write_text("", encoding="utf-8")
        (tmp_dir / "a.md").write_text("match a", encoding="utf-8")
        (tmp_dir / "b.md").write_text("match b", encoding="utf-8")

        middleware = _FakeMiddleware(upload_dir)
        results = patched_python_search(middleware, "match", "/", "*.pdf")

        assert "/a.pdf" in results
        assert "/b.pdf" not in results

    def test_grep_fallback_when_no_tmp_mapping(self, tmp_path, patched_python_search):
        """root_path 不在 data/ 下时，回退到原始 _python_search。"""
        knowledge_dir = tmp_path / "knowledge"
        knowledge_dir.mkdir(parents=True)

        middleware = _FakeMiddleware(knowledge_dir)
        results = patched_python_search(middleware, "match", "/", None)

        assert "/fallback" in results

    def test_grep_no_md_file_skips(self, tmp_path, patched_python_search):
        """原始文件存在但对应 .md 不存在时，静默跳过该文件。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)
        tmp_dir.mkdir(parents=True)
        (upload_dir / "file.pdf").write_text("", encoding="utf-8")
        # 不创建 file.md

        middleware = _FakeMiddleware(upload_dir)
        results = patched_python_search(middleware, "match", "/", None)

        assert "/file.pdf" not in results
        assert results == {}

    def test_grep_returns_original_virtual_path(self, tmp_path, patched_python_search):
        """搜到多个 .md 文件时，返回的虚拟路径均保留原始后缀。"""
        upload_dir = tmp_path / "data/upload/2026/06/19/session-abc"
        tmp_dir = tmp_path / "data/tmp/upload/2026/06/19/session-abc"
        upload_dir.mkdir(parents=True)
        tmp_dir.mkdir(parents=True)
        (upload_dir / "a.pdf").write_text("", encoding="utf-8")
        (upload_dir / "b.txt").write_text("", encoding="utf-8")
        (tmp_dir / "a.md").write_text("match a", encoding="utf-8")
        (tmp_dir / "b.md").write_text("match b", encoding="utf-8")

        middleware = _FakeMiddleware(upload_dir)
        results = patched_python_search(middleware, "match", "/", None)

        assert "/a.pdf" in results
        assert "/b.txt" in results
        assert "/a.md" not in results
        assert "/b.md" not in results


class TestApplyFix:
    """apply_fix 注册行为测试。"""

    def test_apply_fix_registers_read_patch(self, monkeypatch):
        """apply_fix 应将 FilesystemBackend.read 替换为 _patched_read。"""
        import sys

        fake_fs_module = MagicMock()
        fake_fs_module.FilesystemBackend.read = lambda self, x: x
        fake_fs_module.FilesystemBackend.write = lambda self, x, y: y
        monkeypatch.setattr(fix, "fs_module", fake_fs_module)

        fake_module = MagicMock()
        fake_module.EncodingSafeFileSearchMiddleware._python_search = lambda self, pattern, base_path, include: {}
        monkeypatch.setitem(sys.modules, "app.shared.tools.middleware.encoding_safe_file_search", fake_module)

        fix.apply_fix()

        assert fake_fs_module.FilesystemBackend.read is fix._patched_read

    def test_apply_fix_registers_write_patch(self, monkeypatch):
        """apply_fix 应将 FilesystemBackend.write 替换为 _patched_write。"""
        import sys

        fake_fs_module = MagicMock()
        fake_fs_module.FilesystemBackend.read = lambda self, x: x
        fake_fs_module.FilesystemBackend.write = lambda self, x, y: y
        monkeypatch.setattr(fix, "fs_module", fake_fs_module)

        fake_module = MagicMock()
        fake_module.EncodingSafeFileSearchMiddleware._python_search = lambda self, pattern, base_path, include: {}
        monkeypatch.setitem(sys.modules, "app.shared.tools.middleware.encoding_safe_file_search", fake_module)

        fix.apply_fix()

        assert fake_fs_module.FilesystemBackend.write is fix._patched_write
