#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
文件上传与文档加载综合测试模块

本模块实现以下功能：
- 使用 FileTransfer 批量上传文件
- 使用 DocumentLoader 加载上传后的文件内容
- 循环处理多个文件，展示完整的文件处理流程

Date: 2026/03/13
Author: 张镒谱
"""

import asyncio
import os
import sys
from pathlib import Path
from fastapi import UploadFile


from app.utils.files.fileTransfer import FileTransfer
from app.utils.files.DocumentLoader import DocumentLoader


class MockUploadFile:
    """
    模拟 FastAPI 的 UploadFile 类
    
    用于测试环境，模拟文件上传对象
    """
    
    def __init__(self, filename: str, content: bytes):
        self.filename = filename
        self._content = content
    
    async def read(self) -> bytes:
        return self._content


async def upload_and_load_files(test_files: list, session_id: str = "test_session"):
    """
    上传文件并加载内容的综合测试函数
    
    Args:
        test_files: 测试文件路径列表
        session_id: 会话ID，用于隔离不同会话的文件
        
    Returns:
        dict: 包含上传结果和文档内容的字典
    """
    file_transfer = FileTransfer(upload_dir="app/data/upload")
    
    results = {
        "uploaded_files": [],
        "loaded_documents": [],
        "errors": []
    }
    
    for file_path in test_files:
        print(f"\n{'='*60}")
        print(f"📂 正在处理文件: {file_path}")
        print(f"{'='*60}")
        
        try:
            if not os.path.exists(file_path):
                print(f"⚠️  文件不存在，跳过: {file_path}")
                results["errors"].append({"file": file_path, "error": "文件不存在"})
                continue
            
            # 步骤1: 读取文件内容
            with open(file_path, "rb") as f:
                file_content = f.read()
            
            # 步骤2: 创建模拟 UploadFile 对象
            mock_file = MockUploadFile(
                filename=os.path.basename(file_path),
                content=file_content
            )
            
            # 步骤3: 使用 FileTransfer 上传文件
            print(f"📤 正在上传文件...")
            uploaded = await file_transfer.upload_files(
                files=[mock_file],
                session_id=session_id
            )
            
            if not uploaded:
                print(f"❌ 文件上传失败")
                results["errors"].append({"file": file_path, "error": "上传失败"})
                continue
            
            uploaded_info = uploaded[0]
            file_uuid = uploaded_info["id"]
            original_filename = uploaded_info["filename"]
            
            print(f"✅ 上传成功!")
            print(f"   UUID: {file_uuid}")
            print(f"   原始文件名: {original_filename}")
            
            results["uploaded_files"].append({
                "original_path": file_path,
                "uuid": file_uuid,
                "filename": original_filename
            })
            
            # 步骤4: 获取上传后的文件路径
            uploaded_file_path = file_transfer.get_file_path(file_uuid, session_id)
            print(f"   存储路径: {uploaded_file_path}")
            
            # 步骤5: 使用 DocumentLoader 加载文件内容
            print(f"\n📄 正在加载文档内容...")
            doc_loader = DocumentLoader(str(uploaded_file_path))
            documents = doc_loader.load()
            
            if documents:
                print(f"✅ 成功加载 {len(documents)} 个文档片段:\n")
                
                for idx, doc in enumerate(documents, 1):
                    print(f"--- 片段 {idx} ---")
                    content_preview = doc.page_content[:500]
                    if len(doc.page_content) > 500:
                        content_preview += "..."
                    print(f"内容: {content_preview}")
                    print(f"元数据: {doc.metadata}")
                    print()
                
                results["loaded_documents"].append({
                    "file": file_path,
                    "uuid": file_uuid,
                    "document_count": len(documents),
                    "documents": documents
                })
            else:
                print("⚠️  未加载到任何内容")
                results["loaded_documents"].append({
                    "file": file_path,
                    "uuid": file_uuid,
                    "document_count": 0,
                    "documents": []
                })
                
        except Exception as e:
            print(f"❌ 处理失败: {e}")
            results["errors"].append({"file": file_path, "error": str(e)})
    
    return results


async def cleanup_test_files(session_id: str = "test_session"):
    """
    清理测试文件
    
    Args:
        session_id: 要清理的会话ID
    """
    file_transfer = FileTransfer(upload_dir="app/data/upload")
    
    print(f"\n{'='*60}")
    print(f"🧹 正在清理测试文件...")
    print(f"{'='*60}")
    
    try:
        success = await file_transfer.delete_session(session_id)
        if success:
            print(f"✅ 会话 '{session_id}' 清理完成")
        else:
            print(f"⚠️  会话 '{session_id}' 不存在或已清理")
    except Exception as e:
        print(f"❌ 清理失败: {e}")


async def main():
    """
    主测试函数
    
    参考 DocumentLoader 中 __main__ 的逻辑，循环处理多个测试文件
    """
    # 测试文件路径数组（可根据实际情况修改）
    test_files = [
        r"D:\DocumentLoader\TextLoader.txt",
        r"D:\DocumentLoader\MarkdownLoader.md",
        r"D:\DocumentLoader\PdfLoader.pdf",
        r"D:\DocumentLoader\WordLoader.docx",
        r"D:\DocumentLoader\CSVLoader.csv",
        r"D:\DocumentLoader\JSONLoader.json",
    ]
    
    session_id = "test_session_001"
    
    print("\n" + "="*60)
    print("🚀 开始文件上传与文档加载综合测试")
    print("="*60)
    
    # 执行上传和加载测试
    results = await upload_and_load_files(test_files, session_id)
    
    # 输出测试总结
    print("\n" + "="*60)
    print("📊 测试总结")
    print("="*60)
    print(f"✅ 成功上传文件数: {len(results['uploaded_files'])}")
    print(f"✅ 成功加载文档数: {len(results['loaded_documents'])}")
    print(f"❌ 错误数: {len(results['errors'])}")
    
    # 显示已上传的文件列表
    if results['uploaded_files']:
        print("\n📁 已上传的文件列表:")
        print("-" * 60)
        for idx, file_info in enumerate(results['uploaded_files'], 1):
            print(f"  {idx}. 原始路径: {file_info['original_path']}")
            print(f"     UUID: {file_info['uuid']}")
            print(f"     文件名: {file_info['filename']}")
            print(f"     存储路径: app/data/upload/{session_id}/{file_info['uuid']}")
            print()
    
    if results['errors']:
        print("\n错误详情:")
        for error in results['errors']:
            print(f"  - {error['file']}: {error['error']}")
    
    # 清理测试文件（可选，注释掉可保留文件用于调试）
    # await cleanup_test_files(session_id)
    
    print("\n" + "="*60)
    print("🏁 测试完成")
    print("="*60)
    
    return results


if __name__ == "__main__":
    asyncio.run(main())
