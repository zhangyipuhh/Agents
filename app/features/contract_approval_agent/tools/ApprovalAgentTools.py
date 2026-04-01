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
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.store_schema import get_data_session_id, ApprovalResult


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


@tool(description="将合同审批结果保存到存储中，支持多次调用追加历史记录")
def write_approval_result(result_content: str, runtime: ToolRuntime) -> Command:
    """
    【工具用途】
    保存合同条款审批结果到数据存储，每次调用会追加到历史记录中，不会覆盖之前的结果。

    【何时使用】
    - 完成一个或多个条款的审批后，需要记录审批结论时调用
    - 可以多次调用，每次审批完成后都应及时保存结果

    【参数说明】
    result_content: JSON字符串，包含审批结果，必须包含以下字段：
      - status (必填): 审批状态，只能是 "approved"(通过) 或 "rejected"(拒绝)
      - result (必填): 审批结论的文字描述，说明审批通过或拒绝的原因
      - details (可选): 详细审批信息，包含 clauses 数组，每个条款包含：
          - index: 条款编号，如"第一条"
          - error: 错误描述，空字符串表示该条款符合要求
          - reference_file_name: 参考文件名称，如"成交确认书"
          - reference_content: 参考文件中的具体内容

    【使用示例】
    审批通过示例：
    {
        "status": "approved",
        "result": "第一条符合成交确认书要求，审批通过",
        "details": {
            "clauses": [
                {
                    "index": "第一条",
                    "error": "",
                    "reference_file_name": "成交确认书",
                    "reference_content": "土地位置：xx市xx区"
                }
            ]
        }
    }

    审批拒绝示例：
    {
        "status": "rejected",
        "result": "第二条与成交确认书不一致，审批拒绝",
        "details": {
            "clauses": [
                {
                    "index": "第二条",
                    "error": "土地面积不一致，合同写10000平方米，成交确认书写12000平方米",
                    "reference_file_name": "成交确认书",
                    "reference_content": "土地面积：12000平方米"
                }
            ]
        }
    }

    【注意事项】
    1. status 字段只能是 "approved" 或 "rejected"，不要传其他值
    2. 如果条款符合要求，error 字段必须设为空字符串 ""
    3. 每次调用都会追加记录，可以查询历史审批结果
    """

    store_id = runtime.context.get('store_id', 'default')
    data_session_id = get_data_session_id(runtime)

    try:
        namespace = (store_id,)
        key = f"approval/result/{data_session_id}"

        result_data = json.loads(result_content) if isinstance(result_content, str) else result_content
        status = result_data.get("status", "pending")
        result_text = result_data.get("result", "")
        details = result_data.get("details", None)

        approval_result = ApprovalResult(
            host_session_id=data_session_id,
            status=status,
            result=result_text,
            timestamp=datetime.now().isoformat(),
            details=details
        )

        # 获取现有审批结果列表
        existing_item = runtime.store.get(namespace, key)
        if existing_item and existing_item.value:
            if isinstance(existing_item.value, list):
                results_list = existing_item.value
            else:
                # 如果之前存储的是单个对象，转换为列表
                results_list = [existing_item.value]
        else:
            results_list = []

        # 追加新结果
        results_list.append(approval_result.model_dump())

        # 保存更新后的列表
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

    Args:
        clause_numbers (list): 必填，条款编号数组，如 ["第一条", "第二条"]
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含审批规则的命令对象
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

    Args:
        runtime (ToolRuntime): 工具运行时上下文

    Returns:
        Command: 包含参考文件内容的命令对象
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
