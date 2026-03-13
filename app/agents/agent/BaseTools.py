#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
BaseTools - Agent基础工具模块

该模块定义了Agent可用的基础工具函数，包括获取当前时间、文件加载和文档分块读取功能。

Date: 2026-03-13
Author: 张镒谱
"""

import uuid
from datetime import datetime
from pathlib import Path
from typing import Union, List, Dict, Any
from langchain.tools import tool, ToolRuntime
from langchain_text_splitters import RecursiveCharacterTextSplitter
from app.agents.agent.AgentContext import AgentContext
from app.utils.files.DocumentLoader import DocumentLoader


def _get_namespace(session_id: str) -> tuple:
    """获取文件存储的命名空间"""
    return (f"{session_id}_file",)


def _split_content(content: str, chunk_size: int = 4000, chunk_overlap: int = 50) -> List[str]:
    """
    使用 LangChain 的 RecursiveCharacterTextSplitter 分割文本

    Args:
        content: 待分割的文本内容
        chunk_size: 每个块的最大字符数
        chunk_overlap: 块之间的重叠字符数

    Returns:
        List[str]: 分割后的文本块列表
    """
    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False,
    )
    return text_splitter.split_text(content)


def _save_chunks_to_store(
    session_id: str,
    file_id: str,
    chunks: List[str],
    store: any
) -> bool:
    """
    将文本块保存到 store

    Args:
        session_id: 会话 ID
        file_id: 文件 ID (UUID)
        chunks: 文本块列表
        store: store 实例，从 runtime.store 传入

    Returns:
        bool: 是否保存成功
    """
    namespace = _get_namespace(session_id)

    # 构建存储结构: [{index: 1, name: "1/4", content: "..."}, ...]
    chunk_data = [
        {
            "index": i + 1,
            "name": f"{i + 1}/{len(chunks)}",
            "content": chunk
        }
        for i, chunk in enumerate(chunks)
    ]

    # 保存到 store
    store.put(namespace, file_id, chunk_data)
    return True


@tool(description="获取当前时间必须调用此工具")
def get_current_time(runtime: ToolRuntime[AgentContext]) -> str:
    """
    获取当前时间工具,问题涉及当前时间时必须调用此工具。

    返回当前系统时间字符串，格式为 YYYY-MM-DD HH:MM:SS，并附带会话ID。
    用于Agent了解当前时间上下文，支持时间敏感的任务处理。

    Args:
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: 格式化的时间字符串，格式 "YYYY-MM-DD HH:MM:SS (session_id: xxx)"
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time + f" (session_id: {runtime.context.get('session_id', 'default')})"


@tool(description="打开并读取文件内容，支持文本、PDF、Word、CSV、JSON、Markdown等格式。文件会被分块存储，使用 read_next_chunk 工具逐块读取。")
def open_file(
    file_path: Union[str, Path],
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    文件加载工具

    智能识别文件类型并加载内容，将文档分块后存入存储，返回文件ID。
    需要使用 read_next_chunk 工具逐块读取内容。

    Args:
        file_path (Union[str, Path]): 必填 文件或文件夹路径，支持相对路径和绝对路径
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    glob = "**/*"
    session_id = runtime.context.get('session_id', 'default')

    try:
        path = Path(file_path)

        if not path.exists():
            return f'{{"error": "文件或文件夹不存在: {file_path}"}}'

        loader = DocumentLoader(
            path=path,
            glob=glob,
            silent_errors=True,
        )

        docs = loader.load()

        if not docs:
            return f'{{"error": "未加载到任何内容: {file_path}"}}'

        # 合并所有文档内容
        full_content = "\n\n".join([doc.page_content for doc in docs])

        # 分块处理
        chunks = _split_content(full_content, chunk_size=4000, chunk_overlap=200)

        # 检查分块是否为空
        if not chunks or len(chunks) == 0:
            return f'{{"status": "没有文件缓存", "next_step": "没有文件缓存需要读取"}}'

        # 生成文件ID
        file_id = str(uuid.uuid4())

        # 保存到 store (使用 runtime.store)
        _save_chunks_to_store(session_id, file_id, chunks, runtime.store)
        
        return f'{{"cache_id": "{file_id}", "status": "文件缓存完成", "total_chunks": {len(chunks)}, "next_step": "请使用缓存工具读取文档内容"}}'

    except Exception as e:
        return f'{{"error": "加载失败: {e}"}}'


@tool(description="加载指定URL的网页内容。内容会被分块存储，使用 read_next_chunk 工具逐块读取。")
def load_web_page(
    url: str,
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    网页加载工具

    加载指定URL的网页内容，将内容分块后存入存储，返回文件ID。
    需要使用 read_next_chunk 工具逐块读取内容。

    Args:
        url (str): 必填 要加载的网页URL
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    extract_type = "article"
    max_length = 1000000
    include_links = False
    session_id = runtime.context.get('session_id', 'default')

    try:
        docs = DocumentLoader.load_url(
            url=url,
            extract_type=extract_type,
            max_length=max_length,
            include_links=include_links,
        )

        if not docs:
            return f'{{"error": "未从 {url} 加载到任何内容"}}'

        # 合并所有文档内容
        full_content = "\n\n".join([doc.page_content for doc in docs])

        # 分块处理
        chunks = _split_content(full_content, chunk_size=4000, chunk_overlap=200)

        # 生成文件ID
        file_id = str(uuid.uuid4())

        # 保存到 store (使用 runtime.store)
        _save_chunks_to_store(session_id, file_id, chunks, runtime.store)

        return f'{{"file_name": "{file_id}", "status": "文件读取完成", "total_chunks": {len(chunks)}}}'

    except Exception as e:
        return f'{{"error": "加载网页失败: {e}"}}'


@tool(description="缓存工具从存储中读取已经缓存文档的下一块内容。每次调用返回一块，从第1块开始，直到返回 name=\"X/X\" 表示已读完。")
def read_next_chunk(
    cache_id: str,
    runtime: ToolRuntime[AgentContext],
) -> str:
    """
    缓存工具
    读取的内容是缓存在内存中的，每次调用返回一块，从第1块开始，直到返回 name=\"X/X\" 表示已读完。
    从存储中按顺序读取文档的每一块内容。
    首次调用返回第1块，再次调用返回第2块，依此类推。
    当返回的 name 字段等于总块数（如 "4/4"）时，表示已读完。

    Args:
        cache_id (str): 缓存ID，由 open_file 或 load_web_page 返回
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 index、name、content 和 is_last 字段
              如果已读完，返回提示信息
    """
    session_id = runtime.context.get('session_id', 'default')
    namespace = _get_namespace(session_id)

    try:
        # 从 store 获取文档数据 (使用 runtime.store)
        result = runtime.store.get(namespace, cache_id)

        if not result or not result.value:
            return f'{{"error": "未找到缓存: {cache_id}"}}'

        chunks = result.value

        # 查找当前应该返回的块（找到第一个未读的）
        # 通过检查 state 中的读取进度
        progress_key = f"file_chunk_read_progess_{cache_id}"
        current_index = runtime.state.get(progress_key, 1)

        if current_index > len(chunks):
            return r'{{"status": "已读完", "message": "文档已全部读取完毕，共 {len(chunks)} 块"}}'

        # 获取当前块
        chunk = chunks[current_index - 1]

        # 更新读取进度
        runtime.state[progress_key] = current_index + 1

        # 判断是否最后一块
        is_last = current_index == len(chunks)

        # 构建下一步提示
        next_step = "" if is_last else "继续执行 read_next_chunk 工具读取下一块"

        return f'{{"index": {chunk["index"]}, "name": "{chunk["name"]}", "content": {repr(chunk["content"])}, "is_last": {str(is_last).lower()}, "next_step": "{next_step}"}}'

    except Exception as e:
        return f'{{"error": "读取失败: {e}"}}'
