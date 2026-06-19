#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件上传处理类模块

本模块提供文件上传处理功能，支持不同类型文件的处理和 LangGraph Store 存储。
主要功能包括：
1. 文档文件（doc/docx/txt等）的存储管理
2. PDF扫描件的图片转换和存储
3. 图片文件的base64编码存储
4. 图片ID的滚动分组处理

Date: 2026/3/17
Author: 张镒谱
"""
import json
import uuid
import base64
import aiofiles
from pathlib import Path
from typing import List, Dict, Any, Optional, Tuple

from fastapi import UploadFile

from app.shared.utils.files.fileTransfer import FileTransfer
from app.shared.utils.files.pdfToImage import pdf_to_images_parallel
from app.shared.utils.files.session_path_manager import get_session_upload_dir


class FileUploadHandler:
    """
    文件上传处理类
    
    提供文件上传、类型判断、存储等功能。支持文档文件、PDF扫描件、图片文件的处理。
    
    核心处理流程：
    1. 接收上传文件列表
    2. 根据文件类型分类（doc/scan/img）
    3. 分别处理不同类型文件
    4. 将处理结果存储到 LangGraph Store
    5. 返回处理后的文件ID和图片分组信息
    
    Attributes:
        file_transfer (FileTransfer): 文件传输工具类实例
        upload_dir (Path): 文件上传目录路径
    """
    
    def __init__(self, upload_dir: str = "data/upload"):
        """
        初始化文件上传处理器

        Args:
            upload_dir (str): 文件上传目录路径，默认为 "data/upload"
        """
        # 初始化文件传输工具，用于处理文件的上传和路径管理
        self.file_transfer = FileTransfer(upload_dir)
        # 保存上传目录路径，供后续文件处理使用
        self.upload_dir = self.file_transfer.upload_dir
    
    def _get_namespace(self, store_id: str) -> Tuple[str]:
        """
        构建 LangGraph Store 的 namespace
        
        namespace 用于在 Store 中隔离不同会话的文件数据，
        采用 (store_id,) 的一维结构确保数据唯一性。
        
        Args:
            store_id (str): 存储 ID，用于区分不同的存储空间
            session_id (str): 会话 ID，用于区分同一存储空间下的不同会话
            
        Returns:
            Tuple[str, str]: namespace 元组，格式为 (store_id, session_id)
        """
        return (store_id,)
    
    def _group_images(self, image_ids: List[str]) -> List[List[str]]:
        """
        对图片 ID 进行滚动分组
        
        采用滑动窗口算法，每组 3 张图片，窗口步长为 1（即相邻组重叠 1 张图片）。
        这种分组方式可以保证图片之间的上下文连续性，便于后续的多图联合分析。
        
        分组示例：
        - 输入：["1", "2", "3", "4"] （4张图片）
        - 输出：[["1", "2", "3"], ["2", "3", "4"]] （2个分组）
        - 解释：第1组包含图片1,2,3；第2组包含图片2,3,4（图片2和3被两组共享）
        
        Args:
            image_ids (List[str]): 图片 ID 列表
            
        Returns:
            List[List[str]]: 分组后的 ID 组合列表，每个元素是包含3个连续图片ID的列表
            
        Raises:
            TypeError: 当 image_ids 为 None 时
        """
        if image_ids is None:
            raise TypeError("image_ids cannot be None")
        
        if not image_ids:
            return []
        
        # 图片数量不超过3张时，所有图片作为一组
        if len(image_ids) <= 3:
            return [image_ids]
        
        groups = []
        # 滑动窗口遍历：每次取连续的3张图片作为一组
        # i 的范围是 0 到 len-3，确保能取到完整的3张图片
        for i in range(len(image_ids) - 2):
            # 提取当前位置开始的3个连续图片ID作为列表
            group = image_ids[i:i+3]
            groups.append(group)
        
        return groups
    
    async def _read_file_as_base64(self, file_path: Path) -> str:
        """
        读取文件并转换为 base64 编码
        
        使用异步IO读取文件内容，避免阻塞事件循环，
        然后将二进制内容编码为base64字符串，便于在JSON中传输和存储。
        
        Args:
            file_path (Path): 文件路径对象
            
        Returns:
            str: base64 编码的文件内容字符串
            
        Raises:
            Exception: 文件读取失败时抛出异常
        """
        # 异步读取文件二进制内容
        async with aiofiles.open(file_path, "rb") as f:
            content = await f.read()
        # 将二进制内容编码为base64，并解码为UTF-8字符串
        return base64.b64encode(content).decode("utf-8")
    
    async def _store_file_info(
        self, 
        store, 
        namespace: Tuple[str, str], 
        file_id: str, 
        file_path: str
    ) -> None:
        """
        存储文档文件信息到 LangGraph Store（追加模式）
        
        采用追加模式存储文件信息，即多次上传的文件信息会累积存储。
        存储结构为：namespace -> "file_id" -> {file_id1: path1, file_id2: path2, ...}
        
        处理逻辑：
        1. 尝试获取已存在的文件信息
        2. 如果存在，解析现有数据并追加新文件信息
        3. 如果不存在，创建新的数据字典
        4. 将更新后的数据存储回 Store
        
        Args:
            store: LangGraph Store 对象，提供数据持久化能力
            namespace (Tuple[str, str]): namespace 元组，用于数据隔离
            file_id (str): 文件唯一标识符
            file_path (str): 文件在服务器上的存储路径
        """
        # 尝试获取已存在的文件信息记录
        existing = store.get(namespace, "file/registry")
        
        # 判断是否存在历史数据
        if existing and existing.value:
            # 存在历史数据，解析并准备追加
            data = existing.value
            # 如果数据是字符串格式，需要先反序列化为字典
            if isinstance(data, str):
                data = json.loads(data)
        else:
            # 不存在历史数据，初始化空字典
            data = {}
        
        # 追加新的文件信息到数据字典
        data[file_id] = file_path
        # 将更新后的数据存储回 Store
        store.put(namespace, "file/registry", data)
    
    async def _store_image_info(
        self, 
        store, 
        namespace: Tuple[str, str], 
        image_data: Dict[str, str]
    ) -> None:
        """
        存储图片信息到 LangGraph Store（重置模式）
        
        采用重置模式存储图片信息，每次调用都会覆盖之前存储的图片数据。
        这是因为图片处理通常是批量进行的，新的一批图片会替换旧的图片。
        
        存储结构为：namespace -> "image_paths" -> {image_id1: base64_data1, ...}
        
        Args:
            store: LangGraph Store 对象，提供数据持久化能力
            namespace (Tuple[str, str]): namespace 元组，用于数据隔离
            image_data (Dict[str, str]): 图片数据字典，格式为 {"image_id": "base64_data", ...}
        """
        # 直接覆盖存储图片数据，不进行追加
        store.put(namespace, "file/images", image_data)
    
    async def _process_document_files(
        self,
        store,
        namespace: Tuple[str, str],
        doc_files: List[dict],
        session_id: str
    ) -> List[str]:
        """
        处理文档文件
        
        对于非 PDF 扫描件的文档文件（如 doc/docx/txt 等），
        上传成功后生成 file_id 和对应的 file_path，
        并将文件信息存储到 LangGraph Store 中。
        
        处理流程：
        1. 遍历所有文档文件
        2. 获取每个文件的存储路径
        3. 将文件信息存储到 Store
        4. 收集处理成功的文件 ID
        
        Args:
            store: LangGraph Store 对象
            namespace (Tuple[str, str]): namespace 元组
            doc_files (List[dict]): 文档文件信息列表，每个元素包含 id 和 filename
            session_id (str): 会话 ID，用于构建文件存储路径
            
        Returns:
            List[str]: 处理成功的文件 ID 列表
            
        Raises:
            Exception: 处理过程中发生错误时抛出，包含文件名和错误详情
        """
        file_ids = []
        
        # 遍历处理每个文档文件
        for file_info in doc_files:
            try:
                # 获取文件的唯一标识符
                file_id = file_info["id"]
                # 根据文件ID和会话ID构建完整的文件存储路径
                file_path = str(self.file_transfer.get_file_path(file_id, session_id))
                
                # 将文件信息存储到 LangGraph Store（追加模式）
                await self._store_file_info(store, namespace, file_id, file_path)
                # 记录处理成功的文件ID
                file_ids.append(file_id)
                
            except Exception as e:
                # 捕获异常并抛出包含文件名的详细错误信息
                raise Exception(f"文档文件处理失败 [{file_info.get('filename', 'unknown')}]: {str(e)}")
        
        return file_ids
    
    async def _process_scan_files(
        self,
        store,
        namespace: Tuple[str, str],
        scan_files: List[dict],
        session_id: str
    ) -> List[str]:
        """
        处理 PDF 扫描件
        
        对于 PDF 扫描件，首先将 PDF 转换为图片，然后将图片转为 base64 编码，
        并存储到 LangGraph Store 中。
        
        处理流程：
        1. 遍历所有扫描件文件
        2. 为每个PDF创建独立的输出目录
        3. 将PDF转换为图片（并行处理，DPI=200）
        4. 按文件名排序图片
        5. 将每张图片转换为base64编码
        6. 存储所有图片数据到 Store
        7. 返回所有图片ID列表
        
        Args:
            store: LangGraph Store 对象
            namespace (Tuple[str, str]): namespace 元组
            scan_files (List[dict]): 扫描件文件信息列表，每个元素包含 id 和 filename
            session_id (str): 会话 ID，用于构建文件存储路径
            
        Returns:
            List[str]: 处理生成的图片 ID 列表
            
        Raises:
            Exception: 处理过程中发生错误时抛出，包含文件名和错误详情
        """
        image_ids = []
        image_data = {}
        
        # 遍历处理每个PDF扫描件
        for file_info in scan_files:
            try:
                # 获取PDF文件的唯一标识符
                file_id = file_info["id"]
                # 获取PDF文件的存储路径
                pdf_path = self.file_transfer.get_file_path(file_id, session_id)
                
                # 为当前PDF创建独立的图片输出目录
                # 使用UUID确保目录名唯一，避免多文件处理时的冲突
                scan_output_dir = get_session_upload_dir(session_id, create=True) / f"scan_{uuid.uuid4()}"
                scan_output_dir.mkdir(parents=True, exist_ok=True)
                
                # 将PDF转换为图片，使用并行处理提高效率
                # DPI=200 保证图片清晰度，输出格式为JPG
                pdf_to_images_parallel(
                    str(pdf_path), 
                    str(scan_output_dir), 
                    dpi=200, 
                    output_format='jpg'
                )
                
                # 获取输出目录中的所有图片文件，并按文件名排序
                # 排序确保图片顺序与PDF页面顺序一致
                sorted_images = sorted(
                    [p for p in scan_output_dir.iterdir() if p.suffix.lower() in {'.jpg', '.jpeg', '.png'}],
                    key=lambda x: x.name
                )
                
                # 遍历处理每张转换后的图片
                for img_path in sorted_images:
                    # 为每张图片生成唯一ID
                    image_id = str(uuid.uuid4())
                    # 将图片内容转换为base64编码
                    base64_data = await self._read_file_as_base64(img_path)
                    # 存储图片数据
                    image_data[image_id] = base64_data
                    # 记录图片ID
                    image_ids.append(image_id)
                
            except Exception as e:
                # 捕获异常并抛出包含文件名的详细错误信息
                raise Exception(f"PDF扫描件处理失败 [{file_info.get('filename', 'unknown')}]: {str(e)}")
        
        # 如果有图片数据，则存储到 LangGraph Store
        if image_data:
            await self._store_image_info(store, namespace, image_data)
        
        return image_ids
    
    async def _process_image_files(
        self,
        store,
        namespace: Tuple[str, str],
        img_files: List[dict],
        session_id: str
    ) -> List[str]:
        """
        处理图片文件
        
        对于直接上传的图片文件（如 jpg/png 等），
        将其转为 base64 编码，并存储到 LangGraph Store 中。
        
        处理流程：
        1. 遍历所有图片文件
        2. 读取图片内容并转换为base64编码
        3. 存储图片数据到 Store
        4. 返回所有图片ID列表
        
        Args:
            store: LangGraph Store 对象
            namespace (Tuple[str, str]): namespace 元组
            img_files (List[dict]): 图片文件信息列表，每个元素包含 id 和 filename
            session_id (str): 会话 ID，用于构建文件存储路径
            
        Returns:
            List[str]: 处理生成的图片 ID 列表
            
        Raises:
            Exception: 处理过程中发生错误时抛出，包含文件名和错误详情
        """
        image_ids = []
        image_data = {}
        
        # 遍历处理每个图片文件
        for file_info in img_files:
            try:
                # 获取图片文件的唯一标识符
                file_id = file_info["id"]
                # 获取图片文件的存储路径
                img_path = self.file_transfer.get_file_path(file_id, session_id)
                
                # 将图片内容转换为base64编码
                base64_data = await self._read_file_as_base64(img_path)
                # 存储图片数据，使用文件ID作为键
                image_data[file_id] = base64_data
                # 记录图片ID
                image_ids.append(file_id)
                
            except Exception as e:
                # 捕获异常并抛出包含文件名的详细错误信息
                raise Exception(f"图片文件处理失败 [{file_info.get('filename', 'unknown')}]: {str(e)}")
        
        # 如果有图片数据，则存储到 LangGraph Store
        if image_data:
            await self._store_image_info(store, namespace, image_data)
        
        return image_ids
    
    async def process_files(
        self,
        store,
        store_id: str,
        session_id: str,
        files: List[UploadFile]
    ) -> Dict[str, List]:
        """
        主处理方法 - 处理上传的文件列表
        
        对上传的每个文件进行类型判断和相应处理，根据文件类型执行不同的存储逻辑。
        这是文件上传处理的入口方法，协调各子处理方法完成完整的文件处理流程。
        
        处理流程：
        1. 初始化结果字典
        2. 调用文件传输工具上传文件到服务器
        3. 根据文件类型（doc/scan/img）进行分类
        4. 分别处理不同类型的文件
        5. 对图片ID进行滚动分组
        6. 返回处理结果
        
        Args:
            store: LangGraph Store 对象，用于数据持久化
            store_id (str): 存储 ID，用于构建 namespace
            session_id (str): 会话 ID，用于构建 namespace 和文件存储路径
            files (List[UploadFile]): 上传的文件列表
            
        Returns:
            Dict[str, List]: 处理结果，格式为:
                {
                    "doc": [fileid1, fileid2, ...],  # 文档文件 ID 列表
                    "img": [[img_id1, img_id2, img_id3], [img_id2, img_id3, img_id4], ...]  # 图片分组列表，每组3个连续图片ID
                }
                
        Raises:
            Exception: 文件上传或处理失败时抛出，包含详细的错误信息
        """
        # 初始化结果字典
        result = {
            "doc": [],
            "img": []
        }
        
        # 空文件列表直接返回空结果
        if not files:
            return result
        
        # 执行文件上传操作，将文件保存到服务器
        try:
            uploaded_files = await self.file_transfer.upload_files(files, session_id)
        except Exception as e:
            raise Exception(f"文件上传失败: {str(e)}")
        
        # 初始化三种文件类型的列表
        doc_files = []    # 普通文档文件
        scan_files = []   # PDF扫描件
        img_files = []    # 图片文件
        
        # 根据文件类型进行分类
        for file_info in uploaded_files:
            file_type = file_info.get("file_type", "doc")
            
            # 根据文件类型添加到对应的列表
            if file_type == "doc":
                doc_files.append(file_info)
            elif file_type == "scan":
                scan_files.append(file_info)
            elif file_type == "img":
                img_files.append(file_info)
        
        # 构建 LangGraph Store 的 namespace
        namespace = self._get_namespace(store_id, )
        
        # 收集所有图片ID，用于后续分组
        all_image_ids = []
        
        # 标记所有已成功处理的文件ID，用于失败时清理
        processed_file_ids = []
        
        try:
            # 处理文档文件
            if doc_files:
                try:
                    doc_ids = await self._process_document_files(store, namespace, doc_files, session_id)
                    result["doc"].extend(doc_ids)
                    processed_file_ids.extend(doc_ids)
                except Exception as e:
                    raise Exception(f"文档文件处理失败: {str(e)}")
            
            # 处理PDF扫描件
            if scan_files:
                try:
                    scan_image_ids = await self._process_scan_files(store, namespace, scan_files, session_id)
                    all_image_ids.extend(scan_image_ids)
                    # 标记扫描件的file_id为已处理
                    processed_file_ids.extend([f["id"] for f in scan_files])
                except Exception as e:
                    raise Exception(f"PDF扫描件处理失败: {str(e)}")
            
            # 处理图片文件
            if img_files:
                try:
                    img_image_ids = await self._process_image_files(store, namespace, img_files, session_id)
                    all_image_ids.extend(img_image_ids)
                    # 标记图片文件的file_id为已处理
                    processed_file_ids.extend([f["id"] for f in img_files])
                except Exception as e:
                    raise Exception(f"图片文件处理失败: {str(e)}")
            
        except Exception as e:
            # 处理失败，清理已上传但处理失败的文件
            for file_id in processed_file_ids:
                try:
                    await self.file_transfer.delete_file(file_id, session_id)
                except Exception:
                    pass  # 忽略删除失败
            raise Exception(f"文件处理失败: {str(e)}")
        
        # 如果有图片ID，进行滚动分组处理
        if all_image_ids:
            result["img"] = self._group_images(all_image_ids)
        
        return result
if __name__ == "__main__":
    file_upload_handler = FileUploadHandler()