#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
BaseFilesystemTool - 文件系统子智能体基础工具

该模块提供 `BaseFilesystemTool` 类，封装"创建子智能体 + 流式执行 + 事件推送"
的通用逻辑。上层工具（如 explore、query_knowledge）只需指定：
    - tool_name: 工具名（用于 SSE 事件与日志）
    - system_prompt: 子智能体系统提示词
    - max_file_size_mb: 文件搜索大小限制

    然后调用 `await tool.arun(prompt, runtime, root_path)` 即可获得 `Command`。


通过 context 传入不同的 `root_path`，即可灵活扩展不同目标地址的文件/知识库
检索工具，无需重复实现子智能体生命周期管理。

Date: 2026-06-18
Author: AI Assistant
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Union

from langchain.agents import create_agent
from langchain.agents.middleware import ContextEditingMiddleware, TodoListMiddleware
from langchain.agents.middleware.context_editing import ClearToolUsesEdit
from deepagents import FilesystemMiddleware
from deepagents.backends import FilesystemBackend
from langchain.tools import ToolRuntime
from langchain_core.messages import AIMessage, ToolMessage
from langgraph.config import get_stream_writer
from langgraph.types import Command

from app.core.agent.AgentContext import AgentContext
from app.core.config.config import LLM_CONFIG
from app.core.llmcalls.model_factory import ModelFactory
from app.core.tools._stop_signal import get_current_request
from app.core.tools.events import create_tool_event
from app.core.tools.subagent_message_extractor import extract_structured_messages
from app.core.tools.subagent_registry import get_subagent_meta
from app.shared.tools.middleware.encoding_safe_file_search import EncodingSafeFileSearchMiddleware
from app.shared.utils.memory.checkpoint import get_async_checkpointer


class BaseFilesystemTool:
    """
    文件系统子智能体基础执行器。

    负责：
    - 校验目标根目录
    - 创建并运行子智能体
    - 流式事件推送（tool_start / tool_progress / tool_stop / tool_error）
    - 用户停止信号感知
    - 返回 LangGraph Command

    Attributes:
        tool_name: 工具名，用于 SSE 事件与日志。
        system_prompt: 子智能体系统提示词。
        max_file_size_mb: 文件搜索中间件最大文件大小（MB）。
    """

    _STOP_CHECK_INTERVAL = 5

    def __init__(
        self,
        tool_name: str,
        system_prompt: str,
        max_file_size_mb: int = 10,
    ):
        """
        初始化基础文件系统工具。

        Args:
            tool_name: 工具名（SSE 事件、日志使用）。
            system_prompt: 子智能体系统提示词。
            max_file_size_mb: 文件搜索中间件允许的最大单文件大小，默认 10 MB。
        """
        self.tool_name = tool_name
        self.system_prompt = system_prompt
        self.max_file_size_mb = max_file_size_mb
        self.logger = logging.getLogger(self.__class__.__name__)

    def _create_model(self) -> object:
        """
        根据全局 LLM 配置创建模型实例。

        Returns:
            object: LangChain 兼容的聊天模型实例。
        """
        return ModelFactory.create_model(
            model_type=LLM_CONFIG["model_type"],
            model_name=LLM_CONFIG["model_name"],
            api_key=LLM_CONFIG["api_key"],
            temperature=LLM_CONFIG["temperature"],
            base_url=LLM_CONFIG["base_url"],
        )

    async def create_child_agent(self, root_path: Path, model: object) -> object:
        """
        创建文件系统探索子智能体。

        Args:
            root_path: 已校验的根目录路径。
            model: 由 `_create_model` 生成的模型实例。

        Returns:
            object: 配置完成的子智能体（create_agent 返回值）。
        """
        middleware = [
            EncodingSafeFileSearchMiddleware(
                root_path=str(root_path),
                max_file_size_mb=self.max_file_size_mb,
            ),
            FilesystemMiddleware(
                backend=FilesystemBackend(
                    root_dir=str(root_path),
                    virtual_mode=True,
                ),
            ),
            TodoListMiddleware(),
            ContextEditingMiddleware(
                edits=[
                    ClearToolUsesEdit(
                        trigger=100000,
                        keep=20,
                        exclude_tools=[],
                        placeholder="[earlier tool results trimmed for context length]",
                    )
                ]
            ),
        ]

        agent_kwargs = {
            "model": model,
            "middleware": middleware,
            "system_prompt": self.system_prompt,
            # 2026-06-16 改造：使用全局共享 checkpointer 持久化子智能体 messages
            "checkpointer": await get_async_checkpointer(),
        }

        return create_agent(**agent_kwargs)

    def _validate_root_path(self, root_path: Union[str, Path]) -> Path:
        """
        校验目标根目录是否可用。

        Args:
            root_path: 目标目录路径（字符串或 Path）。

        Returns:
            Path: 校验后的 Path 对象。

        Raises:
            FileNotFoundError: 目录不存在。
            NotADirectoryError: 路径不是目录。
            ValueError: 目录为空。
        """
        path = Path(root_path)
        if not path.exists():
            raise FileNotFoundError(f"工作空间文件夹不存在: {path}")
        if not path.is_dir():
            raise NotADirectoryError(f"路径不是文件夹: {path}")
        if not any(path.iterdir()):
            raise ValueError(f"工作空间文件夹为空: {path}")
        return path

    @staticmethod
    def _extract_last_ai_text(messages: list) -> str:
        """
        从消息列表中提取最后一条 AI 消息的文本内容。

        兼容测试环境 Mock：通过消息类型名字符串判断，不依赖真实的 AIMessage 类型。

        Args:
            messages: LangChain 消息对象列表。

        Returns:
            str: 最后一条 AI 文本内容；不存在时返回空字符串。
        """
        for msg in reversed(messages):
            if type(msg).__name__ != "AIMessage":
                continue
            content = msg.content
            if not content:
                continue
            if isinstance(content, str) and content.strip():
                return content.strip()
            if isinstance(content, list):
                text_parts = [
                    b.get("text", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "text"
                ]
                if text_parts:
                    return "".join(text_parts).strip()
                thinking_parts = [
                    b.get("thinking", "")
                    for b in content
                    if isinstance(b, dict) and b.get("type") == "thinking"
                ]
                if thinking_parts:
                    return "".join(thinking_parts).strip()
        return ""

    async def arun(
        self,
        prompt: str,
        runtime: ToolRuntime[AgentContext],
        root_path: Union[str, Path],
    ) -> Command:
        """
        在指定根目录下启动文件系统子智能体并返回结果。

        Args:
            prompt: 详细的任务描述，父 LLM 应将用户问题改写为具体任务。
            runtime: 工具运行时上下文，必须包含 `tool_call_id` 与 `context`。
            root_path: 目标根目录（字符串或 Path），决定子智能体可操作范围。

        Returns:
            Command: 包含 ToolMessage 的 LangGraph Command。

        Raises:
            FileNotFoundError: 目标目录不存在。
            NotADirectoryError: 目标路径不是目录。
            ValueError: 目标目录为空。
        """
        tool_call_id = runtime.tool_call_id
        start_time = datetime.now()
        writer = get_stream_writer()
        request = get_current_request()
        actual_task_id = tool_call_id

        root_path = self._validate_root_path(root_path)

        start_event = create_tool_event(
            event_type="tool_start",
            tool=self.tool_name,
            tool_call_id=tool_call_id,
            data={
                "args": {"prompt": prompt},
                "root_path": str(root_path),
                "description": f"开始文件探索: {prompt[:100]}",
                # 子智能体事件协议字段
                "thread_id": tool_call_id,
                "parent_prompt": prompt,
                # 2026-06-18 新增：展示元信息由后端统一提供，降低前端耦合
                "meta": get_subagent_meta(self.tool_name),
            },
        )
        writer(dict(start_event))

        try:
            model = self._create_model()
            child_agent = await self.create_child_agent(root_path, model)

            config = {"configurable": {"thread_id": actual_task_id}}

            final_answer = ""
            all_messages = []
            stopped_by_user = False

            async for chunk in child_agent.astream(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
                stream_mode=["updates", "values", "messages"],
            ):
                # 用户停止信号检测
                if request is not None and len(all_messages) % self._STOP_CHECK_INTERVAL == 0:
                    try:
                        if await request.is_disconnected():
                            self.logger.info(
                                "[%s] 客户端已断开，停止子智能体。tool_call_id=%s",
                                self.tool_name,
                                tool_call_id,
                            )
                            stopped_by_user = True
                            break
                    except Exception as e:
                        self.logger.warning(f"[{self.tool_name}] is_disconnected 检测异常: {e}")

                if isinstance(chunk, tuple) and len(chunk) == 2:
                    stream_mode, data = chunk
                elif isinstance(chunk, dict):
                    stream_mode = chunk.get("type")
                    data = chunk.get("data")
                else:
                    continue

                if stream_mode == "updates":
                    if isinstance(data, dict):
                        for node_name, node_data in data.items():
                            if isinstance(node_data, dict) and "messages" in node_data:
                                all_messages.extend(node_data["messages"])

                    writer(dict(create_tool_event(
                        event_type="tool_progress",
                        tool=self.tool_name,
                        tool_call_id=tool_call_id,
                        data={
                            "child_stream": data,
                            "message": "子智能体执行中",
                            "thread_id": tool_call_id,
                            "child_messages": extract_structured_messages(all_messages),
                        },
                    )))

            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            if stopped_by_user:
                final_answer = "子智能体已被用户中止"
                stop_event = create_tool_event(
                    event_type="tool_stop",
                    tool=self.tool_name,
                    tool_call_id=tool_call_id,
                    data={
                        "status": "stopped_by_user",
                        "result": {
                            "prompt": prompt,
                            "task_id": actual_task_id,
                            "answer": final_answer,
                        },
                        "duration_ms": duration_ms,
                        "thread_id": tool_call_id,
                        "parent_prompt": prompt,
                        "final_messages": extract_structured_messages(all_messages),
                    },
                )
                writer(dict(stop_event))
                return Command(
                    update={
                        "messages": [
                            ToolMessage(
                                content=json.dumps(
                                    {"subagent": final_answer},
                                    ensure_ascii=False,
                                ),
                                tool_call_id=tool_call_id,
                            )
                        ]
                    }
                )

            # 子智能体最终答案：统一从循环内累计的 all_messages 中提取最后一条 AI 文本。
            # 不能用 data["messages"]：当最后一块流是 updates 模式时，data = {node_name: state_delta}，
            # 没有顶层 messages 键，会导致取不到真实回复。
            if not final_answer and all_messages:
                final_answer = self._extract_last_ai_text(all_messages)

            # 兜底：仅在确实没有任何 AI 文本产出时才使用；同时记录 warning 便于排查
            if not final_answer:
                self.logger.warning(
                    "[%s] 未获取到 AI 文本回复。tool_call_id=%s, all_messages_count=%d",
                    self.tool_name,
                    tool_call_id,
                    len(all_messages),
                )
                final_answer = "子智能体执行完成，但未获取到文本回复。"

            output_text = (
                f"task_id: {actual_task_id} (for resuming to continue this task if needed)\n"
                f"\n"
                f"<task_result>\n"
                f"{final_answer}\n"
                f"</task_result>"
            )

            stop_event = create_tool_event(
                event_type="tool_stop",
                tool=self.tool_name,
                tool_call_id=tool_call_id,
                data={
                    "status": "success",
                    "result": {
                        "prompt": prompt,
                        "task_id": actual_task_id,
                        "answer": final_answer,
                    },
                    "duration_ms": duration_ms,
                    "thread_id": tool_call_id,
                    "parent_prompt": prompt,
                    "final_messages": extract_structured_messages(all_messages),
                },
            )
            writer(dict(stop_event))

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps(
                                {"subagent": output_text},
                                ensure_ascii=False,
                            ),
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )

        except Exception as e:
            self.logger.exception("[%s] 子智能体执行异常: %s", self.tool_name, e)
            end_time = datetime.now()
            duration_ms = int((end_time - start_time).total_seconds() * 1000)

            error_event = create_tool_event(
                event_type="tool_error",
                tool=self.tool_name,
                tool_call_id=tool_call_id,
                data={
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                    "args": {"prompt": prompt, "task_id": actual_task_id},
                    "duration_ms": duration_ms,
                    "thread_id": tool_call_id,
                    "parent_prompt": prompt,
                },
            )
            writer(dict(error_event))

            return Command(
                update={
                    "messages": [
                        ToolMessage(
                            content=json.dumps(
                                {"subagent": str(e)},
                                ensure_ascii=False,
                            ),
                            tool_call_id=tool_call_id,
                        )
                    ]
                }
            )
