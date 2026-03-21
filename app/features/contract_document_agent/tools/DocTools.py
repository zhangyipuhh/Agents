#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocTools - DocAgent工具模块

该模块定义了DocAgent可用的工具函数，包括获取参考文件、获取合同内容和写入审批结果功能。

Date: 2026-03-19
Author: 张镒谱
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from app.shared.utils.files.word_untils import WordProcessor
from logging import getLogger



logger = getLogger(__name__)



@tool(description="将文件内容切分成多个块")
def split_file(type: str, cache_id: str, file_id: str, runtime: ToolRuntime) -> Command:
    """
    切分文件工具
    
    从store中获取文件内容，使用cache_id查找缓存的文件块，拼装后使用DocumentLoader重新切分并存储。
    
    Args:
        cache_id (str): 必填，缓存ID，用于查找存储的文件块
        type (str): 必填，文件类型，可选值为"合同"、"成交确认书"、"会议纪要"
        file_id (str): 必填，文件的ID，用于存储切分后的内容
        runtime (ToolRuntime): 工具运行时上下文
        
    Returns:
        Command: 包含ToolMessage和切分后的文件内容的命令对象    
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


