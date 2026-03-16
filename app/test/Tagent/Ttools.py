#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Ttools - Agent工具模块
ToolRuntime 只关心 Context 类型，State 和 Config 是它内部自动管理的！

该模块定义了Agent可用的工具函数，包括获取当前时间、数值求和以及图片识别功能。

Date: 2026-03-11
Author: 张镒谱
"""

import base64
import os
from app.agents.config.config import LLM_VISION_CONFIG
from langchain.tools import tool, ToolRuntime
from langchain.messages import ToolMessage, HumanMessage
from langchain.chat_models import init_chat_model
from langgraph.types import Command
from app.agents.llmcalls.model_factory import ModelFactory

@tool(description="对列表中的数字进行求和")
def add(numbers: list, runtime: ToolRuntime) -> Command:
    """
    数值求和工具
    
    对输入的数字列表进行求和计算，支持整数和浮点数的混合运算。
    用于Agent执行数学计算任务。
    
    Args:
        numbers (list): 必填，包含数字的列表，支持int或float类型
        runtime (ToolRuntime[TAgentContext]): 工具运行时上下文
        
    Returns:
        float: 列表中所有数字的总和
    """
    # 使用Python内置sum函数对数字列表进行求和计算
    # sum函数内部实现遍历列表元素并累加，算法时间复杂度为O(n)
    
 
    return  Command(
        update={
            "messages": [
                ToolMessage(
                    content=str(sum(numbers)),
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )
@tool(description="使用多模态模型识别图片内容")
def recognize_images(image_paths: list[str], runtime: ToolRuntime) -> Command:
    """
    图片识别工具
    
    使用多模态大语言模型（如 GPT-4o、Claude 3.5 Sonnet 等）识别图片内容。
    支持本地图片文件路径。
    
    Args:
        image_paths (list[str]): 必填，图片文件路径数组
        runtime (ToolRuntime[TAgentContext]): 工具运行时上下文
        
    Returns:
        str: 模型对图片内容的描述和分析结果
        
    Example:
        >>> recognize_images(["/path/to/image1.jpg", "/path/to/image2.png"])
        "图片1显示了一只猫...图片2显示了一片风景..."
    """
    
    if not image_paths:
        return "错误：请提供至少一张图片路径"
    
    # 初始化支持多模态的模型
    # 使用环境变量中的模型配置，默认为gpt-4o
    model_name = LLM_VISION_CONFIG["model_name"]
    model = ModelFactory.create_model( 
        model_type=LLM_VISION_CONFIG["model_type"],
        model_name=model_name,
        temperature=LLM_VISION_CONFIG["temperature"],
        api_key=LLM_VISION_CONFIG["api_key"],
        base_url=LLM_VISION_CONFIG["base_url"]
    )
    
    # 构建消息内容，包含所有图片
    content_parts = [
        {"type": "text", "text": "请详细描述以下图片的内容。如果有多个图片，请分别描述每张图片。"}
    ]
    
    for image_path in image_paths:
        # 检查文件是否存在
        if not os.path.exists(image_path):
            return f"错误：图片文件不存在 - {image_path}"
        
        # 读取图片并编码为base64
        try:
            with open(image_path, "rb") as image_file:
                encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
            
            # 根据文件扩展名确定MIME类型
            ext = os.path.splitext(image_path)[1].lower()
            mime_type = {
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".png": "image/png",
                ".gif": "image/gif",
                ".webp": "image/webp",
                ".bmp": "image/bmp"
            }.get(ext, "image/jpeg")
            
            content_parts.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{encoded_image}"
                }
            })
        except Exception as e:
            return f"错误：读取图片文件失败 - {image_path}，原因：{str(e)}"
    
    # 构建HumanMessage并调用模型
    message = HumanMessage(content=content_parts)
    
    try:
        response = model.invoke([message])
        return  Command(
            update={
                "messages": [
                    ToolMessage(
                        content=response.content,
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
    except Exception as e:
        return  Command(
            update={
                "messages": [
                    ToolMessage(
                        content=f"错误：模型调用失败，原因：{str(e)}",
                        tool_call_id=runtime.tool_call_id
                    )
                ]
            }
        )
if __name__ == "__main__":
    import base64
    test_images = [
        r"app\data\upload\418353f9-0902-4641-b4b7-12f516bc3faf\35d43c19-5e2c-4d53-b962-3bb90aba70d3\c2f44085-5ae9-4a18-9b8c-795aa43a279c\page_006.jpg",
        r"app\data\upload\418353f9-0902-4641-b4b7-12f516bc3faf\35d43c19-5e2c-4d53-b962-3bb90aba70d3\c2f44085-5ae9-4a18-9b8c-795aa43a279c\page_013.jpg",
        r"app\data\upload\418353f9-0902-4641-b4b7-12f516bc3faf\35d43c19-5e2c-4d53-b962-3bb90aba70d3\c2f44085-5ae9-4a18-9b8c-795aa43a279c\page_017.jpg"
    ]
    
    model_name = LLM_VISION_CONFIG["model_name"]
    model = ModelFactory.create_model( 
        model_type=LLM_VISION_CONFIG["model_type"],
        model_name=model_name,
        temperature=LLM_VISION_CONFIG["temperature"],
        api_key=LLM_VISION_CONFIG["api_key"],
        base_url=LLM_VISION_CONFIG["base_url"]
    )
    
    content_parts = [
        {"type": "text", "text": "请详细描述以下图片的内容。如果有多个图片，请分别描述每张图片。"}
    ]
    
    for image_path in test_images:
        if not os.path.exists(image_path):
            print(f"错误：图片文件不存在 - {image_path}")
            continue
        
        with open(image_path, "rb") as image_file:
            encoded_image = base64.b64encode(image_file.read()).decode("utf-8")
        
        ext = os.path.splitext(image_path)[1].lower()
        mime_type = {
            ".jpg": "image/jpeg",
            ".jpeg": "image/jpeg",
            ".png": "image/png",
            ".gif": "image/gif",
            ".webp": "image/webp",
            ".bmp": "image/bmp"
        }.get(ext, "image/jpeg")
        
        content_parts.append({
            "type": "image_url",
            "image_url": {"url": f"data:{mime_type};base64,{encoded_image}"}
        })
    
    message = HumanMessage(content=content_parts)
    response = model.invoke([message])
    print(response.content)