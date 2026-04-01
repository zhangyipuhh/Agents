#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
BaseTools - Agent基础工具模块

该模块定义了Agent可用的基础工具函数，包括获取当前时间、文件加载和文档分块读取功能。

设计核心原则：不要让 AI 看到它可能想解释的东西。状态码 + 系统规则 > 自然语言描述。

namespace = (store_id,) 只要保证多个智能体在使用时，store_id是唯一的，就可以避免冲突，因为id是唯一的，file_id或者image_path是公用的，但是取值的时候需要使用id获取
Date: 2026-03-13
Author: 张镒谱
"""
import logging
from imaplib import Commands
import json
import uuid
from datetime import datetime
from pathlib import Path
from typing import Union, List, Dict, Any
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langgraph.types import Command
from app.core.agent.AgentContext import AgentContext
from app.shared.utils.files.DocumentLoader import DocumentLoader





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
    store_id: str,
    session_id: str,
    file_id: str,
    chunks: List[str],
    store: any
) -> bool:
    """
    将文本块保存到 store

    Args:
        store_id: 存储 ID
        session_id: 会话 ID
        file_id: 文件 ID (UUID)
        chunks: 文本块列表
        store: store 实例，从 runtime.store 传入

    Returns:
        bool: 是否保存成功
    """
    namespace = (store_id,)

    # 构建存储结构: [{index: 1, name: "1/4", content: "..."}, ...]
    chunk_data = [
        {
            "index": i + 1,
            "name": f"{i + 1}/{len(chunks)}",
            "content": chunk
        }
        for i, chunk in enumerate(chunks)
    ]

    # 保存到 store (key: file/cache/{file_id})
    store.put(namespace, f"file/cache/{file_id}", chunk_data)
    return True


def _load_and_cache_file(
    file_path: Union[str, Path, List[Union[str, Path]]],
    session_id: str,
    store_id: str,
    store: any,
    tool_call_id: str,
) -> str:
    """
    加载文件内容并缓存到 store
    支持单个文件路径或文件路径列表，多个文件会统一分块返回一个cache_id。

    Args:
        file_path: 文件路径或文件路径列表
        session_id: 会话 ID
        store_id: 存储 ID
        store: store 实例
        tool_call_id: 工具调用 ID，用于返回 ToolMessage

    Returns:
        Command: 包含缓存结果或错误信息
    """
    glob = "**/*"

    try:
        paths = [file_path] if not isinstance(file_path, list) else file_path
        all_contents = []
        
        for fp in paths:
            path = Path(fp)
            if not path.exists():
                raise FileNotFoundError(f"文件或文件夹不存在: {fp}")

            loader = DocumentLoader(
                path=path,
                glob=glob,
                silent_errors=True,
            )

            docs = loader.load()
            if docs:
                all_contents.append(f"=== File: {fp} ===\n" + "\n\n".join([doc.page_content for doc in docs]))

        if not all_contents:
            raise ValueError(f"未从任何文件加载到内容")

        full_content = "\n\n".join(all_contents)
        return _cache_content(full_content, session_id, store_id, store)

    except Exception as e:
        return f'{{"error": "加载失败: {e}"}}'


def _cache_content(
    content: str,
    session_id: str,
    store_id: str,
    store: any,
    chunk_size: int = 2000,
    chunk_overlap: int = 100,
) -> str:
    """
    将内容分块并缓存到 store

    Args:
        content: 待缓存的内容
        session_id: 会话 ID
        store_id: 存储 ID
        store: store 实例
        chunk_size: 每个块的最大字符数
        chunk_overlap: 块之间的重叠字符数

    Returns:
        str: JSON格式结果字符串
    """
    chunks = _split_content(content, chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    if not chunks or len(chunks) == 0:
        raise ValueError("内容为空，无法缓存")

    file_id = str(uuid.uuid4())
    _save_chunks_to_store(store_id, session_id, file_id, chunks, store)

    return json.dumps({
        "cache_id": file_id,
        "status": "cached",
        "total_chunks": len(chunks),
    }, ensure_ascii=False)


@tool(description="获取当前时间，仅在用户询问时间相关问题时调用")
def get_current_time(runtime: ToolRuntime[AgentContext]) -> str:
    """
    获取当前时间工具。仅在用户明确询问时间、日期或需要时间上下文时才调用。

    返回当前系统时间字符串，格式为 YYYY-MM-DD HH:MM:SS，并附带会话ID。
    用于Agent了解当前时间上下文，支持时间敏感的任务处理。

    Args:
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: 格式化的时间字符串，格式 "YYYY-MM-DD HH:MM:SS (session_id: xxx)"
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time + f" (session_id: {runtime.context.get('session_id', 'default')})"


@tool(description="""
【本地文件加载】加载本地文件（PDF/Word/CSV等）并分块缓存。

**参数**：file_path - 文件或文件夹路径，支持相对路径和绝对路径

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个文件路径或路径列表，多个文件会统一分块返回一个 cache_id。
""")
def open_file(
    file_path: Union[str, Path, List[Union[str, Path]]],
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    文件加载工具

    智能识别文件类型并加载内容，将文档分块后存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。
    支持单个文件路径或路径列表，多个文件会统一分块返回一个cache_id。

    Args:
        file_path (Union[str, Path, List[Union[str, Path]]]): 必填 文件或文件夹路径，支持相对路径和绝对路径
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    content = _load_and_cache_file(file_path, session_id, store_id, runtime.store, runtime.tool_call_id)
    return Command(
        update={
            "file_chunk_read_progress": 1,
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )
@tool(description="""
【本地文件加载】通过文件ID加载本地文件并分块缓存。

**参数**：file_id - 文件ID或ID列表，用于查找文件路径

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个文件ID或ID列表，多个文件会统一分块返回一个 cache_id。
""")
def open_file_by_id(
    file_id: Union[str, List[str]],
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    文件加载工具（通过文件ID）

    通过文件ID从 store 中查找文件路径，加载内容后将文档分块存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。
    支持单个文件ID或ID列表，多个文件会统一分块返回一个cache_id。

    Args:
        file_id (Union[str, List[str]]): 必填 文件ID或ID列表，用于查找文件路径
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id, )
    # 通过 id 在 store 中查找文件路径,这个file_id是公用的，通过外部方法更新,传递给当前会话，只能当前会话看到
    # 数据格式 file_paths 是一个 dict{file_id_1: file_path_1, file_id_2: file_path_2, ...}
    file_paths_result = runtime.store.get(namespace, "file/registry")
    file_paths = file_paths_result.value if file_paths_result else None
    logging.info(f"file_paths: {file_paths}")
    
    ids = [file_id] if isinstance(file_id, str) else file_id
    logging.info(f"open_file_by_id获取得文件ID: {ids}")
    paths = []
    for fid in ids:
        path = file_paths.get(fid, None) if file_paths else None
        if path:
            paths.append(path)
    
    if not paths:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f'{{"error": "未找到任何有效的文件路径"}}',
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    content = _load_and_cache_file(paths, session_id, store_id, runtime.store, runtime.tool_call_id)
    return Command(
        update={
            "file_chunk_read_progress": 1,
            "messages": [
                ToolMessage(
                    content=content,
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool(description="""
【网页加载】加载网页URL内容并分块缓存。

**参数**：url - 网页URL或URL列表

**返回值**：cache_id（用于 read_cached_chunk 读取内容）

支持单个URL或URL列表，多个URL会统一分块返回一个 cache_id。
""")
def load_web_page(
    url: Union[str, List[str]],
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    网页加载工具

    加载指定URL的网页内容，将内容分块后存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。
    支持单个URL或URL列表，多个URL会统一分块返回一个cache_id。

    Args:
        url (Union[str, List[str]]): 必填 要加载的网页URL或URL列表
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    extract_type = "article"
    max_length = 1000000
    include_links = False
    session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    
    urls = [url] if isinstance(url, str) else url
    
    try:
        all_contents = []
        for u in urls:
            docs = DocumentLoader.load_url(
                url=u,
                extract_type=extract_type,
                max_length=max_length,
                include_links=include_links,
            )
            if docs:
                all_contents.append(f"=== URL: {u} ===\n" + "\n\n".join([doc.page_content for doc in docs]))
        
        if not all_contents:
            raise ValueError(f"未从任何URL加载到内容")
        
        full_content = "\n\n".join(all_contents)
        content = _cache_content(full_content, session_id, store_id, runtime.store)
        logging.info(f"load_web_page_content: {content}")
        return Command(
            update={
                "file_chunk_read_progress": 1,
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        logging.error(f"load_web_page_error: {e}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f'{{"error": "加载失败: {e}"}}',
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="""
【读取文档块】从缓存中读取文档内容。

**参数**：
- cache_id: 必填，缓存ID，由 open_file 返回
- start_index: 可选，开始块索引（从1开始），不传则顺序读取
- end_index: 可选，结束块索引，不传则顺序读取下一块

**返回值**：
- index: 当前块序号
- name: 进度标识，如 "2/5" 表示第2块/共5块
- content: 块内容
- is_last: 是否最后一块

**使用模式**：
1. 顺序读取（不传范围参数）：每次调用返回下一块，直到 is_last=True
2. 范围读取（传入起止索引）：返回指定范围的块内容，不追踪进度

**重要**：读取文档可能需要多次调用，is_last=True 时表示读完。
""")
def read_cached_chunk(
    cache_id: str,
    runtime: ToolRuntime[AgentContext],
    start_index: int = None,
    end_index: int = None,
) -> Command:
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)

    try:
        result = runtime.store.get(namespace, f"file/cache/{cache_id}")

        if not result or not result.value:
            raise ValueError(f"未找到缓存: {cache_id}")

        chunks = result.value
        total = len(chunks)

        is_range_read = start_index is not None and end_index is not None

        if is_range_read:
            if start_index < 1:
                start_index = 1
            if end_index > total:
                end_index = total
            if start_index > end_index:
                start_index, end_index = end_index, start_index

            chunk_range = chunks[start_index - 1:end_index]
            chunk_content = "\n\n".join(c.get("content", "") for c in chunk_range)

            content = json.dumps({
                "index": start_index,
                "name": f"{start_index}/{total}",
                "content": chunk_content,
                "is_last": end_index >= total,
                "total_chunks": total,
            }, ensure_ascii=False)
        else:
            progress_key = "file_chunk_read_progress"
            current_index = runtime.state.get(progress_key, 1)

            if current_index > total:
                content = json.dumps({
                    "status": "已读完",
                    "message": f"文档已全部读取完毕，共 {total} 块",
                    "is_last": True,
                }, ensure_ascii=False)
                return Command(
                    update={"messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]}
                )

            chunk = chunks[current_index - 1]
            is_last = current_index >= total

            content = json.dumps({
                "index": current_index,
                "name": f"{current_index}/{total}",
                "content": chunk.get("content", ""),
                "is_last": is_last,
                "total_chunks": total,
            }, ensure_ascii=False)

            return Command(
                update={
                    "file_chunk_read_progress": current_index + 1,
                    "messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]
                }
            )

        return Command(
            update={"messages": [ToolMessage(content=content, tool_call_id=runtime.tool_call_id)]}
        )

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"error": f"读取失败: {e}"}),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )