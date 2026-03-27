#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtTools - 合同审批Agent工具模块

该模块定义了合同审批Agent可用的工具函数，包括警告记录、审批检查和前置条件验证功能。

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


@tool(description="设置审批检查状态")
def check_approval(ischeck: bool, runtime: ToolRuntime) -> Command:
    """
    审批检查工具
    
    设置审批检查状态，标记审批是否通过。
    
    Args:
        ischeck (bool): 必填，审批状态（true=通过，false=未通过）
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
    """
    return Command(
        update={
            "is_check": ischeck,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "approval_checked",
                        "is_check": ischeck,
                        "result": "审批通过" if ischeck else "审批未通过"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool(description="获取已上传的审批要件清单。审批前必须首先调用此工具，返回已上传的合同、成交确认书、会议纪要等要件信息，用于判断是否具备审批条件。")
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    """
    前置条件验证工具
    
    获取当前session已上传的审批要件清单。遍历session_id对应的数据结构，
    返回已上传的要件类型（如：供地合同、成交确认书、会议纪要等）及其内容摘要。
    
    数据结构说明：
    {
        "session_id": {
            "要件类型名称": [
                {"index": "章节索引", "content": [{"question": "问题", "answer": "答案"}]}
            ]
        }
    }
    
    返回已上传的要件清单，空数组表示该要件未上传。
    
    Args:
        runtime (ToolRuntime): 工具运行时上下文，包含session_id和store
        
    Returns:
        Command: 包含已上传要件清单的命令对象
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
        requirement_details = {}
        
        for sid, requirements in all_sessions_data.items():
            if not isinstance(requirements, dict):
                continue
            
            for req_name, req_content in requirements.items():
                if isinstance(req_content, list) and len(req_content) > 0:
                    if req_name not in uploaded_requirements:
                        uploaded_requirements.append(req_name)
                    
                    if req_name not in requirement_details:
                        requirement_details[req_name] = {
                            "sessions": [],
                            "total_items": 0
                        }
                    
                    requirement_details[req_name]["sessions"].append(sid)
                    requirement_details[req_name]["total_items"] += len(req_content)
        
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
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "session_id": data_session_id,
                            "uploaded_requirements": uploaded_requirements,
                            "requirement_details": requirement_details,
                            "all_sessions_data": all_sessions_data,
                            "message": f"已获取要件清单，已上传: {', '.join(uploaded_requirements)}"
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


