#!/usr/bin/python
# -*- coding:utf-8 -*-
# Date: 2026-04-30
# Author: 张镒谱
from typing import Union, List, Any
from langchain_core.messages import BaseMessage


class MessageContentConverter:
    """消息内容转换器

    统一处理不同模型返回的 content 格式，输出字符串。
    主要用于非流式输出的处理场景，统一处理特殊输出格式。

    支持以下格式：
        - 普通字符串：直接返回
        - 列表格式（MiniMax thinking 模式）：提取 text/thinking/image_url 等

    核心功能：
        1. 兼容不同模型返回的 content 结构差异
        2. 提取纯文本内容用于显示
        3. 支持 thinking 内容的过滤与包含
        4. 处理工具调用、工具结果等特殊内容类型
    """

    @staticmethod
    def to_string(
        content: Union[str, List[Any]],
        include_thinking: bool = False,
        thinking_prefix: str = "[思考]: "
    ) -> str:
        """将消息内容转换为字符串

        Args:
            content: 消息的 content 字段，可能是字符串或列表
            include_thinking: 是否包含 thinking 内容，默认 False（只返回 text）
            thinking_prefix: thinking 内容的前缀，默认 "[思考]: "

        Returns:
            str: 转换后的字符串内容

        转换策略：
            - 字符串类型：直接返回
            - 列表类型（MiniMax thinking 模式）：遍历并提取各元素内容
        """
        # 直接返回字符串类型 content，无需处理
        if isinstance(content, str):
            return content

        # 列表类型 content，遍历处理每个元素
        if isinstance(content, list):
            text_parts = []
            # 遍历列表中的每个元素，提取文本内容
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")

                    # text 类型：直接提取 text 字段内容
                    if item_type == "text":
                        text_parts.append(item.get("text", ""))

                    # thinking 类型：当 include_thinking 为 True 时提取
                    elif item_type == "thinking" and include_thinking:
                        thinking_text = item.get("thinking", "")
                        # 非空 thinking 内容才添加
                        if thinking_text:
                            text_parts.append(f"{thinking_prefix}{thinking_text}")

                    # image_url 类型：简化为 [图片] 占位符
                    elif item_type == "image_url":
                        text_parts.append("[图片]")

                    # tool_use 类型：记录工具调用名称和输入参数
                    elif item_type == "tool_use":
                        tool_name = item.get("name", "unknown_tool")
                        tool_input = item.get("input", {})
                        text_parts.append(f"[工具调用]: {tool_name}({tool_input})")

                    # tool_result 类型：记录工具返回结果
                    elif item_type == "tool_result":
                        tool_result = item.get("content", "")
                        text_parts.append(f"[工具结果]: {tool_result}")

                    # 未知类型：尝试从 text 或 content 字段提取内容
                    else:
                        if "text" in item:
                            text_parts.append(str(item.get("text")))
                        elif "content" in item:
                            text_parts.append(str(item.get("content")))

                # 列表元素本身是字符串类型时，直接添加
                elif isinstance(item, str):
                    text_parts.append(item)

            # 使用换行符连接各部分内容
            return "\n".join(text_parts)

        # 其他类型（数字、对象等）转换为字符串返回
        return str(content)

    @staticmethod
    def extract_text(content: Union[str, List[Any]]) -> str:
        """只提取 text 类型的内容，忽略 thinking

        Args:
            content: 消息的 content 字段

        Returns:
            str: 提取的文本内容

        使用场景：
            - 流式输出时，只显示用户可见的文本
            - 不需要展示模型的思考过程
        """
        return MessageContentConverter.to_string(content, include_thinking=False)

    @staticmethod
    def extract_full(content: Union[str, List[Any]]) -> str:
        """提取完整内容，包括 thinking

        Args:
            content: 消息的 content 字段

        Returns:
            str: 完整的内容字符串

        使用场景：
            - 调试模式下查看完整输出
            - 需要分析模型的思考过程
        """
        return MessageContentConverter.to_string(content, include_thinking=True)


# =============================================================================
# 便捷工具函数
# =============================================================================

def extract_message_content(
    message: BaseMessage,
    include_thinking: bool = False
) -> str:
    """从消息对象中提取文本内容

    Args:
        message: LangChain 消息对象
        include_thinking: 是否包含 thinking 内容

    Returns:
        str: 提取的文本内容

    处理逻辑：
        - 优先使用 message.content 属性
        - 无 content 属性时，将整个消息对象转为字符串
    """
    # 获取消息的 content 属性，若不存在则转换为字符串
    content = message.content if hasattr(message, 'content') else str(message)
    return MessageContentConverter.to_string(content, include_thinking=include_thinking)


def extract_text(message: BaseMessage) -> str:
    """从消息对象中提取 text 类型内容，忽略 thinking

    Args:
        message: LangChain 消息对象

    Returns:
        str: 提取的文本内容

    使用场景：
        - 流式输出场景，只显示用户可见文本
        - 不需要展示模型的思考过程
    """
    content = message.content if hasattr(message, 'content') else str(message)
    return MessageContentConverter.to_string(content, include_thinking=False)


def extract_full(message: BaseMessage) -> str:
    """从消息对象中提取完整内容，包括 thinking

    Args:
        message: LangChain 消息对象

    Returns:
        str: 完整的内容字符串

    使用场景：
        - 调试模式下查看完整输出
        - 需要分析模型的思考过程
    """
    content = message.content if hasattr(message, 'content') else str(message)
    return MessageContentConverter.to_string(content, include_thinking=True)
