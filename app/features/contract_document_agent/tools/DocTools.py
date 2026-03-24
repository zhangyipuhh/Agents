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
from typing import Literal
from pydantic import BaseModel, Field, field_validator
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.files.word_untils import WordProcessor
from app.features.contract_document_agent.config.prompts import EXTRACTION_CONFIG, DOC_TYPE_RULE_MAPPING
from logging import getLogger



logger = getLogger(__name__)


class QAItem(BaseModel):
    question: str = Field(..., description="问题内容")
    answer: str = Field(..., description="答案内容")


class ExtractionItem(BaseModel):
    index: str = Field(..., description="索引标识，如'基础信息'、'第一条'、'第五条'等")
    content: list[QAItem] = Field(default_factory=list, description="问题答案列表")

    @field_validator('content', mode='before')
    @classmethod
    def validate_content(cls, v):
        if not isinstance(v, list):
            raise ValueError('content 必须是列表')
        return v


class ExtractedData(BaseModel):
    items: list[ExtractionItem] = Field(..., description="提取数据列表")

    @field_validator('items', mode='before')
    @classmethod
    def convert_legacy_format(cls, v):
        if not isinstance(v, list):
            raise ValueError('extracted_data 必须是列表')
        
        converted = []
        for item in v:
            if isinstance(item, dict):
                if 'index' in item and 'content' in item:
                    converted.append(item)
                elif 'question' in item and 'answer' in item:
                    converted.append({
                        "index": "基础信息",
                        "content": [{"question": item['question'], "answer": item['answer']}]
                    })
                else:
                    raise ValueError(f'无法识别的数据格式: {item}')
            else:
                raise ValueError(f'数据项必须是字典: {item}')
        return converted



@tool(description="**禁止用于图片**。按条款/语义切分已缓存的文档文件。使用前提：必须已有有效的cache_id（文档上传时自动生成）。参数：type(供地合同/成交确认书/会议纪要)、cache_id(缓存ID，必须存在)、file_id(文件ID)。返回切分后的文档块。")
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
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id,)
    
    try:
        # 1. 从缓存中获取所有块
        result = runtime.store.get(namespace, cache_id)
        
        # 如果缓存不存在，说明可能调用了错误的工具
        if not result or not result.value:
            logger.warning(f"[split_file] 未找到缓存: {cache_id}，可能调用了错误的工具")
            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps({
                                "status": "error",
                                "error": f"未找到缓存: {cache_id}",
                                "suggestion": "split_file工具需要有效的cache_id（来自已上传的Word/PDF文档）。如果处理的是图片或用户直接提供的文本，请直接分析内容，无需调用此工具。",
                                "correct_usage": "此工具仅适用于：已上传的Word/PDF文档 + 有效的cache_id"
                            }, ensure_ascii=False),
                            tool_call_id=runtime.tool_call_id
                        )
                    ]
                }
            )
        
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
            
            if len(chunks) < window_size:
                combined_content = "\n\n".join([
                    chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
                    for chunk in chunks
                ])
                chunk_data.append({
                    "index": 1,
                    "name": type,
                    "content": combined_content
                })
            else:
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
        >>> # 返回: {"rule_id": "rule_contract_供地合同_clauses", ...}
    """
    store_id = runtime.context.get('store_id', 'default')
    logger.info(f"[get_extraction_rule_id] store_id: {store_id}, doc_type: {doc_type}, clause_numbers: {clause_numbers}")
    
    try:
        if doc_type not in DOC_TYPE_RULE_MAPPING:
            raise ValueError(f"不支持的文档类型: {doc_type}")
        
        mapping = DOC_TYPE_RULE_MAPPING[doc_type]
        
        if doc_type == "供地合同":
            if clause_numbers:
                rule_id = mapping["clauses"]
            else:
                rule_id = mapping["all"]
        else:
            rule_id = mapping["default"]
        
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
        >>> # 返回: {"questions": [...], "output_format": {...}, ...}
    """
    store_id = runtime.context.get('store_id', 'default')
    logger.info(f"[get_extraction_rule_detail] store_id: {store_id}, rule_id: {rule_id}")
    
    try:
        if rule_id not in EXTRACTION_CONFIG:
            raise ValueError(f"未找到规则ID: {rule_id}")
        
        config = EXTRACTION_CONFIG[rule_id]
        rule_detail = {
            "rule_id": rule_id,
            "doc_type": config["doc_type"],
            "questions": config["questions"],
            "output_example": config["output_example"]
        }
        
        if "clause_questions" in config:
            rule_detail["clause_questions"] = config["clause_questions"]
        
        question_count = len(config["questions"])
        if "clause_questions" in config:
            question_count += sum(len(v) for v in config["clause_questions"].values())
        
        logger.info(f"[get_extraction_rule_detail] 返回规则详情，问题数: {question_count}")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "rule_detail": rule_detail,
                            "message": f"已获取规则详情，共{question_count}个问题"
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


@tool(description="保存提取的结构化数据。参数：doc_type(文档类型)、extracted_data(JSON格式数据)。统一格式：[{\"index\": \"索引标识\", \"content\": [{\"question\": \"问题\", \"answer\": \"答案\"}]}]。index可以是'基础信息'、'第一条'等。返回保存状态和记录ID。")
def save_extraction_result(doc_type: str, extracted_data: list, runtime: ToolRuntime) -> Command:
    """
    保存提取结果
    
    使用场景：
        - 当你完成信息提取后，需要保存结果时
        - 当用户要求"保存提取结果"、"记录关键信息"时
    
    Args:
        doc_type: 文档类型（供地合同/成交确认书/会议纪要）
        extracted_data: 提取的结构化数据，统一格式为:
            [{"index": "索引标识", "content": [{"question": "...", "answer": "..."}]}]
            - index: 索引标识，如"基础信息"、"第一条"、"第五条"等
            - content: 问题答案列表
        runtime: 工具运行时上下文
        
    Returns:
        Command: 包含保存状态的命令对象
        
    存储结构:
        reference = {
            session_id: {
                "成交确认书": [],
                "会议纪要": [],
                "供地合同": []
            }
        }
        
    Example:
        >>> # 所有类型统一格式
        >>> save_extraction_result("供地合同", [
        ...     {"index": "基础信息", "content": [{"question": "合同编号是多少？", "answer": "合同编号为HT2024001"}]},
        ...     {"index": "第五条", "content": [{"question": "合同第五条的不动产单元号是多少？", "answer": "合同第五条的不动产单元号为234455666666"}]}
        ... ])
        >>> save_extraction_result("成交确认书", [
        ...     {"index": "基础信息", "content": [{"question": "成交价格是多少？", "answer": "成交价格为5000万元"}]}
        ... ])
    """
    store_id = runtime.context.get('store_id', 'default')
    host_session_id = runtime.context.get('host_session_id', 'default')
    namespace = (store_id,)
    logger.info(f"[save_extraction_result] store_id: {store_id}, doc_type: {doc_type}, host_session_id: {host_session_id}")
    logger.info(f"[save_extraction_result] extracted_data: {json.dumps(extracted_data, ensure_ascii=False)}")
    
    try:
        import uuid
        record_id = f"record_{doc_type}_{uuid.uuid4().hex[:8]}"
        
        validated_data = ExtractedData(items=extracted_data)
        normalized_data = [item.model_dump() for item in validated_data.items]
        
        existing_data = runtime.store.get(namespace, "reference")
        reference_data = existing_data.value if existing_data and existing_data.value else {}
        
        if host_session_id not in reference_data:
            reference_data[host_session_id] = {}
        
        if doc_type not in reference_data[host_session_id]:
            reference_data[host_session_id][doc_type] = []
        
        reference_data[host_session_id][doc_type].extend(normalized_data)
        
        runtime.store.put(namespace, "reference", reference_data)
        
        logger.info(f"[save_extraction_result] 保存成功，record_id: {record_id}, session_id: {host_session_id}")
        
        return Command(
            update={
                "messages": [
                    ToolMessage(
                        content=json.dumps({
                            "status": "success",
                            "record_id": record_id,
                            "doc_type": doc_type,
                            "session_id": host_session_id,
                            "item_count": len(normalized_data),
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
