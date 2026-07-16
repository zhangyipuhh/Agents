#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
FeishuWebSocketService - 飞书 WebSocket 长连接服务

职责：
    - 启动 lark.ws.Client 订阅 im.message.receive_v1 事件
    - 私聊（p2p）消息全部回复；群聊仅响应 @机器人 消息
    - 将消息路由到 settings.feishu.feishu_ws_agent_name 指定的智能体处理
    - 通过 client.im.v1.message.create 把回复发回飞书

依赖：
    - lark_oapi as lark（真实依赖由 app/requirements.txt 提供）
    - app.shared.utils.agent.agent_config_service.AgentConfigService
    - 主事件循环：lifespan 启动时通过 set_event_loop() 注入
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import uuid
from typing import Any, Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import (
    P2ImMessageReceiveV1,
    CreateMessageRequest,
    CreateMessageRequestBody,
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

        Args:
            chat_type: p2p / group
            chat_id: 飞书 chat_id
            open_id: 用户 open_id

        Returns:
            str: session_id
        """
        if chat_type == "group":
            return f"feishu:group:{chat_id}"
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

        Args:
            session_id: 会话 ID
            chat_id: 飞书 chat_id
            text: 用户消息文本
        """
        if not text:
            logger.info("飞书消息 text 为空，跳过（session_id=%s）", session_id)
            return
        try:
            reply = await self._call_agent(session_id, text)
            if reply:
                self._send_reply(chat_id, reply)
            else:
                logger.info("智能体未产生回复文本（session_id=%s）", session_id)
        except Exception as e:  # noqa: BLE001
            # 单条消息异常不影响 WebSocket 连接
            logger.exception("处理飞书消息失败（已隔离，session_id=%s）: %s", session_id, e)

    async def _call_agent(self, session_id: str, text: str) -> Optional[str]:
        """调用 build_agent_instance 构造 agent，遍历 stream 收集完整回复。

        收集策略（兼容 LangGraph 不同图结构）：
            1) messages 模式流式 token → 直接拼接为回复
            2) updates 模式节点输出 → 从每个节点的 state 找最新 AI/AIMessage
            3) HITL 中断 / interrupt 事件 → 不计入回复，保留 checkpoint

        项目内 project 智能体经测试 stream_mode=["updates", "messages"] 组合模式
        可同时拿到 token 和节点状态。

        Args:
            session_id: 会话 ID
            text: 用户消息

        Returns:
            str: 拼接后的完整回复；agent 无输出时返回 None
        """
        build = getattr(self._agent_config_service, "build_agent_instance", None)
        if build is None:
            logger.error("agent_config_service.build_agent_instance 不可用")
            return None

        # build_agent_instance 返回 (agent, context_instance, input_state)
        agent, _context, _input_state = await build(
            self._agent_name,
            session_id,
            text,
        )

        # 收集策略：优先 messages 模式的流式 token；备选 updates 模式下从
        # state 的 messages 列表提取最后一条 AI/AIMessage 内容。
        chunks_token: list[str] = []
        last_ai_content: Optional[str] = None
        try:
            async for chunk in agent.stream(
                _input_state,
                context=_context,
                config={"configurable": {"thread_id": session_id}, "recursion_limit": 100},
                stream_mode=["messages", "updates"],
            ):
                if not (isinstance(chunk, tuple) and len(chunk) == 2):
                    continue
                mode, payload = chunk
                if mode == "messages":
                    # payload = (msg_chunk, metadata)
                    if not (isinstance(payload, tuple) and len(payload) == 2):
                        continue
                    msg_chunk, _meta = payload
                    text = self._extract_text_from_message(msg_chunk)
                    if text:
                        chunks_token.append(text)
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
            return None

        token_reply = "".join(chunks_token).strip()
        if token_reply:
            return token_reply
        # 流式 token 为空时回退到 last_ai_content（适用于不输出 token 的 agent）
        if last_ai_content:
            return last_ai_content.strip()
        return None

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

    # ------------------------------------------------------------------ #
    # Reply sending                                                      #
    # ------------------------------------------------------------------ #

    def _send_reply(self, chat_id: str, text: str) -> None:
        """通过飞书 Open API 发送文本回复。

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
                    "飞书回复成功 chat_id=%s message_id=%s",
                    chat_id,
                    getattr(resp.data, "message_id", None) if resp.data else None,
                )
            else:
                logger.error(
                    "飞书回复失败 code=%s msg=%s", resp.code, resp.msg
                )
        except Exception as e:  # noqa: BLE001
            logger.exception("飞书回复异常: %s", e)

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
