#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
从 LangGraph Checkpoint 恢复对话历史

本模块提供从 LangGraph Checkpoint 中恢复对话历史的功能，
使用 graph.get_state() 和 graph.get_state_history() API 获取指定 session 的消息记录。

Date: 2026-05-27
Author: AI Assistant
"""
from typing import List, Optional, Dict, Any
from datetime import datetime
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from app.core.messages.converter import MessageContentConverter


class CheckpointHistoryService:
    """
    Checkpoint 历史消息服务

    提供从 LangGraph Checkpoint 中读取对话历史的功能，
    支持获取最新状态和完整历史记录。
    """

    @staticmethod
    def _convert_message_to_dict(msg) -> Optional[Dict[str, Any]]:
        """
        将 LangChain 消息对象转换为前端可用的字典格式

        Args:
            msg: LangChain 消息对象 (HumanMessage, AIMessage, ToolMessage, SystemMessage)

        Returns:
            Optional[Dict[str, Any]]: 转换后的消息字典，无法识别时返回 None
        """
        if isinstance(msg, HumanMessage):
            return {
                "id": getattr(msg, "id", None) or id(msg),
                "type": "user",
                "role": "user",
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "attachments": getattr(msg, "additional_kwargs", {}).get("attachments", [])
            }
        elif isinstance(msg, AIMessage):
            content = msg.content
            is_list = isinstance(content, list)

            # 基础 content（可读文本）
            readable_content = MessageContentConverter.to_string(content, include_thinking=True) if is_list else (content or '')

            result = {
                "id": getattr(msg, "id", None) or id(msg),
                "type": "ai",
                "role": "assistant",
                "content": readable_content,
            }

            # 若为列表格式，额外解析结构化字段
            if is_list:
                text_parts = []
                thinking_parts = []
                timeline = []
                for item in content:
                    if isinstance(item, dict):
                        item_type = item.get("type", "")
                        if item_type == "text":
                            t = item.get("text", "")
                            text_parts.append(t)
                            timeline.append({"type": "text", "content": t})
                        elif item_type == "thinking":
                            th = item.get("thinking", "")
                            thinking_parts.append(th)
                            timeline.append({"type": "thinking", "content": th})
                result["text"] = "\n".join(text_parts)
                result["thinking"] = thinking_parts
                result["timeline"] = timeline
                result["ended"] = True

            return result
        elif isinstance(msg, ToolMessage):
            # 工具消息通常不显示在前端，但保留用于完整历史
            return {
                "id": getattr(msg, "id", hash(str(msg.content))),
                "type": "tool",
                "role": "tool",
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "tool_call_id": getattr(msg, "tool_call_id", None)
            }
        elif isinstance(msg, SystemMessage):
            # 系统消息通常不显示在前端
            return None
        else:
            # 其他类型消息，尝试通用转换
            return {
                "id": getattr(msg, "id", hash(str(msg.content))),
                "type": "unknown",
                "role": getattr(msg, "type", "unknown"),
                "content": str(msg.content) if hasattr(msg, "content") else str(msg)
            }

    @classmethod
    async def get_conversation_history(
        cls,
        checkpointer: BaseCheckpointSaver,
        session_id: str,
        limit: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        从 Checkpoint 获取对话历史

        使用 checkpointer.get() 获取指定 session 的最新状态，
        提取其中的 messages 列表并转换为前端可用格式。

        Args:
            checkpointer: LangGraph checkpointer 实例
            session_id: 会话 ID（对应 thread_id）
            limit: 限制返回消息数量，默认 None 表示返回所有

        Returns:
            List[Dict[str, Any]]: 消息列表，每项包含 id, type, role, content

        Example:
            >>> checkpointer = await get_async_checkpointer()
            >>> messages = await CheckpointHistoryService.get_conversation_history(
            ...     checkpointer=checkpointer,
            ...     session_id="session-123",
            ...     limit=50
            ... )
        """
        config = {"configurable": {"thread_id": session_id}}

        try:
            # 获取最新状态
            state = await checkpointer.aget(config)

            # 诊断日志
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(
                f"[History] session_id={session_id}, checkpointer_type={type(checkpointer).__name__}, "
                f"checkpointer.aget() returned {state is not None}"
            )
            if not state:
                logger.warning(f"[History] session_id={session_id}, checkpointer.aget() returned None")
                return []

            # 从 Checkpoint 的 channel_values 中提取 messages
            # state 是 Checkpoint 对象（dict 子类），消息存储在 channel_values["messages"] 中
            channel_values = state.get("channel_values", {})
            messages_data = channel_values.get("messages", [])

            logger.warning(
                f"[History] session_id={session_id}, "
                f"state_keys={list(state.keys())}, "
                f"cv_keys={list(channel_values.keys())}, "
                f"messages_count={len(messages_data)}"
            )

            if not messages_data:
                return []

            # 转换消息格式
            messages = []
            for msg in messages_data:
                msg_dict = cls._convert_message_to_dict(msg)
                if msg_dict and msg_dict.get("type") != "tool":  # 过滤工具消息
                    messages.append(msg_dict)

            # 应用限制
            if limit and limit > 0:
                messages = messages[-limit:]

            return messages

        except Exception as e:
            # 记录错误但返回空列表，避免影响正常流程
            import logging
            logging.getLogger(__name__).error(
                f"从 Checkpoint 获取对话历史失败: session_id={session_id}, error={e}"
            )
            return []

    @classmethod
    async def get_conversation_history_with_metadata(
        cls,
        checkpointer: BaseCheckpointSaver,
        session_id: str,
        limit: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        从 Checkpoint 获取对话历史（包含元数据）

        除了消息内容外，还返回会话的元数据信息，如创建时间、消息数量等。

        Args:
            checkpointer: LangGraph checkpointer 实例
            session_id: 会话 ID（对应 thread_id）
            limit: 限制返回消息数量

        Returns:
            Dict[str, Any]: 包含 messages 和 metadata 的字典
        """
        messages = await cls.get_conversation_history(checkpointer, session_id, limit)

        return {
            "session_id": session_id,
            "messages": messages,
            "total": len(messages),
            "timestamp": datetime.utcnow().isoformat()
        }

    @classmethod
    async def get_latest_message(
        cls,
        checkpointer: BaseCheckpointSaver,
        session_id: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取会话的最新一条消息

        Args:
            checkpointer: LangGraph checkpointer 实例
            session_id: 会话 ID

        Returns:
            Optional[Dict[str, Any]]: 最新消息字典，无消息时返回 None
        """
        messages = await cls.get_conversation_history(checkpointer, session_id, limit=1)
        return messages[0] if messages else None
