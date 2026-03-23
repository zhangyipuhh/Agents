#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocTools - DocAgent工具模块

该模块定义了DocAgent可用的工具函数，包括获取参考文件、获取合同内容和写入审批结果功能。

Date: 2026-03-19
Author: 张镒谱
"""

import json
import time
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.files.word_untils import WordProcessor
from logging import getLogger



logger = getLogger(__name__)



@tool(description="按条款/语义切分文档。参数：type(供地合同/成交确认书/会议纪要)、cache_id(缓存ID)、file_id(文件ID)。返回切分后的文档块。")
def split_file(type: str, cache_id: str, file_id: str, runtime: ToolRuntime) -> Command:
    """
    切分文件工具
    
    从store中获取文件内容，使用cache_id查找缓存的文件块，拼装后使用DocumentLoader重新切分并存储。
    
    Args:
        cache_id (str): 必填，缓存ID，用于查找存储的文件块
        type (str): 必填，文件类型，可选值为"供地合同"、"成交确认书"、"会议纪要"
        file_id (str): 必填，文件的ID，用于存储切分后的内容
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和切分后的文件内容的命令对象
        
    Example:
        >>> split_file("供地合同", "cache_123", "file_456")
        >>> # 返回: {"total_chunks": 10, "message": "文件已成功切分为 10 个块", ...}
    """
    #session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    try:
        # 1. 从缓存中获取所有块
        result = runtime.store.get(namespace, cache_id)
        
        if not result or not result.value:
            raise ValueError(f"未找到缓存: {cache_id}")
        
        chunks = result.value
        
        # 2. 根据文件类型选择不同的处理方式
        import re
        
        if type == "供地合同":
            word_processor = WordProcessor()
            #获取合同文件路径,后续用于审批结果存储
            file_paths_result = runtime.store.get(namespace, "file_id")
            file_paths = file_paths_result.value if file_paths_result else None
            path = file_paths.get(file_id, None) if file_paths else None
            # 存储合同文件路径
            if not path:
                raise ValueError(f"未找到文件路径: {file_id}")
            runtime.store.put(namespace, "ht_file_path", path)
            # 读取合同文件内容，并将条款前的空格去除，同时将"第几条"替换为"第几条款"
            contract_text,paragraph_data =word_processor.read_contract_word(path, pattern=  r'^\s*(第[一二三四五六七八九十百千万亿]+条)', pattern_replace=r'\1条款')
            

            #存储合同段落信息
            runtime.store.put(namespace, "ht_paragraph_data", paragraph_data)

            
            # 合同类型：先合并内容，再使用正则匹配"第X条"条款进行切分
            
            
            # 步骤0: 截取第一条之前的内容（从电子监管号开始到第一条之前）
            preamble_content = ""
            preamble_pattern = r'(电\s*子\s*监\s*管\s*号.*?)(?=第[一二三四五六七八九十百千万亿]+条|$)'
            preamble_match = re.search(preamble_pattern, contract_text, re.DOTALL)
            if preamble_match:
                preamble_content = preamble_match.group(1).strip()
                # 从contract_text中移除 preamble 部分，避免重复
                contract_text = contract_text[preamble_match.end():].strip()
            

            
            # 步骤2: 定义正则表达式模式，用于匹配每两个第几条条款之间的内容
            pattern = r'(第[\u4e00-\u9fa5\d]+条\s*条款)(.*?)(?=\s*第[\u4e00-\u9fa5\d]+条\s*条款|$)'
            
            # 使用正则表达式查找所有匹配的条款内容
            clause_matches = re.findall(pattern, contract_text, re.DOTALL)
            
            # 去除多余的空格并过滤空内容
            formatted_chunks = []
            for clause in clause_matches:
                title = clause[0].strip()
                content = clause[1].strip()
                if title or content:
                    formatted_chunks.append((title, content))
            
            # 输出每个条款的内容
            for i, chunk in enumerate(formatted_chunks):
                print(f"===================================正在记忆第{i+1}条条款...")
                clause_title = chunk[0] if isinstance(chunk, tuple) else ""
                clause_content = chunk[1] if isinstance(chunk, tuple) else chunk
            
            if not formatted_chunks:
                raise ValueError("合同解析未获取到任何条款数据")
            
            # 3. 构建存储结构，name改为type
            # 先添加 preamble 作为第一个 chunk，然后添加条款
            chunk_data = []
            
            # 添加 preamble（第一条之前的内容）
            if preamble_content:
                chunk_data.append({
                    "index": 1,
                    "name": type,
                    "content": preamble_content
                })
            
            # 添加条款内容，每三条合并为一组
            group_size = 3
            for i in range(0, len(formatted_chunks), group_size):
                group_chunks = formatted_chunks[i:i + group_size]
                combined_content = "\n\n".join([
                    clause[0] + clause[1] if isinstance(clause, tuple) else clause
                    for clause in group_chunks
                ])
                chunk_data.append({
                    "index": len(chunk_data) + 1,
                    "name": type,
                    "content": combined_content
                })
        else:
            # 其他类型：直接循环 chunks，修改 name 字段
            if not isinstance(chunks, list) or not chunks:
                raise ValueError("未加载到任何内容")
            
            # 3. 构建滚动窗口式存储结构，三个chunk为一组，步长为1
            window_size = 3
            chunk_data = []
            for i in range(len(chunks) - window_size + 1):
                window_chunks = chunks[i:i + window_size]
                combined_content = "\n\n".join([
                    chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
                    for chunk in window_chunks
                ])
                chunk_data.append({
                    "index": i + 1,
                    "name": type,
                    "content": combined_content
                })
        
        
        
        
        # 5. 存储到store的file_id键下（使用store_id命名空间），file_id的原内容就被覆盖了。这里要注意
        runtime.store.put(namespace, file_id, chunk_data)
        logger.info(f"[INFO]split_file方法 ，store_id: {store_id}， 切分文件工具: {file_id} 已成功切分为 {len(chunk_data)} 个块")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "file_id": file_id,
                            "type": type,
                            "total_chunks": len(chunk_data),
                            "message": f"文件已成功切分为 {len(chunk_data)} 个块"
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
                            "error": f"切分文件失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )

@tool(description="根据文档类型获取提取规则ID。参数：doc_type(供地合同/成交确认书/会议纪要)、clause_numbers(仅合同需要，如['第一条','第三条']，其他类型传[])。返回规则ID，用于获取具体提取模板。")
def get_extraction_rule_id(doc_type: str, clause_numbers: list[str], runtime: ToolRuntime) -> Command:
    """
    根据文档类型和条款信息获取提取规则ID
    
    使用场景：
        - 当你识别出文档类型后，需要知道应该提取哪些关键信息时
        - 当用户要求提取关键信息、分析文档内容时
    
    Args:
        doc_type: 文档类型（供地合同/成交确认书/会议纪要）
        clause_numbers: 条款编号数组，仅合同类型需要，如["第一条","第三条"]；其他类型传空数组[]
        runtime: 工具运行时上下文
        
    Returns:
        Command: 包含规则ID的命令对象
        
    Example:
        >>> get_extraction_rule_id("供地合同", ["第一条", "第三条"])
        >>> # 返回: {"rule_id": "rule_contract_供地合同_clauses_2", ...}
    """
    store_id = runtime.context.get('store_id', 'default')
    logger.info(f"[get_extraction_rule_id] store_id: {store_id}, doc_type: {doc_type}, clause_numbers: {clause_numbers}")
    
    try:
        rule_id = ""
        
        if doc_type == "供地合同":
            if clause_numbers:
                rule_id = f"rule_contract_{doc_type}_clauses_{len(clause_numbers)}"
            else:
                rule_id = f"rule_contract_{doc_type}_all"
        elif doc_type == "成交确认书":
            rule_id = "rule_confirmation"
        elif doc_type == "会议纪要":
            rule_id = "rule_meeting_minutes"
        else:
            raise ValueError(f"不支持的文档类型: {doc_type}")
        
        logger.info(f"[get_extraction_rule_id] 生成规则ID: {rule_id}")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "rule_id": rule_id,
                            "doc_type": doc_type,
                            "clause_count": len(clause_numbers) if clause_numbers else 0,
                            "message": f"已获取文档类型【{doc_type}】的提取规则ID"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        logger.error(f"[get_extraction_rule_id] 错误: {str(e)}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "error",
                            "error": f"获取提取规则ID失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="根据规则ID获取提取字段和输出格式。参数：rule_id(从get_extraction_rule_id获得)。返回字段列表、字段说明、JSON输出模板。")
def get_extraction_rule_detail(rule_id: str, runtime: ToolRuntime) -> Command:
    """
    获取提取规则的详细信息
    
    使用场景：
        - 当你已经获取到提取规则ID，需要知道具体提取哪些字段时
        - 在调用 get_extraction_rule_id 之后使用
    
    Args:
        rule_id: 提取规则ID
        runtime: 工具运行时上下文
        
    Returns:
        Command: 包含提取规则详情的命令对象
        
    Example:
        >>> get_extraction_rule_detail("rule_contract_供地合同_all")
        >>> # 返回: {"fields": [...], "output_template": {...}, ...}
    """
    store_id = runtime.context.get('store_id', 'default')
    logger.info(f"[get_extraction_rule_detail] store_id: {store_id}, rule_id: {rule_id}")
    
    try:
        extraction_rules = {
            "rule_contract_供地合同_all": {
                "doc_type": "供地合同",
                "fields": [
                    {"name": "合同编号", "description": "合同唯一标识", "required": True},
                    {"name": "出让方", "description": "土地出让方名称", "required": True},
                    {"name": "受让方", "description": "土地受让方名称", "required": True},
                    {"name": "地块位置", "description": "土地具体位置", "required": True},
                    {"name": "面积", "description": "土地面积（平方米）", "required": True},
                    {"name": "用途", "description": "土地用途", "required": True},
                    {"name": "出让年限", "description": "土地出让年限", "required": True},
                    {"name": "成交价格", "description": "土地成交价格", "required": True},
                    {"name": "付款方式", "description": "付款方式和期限", "required": False},
                    {"name": "违约责任", "description": "违约责任条款", "required": False}
                ],
                "output_template": {
                    "合同编号": "",
                    "出让方": "",
                    "受让方": "",
                    "地块位置": "",
                    "面积": "",
                    "用途": "",
                    "出让年限": "",
                    "成交价格": "",
                    "付款方式": "",
                    "违约责任": ""
                }
            },
            "rule_confirmation": {
                "doc_type": "成交确认书",
                "fields": [
                    {"name": "确认书编号", "description": "确认书唯一标识", "required": True},
                    {"name": "成交标的", "description": "成交的土地或项目", "required": True},
                    {"name": "成交价格", "description": "成交金额", "required": True},
                    {"name": "竞得人", "description": "竞得方名称", "required": True},
                    {"name": "成交时间", "description": "成交日期", "required": True},
                    {"name": "签约时限", "description": "签约截止时间", "required": False}
                ],
                "output_template": {
                    "确认书编号": "",
                    "成交标的": "",
                    "成交价格": "",
                    "竞得人": "",
                    "成交时间": "",
                    "签约时限": ""
                }
            },
            "rule_meeting_minutes": {
                "doc_type": "会议纪要",
                "fields": [
                    {"name": "会议时间", "description": "会议召开时间", "required": True},
                    {"name": "会议地点", "description": "会议召开地点", "required": True},
                    {"name": "主持人", "description": "会议主持人", "required": True},
                    {"name": "参会人员", "description": "参会人员名单", "required": True},
                    {"name": "会议议题", "description": "会议讨论的主要议题", "required": True},
                    {"name": "决议事项", "description": "会议达成的决议", "required": True},
                    {"name": "行动计划", "description": "后续行动计划", "required": False}
                ],
                "output_template": {
                    "会议时间": "",
                    "会议地点": "",
                    "主持人": "",
                    "参会人员": "",
                    "会议议题": "",
                    "决议事项": "",
                    "行动计划": ""
                }
            }
        }
        
        if rule_id.startswith("rule_contract_供地合同_clauses_"):
            rule_detail = extraction_rules["rule_contract_供地合同_all"].copy()
            rule_detail["rule_id"] = rule_id
        elif rule_id in extraction_rules:
            rule_detail = extraction_rules[rule_id]
            rule_detail["rule_id"] = rule_id
        else:
            raise ValueError(f"未找到规则ID: {rule_id}")
        
        logger.info(f"[get_extraction_rule_detail] 返回规则详情，字段数: {len(rule_detail['fields'])}")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "rule_detail": rule_detail,
                            "message": f"已获取规则详情，共{len(rule_detail['fields'])}个提取字段"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        logger.error(f"[get_extraction_rule_detail] 错误: {str(e)}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "error",
                            "error": f"获取提取规则详情失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )


@tool(description="保存提取的结构化数据。参数：doc_type(文档类型)、extracted_data(JSON格式数据，需符合提取规则定义的格式)。返回保存状态和记录ID。")
def save_extraction_result(doc_type: str, extracted_data: dict, runtime: ToolRuntime) -> Command:
    """
    保存提取结果
    
    使用场景：
        - 当你完成信息提取后，需要保存结果时
        - 当用户要求"保存提取结果"、"记录关键信息"时
    
    Args:
        doc_type: 文档类型
        extracted_data: 提取的结构化数据，需符合提取规则定义的格式
        runtime: 工具运行时上下文
        
    Returns:
        Command: 包含保存状态的命令对象
        
    Example:
        >>> save_extraction_result("供地合同", {"合同编号": "HT001", "出让方": "XXX", ...})
        >>> # 返回: {"record_id": "record_供地合同_a1b2c3d4", ...}
    """
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    logger.info(f"[save_extraction_result] store_id: {store_id}, doc_type: {doc_type}")
    logger.info(f"[save_extraction_result] extracted_data: {json.dumps(extracted_data, ensure_ascii=False)}")
    
    try:
        import uuid
        record_id = f"record_{doc_type}_{uuid.uuid4().hex[:8]}"
        
        runtime.store.put(namespace, record_id, {
            "doc_type": doc_type,
            "extracted_data": extracted_data,
            "timestamp": str(int(time.time()))
        })
        
        logger.info(f"[save_extraction_result] 保存成功，record_id: {record_id}")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "record_id": record_id,
                            "doc_type": doc_type,
                            "field_count": len(extracted_data),
                            "message": f"已成功保存{doc_type}的提取结果"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
        
    except Exception as e:
        logger.error(f"[save_extraction_result] 错误: {str(e)}")
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "error",
                            "error": f"保存提取结果失败: {str(e)}"
                        }, ensure_ascii=False),
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
