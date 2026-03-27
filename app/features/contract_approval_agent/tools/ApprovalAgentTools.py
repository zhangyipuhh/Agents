#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocTools - ApprovalAgent工具模块

该模块定义了ApprovalAgent可用的工具函数，包括获取参考文件、获取合同内容和写入审批结果功能。

Date: 2026-03-19
Author: 张镒谱
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.store_schema import get_data_session_id


@tool(description="从store中获取参考文件内容")
def get_reference_files(runtime: ToolRuntime) -> Command:
    """
    获取参考文件工具
    
    从store中获取参考文件内容，使用namespace为(store_id,)和extraction/ref/{data_session_id}键查找参考文件。
    
    Args:
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和参考文件内容的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)
    
    try:
        namespace = (store_id,)
        result = runtime.store.get(namespace, f"extraction/ref/{data_session_id}")
        
        if not result or not result.value:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "not_found",
                                "error": f"未找到参考文件"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )
        
        file_content = result.value
        
        if isinstance(file_content, list):
            content_info = {
                "status": "success",
                "key": f"extraction/ref/{data_session_id}",
                "type": "chunks",
                "total_chunks": len(file_content),
                "content": file_content
            }
        else:
            content_info = {
                "status": "success",
                "key": f"extraction/ref/{data_session_id}",
                "type": "single",
                "content": file_content
            }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(content_info, ensure_ascii=False),
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
                            "error": f"获取参考文件失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="从store中获取合同内容")
def get_contract_content(runtime: ToolRuntime) -> Command:
    """
    获取合同内容工具
    
    从store中获取合同内容，使用namespace为(store_id,)和contract/path/{data_session_id}键查找合同路径。
    
    Args:
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和合同内容的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)
    
    try:
        namespace = (store_id,)
        result = runtime.store.get(namespace, f"contract/path/{data_session_id}")
        
        if not result or not result.value:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "not_found",
                                "error": "未找到合同路径"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )
        
        contract_content = result.value
        
        if isinstance(contract_content, list):
            content_info = {
                "status": "success",
                "key": f"contract/path/{data_session_id}",
                "type": "chunks",
                "total_chunks": len(contract_content),
                "content": contract_content
            }
        else:
            content_info = {
                "status": "success",
                "key": f"contract/path/{data_session_id}",
                "type": "single",
                "content": contract_content
            }
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps(content_info, ensure_ascii=False),
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
                            "error": f"获取合同内容失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="将审批结果写入store")
def write_approval_result(result_content: str, runtime: ToolRuntime) -> Command:
    """
    写入审批结果工具
    
    将审批结果写入store，使用namespace为(store_id,)和approval/result/{data_session_id}键存储结果。
    
    Args:
        result_content (str): 必填，审批结果内容
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和写入状态的命令对象
    """
    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)
    
    try:
        namespace = (store_id,)
        
        runtime.store.put(namespace, f"approval/result/{data_session_id}", result_content)
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "message": "审批结果已成功写入",
                            "namespace": f"({store_id},)",
                            "key": f"approval/result/{data_session_id}"
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
                            "error": f"写入审批结果失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
