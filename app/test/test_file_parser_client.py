#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FileParserClient 单元测试模块

本模块提供 FileParserClient 类的全面单元测试，覆盖所有核心功能：
- 初始化和参数配置
- 请求参数构建
- 文件上传和解析
- 状态轮询
- 结果写入

Date: 2026/05/02
Author: 张镒谱
"""
import json
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from requests import RequestException

from app.shared.utils.files.file_parser_client import FileParserClient


class TestFileParserClientInit:
    """测试 FileParserClient 初始化"""

    def test_init_default_values(self):
        """测试默认参数初始化"""
        client = FileParserClient()
        
        assert client.max_retries == 60
        assert client.poll_interval == 2.0
        assert client.timeout == 300
        assert "return_content_list" in client.default_params
        assert client.default_params["return_content_list"] == True

    def test_init_custom_values(self):
        """测试自定义参数初始化"""
        client = FileParserClient(
            server_url="http://custom-server:8080",
            max_retries=30,
            poll_interval=1.0,
            timeout=600
        )
        
        assert client.max_retries == 30
        assert client.poll_interval == 1.0
        assert client.timeout == 600
        assert client.default_params["server_url"] == "http://custom-server:8080"

    def test_init_override_params(self):
        """测试参数覆盖功能"""
        client = FileParserClient(
            return_middle_json=True,
            table_enable=False
        )
        
        assert client.default_params["return_middle_json"] == True
        assert client.default_params["table_enable"] == False
        assert client.default_params["return_content_list"] == True


class TestBuildRequestParams:
    """测试 _build_request_params 方法"""

    def test_build_params_json_format(self):
        """测试 JSON 格式参数构建"""
        client = FileParserClient()
        
        params = client._build_request_params("json")
        
        assert params["return_content_list"] == True
        assert params["return_md"] == False

    def test_build_params_md_format(self):
        """测试 MD 格式参数构建"""
        client = FileParserClient()
        
        params = client._build_request_params("md")
        
        assert params["return_md"] == True
        assert params["return_content_list"] == False

    def test_build_params_invalid_format(self):
        """测试无效格式参数"""
        client = FileParserClient()
        
        with pytest.raises(ValueError) as exc_info:
            client._build_request_params("xml")
        
        assert "不支持的输出格式" in str(exc_info.value)

    def test_build_params_preserves_other_params(self):
        """测试保留其他参数"""
        client = FileParserClient(
            backend="custom-backend",
            lang_list="en"
        )
        
        params = client._build_request_params("json")
        
        assert params["backend"] == "custom-backend"
        assert params["lang_list"] == "en"
        assert params["parse_method"] == "auto"


class TestEnsureOutputDir:
    """测试 _ensure_output_dir 方法"""

    def test_ensure_output_dir_creates_new(self, tmp_path):
        """测试创建新目录"""
        client = FileParserClient()
        output_dir = tmp_path / "new_output_dir"
        
        result = client._ensure_output_dir(str(output_dir))
        
        assert output_dir.exists()
        assert result == output_dir

    def test_ensure_output_dir_existing(self, tmp_path):
        """测试已存在目录"""
        client = FileParserClient()
        output_dir = tmp_path / "existing_dir"
        output_dir.mkdir()
        
        result = client._ensure_output_dir(str(output_dir))
        
        assert output_dir.exists()
        assert result == output_dir

    def test_ensure_output_dir_nested(self, tmp_path):
        """测试创建嵌套目录"""
        client = FileParserClient()
        output_dir = tmp_path / "parent" / "child" / "grandchild"
        
        result = client._ensure_output_dir(str(output_dir))
        
        assert output_dir.exists()
        assert result == output_dir


class TestWriteJsonFile:
    """测试 _write_json_file 方法"""

    def test_write_json_file_list(self, tmp_path):
        """测试写入 JSON 列表"""
        client = FileParserClient()
        file_path = tmp_path / "test.json"
        content = [{"key": "value"}, {"key2": "value2"}]
        
        client._write_json_file(file_path, content)
        
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == content

    def test_write_json_file_dict(self, tmp_path):
        """测试写入 JSON 对象"""
        client = FileParserClient()
        file_path = tmp_path / "test.json"
        content = {"key": "value", "number": 123}
        
        client._write_json_file(file_path, content)
        
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == content

    def test_write_json_file_unicode(self, tmp_path):
        """测试写入 Unicode 内容"""
        client = FileParserClient()
        file_path = tmp_path / "test.json"
        content = {"中文": "测试", "emoji": "😀"}
        
        client._write_json_file(file_path, content)
        
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded == content


class TestWriteMarkdownFile:
    """测试 _write_markdown_file 方法"""

    def test_write_markdown_file(self, tmp_path):
        """测试写入 Markdown 文件"""
        client = FileParserClient()
        file_path = tmp_path / "test.md"
        content = "# 标题\n\n这是内容。"
        
        client._write_markdown_file(file_path, content)
        
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = f.read()
        assert loaded == content

    def test_write_markdown_file_unicode(self, tmp_path):
        """测试写入 Unicode Markdown"""
        client = FileParserClient()
        file_path = tmp_path / "test.md"
        content = "# 中文标题\n\n这是中文内容。\n\n- 列表项1\n- 列表项2"
        
        client._write_markdown_file(file_path, content)
        
        assert file_path.exists()
        with open(file_path, "r", encoding="utf-8") as f:
            loaded = f.read()
        assert loaded == content


class TestGetMimeType:
    """测试 _get_mime_type 方法"""

    def test_get_mime_type_pdf(self):
        """测试 PDF MIME 类型"""
        client = FileParserClient()
        
        assert client._get_mime_type(".pdf") == "application/pdf"

    def test_get_mime_type_docx(self):
        """测试 DOCX MIME 类型"""
        client = FileParserClient()
        
        assert client._get_mime_type(".docx") == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"

    def test_get_mime_type_txt(self):
        """测试 TXT MIME 类型"""
        client = FileParserClient()
        
        assert client._get_mime_type(".txt") == "text/plain"

    def test_get_mime_type_unknown(self):
        """测试未知类型 MIME 类型"""
        client = FileParserClient()
        
        assert client._get_mime_type(".xyz") == "application/octet-stream"


class TestMakeRequest:
    """测试 _make_request 方法"""

    def test_make_request_get(self):
        """测试 GET 请求"""
        client = FileParserClient()
        
        with patch("app.shared.utils.files.file_parser_client.requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response
            
            result = client._make_request("GET", "http://example.com/test")
            
            mock_request.assert_called_once_with("GET", "http://example.com/test")
            assert result == mock_response

    def test_make_request_with_timeout(self):
        """测试带超时的请求"""
        client = FileParserClient(timeout=60)
        
        with patch("app.shared.utils.files.file_parser_client.requests.request") as mock_request:
            mock_response = Mock()
            mock_response.status_code = 200
            mock_request.return_value = mock_response
            
            result = client._make_request("POST", "http://example.com/upload", timeout=60)
            
            mock_request.assert_called_once()
            assert result == mock_response


class TestSendParseRequest:
    """测试 _send_parse_request 方法"""

    def test_send_parse_request_success(self, tmp_path):
        """测试成功发送解析请求"""
        client = FileParserClient()
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "task_id": "test-task-id",
            "status_url": "http://example.com/status/test-task-id",
            "result_url": "http://example.com/result/test-task-id"
        }
        
        with patch.object(client, "_make_request", return_value=mock_response):
            result = client._send_parse_request(
                "http://example.com/api/parse",
                str(test_file),
                {"return_content_list": True}
            )
            
            assert result["task_id"] == "test-task-id"

    def test_send_parse_request_failure(self, tmp_path):
        """测试请求失败"""
        client = FileParserClient()
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.text = "Internal Server Error"
        
        with patch.object(client, "_make_request", return_value=mock_response):
            with pytest.raises(RequestException) as exc_info:
                client._send_parse_request(
                    "http://example.com/api/parse",
                    str(test_file),
                    {}
                )
            
            assert "请求失败" in str(exc_info.value)

    def test_send_parse_request_no_task_id(self, tmp_path):
        """测试响应中没有 task_id"""
        client = FileParserClient()
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"error": "some error"}
        
        with patch.object(client, "_make_request", return_value=mock_response):
            with pytest.raises(ValueError) as exc_info:
                client._send_parse_request(
                    "http://example.com/api/parse",
                    str(test_file),
                    {}
                )
            
            assert "任务创建失败" in str(exc_info.value)


class TestPollTaskStatus:
    """测试 _poll_task_status 方法"""

    def test_poll_task_status_completed(self):
        """测试任务完成"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "completed",
            "task_id": "test-task-id"
        }
        
        with patch.object(client, "_make_request", return_value=mock_response):
            result = client._poll_task_status("http://example.com/status/test-task-id")
            
            assert result["status"] == "completed"

    def test_poll_task_status_failed(self):
        """测试任务失败"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "status": "failed",
            "error": "Processing error"
        }
        
        with patch.object(client, "_make_request", return_value=mock_response):
            with pytest.raises(RuntimeError) as exc_info:
                client._poll_task_status("http://example.com/status/test-task-id")
            
            assert "任务执行失败" in str(exc_info.value)

    def test_poll_task_status_pending(self):
        """测试任务等待中"""
        client = FileParserClient(max_retries=3, poll_interval=0.05)
        
        mock_completed_response = Mock()
        mock_completed_response.status_code = 200
        mock_completed_response.json.return_value = {"status": "completed"}
        
        mock_pending_response = Mock()
        mock_pending_response.status_code = 200
        mock_pending_response.json.return_value = {"status": "pending"}
        
        with patch.object(client, "_make_request") as mock_request:
            mock_request.side_effect = [mock_pending_response, mock_pending_response, mock_completed_response]
            
            result = client._poll_task_status("http://example.com/status/test-task-id")
            
            assert result["status"] == "completed"
            assert mock_request.call_count == 3

    def test_poll_task_status_timeout(self):
        """测试轮询超时"""
        client = FileParserClient(max_retries=3, poll_interval=0.01)
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {"status": "pending"}
        
        with patch.object(client, "_make_request", return_value=mock_response):
            with pytest.raises(TimeoutError) as exc_info:
                client._poll_task_status("http://example.com/status/test-task-id")
            
            assert "轮询超时" in str(exc_info.value)


class TestFetchResult:
    """测试 _fetch_result 方法"""

    def test_fetch_result_success(self):
        """测试成功获取结果"""
        client = FileParserClient()
        
        mock_response = Mock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            "results": {
                "test.pdf": {
                    "content_list": ["content1", "content2"]
                }
            }
        }
        
        with patch.object(client, "_make_request", return_value=mock_response):
            result = client._fetch_result("http://example.com/result/test-task-id")
            
            assert "results" in result
            assert "test.pdf" in result["results"]

    def test_fetch_result_failure(self):
        """测试获取结果失败"""
        client = FileParserClient()
        
        mock_response = Mock()
        mock_response.status_code = 500
        
        with patch.object(client, "_make_request", return_value=mock_response):
            with pytest.raises(RequestException) as exc_info:
                client._fetch_result("http://example.com/result/test-task-id")
            
            assert "获取结果失败" in str(exc_info.value)


class TestParse:
    """测试 parse 主方法"""

    def test_parse_file_not_found(self, tmp_path):
        """测试文件不存在"""
        client = FileParserClient()
        output_dir = tmp_path / "output"
        
        with pytest.raises(FileNotFoundError) as exc_info:
            client.parse(
                str(tmp_path / "non_existent.pdf"),
                str(output_dir),
                "http://example.com/api/parse",
                "json"
            )
        
        assert "文件不存在" in str(exc_info.value)

    def test_parse_json_success(self, tmp_path):
        """测试 JSON 解析成功"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        output_dir = tmp_path / "output"
        
        mock_task_response = Mock()
        mock_task_response.status_code = 200
        mock_task_response.json.return_value = {
            "task_id": "test-task-id",
            "status_url": "http://example.com/status/test-task-id",
            "result_url": "http://example.com/result/test-task-id"
        }
        
        mock_status_response = Mock()
        mock_status_response.status_code = 200
        mock_status_response.json.return_value = {"status": "completed"}
        
        mock_result_response = Mock()
        mock_result_response.status_code = 200
        mock_result_response.json.return_value = {
            "results": {
                "test.docx": {
                    "content_list": ["paragraph 1", "paragraph 2"]
                }
            }
        }
        
        with patch.object(client, "_send_parse_request", return_value=mock_task_response.json.return_value), \
             patch.object(client, "_poll_task_status", return_value=mock_status_response.json.return_value), \
             patch.object(client, "_fetch_result", return_value=mock_result_response.json.return_value):
            
            result = client.parse(str(test_file), str(output_dir), "http://example.com/api/parse", "json")
            
            assert result == str(output_dir / "test.json")
            assert (output_dir / "test.json").exists()

    def test_parse_md_success(self, tmp_path):
        """测试 MD 解析成功"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        output_dir = tmp_path / "output"
        
        mock_task_response = Mock()
        mock_task_response.status_code = 200
        mock_task_response.json.return_value = {
            "task_id": "test-task-id",
            "status_url": "http://example.com/status/test-task-id",
            "result_url": "http://example.com/result/test-task-id"
        }
        
        mock_status_response = Mock()
        mock_status_response.status_code = 200
        mock_status_response.json.return_value = {"status": "completed"}
        
        mock_result_response = Mock()
        mock_result_response.status_code = 200
        mock_result_response.json.return_value = {
            "results": {
                "test.docx": {
                    "md_content": "# Title\n\nContent here."
                }
            }
        }
        
        with patch.object(client, "_send_parse_request", return_value=mock_task_response.json.return_value), \
             patch.object(client, "_poll_task_status", return_value=mock_status_response.json.return_value), \
             patch.object(client, "_fetch_result", return_value=mock_result_response.json.return_value):
            
            result = client.parse(str(test_file), str(output_dir), "http://example.com/api/parse", "md")
            
            assert result == str(output_dir / "test.md")
            assert (output_dir / "test.md").exists()
            with open(output_dir / "test.md", "r", encoding="utf-8") as f:
                assert f.read() == "# Title\n\nContent here."

    def test_parse_invalid_format(self, tmp_path):
        """测试无效输出格式"""
        client = FileParserClient()
        
        test_file = tmp_path / "test.docx"
        test_file.write_bytes(b"fake content")
        output_dir = tmp_path / "output"
        
        with pytest.raises(ValueError) as exc_info:
            client.parse(str(test_file), str(output_dir), "http://example.com/api/parse", "xml")
        
        assert "不支持的输出格式" in str(exc_info.value)


class TestIntegration:
    """集成测试"""

    def test_full_workflow_json(self, tmp_path):
        """测试完整工作流程 - JSON 格式"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        test_file = tmp_path / "机票说明.docx"
        test_file.write_bytes(b"fake docx content")
        output_dir = tmp_path / "parsed_output"
        
        mock_task_result = {
            "task_id": "task-123",
            "status_url": "http://localhost:8000/tasks/task-123",
            "result_url": "http://localhost:8000/tasks/task-123/result"
        }
        
        mock_status_result = {"status": "completed"}
        
        mock_parse_result = {
            "results": {
                "机票说明.docx": {
                    "content_list": [
                        {"text": "第一条：订票信息"},
                        {"text": "第二条：退票规定"}
                    ]
                }
            }
        }
        
        with patch.object(client, "_send_parse_request", return_value=mock_task_result), \
             patch.object(client, "_poll_task_status", return_value=mock_status_result), \
             patch.object(client, "_fetch_result", return_value=mock_parse_result):
            
            result_path = client.parse(
                str(test_file),
                str(output_dir),
                "http://localhost:8000/file_parse",
                "json"
            )
            
            assert Path(result_path).exists()
            assert result_path.endswith(".json")
            
            with open(result_path, "r", encoding="utf-8") as f:
                content = json.load(f)
            assert isinstance(content, list)
            assert len(content) == 2

    def test_full_workflow_md(self, tmp_path):
        """测试完整工作流程 - MD 格式"""
        client = FileParserClient(max_retries=3, poll_interval=0.1)
        
        test_file = tmp_path / "机票说明.docx"
        test_file.write_bytes(b"fake docx content")
        output_dir = tmp_path / "parsed_output"
        
        mock_task_result = {
            "task_id": "task-456",
            "status_url": "http://localhost:8000/tasks/task-456",
            "result_url": "http://localhost:8000/tasks/task-456/result"
        }
        
        mock_status_result = {"status": "completed"}
        
        mock_parse_result = {
            "results": {
                "机票说明.docx": {
                    "md_content": "# 机票说明\n\n## 第一条 订票信息\n\n内容...\n\n## 第二条 退票规定\n\n内容..."
                }
            }
        }
        
        with patch.object(client, "_send_parse_request", return_value=mock_task_result), \
             patch.object(client, "_poll_task_status", return_value=mock_status_result), \
             patch.object(client, "_fetch_result", return_value=mock_parse_result):
            
            result_path = client.parse(
                str(test_file),
                str(output_dir),
                "http://localhost:8000/file_parse",
                "md"
            )
            
            assert Path(result_path).exists()
            assert result_path.endswith(".md")
            
            with open(result_path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "# 机票说明" in content
            assert "## 第一条 订票信息" in content


if __name__ == "__main__":
    pytest.main([__file__, "-v"])