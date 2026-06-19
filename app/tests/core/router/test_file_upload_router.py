# -*- coding:utf-8 -*-
"""
核心文件上传路由测试

测试 app/core/router/file_upload_router 中 upload_files 与 merge_chunks 的
日期化目录存储、原文件保留、md 文件生成逻辑。
"""

import json
from datetime import date
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import UploadFile
from starlette.datastructures import State

from app.core.router.file_upload_router import router, MergeChunksRequest, upload_files, merge_chunks
from app.shared.utils.files import session_path_manager as spm


@pytest.fixture
def mock_request(tmp_path, monkeypatch):
    """构造带 session_id 的 FastAPI Request 模拟对象，并隔离项目根目录。"""
    monkeypatch.setattr(spm, "_get_project_root", lambda: tmp_path)

    class DummyRequest:
        state = State({"session_id": "session-abc"})

    return DummyRequest()


class _FakeDocument:
    """模拟 Document 对象。"""
    def __init__(self, page_content: str):
        self.page_content = page_content


class _FakeDocumentLoader:
    """模拟 DocumentLoader，返回固定内容。"""
    def __init__(self, path: str):
        self.path = path

    def load(self):
        return [_FakeDocument("hello world\nthis is a test")]


class TestUploadFiles:
    """批量上传接口测试。"""

    @pytest.mark.asyncio
    async def test_upload_files_local_saves_original_and_md(self, mock_request, tmp_path):
        """本地模式下应保留原文件到日期目录，并生成 md 到 tmp 日期目录。"""
        content = b"hello world\nthis is a test"
        upload_file = UploadFile(filename="test.txt", file=BytesIO(content))

        with patch("app.core.router.file_upload_router.FILE_PARSER_CONFIG", {"enabled": False}), \
             patch("app.core.router.file_upload_router.DocumentLoader", _FakeDocumentLoader):
            resp = await upload_files(mock_request, [upload_file])

        today = date.today()
        original_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-abc/test.txt"
        md_path = tmp_path / f"data/tmp/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-abc/test.md"

        assert original_path.exists()
        assert original_path.read_text(encoding="utf-8") == content.decode("utf-8")
        assert md_path.exists()
        assert "hello world" in md_path.read_text(encoding="utf-8")

        assert resp.count == 1
        assert resp.files[0].stored_path == str(md_path)
        assert resp.files[0].file_type == "md"
        assert resp.files[0].filename == "test.txt"

    @pytest.mark.asyncio
    async def test_upload_files_remote_returns_md(self, mock_request, tmp_path):
        """远程解析模式下应返回解析服务生成的 md 路径。"""
        content = b"fake pdf content"
        upload_file = UploadFile(filename="report.pdf", file=BytesIO(content))

        today = date.today()
        expected_md = tmp_path / f"data/tmp/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-abc/report.md"

        def fake_parse(*args, **kwargs):
            # 模拟远程解析服务生成 md 文件
            expected_md.parent.mkdir(parents=True, exist_ok=True)
            expected_md.write_text("# Report\n", encoding="utf-8")
            return str(expected_md)

        with patch("app.core.router.file_upload_router.FILE_PARSER_CONFIG", {
            "enabled": True,
            "server_url": "http://test",
            "max_retries": 1,
            "poll_interval": 0.1,
            "timeout": 1,
            "api_url": "http://test/api",
        }):
            with patch("app.shared.utils.files.file_parser_client.FileParserClient.parse", side_effect=fake_parse):
                resp = await upload_files(mock_request, [upload_file])

        assert resp.count == 1
        assert resp.files[0].stored_path == str(expected_md)
        assert resp.files[0].file_type == "md"

        assert resp.count == 1
        assert resp.files[0].stored_path == str(expected_md)
        assert resp.files[0].file_type == "md"


class TestMergeChunks:
    """分片合并接口测试。"""

    @pytest.mark.asyncio
    async def test_merge_chunks_local_saves_original_and_md(self, mock_request, tmp_path):
        """本地模式下合并分片后应保留原文件并生成 md。"""
        file_id = "chunk-file-001"
        chunks_dir = tmp_path / "upload_chunks"
        chunk_dir = chunks_dir / file_id
        chunk_dir.mkdir(parents=True)
        (chunk_dir / "chunk_0").write_text("hello ", encoding="utf-8")
        (chunk_dir / "chunk_1").write_text("world", encoding="utf-8")

        merge_request = MergeChunksRequest(
            file_id=file_id,
            filename="merge.txt",
            total_chunks=2,
        )

        with patch("app.core.router.file_upload_router.CHUNKS_DIR", chunks_dir), \
             patch("app.core.router.file_upload_router.FILE_PARSER_CONFIG", {"enabled": False}):
            with patch("app.core.router.file_upload_router.DocumentLoader", _FakeDocumentLoader):
                resp = await merge_chunks(mock_request, merge_request)

        today = date.today()
        original_path = tmp_path / f"data/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-abc/merge.txt"
        md_path = tmp_path / f"data/tmp/upload/{today.year}/{today.month:02d}/{today.day:02d}/session-abc/merge.md"

        assert original_path.exists()
        assert original_path.read_text(encoding="utf-8") == "hello world"
        assert md_path.exists()
        assert "hello world" in md_path.read_text(encoding="utf-8")

        assert resp.count == 1
        assert resp.files[0].stored_path == str(md_path)
        assert resp.files[0].file_type == "md"
