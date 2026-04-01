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


@tool(description="记录审批过程中发现的问题")
def warn_issue(issue_description: str, runtime: ToolRuntime) -> Command:
    """
    警告问题工具 - 记录审批过程中发现的问题

    【工具用途】
    当审批过程中发现合同存在不符合要求的问题时，使用此工具记录问题详情。
    【调用时机】
    - 在分析合同内容后，发现不符合审批要求的问题时
    - 需要记录问题的类型、具体描述、建议解决方案时

    【参数说明】
    - issue_description (str): 问题描述内容，需包含：
      * 问题类型（如：条款缺失、内容不符、格式错误等）
      * 具体描述（详细说明问题所在）
      * 建议解决方案（如何修改以符合要求）

    【返回值】
    返回 Command 对象，包含：
    - status: "warning_recorded" - 问题已记录
    - issue: 问题描述内容

    【使用示例】
    当发现合同条款与成交确认书不符时：
    issue_description = "条款不符：第三条付款方式与成交确认书不一致，建议修改为..."

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


@tool(description="通知审批智能体开始审批流程")
def check_approval(ischeck: bool, runtime: ToolRuntime) -> Command:
    """
    审批通知工具 - 通知审批智能体开始审批流程

    【工具用途】
    当主智能体确认所有前置条件满足后，调用此工具通知审批智能体可以开始审批流程。
    该工具仅发送通知信号，实际审批由 ApprovalAgent 独立完成。

    【调用时机】
    - 当用户确认所有前置条件满足，表示"可以开始审批"时
    - 当用户发送表示"审批完成"、"确认审批结果"、"同意"等确认性话语时

    【参数说明】
    - ischeck (bool): 审批就绪状态
      * true: 前置条件已满足，通知审批智能体开始审批
      * false: 前置条件未满足，暂缓审批

    【返回值】
    返回 Command 对象，包含：
    - status: "approval_notification_sent" - 通知已发送
    - is_check: 审批就绪状态
    - result: "已通知审批智能体"

    【注意事项】
    - 此工具仅在最终确认阶段使用
    - 调用前需确保用户已明确表示同意审批

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
    获取合同条款内容工具 - 根据条款编号获取合同条款内容

    【工具用途】
    根据条款编号数组获取合同中对应条款的内容，用于核对合同条款与参考文件的一致性。

    【调用时机】
    - 需要查看特定条款内容时
    - 进行条款比对分析时

    【参数说明】
    - clause_numbers (list): 条款编号数组，如 ["第一条", "第二条", "第三条"]

    【返回值】
    返回 Command 对象，包含：
    - status: "success" - 查询成功
    - session_id: 数据会话ID
    - clause_contents: 条款内容列表，每项包含：
      * index: 条款编号
      * content: 条款内容（如未找到则为 null）
      * error: 错误信息（如未找到该条款）

    【可能的状态】
    - success: 查询成功
    - not_found: 未找到合同段落数据
    - invalid_format: 数据格式错误
    - error: 查询过程发生错误

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
    获取审批结果工具 - 获取合同审批结果

    【工具用途】
    从系统中获取合同审批分析结果，返回给大模型处理。这是获取审批结论的核心工具。

    【调用时机 - 重要】
    当检测到用户意图想要获取审批结果时调用，包括但不限于以下表达：
    - "可以"、"是的"、"开始吧"
    - "准备好了"、"开始审批"、"请审批"
    - "查看审批结果"、"获取审批结果"
    - "分析一下"、"审批一下"

    【参数说明】
    无参数，自动从当前 session 中获取审批结果

    【返回值】
    返回 Command 对象，包含：
    - status: "success" - 获取成功
    - session_id: 数据会话ID
    - approval_result: 审批结果数据，包含：
      * 比对结果
      * 风险点列表
      * 修改建议
      * 审批结论

    【可能的状态】
    - success: 获取成功
    - not_found: 未找到审批结果
    - error: 获取过程发生错误

    【使用场景】
    1. 用户上传合同文件后表示"开始审批"
    2. 用户主动询问"审批结果如何"
    3. 用户确认要件齐全后要求"进行审批"

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


@tool(description="获取已上传的审批要件清单")
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    """
    前置条件验证工具 - 获取已上传的审批要件清单

    【工具用途】
    审批前必须首先调用此工具，返回当前 session 下已上传的要件类型及数量，供大模型判断是否具备审批条件。

    【调用时机】
    - 每次执行审批任务时必须首先调用此工具
    - 验证合同审批所需的关键要件是否齐全

    【参数说明】
    无参数，自动从当前 session 中获取要件清单

    【返回值】
    返回 Command 对象，包含：
    - status: "success" - 获取成功
      * session_id: 数据会话ID
      * uploaded_requirements: 已上传的要件类型列表
      * requirement_summary: 各类型要件数量统计
      * approval_ready: 是否具备审批条件
      * message: 友好的提示信息

    - status: "no_documents" - 未找到任何文档
    - status: "no_requirements" - 所有要件为空
    - status: "invalid_format" - 数据格式错误
    - status: "error" - 获取过程发生错误

    【数据结构说明】
    存储的数据结构为：
    {
        "session_id": {
            "要件类型名称": [
                {"index": "章节索引", "content": [{"question": "问题", "answer": "答案"}]}
            ]
        }
    }

    【验证内容】
    - 合同信息是否已完整上传
    - 所有必要的参考信息是否已完整上传
    - 返回要件完整性状态、缺失项详情

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
