#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
BaseTools - Agent基础工具模块

该模块定义了Agent可用的基础工具函数，包括获取当前时间和文件加载功能。

Date: 2026-03-13
Author: 张镒谱
"""

from datetime import datetime
from pathlib import Path
from typing import Union, ClassVar
from langchain.tools import tool, ToolRuntime


class BaseTools:
    TOOL_NAMES: ClassVar[list[str]] = [
        "get_current_time",
        "open_file",
        "load_web_page",
    ]

    @staticmethod
    def get_tool_names() -> list[str]:
        return BaseTools.TOOL_NAMES

    @staticmethod
    def get_tools() -> list:
        from app.agents.agent.BaseTools import get_current_time, open_file, load_web_page
        return [get_current_time, open_file, load_web_page]

    

@tool(description="获取当前时间")
def get_current_time(runtime: ToolRuntime) -> str:
    """
    获取当前时间工具

    返回当前系统时间字符串，格式为 YYYY-MM-DD HH:MM:SS，并附带会话ID。
    用于Agent了解当前时间上下文，支持时间敏感的任务处理。

    Args:
        runtime (ToolRuntime): 工具运行时上下文，包含会话信息

    Returns:
        str: 格式化的时间字符串，格式 "YYYY-MM-DD HH:MM:SS (session_id: xxx)"
    """
    current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    return current_time + f" (session_id: {runtime.context.get('session_id', 'default')})"


@tool(description="打开并读取文件内容，支持文本、PDF、Word、CSV、JSON、Markdown等格式")
def open_file(
    file_path: Union[str, Path],
    runtime: ToolRuntime,
) -> str:
    """
    文件加载工具

    智能识别文件类型并加载内容，支持单个文件或文件夹批量加载。

    Args:
        file_path (Union[str, Path]): 必填 文件或文件夹路径，支持相对路径和绝对路径
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        str: 加载结果字符串，包含文档内容或错误信息
    """
    glob = "**/*"

    try:
        path = Path(file_path)

        if not path.exists():
            return f"❌ 文件或文件夹不存在: {file_path}"

        loader = DocumentLoader(
            path=path,
            glob=glob,
            silent_errors=True,
        )

        docs = loader.load()

        if not docs:
            return f"⚠️ 未加载到任何内容: {file_path}"

        result_parts = [f"✅ 成功加载 {len(docs)} 个文档片段:\n"]

        for doc in docs:
            result_parts.append(doc.page_content)
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"❌ 加载失败: {e}"


@tool(description="加载指定URL的网页内容")
def load_web_page(
    url: str,
    runtime: ToolRuntime,
) -> str:
    """
    网页加载工具

    加载指定URL的网页内容。

    Args:
        url (str): 必填 要加载的网页URL ，需要读取url内容时使用
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        str: 加载的网页内容
    """
    extract_type = "article"
    max_length = 1000000
    include_links = False
    try:
        docs = DocumentLoader.load_url(
            url=url,
            extract_type=extract_type,
            max_length=max_length,
            include_links=include_links,
        )

        if not docs:
            return f"⚠️ 未从 {url} 加载到任何内容"

        result_parts = [f"✅ 成功加载 {len(docs)} 个文档片段:\n"]

        for doc in docs:
            result_parts.append(doc.page_content)
            result_parts.append("")

        return "\n".join(result_parts)

    except Exception as e:
        return f"❌ 加载网页失败: {e}"