#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent 客户端测试脚本

用于测试文件上传和文档对话功能。

Date: 2026-03-23
Author: 张镒谱
"""

import asyncio
import uuid
from io import BytesIO
from pathlib import Path

from fastapi import UploadFile
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

from app.shared.utils.files.file_upload_handler import FileUploadHandler
from app.features.contract_document_agent.DocAgent import DocAgent

from logging import getLogger
import logging

# 配置日志格式和级别
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = getLogger(__name__)
async def main():
    store_id = str(uuid.uuid4())

    host_session_id = str(uuid.uuid4())
    logger.info(f"host_session_id: {host_session_id}")


    checkpointer = MemorySaver()
    store = InMemoryStore()

    file_path = Path(r"C:\Users\54299\Desktop\1.pdf")
    
    with open(file_path, "rb") as f:
        file_content = f.read()
    
    upload_file = UploadFile(
        filename=file_path.name,
        file=BytesIO(file_content)
    )

    file_upload_handler = FileUploadHandler()
    result = await file_upload_handler.process_files(
        store=store,
        store_id=store_id,
        session_id=host_session_id,
        files=[upload_file]
    )

    logger.info(f"上传结果: {result}")

    doc_agent = DocAgent(
        checkpointer=checkpointer,
        store=store,
        store_id=store_id,
    )

    doc_ids = result.get("doc", [])
    img_groups = result.get("img", [])

    user_input = f"识别图片内容，返回文件类型。要求：直接返回类型名称，不要任何修饰词、前缀或后缀。例如：返回'成交确认书'而不是'这是一份成交确认书'。"
    session_id = str(uuid.uuid4())
    logger.info(f"session_id: {session_id}")
    
    image_ids = img_groups[0] if img_groups else None

    response = await doc_agent.invoke(
        user_input=user_input,
        session_id=session_id,
        host_session_id=host_session_id,
        image_ids=image_ids,
    )
        
    logger.info(f"\n回答: {response}")
    while True:
        # 构建提取信息的提示词，明确告知模型这是图片处理任务，不需要切分
        user_input = f"从图片中提取{response}的关键信息并保存。注意：处理图片时不需要切分文档。"
        
        if user_input.lower() == 'quit':
            break
        session_id = str(uuid.uuid4())
        logger.info(f"session_id: {session_id}")
        
        image_ids = img_groups[0] if img_groups else None

        response = await doc_agent.invoke(
            user_input=user_input,
            session_id=session_id,
            host_session_id=host_session_id,
            image_ids=image_ids,
        )
        
        logger.info(f"\n回答: {response}")


if __name__ == "__main__":
    asyncio.run(main())
