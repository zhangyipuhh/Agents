import io
import zipfile
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.router.file_download_router import router


@pytest.fixture
def tmp_download_dir(tmp_path):
    return tmp_path


@pytest.fixture
def app_with_download_router(tmp_download_dir):
    app = FastAPI()
    app.include_router(router)

    @app.middleware("http")
    async def inject_session_id(request, call_next):
        request.state.session_id = "test_session"
        response = await call_next(request)
        return response

    with patch("app.core.router.file_download_router.DOWNLOAD_DIR", tmp_download_dir):
        yield app


@pytest.fixture
def client(app_with_download_router):
    return TestClient(app_with_download_router)


@pytest.fixture
def session_dir(tmp_download_dir):
    d = tmp_download_dir / "test_session"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _create_file(directory: Path, name: str, content: bytes = b"hello world") -> Path:
    f = directory / name
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_bytes(content)
    return f


class TestDownloadFile:
    def test_normal_download(self, client, session_dir):
        _create_file(session_dir, "test.txt", b"hello world")

        resp = client.get("/api/core/download/file", params={"path": "test.txt"})
        assert resp.status_code == 200
        assert resp.content == b"hello world"
        assert "text/plain" in resp.headers.get("content-type", "")

    def test_custom_filename(self, client, session_dir):
        _create_file(session_dir, "test.txt", b"hello world")

        resp = client.get(
            "/api/core/download/file",
            params={"path": "test.txt", "filename": "custom.txt"},
        )
        assert resp.status_code == 200
        assert 'filename="custom.txt"' in resp.headers.get("content-disposition", "")

    def test_file_not_found(self, client, session_dir):
        resp = client.get("/api/core/download/file", params={"path": "nonexistent.txt"})
        assert resp.status_code == 404

    def test_path_traversal_attack(self, client, session_dir):
        _create_file(session_dir, "safe.txt", b"secret")

        resp = client.get(
            "/api/core/download/file",
            params={"path": "../../etc/passwd"},
        )
        assert resp.status_code == 400

    def test_range_request(self, client, session_dir):
        content = b"0123456789abcdef"
        _create_file(session_dir, "ranged.txt", content)

        resp = client.get(
            "/api/core/download/file",
            params={"path": "ranged.txt"},
            headers={"Range": "bytes=0-9"},
        )
        assert resp.status_code == 206
        assert resp.content == b"0123456789"
        assert "content-range" in resp.headers
        assert resp.headers["content-range"].startswith("bytes 0-9/")

    def test_range_tail(self, client, session_dir):
        content = b"0123456789abcdef"
        _create_file(session_dir, "ranged_tail.txt", content)

        resp = client.get(
            "/api/core/download/file",
            params={"path": "ranged_tail.txt"},
            headers={"Range": "bytes=10-"},
        )
        assert resp.status_code == 206
        assert resp.content == b"abcdef"

    def test_empty_file(self, client, session_dir):
        _create_file(session_dir, "empty.txt", b"")

        resp = client.get("/api/core/download/file", params={"path": "empty.txt"})
        assert resp.status_code == 200
        assert resp.content == b""

    def test_subdirectory_file(self, client, session_dir):
        _create_file(session_dir, "subdir/nested.txt", b"nested content")

        resp = client.get(
            "/api/core/download/file", params={"path": "subdir/nested.txt"}
        )
        assert resp.status_code == 200
        assert resp.content == b"nested content"


class TestDownloadByName:
    def test_exact_match(self, client, session_dir):
        _create_file(session_dir, "report.pdf", b"pdf content")
        _create_file(session_dir, "report_v2.pdf", b"v2 content")

        resp = client.get(
            "/api/core/download/by-name",
            params={"name": "report.pdf", "exact": True},
        )
        assert resp.status_code == 200
        assert resp.content == b"pdf content"

    def test_fuzzy_match_unique(self, client, session_dir):
        _create_file(session_dir, "unique_report.docx", b"unique content")

        resp = client.get(
            "/api/core/download/by-name",
            params={"name": "unique_report", "exact": False},
        )
        assert resp.status_code == 200
        assert resp.content == b"unique content"

    def test_fuzzy_match_multiple(self, client, session_dir):
        _create_file(session_dir, "report_v1.pdf", b"v1")
        _create_file(session_dir, "report_v2.pdf", b"v2")

        resp = client.get(
            "/api/core/download/by-name",
            params={"name": "report", "exact": False},
        )
        assert resp.status_code == 300
        data = resp.json()
        assert "files" in data
        assert len(data["files"]) == 2

    def test_no_match(self, client, session_dir):
        _create_file(session_dir, "other.txt", b"other")

        resp = client.get(
            "/api/core/download/by-name",
            params={"name": "nonexistent", "exact": False},
        )
        assert resp.status_code == 404

    def test_exact_no_match(self, client, session_dir):
        _create_file(session_dir, "report_v1.pdf", b"v1")

        resp = client.get(
            "/api/core/download/by-name",
            params={"name": "report_v2.pdf", "exact": True},
        )
        assert resp.status_code == 404


class TestBatchDownload:
    def test_normal_batch(self, client, session_dir):
        _create_file(session_dir, "a.txt", b"aaa")
        _create_file(session_dir, "b.txt", b"bbb")

        resp = client.post(
            "/api/core/download/batch",
            json={"paths": ["a.txt", "b.txt"]},
        )
        assert resp.status_code == 200
        assert resp.headers.get("content-type") == "application/zip"

        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        names = zf.namelist()
        assert "a.txt" in names
        assert "b.txt" in names
        assert zf.read("a.txt") == b"aaa"
        assert zf.read("b.txt") == b"bbb"

    def test_custom_zip_filename(self, client, session_dir):
        _create_file(session_dir, "a.txt", b"aaa")

        resp = client.post(
            "/api/core/download/batch",
            json={"paths": ["a.txt"], "zip_filename": "custom.zip"},
        )
        assert resp.status_code == 200
        assert 'filename="custom.zip"' in resp.headers.get("content-disposition", "")

    def test_partial_not_found(self, client, session_dir):
        _create_file(session_dir, "a.txt", b"aaa")

        resp = client.post(
            "/api/core/download/batch",
            json={"paths": ["a.txt", "missing.txt"]},
        )
        assert resp.status_code == 404

    def test_empty_paths(self, client, session_dir):
        resp = client.post(
            "/api/core/download/batch",
            json={"paths": []},
        )
        assert resp.status_code == 422

    def test_single_file_batch(self, client, session_dir):
        _create_file(session_dir, "single.txt", b"single content")

        resp = client.post(
            "/api/core/download/batch",
            json={"paths": ["single.txt"]},
        )
        assert resp.status_code == 200
        zf = zipfile.ZipFile(io.BytesIO(resp.content))
        assert len(zf.namelist()) == 1
        assert zf.read("single.txt") == b"single content"


class TestListDownloadableFiles:
    def test_list_root(self, client, session_dir):
        _create_file(session_dir, "a.txt", b"a")
        _create_file(session_dir, "b.txt", b"bb")

        resp = client.get("/api/core/download/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2
        assert len(data["files"]) == 2

    def test_list_subdir(self, client, session_dir):
        _create_file(session_dir, "root.txt", b"root")
        _create_file(session_dir, "sub/nested.txt", b"nested")

        resp = client.get("/api/core/download/list", params={"subdir": "sub"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 1
        assert data["files"][0]["name"] == "nested.txt"

    def test_list_recursive(self, client, session_dir):
        _create_file(session_dir, "root.txt", b"root")
        _create_file(session_dir, "sub/nested.txt", b"nested")

        resp = client.get("/api/core/download/list", params={"recursive": True})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 2

    def test_list_empty_directory(self, client, session_dir):
        resp = client.get("/api/core/download/list")
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["files"] == []

    def test_list_nonexistent_subdir(self, client, session_dir):
        resp = client.get("/api/core/download/list", params={"subdir": "nonexistent"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["count"] == 0
        assert data["files"] == []
