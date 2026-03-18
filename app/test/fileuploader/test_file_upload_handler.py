#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FileUploadHandler 单元测试模块

本模块提供 FileUploadHandler 类的全面单元测试，覆盖所有核心功能：
- 文件验证
- 上传处理
- 错误处理
- 响应生成

测试覆盖率目标：90%+

================================================================================
Mock 技术说明 (Mocking Technology)
================================================================================

本测试模块使用 unittest.mock 库来实现 Mock 技术，用于模拟依赖组件以实现
单元测试的隔离。以下是本文件中使用的核心 Mock 技术：

1. Mock 类 (Mock 类)
   - 用于创建任意对象的替代品，可动态设置属性和方法
   - 示例: mock_store = Mock() 创建一个模拟的存储对象

2. Mock.return_value (设置返回值)
   - 为 Mock 对象的方法设置返回值，模拟真实方法的返回值
   - 示例: mock_store.get.return_value = None 模拟 get 方法返回 None

3. Mock.side_effect (设置副作用/异常)
   - 设置方法的副作用，可用于抛出异常或返回动态计算的值
   - 示例: mock_store.get.side_effect = Exception("Error") 模拟抛出异常

4. patch 装饰器/上下文管理器
   - 临时替换模块中的函数或方法，常用于模拟外部依赖（如 pdf_to_images_parallel）
   - 示例: @patch('module.function') 或 with patch('module.function') as mock:

5. tmp_path fixture (pytest 内置)
   - pytest 提供的临时目录 fixture，用于创建测试用的临时文件
   - 测试结束后自动清理，无需手动管理

主要模拟的依赖组件：
- store (存储服务): 使用 Mock 模拟，用于测试文件信息存储逻辑
- file_transfer (文件传输): 使用 Mock 模拟，用于获取文件路径
- pdf_to_images_parallel (PDF转图片函数): 使用 patch 模拟，避免真实PDF转换

测试原则：
- 每个测试方法应只测试一个功能点（单一职责）
- 测试应具有确定性（相同的输入产生相同的输出）
- 测试之间应相互独立，不依赖执行顺序

Date: 2026/3/17
Author: 张镒谱
"""
import base64
import json
import pytest
import asyncio
from pathlib import Path
from unittest.mock import Mock, MagicMock, AsyncMock, patch, mock_open
from typing import Dict, Any, List

from app.utils.files.file_upload_handler import FileUploadHandler


class TestFileUploadHandlerInit:
    """测试 FileUploadHandler 初始化"""

    def test_init_default_upload_dir(self):
        """测试默认上传目录初始化"""
        handler = FileUploadHandler()
        assert handler.upload_dir is not None
        assert handler.file_transfer is not None

    def test_init_custom_upload_dir(self, tmp_path):
        """测试自定义上传目录初始化"""
        custom_dir = str(tmp_path / "custom_upload")
        handler = FileUploadHandler(upload_dir=custom_dir)
        assert handler.file_transfer is not None


class TestGetNamespace:
    """测试 _get_namespace 方法"""

    def test_get_namespace_basic(self):
        """测试基本 namespace 生成"""
        handler = FileUploadHandler()
        store_id = "store_123"
        session_id = "session_456"
        
        result = handler._get_namespace(store_id, session_id)
        
        assert result == (store_id, session_id)
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_get_namespace_with_empty_strings(self):
        """测试空字符串参数"""
        handler = FileUploadHandler()
        
        result = handler._get_namespace("", "")
        
        assert result == ("", "")

    def test_get_namespace_with_special_characters(self):
        """测试特殊字符参数"""
        handler = FileUploadHandler()
        store_id = "store-123_test"
        session_id = "session@456#789"
        
        result = handler._get_namespace(store_id, session_id)
        
        assert result == (store_id, session_id)


class TestGroupImages:
    """测试 _group_images 方法"""

    def test_group_images_empty_list(self):
        """测试空列表"""
        handler = FileUploadHandler()
        
        result = handler._group_images([])
        
        assert result == []

    def test_group_images_single_image(self):
        """测试单张图片"""
        handler = FileUploadHandler()
        image_ids = ["img_1"]
        
        result = handler._group_images(image_ids)
        
        assert result == [["img_1"]]

    def test_group_images_two_images(self):
        """测试两张图片"""
        handler = FileUploadHandler()
        image_ids = ["img_1", "img_2"]
        
        result = handler._group_images(image_ids)
        
        assert result == [["img_1", "img_2"]]

    def test_group_images_three_images(self):
        """测试三张图片（刚好一组）"""
        handler = FileUploadHandler()
        image_ids = ["img_1", "img_2", "img_3"]
        
        result = handler._group_images(image_ids)
        
        assert result == [["img_1", "img_2", "img_3"]]

    def test_group_images_four_images(self):
        """测试四张图片（滑动窗口）"""
        handler = FileUploadHandler()
        image_ids = ["img_1", "img_2", "img_3", "img_4"]
        
        result = handler._group_images(image_ids)
        
        assert result == [["img_1", "img_2", "img_3"], ["img_2", "img_3", "img_4"]]

    def test_group_images_five_images(self):
        """测试五张图片"""
        handler = FileUploadHandler()
        image_ids = ["img_1", "img_2", "img_3", "img_4", "img_5"]
        
        result = handler._group_images(image_ids)
        
        assert result == [
            ["img_1", "img_2", "img_3"],
            ["img_2", "img_3", "img_4"],
            ["img_3", "img_4", "img_5"]
        ]

    def test_group_images_many_images(self):
        """测试大量图片"""
        handler = FileUploadHandler()
        image_ids = [f"img_{i}" for i in range(1, 11)]
        
        result = handler._group_images(image_ids)
        
        assert len(result) == 8
        assert result[0] == ["img_1", "img_2", "img_3"]
        assert result[-1] == ["img_8", "img_9", "img_10"]


class TestReadFileAsBase64:
    """测试 _read_file_as_base64 方法"""

    @pytest.mark.asyncio
    async def test_read_file_as_base64_success(self, tmp_path):
        """测试成功读取文件并转换为 base64"""
        handler = FileUploadHandler()
        test_content = b"Hello, World!"
        test_file = tmp_path / "test.txt"
        test_file.write_bytes(test_content)
        
        result = await handler._read_file_as_base64(test_file)
        
        expected = base64.b64encode(test_content).decode("utf-8")
        assert result == expected

    @pytest.mark.asyncio
    async def test_read_file_as_base64_empty_file(self, tmp_path):
        """测试空文件"""
        handler = FileUploadHandler()
        test_file = tmp_path / "empty.txt"
        test_file.write_bytes(b"")
        
        result = await handler._read_file_as_base64(test_file)
        
        assert result == ""

    @pytest.mark.asyncio
    async def test_read_file_as_base64_binary_file(self, tmp_path):
        """测试二进制文件"""
        handler = FileUploadHandler()
        test_content = bytes(range(256))
        test_file = tmp_path / "binary.bin"
        test_file.write_bytes(test_content)
        
        result = await handler._read_file_as_base64(test_file)
        
        expected = base64.b64encode(test_content).decode("utf-8")
        assert result == expected

    @pytest.mark.asyncio
    async def test_read_file_as_base64_large_file(self, tmp_path):
        """测试大文件"""
        handler = FileUploadHandler()
        test_content = b"x" * (1024 * 1024)
        test_file = tmp_path / "large.bin"
        test_file.write_bytes(test_content)
        
        result = await handler._read_file_as_base64(test_file)
        
        expected = base64.b64encode(test_content).decode("utf-8")
        assert result == expected

    @pytest.mark.asyncio
    async def test_read_file_as_base64_file_not_found(self):
        """测试文件不存在"""
        handler = FileUploadHandler()
        non_existent_file = Path("/non/existent/file.txt")
        
        with pytest.raises(Exception):
            await handler._read_file_as_base64(non_existent_file)


class TestStoreFileInfo:
    """测试 _store_file_info 方法"""

    @pytest.mark.asyncio
    async def test_store_file_info_new_store(self):
        """测试新存储（无历史数据）"""
        handler = FileUploadHandler()
        mock_store = Mock()
        mock_store.get.return_value = None
        
        namespace = ("store_123", "session_456")
        file_id = "file_001"
        file_path = "/path/to/file.pdf"
        
        await handler._store_file_info(mock_store, namespace, file_id, file_path)
        
        mock_store.get.assert_called_once_with(namespace, "file_id")
        mock_store.put.assert_called_once()
        call_args = mock_store.put.call_args
        assert call_args[0][0] == namespace
        assert call_args[0][1] == "file_id"
        assert call_args[0][2] == {file_id: file_path}

    @pytest.mark.asyncio
    async def test_store_file_info_append_to_existing(self):
        """测试追加到已有数据"""
        handler = FileUploadHandler()
        mock_store = Mock()
        existing_data = {"file_001": "/path/to/file1.pdf"}
        mock_existing = Mock()
        mock_existing.value = existing_data
        mock_store.get.return_value = mock_existing
        
        namespace = ("store_123", "session_456")
        file_id = "file_002"
        file_path = "/path/to/file2.pdf"
        
        await handler._store_file_info(mock_store, namespace, file_id, file_path)
        
        expected_data = {"file_001": "/path/to/file1.pdf", "file_002": "/path/to/file2.pdf"}
        mock_store.put.assert_called_once_with(namespace, "file_id", expected_data)

    @pytest.mark.asyncio
    async def test_store_file_info_with_string_data(self):
        """测试已有数据为字符串格式（JSON）"""
        handler = FileUploadHandler()
        mock_store = Mock()
        existing_data = {"file_001": "/path/to/file1.pdf"}
        mock_existing = Mock()
        mock_existing.value = json.dumps(existing_data)
        mock_store.get.return_value = mock_existing
        
        namespace = ("store_123", "session_456")
        file_id = "file_002"
        file_path = "/path/to/file2.pdf"
        
        await handler._store_file_info(mock_store, namespace, file_id, file_path)
        
        expected_data = {"file_001": "/path/to/file1.pdf", "file_002": "/path/to/file2.pdf"}
        mock_store.put.assert_called_once_with(namespace, "file_id", expected_data)

    @pytest.mark.asyncio
    async def test_store_file_info_empty_existing_value(self):
        """测试已有数据为空值"""
        handler = FileUploadHandler()
        mock_store = Mock()
        mock_existing = Mock()
        mock_existing.value = None
        mock_store.get.return_value = mock_existing
        
        namespace = ("store_123", "session_456")
        file_id = "file_001"
        file_path = "/path/to/file.pdf"
        
        await handler._store_file_info(mock_store, namespace, file_id, file_path)
        
        mock_store.put.assert_called_once_with(namespace, "file_id", {file_id: file_path})


class TestStoreImageInfo:
    """测试 _store_image_info 方法"""

    @pytest.mark.asyncio
    async def test_store_image_info_basic(self):
        """测试基本图片信息存储"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        image_data = {
            "img_001": "base64_data_1",
            "img_002": "base64_data_2"
        }
        
        await handler._store_image_info(mock_store, namespace, image_data)
        
        mock_store.put.assert_called_once_with(namespace, "image_paths", image_data)

    @pytest.mark.asyncio
    async def test_store_image_info_empty_data(self):
        """测试空图片数据"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        image_data = {}
        
        await handler._store_image_info(mock_store, namespace, image_data)
        
        mock_store.put.assert_called_once_with(namespace, "image_paths", {})

    @pytest.mark.asyncio
    async def test_store_image_info_overwrites_existing(self):
        """测试覆盖已有数据"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        image_data = {"img_new": "new_base64_data"}
        
        await handler._store_image_info(mock_store, namespace, image_data)
        
        mock_store.put.assert_called_once()


class TestProcessDocumentFiles:
    """测试 _process_document_files 方法"""

    @pytest.mark.asyncio
    async def test_process_document_files_success(self, tmp_path):
        """测试成功处理文档文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_store.get.return_value = None
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        file_content = b"test document content"
        file_path = tmp_path / session_id / "file_001.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(file_content)
        
        doc_files = [{"id": "file_001", "filename": "document.txt"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = file_path
        handler.file_transfer = mock_file_transfer
        
        result = await handler._process_document_files(
            mock_store, namespace, doc_files, session_id
        )
        
        assert result == ["file_001"]
        mock_store.put.assert_called()

    @pytest.mark.asyncio
    async def test_process_document_files_multiple_files(self, tmp_path):
        """测试处理多个文档文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_existing = Mock()
        mock_existing.value = None
        mock_store.get.return_value = mock_existing
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        doc_files = [
            {"id": "file_001", "filename": "doc1.txt"},
            {"id": "file_002", "filename": "doc2.txt"},
            {"id": "file_003", "filename": "doc3.txt"}
        ]
        
        for file_info in doc_files:
            file_path = tmp_path / session_id / f"{file_info['id']}.txt"
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_bytes(b"content")
        
        def get_file_path_side_effect(file_id, session):
            return tmp_path / session / f"{file_id}.txt"
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.side_effect = get_file_path_side_effect
        handler.file_transfer = mock_file_transfer
        
        result = await handler._process_document_files(
            mock_store, namespace, doc_files, session_id
        )
        
        assert len(result) == 3
        assert "file_001" in result
        assert "file_002" in result
        assert "file_003" in result

    @pytest.mark.asyncio
    async def test_process_document_files_empty_list(self):
        """测试空文件列表"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        
        result = await handler._process_document_files(
            mock_store, namespace, [], "session_456"
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_process_document_files_error_handling(self):
        """测试错误处理"""
        handler = FileUploadHandler()
        mock_store = Mock()
        mock_store.get.side_effect = Exception("Store error")
        
        namespace = ("store_123", "session_456")
        doc_files = [{"id": "file_001", "filename": "document.txt"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = Path("/some/path")
        handler.file_transfer = mock_file_transfer
        
        with pytest.raises(Exception) as exc_info:
            await handler._process_document_files(
                mock_store, namespace, doc_files, "session_456"
            )
        
        assert "文档文件处理失败" in str(exc_info.value)


class TestProcessScanFiles:
    """测试 _process_scan_files 方法"""

    @pytest.mark.asyncio
    async def test_process_scan_files_success(self, tmp_path):
        """测试成功处理扫描件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        pdf_path = tmp_path / session_id / "scan_001.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf content")
        
        scan_files = [{"id": "scan_001", "filename": "scan.pdf"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = pdf_path
        handler.file_transfer = mock_file_transfer
        
        with patch('app.test.fileuploader.file_upload_handler.pdf_to_images_parallel') as mock_pdf_to_img, \
             patch('app.test.fileuploader.file_upload_handler.uuid.uuid4') as mock_uuid:
            
            mock_uuid.return_value = "test-uuid-1234"
            
            scan_output_dir = tmp_path / session_id / "scan_test-uuid-1234"
            scan_output_dir.mkdir(parents=True, exist_ok=True)
            
            img1 = scan_output_dir / "page_000.jpg"
            img2 = scan_output_dir / "page_001.jpg"
            img1.write_bytes(b"fake image 1")
            img2.write_bytes(b"fake image 2")
            
            mock_pdf_to_img.return_value = None
            
            result = await handler._process_scan_files(
                mock_store, namespace, scan_files, session_id
            )
        
        assert len(result) == 2
        mock_store.put.assert_called()

    @pytest.mark.asyncio
    async def test_process_scan_files_empty_list(self):
        """测试空扫描件列表"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        
        result = await handler._process_scan_files(
            mock_store, namespace, [], "session_456"
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_process_scan_files_error_handling(self, tmp_path):
        """测试扫描件处理错误"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        pdf_path = tmp_path / session_id / "scan_001.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"fake pdf")
        
        scan_files = [{"id": "scan_001", "filename": "scan.pdf"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = pdf_path
        handler.file_transfer = mock_file_transfer
        
        with patch('app.test.fileuploader.file_upload_handler.pdf_to_images_parallel') as mock_pdf_to_img:
            mock_pdf_to_img.side_effect = Exception("PDF conversion failed")
            
            with pytest.raises(Exception) as exc_info:
                await handler._process_scan_files(
                    mock_store, namespace, scan_files, session_id
                )
            
            assert "PDF扫描件处理失败" in str(exc_info.value)


class TestProcessImageFiles:
    """测试 _process_image_files 方法"""

    @pytest.mark.asyncio
    async def test_process_image_files_success(self, tmp_path):
        """测试成功处理图片文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        image_content = b"fake image content"
        img_path = tmp_path / session_id / "img_001.jpg"
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(image_content)
        
        img_files = [{"id": "img_001", "filename": "image.jpg"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = img_path
        handler.file_transfer = mock_file_transfer
        
        result = await handler._process_image_files(
            mock_store, namespace, img_files, session_id
        )
        
        assert len(result) == 1
        assert "img_001" in result
        mock_store.put.assert_called()

    @pytest.mark.asyncio
    async def test_process_image_files_multiple_images(self, tmp_path):
        """测试处理多个图片文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        namespace = handler._get_namespace("store_123", session_id)
        
        img_files = [
            {"id": "img_001", "filename": "image1.jpg"},
            {"id": "img_002", "filename": "image2.png"},
            {"id": "img_003", "filename": "image3.gif"}
        ]
        
        for file_info in img_files:
            img_path = tmp_path / session_id / f"{file_info['id']}.jpg"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(b"fake image")
        
        def get_file_path_side_effect(file_id, session):
            return tmp_path / session / f"{file_id}.jpg"
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.side_effect = get_file_path_side_effect
        handler.file_transfer = mock_file_transfer
        
        result = await handler._process_image_files(
            mock_store, namespace, img_files, session_id
        )
        
        assert len(result) == 3

    @pytest.mark.asyncio
    async def test_process_image_files_empty_list(self):
        """测试空图片列表"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        
        result = await handler._process_image_files(
            mock_store, namespace, [], "session_456"
        )
        
        assert result == []

    @pytest.mark.asyncio
    async def test_process_image_files_error_handling(self):
        """测试图片处理错误"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        namespace = ("store_123", "session_456")
        img_files = [{"id": "img_001", "filename": "image.jpg"}]
        
        mock_file_transfer = Mock()
        mock_file_transfer.get_file_path.return_value = Path("/non/existent/path.jpg")
        handler.file_transfer = mock_file_transfer
        
        with pytest.raises(Exception) as exc_info:
            await handler._process_image_files(
                mock_store, namespace, img_files, "session_456"
            )
        
        assert "图片文件处理失败" in str(exc_info.value)


class TestProcessFiles:
    """测试 process_files 主方法"""

    @pytest.mark.asyncio
    async def test_process_files_empty_list(self):
        """测试空文件列表"""
        handler = FileUploadHandler()
        mock_store = Mock()
        
        result = await handler.process_files(
            mock_store, "store_123", "session_456", []
        )
        
        assert result == {"doc": [], "img": []}

    @pytest.mark.asyncio
    async def test_process_files_document_only(self, tmp_path):
        """测试仅处理文档文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_store.get.return_value = None
        
        session_id = "session_123"
        
        mock_upload_file = Mock()
        mock_upload_file.filename = "document.txt"
        mock_upload_file.read = AsyncMock(return_value=b"test content")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "doc_001", "filename": "document", "file_type": "doc"}
        ])
        mock_file_transfer.get_file_path.return_value = tmp_path / session_id / "doc_001.txt"
        handler.file_transfer = mock_file_transfer
        
        file_path = tmp_path / session_id / "doc_001.txt"
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(b"test content")
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, [mock_upload_file]
        )
        
        assert "doc" in result
        assert len(result["doc"]) == 1

    @pytest.mark.asyncio
    async def test_process_files_image_only(self, tmp_path):
        """测试仅处理图片文件"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        
        mock_upload_file = Mock()
        mock_upload_file.filename = "image.jpg"
        mock_upload_file.read = AsyncMock(return_value=b"fake image")
        
        img_path = tmp_path / session_id / "img_001.jpg"
        img_path.parent.mkdir(parents=True, exist_ok=True)
        img_path.write_bytes(b"fake image")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "img_001", "filename": "image", "file_type": "img"}
        ])
        mock_file_transfer.get_file_path.return_value = img_path
        handler.file_transfer = mock_file_transfer
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, [mock_upload_file]
        )
        
        assert "img" in result
        assert len(result["img"]) == 1

    @pytest.mark.asyncio
    async def test_process_files_mixed_types(self, tmp_path):
        """测试混合类型文件处理"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_store.get.return_value = None
        
        session_id = "session_123"
        
        doc_path = tmp_path / session_id / "doc_001.txt"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_bytes(b"doc content")
        
        img_path = tmp_path / session_id / "img_001.jpg"
        img_path.write_bytes(b"fake image")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "doc_001", "filename": "document", "file_type": "doc"},
            {"id": "img_001", "filename": "image", "file_type": "img"}
        ])
        
        def get_file_path_side_effect(file_id, session):
            if file_id.startswith("doc"):
                return tmp_path / session / f"{file_id}.txt"
            return tmp_path / session / f"{file_id}.jpg"
        
        mock_file_transfer.get_file_path.side_effect = get_file_path_side_effect
        handler.file_transfer = mock_file_transfer
        
        mock_files = [Mock(filename="document.txt"), Mock(filename="image.jpg")]
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, mock_files
        )
        
        assert len(result["doc"]) == 1
        assert len(result["img"]) == 1

    @pytest.mark.asyncio
    async def test_process_files_upload_error(self):
        """测试文件上传错误"""
        handler = FileUploadHandler()
        
        mock_store = Mock()
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(side_effect=Exception("Upload failed"))
        handler.file_transfer = mock_file_transfer
        
        mock_file = Mock()
        mock_file.filename = "test.txt"
        
        with pytest.raises(Exception) as exc_info:
            await handler.process_files(
                mock_store, "store_123", "session_456", [mock_file]
            )
        
        assert "文件上传失败" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_files_document_processing_error(self, tmp_path):
        """测试文档处理错误"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_store.get.side_effect = Exception("Store error")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "doc_001", "filename": "document", "file_type": "doc"}
        ])
        mock_file_transfer.get_file_path.return_value = tmp_path / "doc_001.txt"
        handler.file_transfer = mock_file_transfer
        
        mock_file = Mock()
        mock_file.filename = "document.txt"
        
        with pytest.raises(Exception) as exc_info:
            await handler.process_files(
                mock_store, "store_123", "session_456", [mock_file]
            )
        
        assert "文档文件处理失败" in str(exc_info.value)

    @pytest.mark.asyncio
    async def test_process_files_image_grouping(self, tmp_path):
        """测试图片分组功能"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        
        session_id = "session_123"
        
        for i in range(1, 5):
            img_path = tmp_path / session_id / f"img_00{i}.jpg"
            img_path.parent.mkdir(parents=True, exist_ok=True)
            img_path.write_bytes(b"fake image")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": f"img_00{i}", "filename": f"image{i}", "file_type": "img"}
            for i in range(1, 5)
        ])
        
        def get_file_path_side_effect(file_id, session):
            return tmp_path / session / f"{file_id}.jpg"
        
        mock_file_transfer.get_file_path.side_effect = get_file_path_side_effect
        handler.file_transfer = mock_file_transfer
        
        mock_files = [Mock(filename=f"image{i}.jpg") for i in range(1, 5)]
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, mock_files
        )
        
        assert len(result["img"]) == 2
        assert result["img"][0] == ["img_001", "img_002", "img_003"]
        assert result["img"][1] == ["img_002", "img_003", "img_004"]


class TestEdgeCases:
    """测试边界情况"""

    def test_group_images_with_none(self):
        """测试 _group_images 处理 None 输入"""
        handler = FileUploadHandler()
        
        with pytest.raises(TypeError):
            handler._group_images(None)

    @pytest.mark.asyncio
    async def test_read_file_as_base64_unicode_filename(self, tmp_path):
        """测试 Unicode 文件名"""
        handler = FileUploadHandler()
        test_content = b"Unicode filename test"
        test_file = tmp_path / "测试文件.txt"
        test_file.write_bytes(test_content)
        
        result = await handler._read_file_as_base64(test_file)
        
        expected = base64.b64encode(test_content).decode("utf-8")
        assert result == expected

    @pytest.mark.asyncio
    async def test_process_files_with_unknown_file_type(self, tmp_path):
        """测试未知文件类型（默认为 doc）"""
        handler = FileUploadHandler()
        handler.upload_dir = tmp_path
        
        mock_store = Mock()
        mock_store.get.return_value = None
        
        session_id = "session_123"
        
        doc_path = tmp_path / session_id / "file_001.xyz"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_bytes(b"unknown content")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "file_001", "filename": "unknown", "file_type": "doc"}
        ])
        mock_file_transfer.get_file_path.return_value = doc_path
        handler.file_transfer = mock_file_transfer
        
        mock_file = Mock()
        mock_file.filename = "unknown.xyz"
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, [mock_file]
        )
        
        assert len(result["doc"]) == 1

    @pytest.mark.asyncio
    async def test_store_file_info_with_malformed_json(self):
        """测试处理格式错误的 JSON 数据"""
        handler = FileUploadHandler()
        mock_store = Mock()
        mock_existing = Mock()
        mock_existing.value = "not a valid json"
        mock_store.get.return_value = mock_existing
        
        namespace = ("store_123", "session_456")
        file_id = "file_001"
        file_path = "/path/to/file.pdf"
        
        with pytest.raises(json.JSONDecodeError):
            await handler._store_file_info(mock_store, namespace, file_id, file_path)


class TestIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, tmp_path):
        """测试完整工作流程"""
        handler = FileUploadHandler(upload_dir=str(tmp_path))
        
        mock_store = Mock()
        mock_store.get.return_value = None
        
        session_id = "test_session"
        
        doc_path = tmp_path / session_id / "doc_001.txt"
        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_bytes(b"document content")
        
        img_path = tmp_path / session_id / "img_001.jpg"
        img_path.write_bytes(b"image content")
        
        mock_file_transfer = Mock()
        mock_file_transfer.upload_files = AsyncMock(return_value=[
            {"id": "doc_001", "filename": "document", "file_type": "doc"},
            {"id": "img_001", "filename": "image", "file_type": "img"}
        ])
        
        def get_file_path_side_effect(file_id, session):
            if file_id.startswith("doc"):
                return tmp_path / session / f"{file_id}.txt"
            return tmp_path / session / f"{file_id}.jpg"
        
        mock_file_transfer.get_file_path.side_effect = get_file_path_side_effect
        handler.file_transfer = mock_file_transfer
        
        mock_files = [
            Mock(filename="document.txt"),
            Mock(filename="image.jpg")
        ]
        
        result = await handler.process_files(
            mock_store, "store_123", session_id, mock_files
        )
        
        assert "doc" in result
        assert "img" in result
        assert len(result["doc"]) == 1
        assert len(result["img"]) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=app.test.fileuploader.file_upload_handler", "--cov-report=term-missing"])
