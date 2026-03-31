#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtTools - 合同审批Agent工具模块

该模块定义了合同审批Agent可用的工具函数，包括警告记录、审批检查、前置条件验证、条款查询和审批结果获取功能。

Date: 2026-03-17
Author: 张镒谱
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.store_schema import get_data_session_id


@tool(description="当审批要求不满足时记录问题")
def warn_issue(issue_description: str, runtime: ToolRuntime) -> Command:
    """
    警告问题工具

    当审批要求不满足时记录问题描述，将问题写入状态中的警告消息字段。

    Args:
        issue_description (str): 必填，问题描述内容
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
    """
    return Command(
        update={
            "warn_message": issue_description,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "warning_recorded",
                        "issue": issue_description
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool(description="通知下一个智能体开始审批流程")
def check_approval(ischeck: bool, runtime: ToolRuntime) -> Command:
    """
    审批通知工具

    当主智能体确认所有前置条件满足后，调用该工具通知审批智能体可以开始审批流程。
    该工具仅发送通知信号，实际审批由 ApprovalAgent 独立完成。

    Args:
        ischeck (bool): 必填，审批就绪状态（true=就绪，false=未就绪）
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)
    namespace = (store_id,)
    runtime.store.put(namespace, f"approval/ready/{data_session_id}", ischeck)
    return Command(
        update={
            "is_check": ischeck,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "approval_notification_sent",
                        "is_check": ischeck,
                        "result": "已通知审批智能体"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool(description="根据条款编号获取合同条款内容")
def get_contract_clause_content(clause_numbers: list, runtime: ToolRuntime) -> Command:
    """
    获取合同条款内容工具

    根据条款编号数组获取合同中对应条款的内容。

    Args:
        clause_numbers (list): 必填，条款编号数组，如 ["第一条", "第二条"]
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含条款内容的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)

    try:
        namespace = (store_id,)
        result = runtime.store.get(namespace, f"contract/paragraph/{data_session_id}")

        if not result or not result.value:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "not_found",
                                "error": "未找到合同段落数据"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        paragraph_data = result.value

        if not isinstance(paragraph_data, dict):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "invalid_format",
                                "error": "数据格式错误，期望字典结构"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        clause_contents = []
        for clause_index in clause_numbers:
            if clause_index in paragraph_data:
                clause_contents.append({
                    "index": clause_index,
                    "content": paragraph_data[clause_index]
                })
            else:
                clause_contents.append({
                    "index": clause_index,
                    "content": None,
                    "error": "未找到该条款"
                })

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "session_id": data_session_id,
                            "clause_contents": clause_contents
                        }, ensure_ascii=False),
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
                        content=json.dumps({
                            "status": "error",
                            "error": f"获取合同条款内容失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="获取合同审批结果")
def get_approval_result(runtime: ToolRuntime) -> Command:
    """
    获取审批结果工具

    从store中获取合同审批结果，返回给大模型处理。

    Args:
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含审批结果的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)

    try:
        namespace = (store_id,)
        result = runtime.store.get(namespace, f"approval/result/{data_session_id}")

        if not result or not result.value:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "not_found",
                                "error": "未找到审批结果"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        approval_result = result.value

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "session_id": data_session_id,
                            "approval_result": approval_result
                        }, ensure_ascii=False),
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
                        content=json.dumps({
                            "status": "error",
                            "error": f"获取审批结果失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="获取已上传的审批要件清单。审批前必须首先调用此工具，返回当前 session 下已上传的要件类型及数量，供大模型判断是否具备审批条件。")
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    """
    前置条件验证工具

    获取当前 session 已上传的审批要件清单。返回已上传的要件类型（如：供地合同、成交确认书、会议纪要等）
    及其数量摘要，不返回完整内容。当要件齐全时，更新 store 中的 approval/ready/{hsid} 字段。

    数据结构说明：
    {
        "session_id": {
            "要件类型名称": [
                {"index": "章节索引", "content": [{"question": "问题", "answer": "答案"}]}
            ]
        }
    }

    返回已上传的要件清单及数量摘要。

    Args:
        runtime (ToolRuntime): 工具运行时上下文，包含session_id和store

    Returns:
        Command: 包含已上传要件清单摘要的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)
    try:
        namespace = (store_id,)
        store_result = runtime.store.get(namespace, f"approval/prereq/{data_session_id}")

        if not store_result or not store_result.value:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "no_documents",
                                "session_id": data_session_id,
                                "uploaded_requirements": [],
                                "message": "未找到任何已上传的要件文档，请先上传审批所需材料"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        all_sessions_data = store_result.value

        if not isinstance(all_sessions_data, dict):
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "invalid_format",
                                "error": "数据格式错误，期望字典结构"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        uploaded_requirements = []
        requirement_summary = {}

        for sid, requirements in all_sessions_data.items():
            if not isinstance(requirements, dict):
                continue

            for req_name, req_content in requirements.items():
                if isinstance(req_content, list) and len(req_content) > 0:
                    if req_name not in uploaded_requirements:
                        uploaded_requirements.append(req_name)
                        requirement_summary[req_name] = 0

                    requirement_summary[req_name] += len(req_content)

        if not uploaded_requirements:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "no_requirements",
                                "session_id": data_session_id,
                                "uploaded_requirements": [],
                                "message": "所有要件均为空，请先上传审批所需材料（如：供地合同、成交确认书、会议纪要等）"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )



        message_parts = [f"{name}({count}份)" for name, count in requirement_summary.items()]
        message = f"已获取要件清单，已上传: {', '.join(message_parts)}"

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "session_id": data_session_id,
                            "uploaded_requirements": uploaded_requirements,
                            "requirement_summary": requirement_summary,
                            "approval_ready": True,
                            "message": message
                        }, ensure_ascii=False),
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
                        content=json.dumps({
                            "status": "error",
                            "error": f"获取要件清单失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
