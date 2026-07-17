#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuWebSocketService - 飞书 WebSocket 长连接服务

职责：
    - 启动 lark.ws.Client 订阅 im.message.receive_v1 事件
    - 私聊（p2p）消息全部回复；群聊仅响应 @机器人 消息
    - 将消息路由到 settings.feishu.feishu_ws_agent_name 指定的智能体处理
    - 通过 client.im.v1.message.create 把回复发回飞书

回复渲染（2026-07-17 新增）：
    - 路径 1：agent 回复含 markdown 特征 → 自动转飞书交互式卡片
    - 路径 2（HITL 人工回路）：agent 触发 LangGraph interrupt 暂停 → 发带选项按钮的
      交互式卡片；用户点击 → 飞书回调 card.action.trigger → 解析 qid/oid →
      构造 Command(resume=...) 续跑 → 最终回复走路径 1
    - 卡片 API 任何失败 → 自动降级纯文本发送

依赖：
    - lark_oapi as lark（真实依赖由 app/requirements.txt 提供）
    - app.shared.utils.agent.agent_config_service.AgentConfigService
    - app.shared.tools.skills.feishu.MarkdownToCardConverter（markdown → 卡片 JSON）
    - app.shared.tools.skills.feishu.InterruptToCardConverter（interrupt → 按钮卡片 JSON）
    - 主事件循环：lifespan 启动时通过 set_event_loop() 注入
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from typing import Any, Dict, Optional, Tuple

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    CreateMessageRequest,
    CreateMessageRequestBody,
)

from app.shared.tools.skills.feishu.InterruptToCardConverter import (
    InterruptToCardConverter,
    parse_card_action_value,
)
from app.shared.tools.skills.feishu.MarkdownToCardConverter import (
    MarkdownToCardConverter,
)

logger = logging.getLogger(__name__)

# 飞书单条消息文本上限（字节；UTF-8 约 4000 字符）
_FEISHU_TEXT_MAX_LEN = 4000
_TRUNCATE_HINT = "\n...(内容过长已截断)"


class FeishuWebSocketService:
    """飞书 WebSocket 长连接服务管理器。

    Attributes:
        agent_name: 飞书消息路由到的目标智能体名称（默认 project）
    """

    def __init__(
        self,
        lark_client: lark.Client,
        agent_config_service: Any,
        agent_name: str = "project",
        log_level: str = "INFO",
    ) -> None:
        """初始化飞书 WebSocket 服务。

        Args:
            lark_client: 已配置好的 lark.Client 实例
            agent_config_service: AgentConfigService 实例，用于 build_agent_instance
            agent_name: 智能体名称
            log_level: lark SDK 日志级别（DEBUG/INFO/WARNING/ERROR）
        """
        self._lark_client = lark_client
        self._agent_config_service = agent_config_service
        self._agent_name = agent_name
        self._log_level = log_level
        self._ws_client: Optional[lark.ws.Client] = None
        self._should_run = False
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._bot_open_id: Optional[str] = None
        # HITL 状态：session_id → {"chat_id": ..., "request": ...}
        # 仅存内存，lifespan 重启后丢失；用户需重新提问。
        self._pending_interrupts: Dict[str, Dict[str, Any]] = {}

    # ------------------------------------------------------------------ #
    # Lifecycle                                                          #
    # ------------------------------------------------------------------ #

    def set_event_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入主事件循环（lifespan 启动时调用）。

        Args:
            loop: FastAPI 主事件循环
        """
        self._loop = loop

    async def start_async(self) -> None:
        """异步启动 WebSocket 服务（lifespan 调用）。

        把阻塞的 ws_client.start() 包装到后台线程，避免阻塞事件循环。
        """
        if self._should_run:
            logger.warning("FeishuWebSocketService 已启动，跳过重复启动")
            return

        self._should_run = True
        # 尝试获取机器人 open_id（同步 HTTP 调用，在线程池跑，避免阻塞主 loop）
        # 用于群聊 @机器人 精确检测；失败降级为 '@' in content
        try:
            self._bot_open_id = await asyncio.to_thread(self._fetch_bot_open_id)
            if self._bot_open_id:
                logger.info("飞书机器人 open_id: %s", self._bot_open_id)
            else:
                logger.info("未获取到飞书机器人 open_id，群聊@检测将降级为 '@' in content")
        except Exception as e:  # noqa: BLE001
            logger.warning("获取飞书机器人 open_id 异常，降级使用 '@' 检测: %s", e)
            self._bot_open_id = None

        # 主线程中预构造 ws_client（仅注册事件处理器；连接操作放到线程里做）
        self._ws_client = self._build_ws_client()
        self._thread = threading.Thread(
            target=self._run_ws_blocking,
            name="feishu-ws",
            daemon=True,
        )
        self._thread.start()
        logger.info("FeishuWebSocketService 已异步启动（agent_name=%s）", self._agent_name)

    def _run_ws_blocking(self) -> None:
        """后台线程入口：阻塞运行 ws_client.start()。

        关键约束（lark SDK 模块级 loop 陷阱）：
            lark_oapi.ws.client 在模块导入时执行 ``loop = asyncio.get_event_loop()``，
            并把该 loop 缓存在模块级变量。FastAPI/uvicorn 主线程的 loop 在 lifespan
            期间已运行，导致线程中 ``loop.run_until_complete(...)`` 报
            "This event loop is already running"。

        解决方案：
            在后台线程入口创建独立的新 event loop，把它 set_event_loop 到当前线程，
            并 monkey-patch ``lark_oapi.ws.client.loop`` 指向新 loop。
            同时把 ``client.bot.v1.bot.get`` 等外部读取也放在主线程（lifespan 阶段）
            完成，线程只负责建立 WebSocket。

        重连处理：SDK 内部自动捕获断开并重连，循环直到 _should_run=False 或进程退出。
        """
        import lark_oapi.ws.client as _lark_ws_client_mod

        new_loop = asyncio.new_event_loop()
        asyncio.set_event_loop(new_loop)
        # 把模块级 loop 指向新 loop（lark SDK 内部用此变量调用 run_until_complete）
        _lark_ws_client_mod.loop = new_loop
        try:
            if self._ws_client is not None:
                self._ws_client.start()
        except Exception as e:  # noqa: BLE001
            logger.error("飞书 WebSocket 异常退出: %s", e, exc_info=True)
        finally:
            try:
                new_loop.close()
            except Exception:  # noqa: BLE001
                pass

    def stop(self) -> None:
        """停止服务（lifespan 关闭时调用）。

        由于 lark.ws.Client 无原生 stop，仅设置标志；线程随进程退出而终止。
        """
        self._should_run = False
        logger.info("FeishuWebSocketService stop 标志已设置")

    # ------------------------------------------------------------------ #
    # Internals                                                          #
    # ------------------------------------------------------------------ #

    def _fetch_bot_open_id(self) -> Optional[str]:
        """从飞书 Open API 获取机器人的 open_id（一次性缓存）。

        Returns:
            str: 机器人的 open_id；获取失败或 SDK 未提供 bot 模块时返回 None。

        Raises:
            RuntimeError: 当 lark SDK 返回失败响应时
        """
        try:
            from lark_oapi.api.bot.v1 import GetBotRequest
        except ImportError:
            # 2026-07-16:当前 lark-oapi 版本未提供 bot/v1 子模块;
            # 群聊@机器人检测降级到 'in' content 策略。
            return None
        try:
            req = GetBotRequest.builder().build()
            resp = self._lark_client.bot.v1.bot.get(req)
        except (ImportError, AttributeError):
            return None
        if resp.success() and resp.data and resp.data.bot:
            return getattr(resp.data.bot, "open_id", None) or getattr(
                resp.data.bot, "app_id", None
            )
        return None

    def _resolve_lark_log_level(self) -> int:
        """将字符串日志级别映射为 lark.LogLevel 枚举值。"""
        mapping = {
            "DEBUG": lark.LogLevel.DEBUG,
            "INFO": lark.LogLevel.INFO,
            "WARNING": lark.LogLevel.WARNING,
            "ERROR": lark.LogLevel.ERROR,
        }
        return mapping.get((self._log_level or "").upper(), lark.LogLevel.INFO)

    def _build_ws_client(self) -> lark.ws.Client:
        """构造 lark.ws.Client 实例并注册消息事件处理器。

        Returns:
            lark.ws.Client: 配置完成的 WebSocket 客户端

        Raises:
            RuntimeError: 当 lark 模块未提供 ws.Client / EventDispatcherHandler / 凭证缺失时
        """
        ws_module = getattr(lark, "ws", None)
        if ws_module is None or not hasattr(ws_module, "Client"):
            raise RuntimeError("lark.ws.Client 不可用（lark-oapi SDK 未正确安装或 mock 环境）")

        ed_module = getattr(lark, "EventDispatcherHandler", None)
        if ed_module is None or not hasattr(ed_module, "builder"):
            raise RuntimeError(
                "lark.EventDispatcherHandler 不可用（lark-oapi SDK 未正确安装或 mock 环境）"
            )

        # 2026-07-16 修复：lark SDK 把凭证存到 client._config.app_id / .app_secret，
        # 不是 client._app_id（之前用 getattr 永远拿不到）。
        config = getattr(self._lark_client, "_config", None)
        app_id = (getattr(config, "app_id", None) if config else None) or ""
        app_secret = (getattr(config, "app_secret", None) if config else None) or ""
        if not app_id or not app_secret:
            raise RuntimeError(
                "飞书凭证缺失：feishu_app_id 与 feishu_app_secret 必须在 .env 中正确配置"
            )

        handler = (
            ed_module.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .register_p2_card_action_trigger(self._on_card_action)
            .build()
        )
        return ws_module.Client(
            app_id,
            app_secret,
            event_handler=handler,
            log_level=self._resolve_lark_log_level(),
        )

    # ------------------------------------------------------------------ #
    # Message handling                                                   #
    # ------------------------------------------------------------------ #

    def _on_message(self, data: P2ImMessageReceiveV1) -> None:
        """lark SDK 同步事件回调入口。

        1) 解析 chat_type / chat_id / open_id / text
        2) 群聊未 @机器人 → 跳过
        3) 非文本消息 → 跳过
        4) 构造 session_id
        5) 投递协程 _handle_message 到主事件循环

        Args:
            data: 飞书消息事件对象
        """
        try:
            chat_type, chat_id, open_id, msg_type, text = self._extract_message(data)
            if not chat_id or not open_id:
                logger.warning("飞书消息缺少 chat_id 或 open_id，跳过")
                return

            # 群聊：仅响应 @机器人
            if chat_type == "group":
                if not self._is_bot_mentioned(data):
                    logger.debug(
                        "群聊 %s 消息未 @机器人，跳过（msg_type=%s）", chat_id, msg_type
                    )
                    return

            # 非文本消息：跳过（仅日志）
            if msg_type != "text":
                logger.info(
                    "飞书 %s chat=%s 收到非文本消息 msg_type=%s，跳过",
                    chat_type, chat_id, msg_type,
                )
                return

            session_id = self._build_session_id(chat_type, chat_id, open_id)
            self._dispatch_async(self._handle_message(session_id, chat_id, text))
        except Exception as e:  # noqa: BLE001
            logger.exception("处理飞书消息异常（不影响 WebSocket）: %s", e)

    def _extract_message(
        self, data: P2ImMessageReceiveV1
    ) -> tuple[str, str, str, str, str]:
        """从飞书消息事件中提取关键字段。

        Args:
            data: 飞书消息事件对象

        Returns:
            tuple: (chat_type, chat_id, open_id, msg_type, text)
        """
        event = getattr(data, "event", None)
        msg = getattr(event, "message", None) if event else None
        sender = getattr(event, "sender", None) if event else None

        chat_type = (getattr(msg, "chat_type", None) or "p2p") if msg else "p2p"
        chat_id = getattr(msg, "chat_id", None) if msg else None
        chat_id = chat_id or ""

        sender_id = getattr(sender, "sender_id", None) if sender else None
        open_id = getattr(sender_id, "open_id", None) if sender_id else None
        open_id = open_id or ""

        msg_type = getattr(msg, "message_type", None) or "" if msg else ""

        text = ""
        content_raw = getattr(msg, "content", None) if msg else None
        if content_raw:
            try:
                payload = json.loads(content_raw)
                text = str(payload.get("text", "") or "").strip()
            except Exception:  # noqa: BLE001
                text = ""

        return chat_type, chat_id, open_id, msg_type, text

    def _is_bot_mentioned(self, data: P2ImMessageReceiveV1) -> bool:
        """判断群聊消息中是否 @机器人。

        优先精确匹配 mentions 中的 bot open_id；获取失败时降级使用 '@' in content。

        Args:
            data: 飞书消息事件对象

        Returns:
            bool: 是否 @机器人
        """
        event = getattr(data, "event", None)
        msg = getattr(event, "message", None) if event else None
        mentions = getattr(msg, "mentions", None) if msg else None
        if mentions and self._bot_open_id:
            for m in mentions:
                m_id = getattr(m, "id", None)
                m_open_id = getattr(m_id, "open_id", None) if m_id else None
                if m_open_id and m_open_id == self._bot_open_id:
                    return True
        # 降级：content_raw 中含 '@'
        content_raw = getattr(msg, "content", None) if msg else None
        if content_raw and "@" in content_raw:
            return True
        return False

    def _build_session_id(self, chat_type: str, chat_id: str, open_id: str) -> str:
        """构造 session_id，私聊/群聊分别隔离会话上下文。

        策略（2026-07-16 调整）：
            - 私聊（p2p）：按用户 open_id 区分，每个用户独立会话上下文
            - 群聊（group）：按 chat_id + open_id 组合区分，每位用户在每个群里
              各自维护独立会话上下文。这样能避免群里所有人的消息都堆到一个
              LangGraph checkpointer thread 中导致上下文无限膨胀、token 飙升。

        Args:
            chat_type: p2p / group
            chat_id: 飞书 chat_id
            open_id: 用户 open_id

        Returns:
            str: session_id
        """
        if chat_type == "group":
            return f"feishu:group:{chat_id}:{open_id}"
        return f"feishu:p2p:{open_id}"

    def _dispatch_async(self, coro: Any) -> None:
        """把协程投递回主事件循环（在 SDK 同步回调中调用）。

        Args:
            coro: 协程对象
        """
        if self._loop is None or self._loop.is_closed():
            logger.warning("主事件循环不可用，无法投递飞书消息处理任务")
            return
        try:
            asyncio.run_coroutine_threadsafe(coro, self._loop)
        except Exception as e:  # noqa: BLE001
            logger.error("投递飞书消息处理协程失败: %s", e)

    # ------------------------------------------------------------------ #
    # Agent orchestration                                                #
    # ------------------------------------------------------------------ #

    async def _handle_message(self, session_id: str, chat_id: str, text: str) -> None:
        """路由消息到目标智能体，收集完整回复后发回飞书。

        优先处理 HITL：若 agent 触发 interrupt 暂停 → 发带选项按钮卡片 → 等待用户
        在飞书里点击 → 飞书回调 → 续跑 agent。否则走普通文本/卡片回复路径。

        Args:
            session_id: 会话 ID（LangGraph thread_id）
            chat_id: 飞书 chat_id
            text: 用户消息文本
        """
        if not text:
            logger.info("飞书消息 text 为空，跳过（session_id=%s）", session_id)
            return
        try:
            reply, interrupt_req = await self._call_agent(session_id, text)
            if interrupt_req:
                # 路径 2：HITL 人工回路
                self._pending_interrupts[session_id] = {
                    "chat_id": chat_id,
                    "request": interrupt_req,
                }
                self._send_interrupt_card(chat_id, interrupt_req, session_id)
            elif reply:
                # 路径 1：普通回复（自动 markdown → 卡片 / 文本）
                self._send_reply(chat_id, reply)
            else:
                logger.info("智能体未产生回复/HITL（session_id=%s）", session_id)
        except Exception as e:  # noqa: BLE001
            # 单条消息异常不影响 WebSocket 连接
            logger.exception("处理飞书消息失败（已隔离，session_id=%s）: %s", session_id, e)

    async def _call_agent(
        self,
        session_id: str,
        text: str,
        resume: Optional[Dict[str, Any]] = None,
    ) -> Tuple[Optional[str], Optional[Dict[str, Any]]]:
        """调用 build_agent_instance 构造 agent，遍历 stream 收集完整回复。

        收集策略（兼容 LangGraph 不同图结构）：
            1) messages 模式流式 token → 直接拼接为回复
            2) updates 模式节点输出 → 从每个节点的 state 找最新 AI/AIMessage
            3) HITL 中断 / interrupt 事件 → 不计入回复，保留 checkpoint
                （返回 (None, structured_interrupt)）

        项目内 project 智能体经测试 stream_mode=["updates", "messages"] 组合模式
        可同时拿到 token 和节点状态。

        Args:
            session_id: 会话 ID（LangGraph thread_id）
            text: 用户消息（resume 场景可为空）
            resume: HITL 恢复参数；传入时构造 Command(resume=...)

        Returns:
            tuple: (reply_text, interrupt_request)
                - reply_text: 拼接后的完整回复；agent 无输出时为 None
                - interrupt_request: 结构化 interrupt 请求（HITL 触发时），否则 None
        """
        build = getattr(self._agent_config_service, "build_agent_instance", None)
        if build is None:
            logger.error("agent_config_service.build_agent_instance 不可用")
            return None, None

        # build_agent_instance 返回 (agent, context_instance, input_state)
        kwargs: Dict[str, Any] = {}
        if resume is not None:
            kwargs["resume"] = resume
        try:
            agent, _context, _input_state = await build(
                self._agent_name,
                session_id,
                text,
                **kwargs,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("build_agent_instance 失败: %s", e)
            return None, None

        # 收集策略：优先 messages 模式的流式 token；备选 updates 模式下从
        # state 的 messages 列表提取最后一条 AI/AIMessage 内容。
        chunks_token: list[str] = []
        last_ai_content: Optional[str] = None
        interrupt_request: Optional[Dict[str, Any]] = None
        try:
            async for chunk in agent.stream(
                _input_state,
                context=_context,
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 100},
                stream_mode=["messages", "updates"],
            ):
                # ===== 中断检测（多模式兼容，参考 app/routers/_stream_helper.py） =====
                interrupt_data = self._extract_interrupt_from_chunk(chunk)
                if interrupt_data:
                    interrupt_request = self._parse_interrupt_data(interrupt_data)
                    if interrupt_request:
                        # HITL 触发：停止继续收集 token
                        break

                if not (isinstance(chunk, tuple) and len(chunk) == 2):
                    continue
                mode, payload = chunk
                if mode == "messages":
                    # payload = (msg_chunk, metadata)
                    if not (isinstance(payload, tuple) and len(payload) == 2):
                        continue
                    msg_chunk, _meta = payload
                    text_part = self._extract_text_from_message(msg_chunk)
                    if text_part:
                        chunks_token.append(text_part)
                elif mode == "updates":
                    # payload = {node_name: {state_updates}}
                    if not isinstance(payload, dict):
                        continue
                    for _node, node_data in payload.items():
                        if not isinstance(node_data, dict):
                            continue
                        msgs = node_data.get("messages") or []
                        if isinstance(msgs, list) and msgs:
                            last = msgs[-1]
                            # AIMessage / ToolMessage / HumanMessage 都有 content
                            ai_text = self._extract_text_from_message(last)
                            if ai_text:
                                last_ai_content = ai_text
        except Exception as e:  # noqa: BLE001
            logger.exception("agent.stream 调用失败: %s", e)
            return None, None

        if interrupt_request:
            return None, interrupt_request

        token_reply = "".join(chunks_token).strip()
        if token_reply:
            return token_reply, None
        # 流式 token 为空时回退到 last_ai_content（适用于不输出 token 的 agent）
        if last_ai_content:
            return last_ai_content.strip(), None
        return None, None

    @staticmethod
    def _extract_text_from_message(msg: Any) -> Optional[str]:
        """从 LangChain Message 对象提取文本内容。

        兼容三种 content 形态：
            - str：直接返回
            - list[dict]：每个 dict 形如 {"type": "text", "text": "..."}
            - list[tuple[tool_call, str]]：AIMessage token chunk
            - list[str]：直接拼接

        Args:
            msg: AIMessage / ToolMessage 等实例（duck-typed）

        Returns:
            str: 文本内容，无则返回 None
        """
        content = getattr(msg, "content", None)
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, dict):
                    txt = item.get("text")
                    if isinstance(txt, str):
                        parts.append(txt)
                elif isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, tuple) and len(item) >= 2:
                    # LangChain AIMessage chunk: (tool_call, content_str)
                    text_part = item[1]
                    if isinstance(text_part, str):
                        parts.append(text_part)
            joined = "".join(parts).strip()
            return joined or None
        return None

    @staticmethod
    def _extract_interrupt_from_chunk(chunk: Any) -> Optional[Any]:
        """从 agent.stream 的 chunk 中提取 ``__interrupt__`` 数据。

        兼容多种 stream 模式（参考 ``app/routers/_stream_helper.py``）：
            1) chunk 直接是 dict 且含 ``__interrupt__``
            2) chunk 是 (mode, data) 元组，mode="updates" 且 data 含 ``__interrupt__``
            3) chunk 是 (mode, data) 元组，mode="updates" 且 data 的某节点含 ``__interrupt__``

        Args:
            chunk: agent.stream 产出的单个 chunk

        Returns:
            interrupt_data: 原始 interrupt 数据（含 Interrupt 对象或 dict），未命中返回 None
        """
        # 情况 1：直接 dict 含 __interrupt__
        if isinstance(chunk, dict) and "__interrupt__" in chunk:
            return chunk["__interrupt__"]

        # 情况 2/3：组合模式 (mode, data)
        if isinstance(chunk, tuple) and len(chunk) == 2:
            mode, data = chunk
            if mode == "updates" and isinstance(data, dict):
                if "__interrupt__" in data:
                    return data["__interrupt__"]
                for _node_name, node_data in data.items():
                    if isinstance(node_data, dict) and "__interrupt__" in node_data:
                        return node_data["__interrupt__"]
        return None

    @staticmethod
    def _parse_interrupt_data(interrupt_data: Any) -> Optional[Dict[str, Any]]:
        """把 LangGraph interrupt 数据解析为结构化 dict。

        复用 ``app/routers/_stream_helper.py::_extract_interrupt_requests`` 的逻辑：
            - Interrupt 对象（有 ``.value`` 属性）→ 取 ``.value``
            - dict 含 ``value`` 字段 → 取 ``item["value"]``（duck-typed Interrupt）
            - list → 遍历提取 dict
            - dict → 直接使用

        Args:
            interrupt_data: ``__interrupt__`` 字段值

        Returns:
            dict: 结构化 interrupt 请求（含 ``action`` / ``questions`` 等），解析失败返回 None
        """
        requests: list = []
        items = interrupt_data if isinstance(interrupt_data, list) else [interrupt_data]
        for item in items:
            if hasattr(item, "value"):
                # LangGraph Interrupt 对象
                value = item.value
                if isinstance(value, list):
                    for req in value:
                        if isinstance(req, dict):
                            requests.append(req)
                        else:
                            requests.append({"data": str(req)})
                elif isinstance(value, dict):
                    requests.append(value)
                else:
                    requests.append({"data": str(value)})
            elif isinstance(item, dict):
                # duck-typed Interrupt：{"value": {...}} 形态
                if "value" in item and isinstance(item["value"], (dict, list)):
                    v = item["value"]
                    if isinstance(v, list):
                        for req in v:
                            if isinstance(req, dict):
                                requests.append(req)
                            else:
                                requests.append({"data": str(req)})
                    else:
                        requests.append(v)
                else:
                    requests.append(item)
            else:
                requests.append({"data": str(item)})
        # 取第一个 action 类型的请求（当前 project 智能体只发一个 interrupt）
        for req in requests:
            if isinstance(req, dict) and req.get("action"):
                return req
        return None

    # ------------------------------------------------------------------ #
    # Reply sending                                                      #
    # ------------------------------------------------------------------ #

    def _send_reply(self, chat_id: str, text: str) -> None:
        """路由入口：根据 Markdown 特征自动选择"纯文本"或"卡片"渲染。

        Args:
            chat_id: 飞书 chat_id
            text: 回复文本
        """
        if not text:
            return
        if MarkdownToCardConverter.looks_like_markdown(text):
            self._send_card_reply(chat_id, text)
        else:
            self._send_text_reply(chat_id, text)

    def _send_text_reply(self, chat_id: str, text: str) -> None:
        """通过飞书 Open API 发送纯文本回复。

        Args:
            chat_id: 飞书 chat_id（群或用户均可）
            text: 回复文本
        """
        truncated = self._truncate_text(text)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("text")
                .content(json.dumps({"text": truncated}, ensure_ascii=False))
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            if resp.success():
                logger.info(
                    "飞书文本回复成功 chat_id=%s message_id=%s",
                    chat_id,
                    getattr(resp.data, "message_id", None) if resp.data else None,
                )
            else:
                logger.error(
                    "飞书文本回复失败 code=%s msg=%s", resp.code, resp.msg
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("飞书文本回复异常: %s", e)

    def _send_card_reply(self, chat_id: str, text: str) -> None:
        """通过飞书 Open API 发送交互式卡片（Markdown 自动转卡片 JSON）。

        失败时降级到 ``_send_text_reply`` 保证可达性。

        Args:
            chat_id: 飞书 chat_id
            text: 含 Markdown 的回复文本
        """
        card = MarkdownToCardConverter.to_card_json(text)
        content_str = json.dumps(card, ensure_ascii=False)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content_str)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            if resp.success():
                logger.info(
                    "飞书卡片回复成功 chat_id=%s message_id=%s",
                    chat_id,
                    getattr(resp.data, "message_id", None) if resp.data else None,
                )
            else:
                logger.error(
                    "飞书卡片回复失败 code=%s msg=%s，降级文本",
                    resp.code, resp.msg,
                )
                self._send_text_reply(chat_id, text)
        except Exception as e:  # noqa: BLE001
            logger.exception("飞书卡片回复异常，降级文本: %s", e)
            self._send_text_reply(chat_id, text)

    def _send_interrupt_card(
        self,
        chat_id: str,
        interrupt_request: Dict[str, Any],
        session_id: str,
    ) -> None:
        """发送 HITL 带按钮交互式卡片。

        失败时降级为提示文本卡片。

        Args:
            chat_id: 飞书 chat_id
            interrupt_request: 结构化 interrupt 请求
            session_id: LangGraph thread_id（嵌入按钮 value）
        """
        card = InterruptToCardConverter.to_interactive_card(
            interrupt_request, session_id, chat_id
        )
        content_str = json.dumps(card, ensure_ascii=False)

        request = (
            CreateMessageRequest.builder()
            .receive_id_type("chat_id")
            .request_body(
                CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(content_str)
                .uuid(str(uuid.uuid4()))
                .build()
            )
            .build()
        )
        try:
            resp = self._lark_client.im.v1.message.create(request)
            if resp.success():
                logger.info(
                    "飞书 HITL 卡片发送成功 chat_id=%s session_id=%s",
                    chat_id, session_id,
                )
            else:
                logger.error(
                    "飞书 HITL 卡片发送失败 code=%s msg=%s",
                    resp.code, resp.msg,
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("飞书 HITL 卡片发送异常: %s", e)

    # ------------------------------------------------------------------ #
    # Card action (HITL callback)                                        #
    # ------------------------------------------------------------------ #

    def _on_card_action(self, data: Any) -> None:
        """飞书卡片按钮点击回调（HITL 路径）。

        解析 ``value`` 里的 ``session_id`` / ``qid`` / ``oid`` →
        构造 ``resume={"answers": [{qid, oid}]}`` →
        投递 ``_resume_agent`` 到主事件循环。

        注意：飞书要求按钮回调 3 秒内 ack。本回调仅记录日志 + 投递异步任务，
        不在回调线程内调 agent（agent.stream 慢，会触发超时）。

        Args:
            data: 飞书 ``P2CardActionTrigger`` 事件对象
        """
        try:
            value = self._extract_card_action_value(data)
            if not value or value.get("action") != "hitl_answer":
                logger.debug("飞书卡片回调 value 非 hitl_answer，跳过: %s", value)
                return
            session_id = value.get("session_id")
            qid = value.get("qid")
            oid = value.get("oid")
            if not session_id or qid is None or oid is None:
                logger.warning("飞书卡片回调 value 缺字段: %s", value)
                return
            # 构造 resume 答案（单选 + 自由输入两种形态）
            if value.get("is_other") or oid == -1:
                # "其他"按钮：等待用户自由输入下一条消息走普通路径
                self._pending_interrupts.pop(session_id, None)
                self._send_text_reply(
                    value.get("chat_id") or "",
                    "（请直接在对话中输入您的选择）",
                )
                return
            resume = {"answers": [{"qid": int(qid), "oid": [int(oid)]}]}
            # 投递到主事件循环（不能阻塞 SDK 回调线程）
            self._dispatch_async(self._resume_agent(session_id, resume))
        except Exception as e:  # noqa: BLE001
            logger.exception("处理飞书卡片回调异常: %s", e)

    @staticmethod
    def _extract_card_action_value(data: Any) -> Optional[Dict[str, Any]]:
        """从飞书 ``P2CardActionTrigger`` 事件对象中提取按钮 value dict。

        lark SDK 在不同版本中可能把 ``value`` 嵌套在不同位置，且 JSON 字符串 vs dict 两种形态
        都可能出现。本方法兼容：

            - ``data.event.action.value``
            - ``data.action.value``
            - 顶层 ``data.value``

        Args:
            data: 飞书卡片回调事件对象

        Returns:
            dict: 解析后的 value dict；失败返回 None
        """
        if data is None:
            return None
        # 多路径查找 action.value
        candidates = []
        event = getattr(data, "event", None)
        if event is not None:
            action = getattr(event, "action", None)
            if action is not None:
                candidates.append(getattr(action, "value", None))
            candidates.append(getattr(event, "value", None))
        action_top = getattr(data, "action", None)
        if action_top is not None:
            candidates.append(getattr(action_top, "value", None))
        candidates.append(getattr(data, "value", None))

        for raw in candidates:
            parsed = parse_card_action_value(raw)
            if parsed:
                return parsed
        return None

    async def _resume_agent(
        self,
        session_id: str,
        resume: Dict[str, Any],
    ) -> None:
        """续跑被 interrupt 暂停的 agent。

        - 续跑结果若再次产生 interrupt → 更新 pending + 再次发卡片
        - 续跑结果若产生文本回复 → 清理 pending + 发最终回复
        - 未找到 pending 上下文（可能过期）→ 仅记日志

        Args:
            session_id: LangGraph thread_id
            resume: 传给 ``Command(resume=...)`` 的参数
        """
        pending = self._pending_interrupts.get(session_id)
        if not pending:
            logger.warning(
                "未找到 session_id=%s 的 interrupt 上下文（可能已过期），跳过 resume",
                session_id,
            )
            return
        chat_id = pending.get("chat_id") or ""
        try:
            reply, intr = await self._call_agent(session_id, "", resume=resume)
        except Exception as e:  # noqa: BLE001
            logger.exception("续跑 agent 失败 session_id=%s: %s", session_id, e)
            return

        if intr:
            # 多轮 interrupt（可能连续追问）→ 更新 pending + 再次发卡片
            self._pending_interrupts[session_id] = {
                "chat_id": chat_id,
                "request": intr,
            }
            self._send_interrupt_card(chat_id, intr, session_id)
        elif reply:
            # 完成 → 清理 pending + 发最终回复
            self._pending_interrupts.pop(session_id, None)
            self._send_reply(chat_id, reply)
        else:
            # 续跑无产出（异常路径）
            logger.info(
                "续跑 agent 无产出 session_id=%s，清理 pending", session_id
            )
            self._pending_interrupts.pop(session_id, None)

    @staticmethod
    def _truncate_text(text: str) -> str:
        """截断超长文本。

        Args:
            text: 原始文本

        Returns:
            str: 截断后的文本（不超过 4000 字符 + 截断提示）
        """
        if len(text) <= _FEISHU_TEXT_MAX_LEN:
            return text
        keep = _FEISHU_TEXT_MAX_LEN - len(_TRUNCATE_HINT)
        return text[:keep] + _TRUNCATE_HINT
