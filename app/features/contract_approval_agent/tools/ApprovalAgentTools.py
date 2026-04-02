#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ApprovalAgentTools - 审批Agent工具模块

该模块定义了ApprovalAgent可用的工具函数，包括获取参考文件、获取合同内容、写入审批结果、获取审批规则和提取参考内容功能。

Date: 2026-03-19
Author: 张镒谱
"""

import json
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.store_schema import get_data_session_id, ApprovalResult


class ClauseDetail(BaseModel):
    """条款审批详情"""
    
    index: str = Field(description="条款编号，如'第一条'")
    error: str = Field(description="错误描述，空字符串表示该条款符合要求")
    clause: str = Field(description="条款内容，如'土地位置：xx市xx区'")
    suggestion: str = Field(description="修改建议，如'请确认土地位置是否正确'")
    reference_file_name: str = Field(description="参考文件名称，如'成交确认书'")
    reference_content: str = Field(description="参考文件中的具体内容")


class ApprovalDetails(BaseModel):
    """审批详细信息"""
    
    clauses: List[ClauseDetail] = Field(description="条款审批详情列表")


class ApprovalResultInput(BaseModel):
    """审批结果输入参数"""
    
    status: str = Field(
        description="审批状态，只能是 'approved'(通过) 或 'rejected'(拒绝)"
    )
    result: str = Field(
        description="审批结论的文字描述，说明审批通过或拒绝的原因"
    )
    details: Optional[ApprovalDetails] = Field(
        default=None,
        description="详细审批信息，包含条款详情列表"
    )


@tool(description="将合同审批结果保存到存储中，支持多次调用追加历史记录")
def write_approval_result(approval_result: ApprovalResultInput, runtime: ToolRuntime) -> Command:
    """
    保存合同条款审批结果工具
    
    保存合同条款审批结果到数据存储，每次调用会追加到历史记录中，不会覆盖之前的结果。
    
    Args:
        approval_result: 审批结果对象，包含状态、结论和详细信息
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含操作结果的命令对象
    
    Example:
        审批通过示例：
        {
            "status": "approved",
            "result": "第一条符合成交确认书要求，审批通过",
            "details": {
                "clauses": [{
                    "index": "第一条",
                    "error": "",
                    "reference_file_name": "成交确认书",
                    "reference_content": "土地位置：xx市xx区"
                }]
            }
        }
    """

    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)

    try:
        namespace = (store_id,)
        key = f"approval/result/{data_session_id}"

        result_data = approval_result.model_dump()
        status = result_data.get("status", "pending")
        result_text = result_data.get("result", "")
        details = result_data.get("details", None)

        approval_record = ApprovalResult(
            host_session_id=data_session_id,
            status=status,
            result=result_text,
            timestamp=datetime.now().isoformat(),
            details=details
        )

        existing_item = runtime.store.get(namespace, key)
        if existing_item and existing_item.value:
            if isinstance(existing_item.value, list):
                results_list = existing_item.value
            else:
                results_list = [existing_item.value]
        else:
            results_list = []

        results_list.append(approval_record.model_dump())

        runtime.store.put(namespace, key, results_list)

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "message": "审批结果已成功追加",
                            "namespace": f"({store_id},)",
                            "key": key,
                            "total_results": len(results_list)
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


@tool(description="根据条款编号获取审批规则")
def get_clause_approval_rules(clause_numbers: list, runtime: ToolRuntime) -> Command:
    """
    获取审批规则工具

    根据条款编号数组获取对应的审批规则，从APPROVAL_CLAUSES配置中筛选。

    【参数说明】
    - clause_numbers (list): 必填，条款编号数组，如 ["第一条", "第二条"]
    - runtime (ToolRuntime): 工具运行时上下文，包含：
        - tool_call_id: 工具调用ID，用于构建ToolMessage

    【返回值】
    Command: 包含ToolMessage的命令对象，message内容格式如下：
    - 成功时: {"status": "success", "rules": [...], "count": N, "message": "..."}
    - 部分成功时: {"status": "partial", "rules": [...], "missing_clauses": [...], "message": "..."}
    - 错误时: {"status": "error", "error": "错误信息"}

    【调用时机】
    - 接收到审批条款编号数组后调用
    - 仅在审批流程开始时调用一次

    【注意事项】
    - 获取成功后，不要重复调用
    - 如果部分条款未找到规则，会返回partial状态
    """
    try:
        from app.features.contract_approval_agent.config.prompts import APPROVAL_CLAUSES

        rules = []
        for clause in APPROVAL_CLAUSES:
            if clause["index"] in clause_numbers:
                rules.append(clause)

        missing = [c for c in clause_numbers if c not in [r["index"] for r in rules]]
        if missing:
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "partial",
                                "rules": rules,
                                "missing_clauses": missing,
                                "message": f"找到 {len(rules)} 条审批规则，未找到以下条款: {', '.join(missing)}"
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
                            "rules": rules,
                            "count": len(rules),
                            "message": f"已获取 {len(rules)} 条审批规则"
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
                            "error": f"获取审批规则失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="提取所有参考文件内容")
def extract_all_reference_content(runtime: ToolRuntime) -> Command:
    """
    提取参考内容工具

    从store中获取所有参考文件内容，返回提取结果供审批使用。

    【参数说明】
    - runtime (ToolRuntime): 工具运行时上下文，包含：
        - store_id: 存储ID，从context中获取，默认值为'default'
        - data_session_id: 数据会话ID，用于构建存储键
        - store: 存储对象，用于读写数据
        - tool_call_id: 工具调用ID，用于构建ToolMessage

    【返回值】
    Command: 包含ToolMessage的命令对象，message内容格式如下：
    - 成功时: {"status": "success", "key": "...", "content": {...}, "message": "..."}
    - 未找到时: {"status": "not_found", "error": "未找到参考文件内容"}
    - 错误时: {"status": "error", "error": "错误信息"}

    【调用时机】
    - 获取审批规则后调用
    - 需要查找审批依据时调用
    - 仅在审批流程中调用一次

    【注意事项】
    - 获取成功后，不要重复调用
    - 返回的content中不包含"供地合同"文档
    - 返回的documents对象包含各参考文件的提取内容
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
                                "error": "未找到参考文件内容"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )

        ref_content = result.value

        documents = ref_content.get("documents", {})
        if "供地合同" in documents:
            del documents["供地合同"]

        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "key": f"extraction/ref/{data_session_id}",
                            "content": documents,
                            "message": "已获取参考文件内容"
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
                            "error": f"提取参考内容失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
