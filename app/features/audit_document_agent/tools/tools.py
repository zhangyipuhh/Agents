#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
合同审批解析附件智能体工具模块

本模块定义了用于解析合同、成交确认书、会议纪要的工具函数。
使用 @tool 装饰器注册为 LangChain 工具。

设计理念：
- 解析工具内部完成解析并保存到长期记忆，返回简洁的摘要信息
- 返回内容包含：成功/失败状态、提取的内容条数、错误信息等
- 避免返回完整的解析内容，减少 token 消耗和传输开销

Date: 2026-03-05
Author: AI Assistant
"""
import os
import re
import uuid
from pathlib import Path
from typing import Dict, Any, List, Optional
from langchain.tools import tool
from langchain_core.tools import BaseTool
from app.shared.utils.files.word_untils import WordProcessor
from app.shared.utils.files.pdf_untils import PDFProcessor
from app.shared.utils.files.pdfToImage import convert_pdfs_to_images
from app.shared.utils.files.session_path_manager import get_session_upload_dir
from app.shared.utils.memory.document_memory_store import document_memory_store


class AuditDocumentTools:
    """合同审批解析工具类"""

    def __init__(self):
        """初始化文档处理器实例"""
        self._word_processor = WordProcessor()
        self._pdf_processor = PDFProcessor()

    def _save_to_memory(
        self,
        session_id: str,
        file_id: str,
        file_type: str,
        content: Dict[str, Any],
        file_name: str = ""
    ) -> bool:
        """
        内部方法：保存解析结果到长期记忆

        Args:
            session_id: 会话 ID
            file_id: 文件 ID
            file_type: 文件类型
            content: 解析内容
            file_name: 文件名

        Returns:
            保存是否成功
        """
        return document_memory_store.save_document(
            session_id=session_id,
            file_id=file_id,
            file_type=file_type,
            content=content,
            file_name=file_name
        )

    def parse_contract(
        self,
        file_path: str,
        file_id: str,
        session_id: str,
        file_name: str = ""
    ) -> Dict[str, Any]:
        """
        解析合同文件并保存到长期记忆

        Args:
            file_path: 合同文件的完整路径
            file_id: 文件唯一标识符
            session_id: 会话 ID
            file_name: 文件名

        Returns:
            包含解析状态和摘要信息的字典
        """
        file_ext = Path(file_path).suffix.lower()

        contract_text = ""
        paragraph_data = []

        if file_ext == '.docx' or file_ext == '.doc':
            contract_text, paragraph_data = self._word_processor.read_contract_word(
                file_path,
                pattern=r'^\s*(第[一二三四五六七八九十百千万亿]+条)',
                pattern_replace=r'\1条款'
            )
        elif file_ext == '.pdf':
            contract_text = self._pdf_processor.extract_text_from_pdf(file_path)
        else:
            return {
                "status": "error",
                "file_id": file_id,
                "file_type": "contract",
                "success": False,
                "message": f"不支持的文件类型: {file_ext}",
                "need_retry": False
            }

        if not contract_text:
            return {
                "status": "error",
                "file_id": file_id,
                "file_type": "contract",
                "success": False,
                "message": "合同文本提取失败",
                "need_retry": False
            }

        pattern = r'(第[\u4e00-\u9fa5\d]+条\s*条款)(.*?)(?=\s*第[\u4e00-\u9fa5\d]+条\s*条款|$)'
        chunks = re.findall(pattern, contract_text, re.DOTALL)

        content = {
            "file_id": file_id,
            "type": "contract",
            "contract_text": contract_text,
            "contract_paragraph_list": paragraph_data,
            "clauses": [
                {
                    "clause_title": chunk[0],
                    "clause_content": chunk[1].strip()
                }
                for chunk in chunks
            ]
        }

        save_success = self._save_to_memory(
            session_id=session_id,
            file_id=file_id,
            file_type="contract",
            content=content,
            file_name=file_name or os.path.basename(file_path)
        )

        clause_count = len(chunks)
        return {
            "status": "success",
            "file_id": file_id,
            "file_type": "contract",
            "success": True,
            "message": f"合同解析成功，提取了 {clause_count} 个条款",
            "parsed_count": clause_count,
            "need_retry": False
        }

    def parse_transaction(
        self,
        file_path: str,
        file_id: str,
        session_id: str,
        file_name: str = "",
        project_id: Optional[int] = None,  # 2026-06-30 新增
    ) -> Dict[str, Any]:
        """
        解析成交确认书 PDF 并保存到长期记忆

        Args:
            file_path: 成交确认书 PDF 文件的完整路径
            file_id: 文件唯一标识符
            session_id: 会话 ID
            file_name: 文件名

        Returns:
            包含解析状态和摘要信息的字典
        """
        step_id = convert_pdfs_to_images(
            session_id=session_id,
            file_ids=[file_id],
            dpi=300,
            max_workers=4,
            output_format='jpg'
        )

        image_dir = get_session_upload_dir(session_id, project_id=project_id) / step_id / file_id
        image_paths = sorted(image_dir.glob("*.jpg"))

        if not image_paths:
            return {
                "status": "error",
                "file_id": file_id,
                "file_type": "transaction",
                "success": False,
                "message": "PDF 转换图片失败",
                "need_retry": True,
                "retry_hint": "请检查 PDF 文件是否损坏或密码保护"
            }

        image_paths_str = [str(p) for p in image_paths]

        content = {
            "file_id": file_id,
            "type": "transaction",
            "image_paths": image_paths_str,
            "note": "图片已生成，请使用 LLM 提取付款方式、付款时间等信息"
        }

        save_success = self._save_to_memory(
            session_id=session_id,
            file_id=file_id,
            file_type="transaction",
            content=content,
            file_name=file_name or os.path.basename(file_path)
        )

        return {
            "status": "success",
            "file_id": file_id,
            "file_type": "transaction",
            "success": True,
            "message": f"成交确认书解析成功，已生成 {len(image_paths_str)} 张图片",
            "image_count": len(image_paths_str),
            "need_retry": False
        }

    def parse_meeting_minutes(
        self,
        file_path: str,
        file_id: str,
        session_id: str,
        file_name: str = ""
    ) -> Dict[str, Any]:
        """
        解析会议纪要 PDF 并保存到长期记忆

        Args:
            file_path: 会议纪要 PDF 文件的完整路径
            file_id: 文件唯一标识符
            session_id: 会话 ID
            file_name: 文件名

        Returns:
            包含解析状态和摘要信息的字典
        """
        from langchain_text_splitters import RecursiveCharacterTextSplitter

        text = self._pdf_processor.read_pdf(file_path)

        if not text:
            return {
                "status": "error",
                "file_id": file_id,
                "file_type": "meeting",
                "success": False,
                "message": "PDF 文本提取失败",
                "need_retry": False
            }

        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            length_function=len,
            separators=["\n\n", "\n", "。", "，", " ", ""]
        )

        chunks = text_splitter.split_text(text)

        content = {
            "file_id": file_id,
            "type": "meeting",
            "meeting_text": text,
            "chunks": [
                {
                    "chunk_id": idx,
                    "chunk_text": chunk
                }
                for idx, chunk in enumerate(chunks)
            ]
        }

        save_success = self._save_to_memory(
            session_id=session_id,
            file_id=file_id,
            file_type="meeting",
            content=content,
            file_name=file_name or os.path.basename(file_path)
        )

        return {
            "status": "success",
            "file_id": file_id,
            "file_type": "meeting",
            "success": True,
            "message": f"会议纪要解析成功，已分割为 {len(chunks)} 个文本块",
            "chunk_count": len(chunks),
            "need_retry": False
        }


_audit_tools_instance = AuditDocumentTools()


@tool(description="合同解析工具")
def parse_contract_tool(runtime: Any) -> str:
    """解析合同文件，提取关键条款信息"""
    context = runtime.context
    file_paths = context.get("file_paths", [])
    file_ids = context.get("file_ids", [])
    session_id = context.get("session_id", "")
    
    file_path = file_paths[0] if file_paths else ""
    file_id = file_ids[0] if file_ids else ""
    
    result = _audit_tools_instance.parse_contract(
        file_path=file_path,
        file_id=file_id,
        session_id=session_id,
        file_name=""
    )
    return str(result)


@tool
def parse_transaction_tool(runtime: Any) -> str:
    """解析成交确认书，提取交易信息"""
    context = runtime.context
    file_paths = context.get("file_paths", [])
    file_ids = context.get("file_ids", [])
    session_id = context.get("session_id", "")
    
    file_path = file_paths[0] if file_paths else ""
    file_id = file_ids[0] if file_ids else ""
    
    result = _audit_tools_instance.parse_transaction(
        file_path=file_path,
        file_id=file_id,
        session_id=session_id,
        file_name=""
    )
    return str(result)


@tool
def parse_meeting_minutes_tool(runtime: Any) -> str:
    """解析会议纪要，提取决策事项"""
    context = runtime.context
    file_paths = context.get("file_paths", [])
    file_ids = context.get("file_ids", [])
    session_id = context.get("session_id", "")
    
    file_path = file_paths[0] if file_paths else ""
    file_id = file_ids[0] if file_ids else ""
    
    result = _audit_tools_instance.parse_meeting_minutes(
        file_path=file_path,
        file_id=file_id,
        session_id=session_id,
        file_name=""
    )
    return str(result)


@tool
def save_to_memory_tool(runtime: Any) -> str:
    """将解析内容保存到长期记忆"""
    context = runtime.context
    session_id = context.get("session_id", "")
    file_id = context.get("file_ids", [None])[0] if context.get("file_ids") else None
    file_type = "document"
    content = {}
    file_name = ""
    
    if file_id is None:
        return '{"status": "error", "file_id": null, "message": "缺少文件ID"}'
    
    success = document_memory_store.save_document(
        session_id=session_id,
        file_id=file_id,
        file_type=file_type,
        content=content,
        file_name=file_name
    )
    if success:
        return f'{{"status": "success", "file_id": "{file_id}", "message": "文件已成功保存到长期记忆"}}'
    else:
        return f'{{"status": "error", "file_id": "{file_id}", "message": "文件保存失败"}}'


def get_audit_tools() -> List[BaseTool]:
    """获取所有审计文档工具列表"""
    return [
        parse_contract_tool,
        parse_transaction_tool,
        parse_meeting_minutes_tool,
        save_to_memory_tool
    ]


def get_tool_names() -> List[str]:
    """获取所有审计文档工具名称列表"""
    return [
        "parse_contract_tool",
        "parse_transaction_tool",
        "parse_meeting_minutes_tool",
        "save_to_memory_tool"
    ]
