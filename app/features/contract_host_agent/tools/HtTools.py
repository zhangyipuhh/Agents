#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtTools - 合同审批Agent工具模块

该模块定义了合同审批Agent可用的工具函数，包括警告记录、审批检查、前置条件验证、条款查询和审批结果获取功能。

工具清单：
1. warn_issue - 记录审批问题
2. check_approval - 通知审批智能体开始审批
3. get_contract_clause_content - 获取合同条款内容
4. get_approval_result - 获取合同审批结果（重点工具）
5. validate_prerequisites - 验证前置条件

Date: 2026-03-17
Author: 张镒谱
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.store_schema import get_data_session_id


@tool
def warn_issue(issue_description: str, runtime: ToolRuntime) -> Command:
    """
    【记录审批问题】记录审批过程中发现的问题。
    
    调用时机：
    - 审批过程中发现合同存在不符合要求的问题时
    - 需要记录问题的类型、具体描述、建议解决方案时
    
    Args:
        issue_description: 问题描述内容，需包含：
            - 问题类型（如：条款缺失、内容不符、格式错误等）
            - 具体描述（详细说明问题所在）
            - 建议解决方案（如何修改以符合要求）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "warning_recorded" - 问题已记录
            - issue: 问题描述内容
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


@tool
def check_approval(ischeck: bool, runtime: ToolRuntime) -> Command:
    """
    【启动审批流程】通知审批智能体开始审批流程。
    
    调用时机：
    - 用户明确表示"开始审批"、"请审批"、"可以审批了"时
    - 用户确认"可以"、"是的"、"开始吧"、"准备好了"等同意审批时
    - 要件验证通过后，用户同意启动审批时
    
    Args:
        ischeck: 审批就绪状态（true=就绪，false=未就绪）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "approval_notification_sent" - 通知已发送
            - is_check: 审批就绪状态
            - result: "已通知审批智能体"
    
    注意：此工具仅发送通知信号，实际审批由审批智能体独立完成。
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


@tool
def get_contract_clause_content(clause_numbers: list, runtime: ToolRuntime) -> Command:
    """
    【获取合同条款】根据条款编号获取合同条款内容。
    
    调用时机：
    - 需要查看特定条款内容时
    - 进行条款比对分析时
    
    Args:
        clause_numbers: 条款编号数组，如 ["第一条", "第二条", "第三条"]
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含条款内容的命令对象
            - status: 查询状态（success/not_found/invalid_format/error）
            - session_id: 数据会话ID
            - clause_contents: 条款内容列表，每项包含：
                * index: 条款编号
                * content: 条款内容（如未找到则为 null）
                * error: 错误信息（如未找到该条款）
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


@tool
def get_approval_result(runtime: ToolRuntime) -> Command:
    """
    【获取审批结果】获取合同审批分析结果报告。
    
    调用时机：
    - 用户说"审批完成"、"输出审批结果"、"查看审批结果"、"获取审批报告"时
    - 用户询问"审批结果如何"、"审批怎么样"时
    - 用户确认"可以"、"是的"、"开始吧"等表示同意审批时
    
    Args:
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含审批结果的命令对象
            - status: 获取状态（success/not_found/error）
            - session_id: 数据会话ID
            - approval_result: 审批结果数据，包含：
                * 比对结果
                * 风险点列表
                * 修改建议
                * 审批结论
    
    重要：这是获取审批结论的核心工具，当用户要求查看审批结果时必须调用此工具。
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

        approval_result = [item.get("details") for item in result.value] if isinstance(result.value, list) else result.value.get("details")

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


@tool
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    """
    【验证审批要件】获取已上传的审批要件清单，验证是否具备审批条件。
    
    调用时机：
    - 每次执行审批任务时必须首先调用此工具
    - 用户上传文件后，需要验证要件是否齐全时
    
    Args:
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含已上传要件清单摘要的命令对象
            - status: 获取状态（success/no_documents/no_requirements/invalid_format/error）
            - session_id: 数据会话ID
            - uploaded_requirements: 已上传的要件类型列表
            - requirement_summary: 各类型要件数量统计
            - approval_ready: 是否具备审批条件（true/false）
            - message: 友好的提示信息
    
    强制要求：
    - 必须同时满足以下两个条件才能审批：
        1. 供地合同已上传
        2. 至少1份参考文件已上传（成交确认书、会议纪要等）
    
    重要：这是审批流程的第一步，必须首先调用。
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
