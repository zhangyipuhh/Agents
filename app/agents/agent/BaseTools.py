#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
BaseTools - Agent基础工具模块

该模块定义了Agent可用的基础工具函数，包括获取当前时间、文件加载和文档分块读取功能。

设计核心原则：不要让 AI 看到它可能想解释的东西。状态码 + 系统规则 > 自然语言描述。

Date: 2026-03-13
Author: 张镒谱
"""

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
from app.agents.agent.AgentContext import AgentContext
from app.utils.files.DocumentLoader import DocumentLoader





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
    namespace = (store_id, session_id)

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


def _load_and_cache_file(
    file_path: Union[str, Path],
    session_id: str,
    store_id: str,
    store: any,
    tool_call_id: str,
) -> str:
    """
    加载文件内容并缓存到 store

    Args:
        file_path: 文件路径
        session_id: 会话 ID
        store_id: 存储 ID
        store: store 实例
        tool_call_id: 工具调用 ID，用于返回 ToolMessage

    Returns:
        Command: 包含缓存结果或错误信息
    """
    glob = "**/*"

    try:
        path = Path(file_path)

        if not path.exists():
            raise FileNotFoundError(f"文件或文件夹不存在: {file_path}")

        loader = DocumentLoader(
            path=path,
            glob=glob,
            silent_errors=True,
        )

        docs = loader.load()

        if not docs:
            raise ValueError(f"未加载到任何内容: {file_path}")

        full_content = "\n\n".join([doc.page_content for doc in docs])
        return _cache_content(full_content, session_id, store_id, store)

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f'{{"error": "加载失败: {e}"}}',
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )


def _cache_content(
    content: str,
    session_id: str,
    store_id: str,
    store: any,
    chunk_size: int = 4000,
    chunk_overlap: int = 200,
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
    
    content=json.dumps({
                        "cache_id": file_id,
                        "status": "cached",  # 改为简洁状态
                        "total_chunks": len(chunks),
                        "next_tool": "read_cached_chunk",  # 明确工具名
                        "next_step": f"请调用 read_cached_chunk 工具，传入 cache_id='{file_id}' 读取第1块内容"
                    }, ensure_ascii=False)
    # 初始化文件读取进度为1
    return content


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


@tool(description="""
【本地文件加载】加载本地文件（PDF/Word/CSV等）并分块缓存。
⚠️ 这是第一步：通过物理路径加载文件。加载后必须使用 read_cached_chunk 读取内容。
返回 cache_id，用于后续 read_cached_chunk 调用。
""")
def open_file(
    file_path: Union[str, Path],
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    文件加载工具

    智能识别文件类型并加载内容，将文档分块后存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。

    Args:
        file_path (Union[str, Path]): 必填 文件或文件夹路径，支持相对路径和绝对路径
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
【本地文件加载】加载本地文件（PDF/Word/CSV等）并分块缓存。
⚠️ 这是第一步：通过文件ID加载文件。加载后必须使用 read_cached_chunk 读取内容。
返回 cache_id，用于后续 read_cached_chunk 调用。
""")
def open_file_by_id(
    file_id: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    文件加载工具（通过文件ID）

    通过文件ID从 store 中查找文件路径，加载内容后将文档分块存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。

    Args:
        file_id (str): 必填 文件ID，用于查找文件路径
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息

    Returns:
        str: JSON格式结果，包含 file_name 和状态信息
    """
    session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id, session_id)
    # 通过 id 在 store 中查找文件路径,这个file_id是公用的，通过外部方法更新,传递给当前会话，只能当前会话看到
    # 数据格式 file_paths 是一个 dict{file_id_1: file_path_1, file_id_2: file_path_2, ...}
    file_paths = runtime.store.get(namespace, "file_id", default=None)
    # 从 file_paths 中查找 file_id 对应的文件路径
    file_path = file_paths.get(file_id, None) if file_paths else None

    

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
【网页加载】加载网页URL内容并分块缓存。  
⚠️ 这是第一步：加载网页。加载后必须使用 read_cached_chunk 读取内容。
返回 cache_id，用于后续 read_cached_chunk 调用。
""")
def load_web_page(
    url: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
    """
    网页加载工具

    加载指定URL的网页内容，将内容分块后存入存储，返回文件ID。
    需要使用 read_cached_chunk 工具逐块读取内容。

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
    store_id = runtime.context.get('store_id', 'default')
    try:
        docs = DocumentLoader.load_url(
            url=url,
            extract_type=extract_type,
            max_length=max_length,
            include_links=include_links,
        )

        if not docs:
            raise ValueError(f"未从 {url} 加载到任何内容")
        
        full_content = "\n\n".join([doc.page_content for doc in docs])
        content = _cache_content(full_content, session_id, store_id, runtime.store)
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
【第二步-读取缓存】读取已缓存文档的分块内容。
前置条件：必须先调用 open_file 或 load_web_page 获取 cache_id。
行为：每次调用返回一块，自动推进进度，is_last=true 时表示读完。
""")
def read_cached_chunk(
    cache_id: str,
    runtime: ToolRuntime[AgentContext],
) -> Command:
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
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id, session_id)

    try:
        # 从 store 获取文档数据 (使用 runtime.store)
        result = runtime.store.get(namespace, cache_id)

        if not result or not result.value:
            raise ValueError(f"未找到缓存: {cache_id}")

        chunks = result.value

        # 查找当前应该返回的块（找到第一个未读的）
        # 通过检查 state 中的读取进度
        progress_key = f"file_chunk_read_progress"
        current_index = runtime.state.get(progress_key, 1)

        if current_index > len(chunks):
            return r'{{"status": "已读完", "message": "文档已全部读取完毕，共 {len(chunks)} 块"}}'

        # 获取当前块
        chunk = chunks[current_index - 1]

        # 判断是否最后一块
        is_last = current_index == len(chunks)

        # 准备返回内容
        content = json.dumps({
            "index": chunk["index"],
            "name": chunk["name"],
            "content": chunk["content"],
            "is_last": is_last,
            "next_tool": None if is_last else "read_cached_chunk",
            "next_step": "文档读取完毕" if is_last else f"继续调用 read_cached_chunk(cache_id='{cache_id}') 读取下一块"
        }, ensure_ascii=False)

        # 使用 Command 返回工具结果和状态更新
        # update 参数用于更新 state 中的字段
        # 注意：messages 需要使用 ToolMessage，且需要 tool_call_id
        return Command(
            update={
                "file_chunk_read_progress": current_index + 1,
                # 可以添加更多状态更新字段
                # "last_read_time": datetime.now().isoformat(),
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"error": f"读取失败: {e}"}),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )
@tool(description="""
【读取部分缓存】读取已缓存文档的部分内容。
前置条件：提示词中明确指定要调用的方法。
""")
def read_cached_chunk_range(
    cache_id: str,
    runtime: ToolRuntime[AgentContext],
    start_index: int=1,
    end_index: int=1,
) -> Command:
    """
    该工具需要有明确调用的场景，通常不使用。
    读取指定范围的文档内容。
    start_index 为开始索引，end_index 为结束索引。

    Args:
        cache_id (str): 缓存ID，由 open_file 或 load_web_page 返回
        runtime (ToolRuntime[AgentContext]): 工具运行时上下文，包含会话信息
        start_index (int): 开始索引，默认1
        end_index (int): 结束索引，默认1

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


        if end_index > len(chunks):
            end_index = len(chunks)
        chunk_range = chunks[start_index - 1:end_index]

        chunk_content = ""
        for c in chunk_range:
            chunk_content += c["content"]

        # 准备返回内容
        content = json.dumps({
            "index": start_index,
            "name": f"第{start_index}至第{end_index}块节",
            "content": chunk_content,
            "is_last": True,
            "next_tool":  None,
            "next_step": "文档读取完毕" 
        }, ensure_ascii=False)

        # 使用 Command 返回工具结果和状态更新
        # update 参数用于更新 state 中的字段
        # 注意：messages 需要使用 ToolMessage，且需要 tool_call_id
        return Command(
            update={
                # 可以添加更多状态更新
                # "last_read_time": datetime.now().isoformat(),
                "messages": [
                    ToolMessage(
                        content=content,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({"error": f"读取失败: {e}"}),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )