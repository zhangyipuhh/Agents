#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
从 LangGraph Checkpoint 恢复对话历史

本模块提供从 LangGraph Checkpoint 中恢复对话历史的功能，
使用 graph.get_state() 和 graph.get_state_history() API 获取指定 session 的消息记录。

Date: 2026-05-27
Author: AI Assistant

2026-06-16 扩展：
    - 新增 get_subagent_history()：从全局 checkpointer 反查子智能体 thread（thread_id == tool_call_id）
    - 新增 collect_subagent_tool_call_ids()：遍历主 thread 的 AIMessage.tool_calls 收集所有子 thread_id
    - 新增 merge_main_and_subagent_messages()：按时序合并主消息与子智能体消息流
"""
from typing import List, Optional, Dict, Any, Iterable
from datetime import datetime
from langgraph.checkpoint.base import BaseCheckpointSaver
from langchain_core.messages import HumanMessage, AIMessage, ToolMessage, SystemMessage
from app.core.messages.converter import MessageContentConverter
from app.core.tools.subagent_registry import is_subagent_tool, get_subagent_meta


class CheckpointHistoryService:
    """
    Checkpoint 历史消息服务

    提供从 LangGraph Checkpoint 中读取对话历史的功能，
    支持获取最新状态和完整历史记录。

    2026-06-16 扩展：增加子智能体（sandbox / explore 等）历史反查与合并能力。
    """

    @staticmethod
    def _convert_message_to_dict(msg) -> Optional[Dict[str, Any]]:
        """
        将 LangChain 消息对象转换为前端可用的字典格式

        2026-06-16 改造：使用 type(msg).__name__ 匹配（与 subagent_message_extractor 一致），
        以兼容测试环境的 Mock 类和 langchain-core 1.x 的所有 BaseMessage 派生。

        Args:
            msg: LangChain 消息对象 (HumanMessage, AIMessage, ToolMessage, SystemMessage)

        Returns:
            Optional[Dict[str, Any]]: 转换后的消息字典，无法识别时返回 None
        """
        # 优先尝试 isinstance，失败时降级到 type(msg).__name__ 字符串匹配
        type_name = type(msg).__name__

        def _is(cls_name_set):
            if type_name in cls_name_set:
                return True
            # isinstance 仅在 cls 是 type 时合法；测试环境 cls 可能是 Mock
            try:
                if isinstance(msg, HumanMessage) and "HumanMessage" in cls_name_set:
                    return True
                if isinstance(msg, AIMessage) and "AIMessage" in cls_name_set:
                    return True
                if isinstance(msg, ToolMessage) and "ToolMessage" in cls_name_set:
                    return True
                if isinstance(msg, SystemMessage) and "SystemMessage" in cls_name_set:
                    return True
            except TypeError:
                # 测试环境下 HumanMessage 等是 Mock，isinstance 抛 TypeError
                pass
            return False

        if _is({"HumanMessage", "MockHumanMessage", "_MockHumanMessage"}):
            return {
                "id": getattr(msg, "id", None) or id(msg),
                "type": "user",
                "role": "user",
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "attachments": getattr(msg, "additional_kwargs", {}).get("attachments", [])
            }
        elif _is({"AIMessage", "MockAIMessage", "_MockAIMessage", "AIMessageChunk"}):
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

            # 2026-06-26 新增：提取 tool_calls，供前端历史恢复时重构普通工具卡片
            tool_calls = CheckpointHistoryService._extract_ai_tool_call_ids(msg)
            if tool_calls:
                result["tool_calls"] = tool_calls

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
        elif _is({"ToolMessage", "MockToolMessage", "_MockToolMessage", "ToolCall"}):
            # 工具消息通常不显示在前端，但保留用于完整历史
            return {
                "id": getattr(msg, "id", hash(str(msg.content))),
                "type": "tool",
                "role": "tool",
                "content": msg.content if isinstance(msg.content, str) else str(msg.content),
                "tool_call_id": getattr(msg, "tool_call_id", None)
            }
        elif _is({"SystemMessage", "MockSystemMessage", "_MockSystemMessage"}):
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

    @staticmethod
    def _extract_ai_tool_call_ids(msg) -> List[Dict[str, Optional[str]]]:
        """
        从 AIMessage 中提取 tool_call_id 与对应工具名。

        2026-06-16 新增：用于反查子智能体历史。
        兼容三种来源（同 subagent_message_extractor._extract_tool_calls_from_ai）：
            1. msg.tool_calls（OpenAI 风格）
            2. msg.content list 中 type='tool_use'（Anthropic 风格）
            3. msg.content_blocks 中 type='tool_call'/'non_standard'（langchain-core 1.x）

        Args:
            msg: AIMessage 派生对象

        Returns:
            List[Dict[str, Optional[str]]]: [{"id": str, "name": str}, ...]
            无 tool_calls 时返回空列表
        """
        result: List[Dict[str, Optional[str]]] = []
        # 1) OpenAI 风格
        for tc in (getattr(msg, "tool_calls", None) or []):
            if isinstance(tc, dict):
                result.append({
                    "id": tc.get("id"),
                    "name": tc.get("name") or "",
                })
        # 2) Anthropic 风格
        content = getattr(msg, "content", None)
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict) and block.get("type") == "tool_use":
                    result.append({
                        "id": block.get("id"),
                        "name": block.get("name") or "",
                    })
        # 3) langchain-core 1.x content_blocks
        for block in (getattr(msg, "content_blocks", None) or []):
            if not isinstance(block, dict):
                continue
            btype = block.get("type")
            if btype == "tool_call":
                result.append({
                    "id": block.get("id"),
                    "name": block.get("name") or "",
                })
            elif btype == "non_standard":
                value = block.get("value")
                if isinstance(value, dict) and value.get("type") == "tool_use":
                    result.append({
                        "id": value.get("id"),
                        "name": value.get("name") or "",
                    })
        return result

    @staticmethod
    def _is_ai_message(msg) -> bool:
        """
        判断消息对象是否为 AIMessage 派生类（兼容 Mock 后缀）。

        2026-06-16 新增。
        与 subagent_message_extractor._classify_role 一致：使用 type(msg).__name__ 匹配。
        这样在测试环境中用 type("AIMessage", ...) 构造的 Mock 类也能被正确识别。

        Args:
            msg: 任意消息对象

        Returns:
            bool: 是否为 AIMessage 派生
        """
        type_name = type(msg).__name__ if not isinstance(msg, type) else ""
        return type_name in {"AIMessage", "MockAIMessage", "_MockAIMessage", "AIMessageChunk"}

    @classmethod
    def collect_subagent_tool_call_ids(
        cls,
        main_messages: Iterable[Dict[str, Any]],
    ) -> List[Dict[str, Optional[str]]]:
        """
        从主消息列表（AIMessage 转换后的 dict）中收集所有子智能体 tool_call_id。

        2026-06-16 新增。
        注意：调用方传入的 dict 形态来自 _convert_message_to_dict（AIMessage 分支），
        其保留了原始 msg 的 id；tool_call 详情需另外从原始 LangChain 消息中获取。
        本方法主要作为接口签名占位，实际从 LangChain 消息提取走 _extract_ai_tool_call_ids。

        Args:
            main_messages: 已转换的主消息 dict 列表

        Returns:
            List[Dict[str, Optional[str]]]: 子智能体 tool_call 列表（仅占位返回空，调用方应直接用原始消息列表）
        """
        # 主消息 dict 不含 tool_call_ids 字段（_convert_message_to_dict 故意丢弃），
        # 故该方法仅作为签名占位。实际从原始 LangChain 消息提取请用 collect_tool_calls_from_raw。
        return []

    @classmethod
    async def get_subagent_history(
        cls,
        checkpointer: BaseCheckpointSaver,
        tool_call_id: str,
        limit: Optional[int] = None,
        include_tool: bool = True,
    ) -> Dict[str, Any]:
        """
        从全局 checkpointer 反查单个子智能体 thread 的历史消息。

        2026-06-16 新增。
        子智能体（sandbox / explore）的 thread_id == 父 LLM 调该工具时的 tool_call_id，
        故可以直接按 tool_call_id 反查完整子图状态。

        Args:
            checkpointer: LangGraph checkpointer 实例（与 SandboxTools/FilesystemReadTools 共享）
            tool_call_id: 子智能体 thread_id（== 父 LLM tool_call_id）
            limit: 限制返回消息数量，None 表示全部
            include_tool: 是否包含 ToolMessage，True 用于完整轨迹，False 仅 Human/AI

        Returns:
            Dict[str, Any]: {
                "thread_id": str,
                "messages": [dict, ...],   # 与 _convert_message_to_dict 输出格式一致
                "total": int,
            }
            thread 不存在时 messages = []，total = 0
        """
        config = {"configurable": {"thread_id": tool_call_id}}
        result: Dict[str, Any] = {
            "thread_id": tool_call_id,
            "messages": [],
            "total": 0,
        }

        if not tool_call_id:
            return result

        try:
            state = await checkpointer.aget(config)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[History] get_subagent_history aget 失败: thread_id={tool_call_id}, error={e}"
            )
            return result

        if not state:
            return result

        channel_values = state.get("channel_values", {}) if hasattr(state, "get") else {}
        messages_data = channel_values.get("messages", []) if isinstance(channel_values, dict) else []

        messages: List[Dict[str, Any]] = []
        for msg in messages_data:
            msg_dict = cls._convert_message_to_dict(msg)
            if not msg_dict:
                continue
            if not include_tool and msg_dict.get("type") == "tool":
                continue
            messages.append(msg_dict)

        if limit and limit > 0:
            messages = messages[-limit:]

        result["messages"] = messages
        result["total"] = len(messages)
        return result

    @classmethod
    async def merge_main_and_subagent_messages(
        cls,
        checkpointer: BaseCheckpointSaver,
        main_messages: List[Dict[str, Any]],
        raw_main_messages: Optional[Iterable[Any]] = None,
        subagent_limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        合并主消息与子智能体消息流（按时序）。

        2026-06-16 新增。
        流程：
            1. 遍历 raw_main_messages（LangChain AIMessage 列表），提取所有 tool_call_id
            2. 跳过 raw_main_messages 时，仅返回 main_messages 转换结果（无子消息）
            3. 对每个 tool_call_id 反查子智能体历史，构造 type='subagent' 的中间元素
            4. 主消息与子消息按时序插入（AIMessage 之后立即跟对应子智能体消息流）

        Args:
            checkpointer: LangGraph checkpointer 实例
            main_messages: 主消息 dict 列表（已转换）
            raw_main_messages: 原始 LangChain 消息列表（提供 tool_call_id 提取能力）
            subagent_limit: 子智能体单 thread 返回消息数限制

        Returns:
            List[Dict[str, Any]]: 合并后的消息列表，元素可能是：
                - 主消息 dict（type=user/ai/...）
                - 子智能体 dict（type='subagent'，含 thread_id/tool/parent_message_id/messages）
        """
        if not main_messages:
            return main_messages

        # 1) 收集子智能体 tool_call 信息（按出现顺序）
        #    2026-06-17 修复：原实现直接用 raw idx 访问 main_messages，但 main_messages 已过滤 ToolMessage，
        #    索引错位导致中间位置的子智能体丢失、末尾 AI 因 idx 越界被 break。
        #    修复方案：分别收集 raw 与 main 中所有 AI 消息的位置，按出现顺序一一配对。
        ordered_subagents: List[Dict[str, Any]] = []
        if raw_main_messages:
            raw_list = list(raw_main_messages)

            # 构建"raw 中 AI 位置列表"与"main 中 AI 位置列表"
            raw_ai_positions: List[int] = [
                i for i, m in enumerate(raw_list) if cls._is_ai_message(m)
            ]
            main_ai_positions: List[int] = [
                i for i, m in enumerate(main_messages) if m.get("type") == "ai"
            ]

            # 防御：若两边 AI 数量不一致（极端边界），取较小长度避免越界
            paired_count = min(len(raw_ai_positions), len(main_ai_positions))

            for k in range(paired_count):
                raw_idx = raw_ai_positions[k]
                main_idx = main_ai_positions[k]
                raw_msg = raw_list[raw_idx]
                main_msg = main_messages[main_idx]

                tool_calls = cls._extract_ai_tool_call_ids(raw_msg)
                for tc in tool_calls:
                    tid = tc.get("id")
                    tool_name = tc.get("name") or ""
                    if not tid:
                        continue
                    # 2026-06-16 修复：仅子智能体工具（注册表内）的 tool_call 才反查子 thread 历史。
                    # 普通工具（如 generate_report）的 tool_call_id 在 checkpointer 中无对应子 thread，
                    # 反查会返回空 messages，但仍会被错误包装成 type:"subagent"，前端误渲染为 SubAgentCard。
                    if not is_subagent_tool(tool_name):
                        continue
                    ordered_subagents.append({
                        "thread_id": tid,
                        "tool": tool_name,
                        # 用 main 索引（不是 raw 索引），确保合并阶段 grouped[main_idx]
                        # 能把 subagent 元素正确插入到 main_messages[main_idx] 之后
                        "parent_message_index": main_idx,
                        "parent_message_id": main_msg.get("id"),
                    })

        if not ordered_subagents:
            return main_messages

        # 2) 反查每个子 thread 的历史
        sub_histories: Dict[str, Dict[str, Any]] = {}
        for sa in ordered_subagents:
            tid = sa["thread_id"]
            if tid in sub_histories:
                # 同一 thread 只查一次
                continue
            sub_histories[tid] = await cls.get_subagent_history(
                checkpointer=checkpointer,
                tool_call_id=tid,
                limit=subagent_limit,
                include_tool=True,
            )

        # 3) 按 parent_message_index 按时序合并
        #    对每个主消息位置，在其后追加所有归属于该位置的 subagent 元素
        #    使用 group 避免同一索引下出现多个 subagent 时丢失
        grouped: Dict[int, List[Dict[str, Any]]] = {}
        for sa in ordered_subagents:
            grouped.setdefault(sa["parent_message_index"], []).append(sa)

        merged: List[Dict[str, Any]] = []
        for i, main_msg in enumerate(main_messages):
            merged.append(main_msg)
            for sa in grouped.get(i, []):
                history = sub_histories.get(sa["thread_id"], {})
                sub_messages = history.get("messages", [])
                merged.append({
                    "type": "subagent",
                    "role": "subagent",
                    "id": f"subagent-{sa['thread_id']}",
                    "thread_id": sa["thread_id"],
                    "tool": sa["tool"],
                    "parent_message_id": sa["parent_message_id"],
                    "messages": sub_messages,
                    "total": history.get("total", 0),
                    # 2026-06-18 新增：展示元信息由后端统一提供，降低前端耦合
                    "meta": get_subagent_meta(sa["tool"]),
                })

        return merged

    @classmethod
    async def collect_subagent_thread_ids_for_cleanup(
        cls,
        checkpointer: BaseCheckpointSaver,
        session_id: str,
    ) -> List[str]:
        """
        收集主会话下所有需要清理的子智能体 thread_id（用于 delete_session）。

        2026-06-16 新增。
        流程：
            1. 通过 checkpointer.aget 获取主 session 最新 state
            2. 遍历 channel_values.messages 中所有 AIMessage
            3. 提取每个 AIMessage 的 tool_call_id

        Args:
            checkpointer: LangGraph checkpointer 实例
            session_id: 主会话 ID

        Returns:
            List[str]: 去重后的子 thread_id 列表
        """
        config = {"configurable": {"thread_id": session_id}}
        ids: List[str] = []
        seen: set = set()
        try:
            state = await checkpointer.aget(config)
        except Exception as e:
            import logging
            logging.getLogger(__name__).warning(
                f"[History] collect_subagent_thread_ids aget 失败: session_id={session_id}, error={e}"
            )
            return ids

        if not state:
            return ids

        channel_values = state.get("channel_values", {}) if hasattr(state, "get") else {}
        messages_data = channel_values.get("messages", []) if isinstance(channel_values, dict) else []

        for msg in messages_data:
            if not cls._is_ai_message(msg):
                continue
            for tc in cls._extract_ai_tool_call_ids(msg):
                tid = tc.get("id")
                # 2026-06-16 修复：仅收集子智能体工具的 thread_id，
                # 避免删除会话时尝试清理普通工具的 tool_call_id（虽不致命但浪费 DB 调用 + 噪音日志）
                if not tid or not is_subagent_tool(tc.get("name") or ""):
                    continue
                if tid not in seen:
                    seen.add(tid)
                    ids.append(tid)

        return ids

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
