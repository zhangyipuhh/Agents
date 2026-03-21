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


@tool(description="验证合同审批前置条件，必须首先调用")
def validate_prerequisites(runtime: ToolRuntime) -> Command:
    """
    前置条件验证工具
    
    验证合同审批的前置条件，检查store中存储的合同参考文档内容。
    检查store结构格式是否为 {"ht": [chunk1, chunk2, ...], "[非中文文档名]": [chunk1, chunk2, ...]}
    
    Args:
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和验证结果的命令对象
    """
    session_id = runtime.context.get('session_id', 'default')
    
    try:
        store_data = {}
        namespace = (f"{session_id}_ht",)
        
        ht_result = runtime.store.get(namespace, "ht")
        if ht_result and ht_result.value:
            store_data["ht"] = ht_result.value
        
        all_items = runtime.store.search(namespace)
        for item in all_items:
            if item.key != "ht":
                store_data[item.key] = item.value
        
        if not store_data:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "validation_failed",
                                "error": "store中没有找到任何合同参考文档内容"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )
        
        validation_errors = []
        
        for doc_name, chunks in store_data.items():
            if not isinstance(chunks, list):
                validation_errors.append(f"文档'{doc_name}'的chunks不是列表格式")
                continue
            
            for i, chunk in enumerate(chunks):
                if not isinstance(chunk, dict):
                    validation_errors.append(f"文档'{doc_name}'的第{i+1}块不是字典格式")
                elif "content" not in chunk:
                    validation_errors.append(f"文档'{doc_name}'的第{i+1}块缺少content字段")
        
        if validation_errors:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "validation_failed",
                                "errors": validation_errors,
                                "store_structure": list(store_data.keys())
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )
        
        doc_summary = {}
        for doc_name, chunks in store_data.items():
            doc_summary[doc_name] = {
                "total_chunks": len(chunks),
                "has_content": all("content" in chunk for chunk in chunks if isinstance(chunk, dict))
            }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "validation_passed",
                            "session_id": session_id,
                            "documents": doc_summary,
                            "message": "前置条件验证通过，可以继续审批流程"
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
                            "status": "validation_error",
                            "error": f"验证过程发生错误: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
