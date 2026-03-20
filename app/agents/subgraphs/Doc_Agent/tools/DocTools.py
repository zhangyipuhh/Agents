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

from app.utils.files.DocumentLoader import DocumentLoader


@tool(name="split_file", description="将文件内容切分成多个块")
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
    session_id = runtime.context.get('session_id', 'default')
    store_id = runtime.context.get('store_id', 'default')
    namespace = (store_id, session_id)
    try:
        # 1. 从缓存中获取所有块
        result = runtime.store.get(namespace, cache_id)
        
        if not result or not result.value:
            raise ValueError(f"未找到缓存: {cache_id}")
        
        chunks = result.value
        
        # 2. 根据文件类型选择不同的处理方式
        import re
        
        if type == "合同":
            # 合同类型：先合并内容，再使用正则匹配"第X条"进行切分
            if isinstance(chunks, list):
                full_content = "\n\n".join([chunk.get("content", "") for chunk in chunks])
            else:
                full_content = str(chunks)
            
            pattern = r'^\s*(第[\u4e00-\u9fa5\d]+条)'
            lines = full_content.split('\n')
            paragraph_data = []
            _tmp_index = 0
            
            for idx, line in enumerate(lines):
                text = line.strip()
                if not text:
                    continue
                    
                # 检查是否匹配条款模式
                _is_match = re.match(pattern, text)
                if _is_match:
                    _tmp_index += 1
                
                paragraph_data.append({
                    "paragraph_type": _tmp_index,
                    "paragraph_num": idx,
                    "paragraph_text": text
                })
            
            if not paragraph_data:
                raise ValueError("合同解析未获取到任何段落数据")
            
            # 3. 构建存储结构，name改为type
            chunk_data = [
                {
                    "index": i + 1,
                    "name": type,
                    "content": para["paragraph_text"],
                    "paragraph_type": para["paragraph_type"],
                    "paragraph_num": para["paragraph_num"]
                }
                for i, para in enumerate(paragraph_data)
            ]
        else:
            # 其他类型：直接循环 chunks，修改 name 字段
            if not isinstance(chunks, list) or not chunks:
                raise ValueError("未加载到任何内容")
            
            # 3. 构建存储结构，name改为type
            chunk_data = [
                {
                    "index": i + 1,
                    "name": type,
                    "content": chunk.get("content", "") if isinstance(chunk, dict) else str(chunk)
                }
                for i, chunk in enumerate(chunks)
            ]
        
        # 5. 存储到store的file_id键下（使用session_id_file命名空间），file_id的原内容就被覆盖了。这里要注意
        runtime.store.put(namespace, file_id, chunk_data)
        
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


