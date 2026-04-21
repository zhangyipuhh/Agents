#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AICodingCheckTools - AI编码评审Agent工具模块

该模块定义了AI编码评审Agent可用的工具函数，包括开发者评审和评审结果解析功能。

工具清单：
1. review_developer - 评审开发者数据
2. parse_review_response - 解析评审响应

Date: 2026-04-21
Author: 张镒谱
"""

import json
import logging
from datetime import datetime
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.config import get_stream_writer
from app.core.tools.events import create_tool_event

# 模块级日志记录器
logger = logging.getLogger(__name__)

# 评审失败的默认结果模板，包含5个评审维度的初始值
# 当评审响应解析失败时，使用此模板作为兜底返回值
DEFAULT_REVIEW_RESULT = {
    "name": "",
    "review_time": "",
    "dimensions": {
        "document_quality": {"score": 0, "completeness": "", "clarity": "", "technical_accuracy": ""},
        "ai_adoption_rate": {"rate": 0.0, "analysis": ""},
        "duplicate_commits": {"has_duplicate": False, "duplicate_functions": [], "analysis": ""},
        "doc_code_sync": {"score": 0, "analysis": ""},
        "doc_task_sync": {"score": 0, "analysis": ""},
    },
    "overall_score": 0.0,
    "summary": "评审失败，返回默认结果",
}


@tool
def review_developer(
    name: str,
    content: str,
    code: str,
    task: str = "",
    runtime: ToolRuntime = None
) -> Command:
    """
    【评审开发者】评审开发者数据的工具。当Agent需要对开发者进行评审时调用。

    调用时机：
    - Agent收到开发者评审请求时
    - 需要对开发者的文档质量、AI采纳率、重复提交等进行评审时
    - 需要构建评审请求数据并更新评审状态时

    Args:
        name: 开发者姓名
        content: 开发者提交的文档内容
        code: 开发者提交的代码内容
        task: 开发者对应的任务描述（可选，默认为空字符串）
        runtime: 工具运行时上下文

    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - developer_data: 开发者评审请求数据
            - review_result: 评审结果状态
    """
    tool_name = "review_developer"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    # 发送工具开始执行的事件，用于流式输出追踪
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {
                "name": name,
                "content": content,
                "code": code,
                "task": task,
            },
            "description": f"开始评审开发者: {name}"
        }
    )
    writer(dict(start_event))

    # 构建开发者评审请求数据，包含开发者基本信息和评审时间
    developer_data = {
        "name": name,
        "content": content,
        "code": code,
        "task": task,
        "review_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    # 初始化评审结果状态为待评审，等待后续模型调用完成评审
    review_result = {
        "status": "pending",
        "name": name,
        "review_time": developer_data["review_time"],
        "message": f"开发者 {name} 的评审请求已构建，等待评审"
    }

    # 汇总工具执行结果数据
    result_data = {
        "status": "review_requested",
        "developer_data": developer_data,
        "review_result": review_result,
        "message": f"已构建开发者 {name} 的评审请求数据"
    }

    # 计算工具执行耗时
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # 发送工具执行完成事件，包含执行状态和耗时信息
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))

    # 构建工具执行摘要，包含完整的执行时间线和结果
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }

    # 返回Command对象，更新状态中的开发者数据和评审结果，同时发送工具消息
    return Command(
        update={
            "developer_data": developer_data,
            "review_result": review_result,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
                )
            ]
        }
    )


@tool
def parse_review_response(
    response_text: str,
    runtime: ToolRuntime = None
) -> Command:
    """
    【解析评审响应】解析评审响应的工具。当Agent需要解析模型返回的评审结果时调用。

    调用时机：
    - 模型返回评审结果文本后，需要将其解析为结构化数据时
    - 需要将JSON格式的评审响应转换为标准评审结果结构时
    - 评审响应解析失败时，需要返回默认评审结果时

    Args:
        response_text: 模型返回的评审结果文本，应为JSON格式
        runtime: 工具运行时上下文

    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - review_result: 解析后的评审结果，包含各维度评分和总评
    """
    tool_name = "parse_review_response"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    # 发送工具开始执行的事件
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {"response_text": response_text},
            "description": "开始解析评审响应"
        }
    )
    writer(dict(start_event))

    # 尝试将模型返回的JSON文本解析为结构化评审结果
    try:
        parsed_result = json.loads(response_text)
        review_result = parsed_result
        parse_status = "success"
        message = "评审响应解析成功"
    except (json.JSONDecodeError, TypeError) as e:
        # JSON解析失败时，使用默认评审结果模板作为兜底
        logger.warning(f"评审响应JSON解析失败: {e}")
        review_result = dict(DEFAULT_REVIEW_RESULT)
        # 补充当前评审时间到默认结果中
        review_result["review_time"] = start_time.strftime("%Y-%m-%d %H:%M:%S")
        parse_status = "parse_failed"
        message = f"评审响应解析失败，返回默认结果: {str(e)}"

    # 汇总解析结果数据
    result_data = {
        "status": parse_status,
        "review_result": review_result,
        "message": message
    }

    # 计算工具执行耗时
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)

    # 发送工具执行完成事件
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": parse_status,
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))

    # 构建工具执行摘要
    summary = {
        "status": parse_status,
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }

    # 返回Command对象，更新状态中的评审结果
    return Command(
        update={
            "review_result": review_result,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
                )
            ]
        }
    )
