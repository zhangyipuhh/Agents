#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SSE 流式响应辅助模块

从 map_router.py 完整迁移的通用 SSE 生成逻辑，供 agent_router 与 map_router 复用。

完整保留原 map_router.py::generate_stream_response 的全部逻辑，包括：
- ContextVar 挂载/清理（子智能体停止信号传递，2026-06-15 新增）
- 精确延迟中断（disconnect 标记 + tools 节点完成时真正断开，2026-06-22 改造）
- HITL 中断检测（多模式兼容）+ _extract_interrupt_requests
- updates / custom / messages 三种 stream_mode 的差异化处理
- thread_id / langgraph_node 字段透传（2026-06-14-2 新增）
- stream_format_context.format_message 用于 messages 模式格式化

Date: 2026-06-23
Author: AI Assistant
"""

import json
import logging
from typing import Any, AsyncGenerator

from fastapi import Request
from langchain_core.messages import ToolMessage

from app.core.format.stream import stream_format_context
from app.core.tools._stop_signal import (
    register_abort_signal,
    reset_current_request,
    set_current_request,
    trigger_abort,
    unregister_abort_signal,
)


logger = logging.getLogger(__name__)


async def generate_stream_response(
    agent: Any,
    input_state: Any,
    context: Any,
    session_id: str,
    request: Request,
) -> AsyncGenerator[str, None]:
    """
    生成 SSE 流式响应。

    完整迁移自 map_router.py::generate_stream_response，保留全部 SSE 处理逻辑。
    使用 stream_mode=["updates", "custom", "messages"] 组合模式，实时获取节点
    状态更新、自定义数据和 LLM token，并通过 SSE 格式发送给前端。
    支持 HITL 中断检测与恢复。

    处理流程：
    1. 把 FastAPI Request 挂到 ContextVar（子智能体工具可通过 get_current_request 取出）
    2. 调用 agent.stream 方法，使用组合模式
    3. 检测客户端断开 → 精确延迟中断（等待 tools 节点完成 ToolMessage 后才真正断开）
    4. 检测是否存在 __interrupt__ 中断事件（多模式兼容）
    5. 根据不同的流式数据类型（updates、custom、messages）进行处理
    6. 将每个数据块转换为 SSE 格式发送给前端
    7. 发送结束信号或错误信息
    8. finally 块清理 ContextVar

    Args:
        agent: Agent 实例（需实现 stream 方法，签名为
            stream(input_state, context, config, stream_mode) -> AsyncGenerator）
        input_state: 输入状态（AgentState 或 Command(resume=...)）
        context: AgentContext 实例
        session_id: 会话 ID
        request: FastAPI Request（用于检测客户端断开；可为 None 兼容非 HTTP 上下文）

    Yields:
        str: SSE 格式的响应数据（data: {json}\\n\\n），包含 type 字段和对应的数据

    Raises:
        不直接抛出异常：所有异常被捕获并转换为 SSE error 事件
    """
    from app.core.agent.AgentConfig import ExecuteConfig

    # 2026-06-15 新增：把 FastAPI Request 挂到 ContextVar，
    # 让子智能体工具（sandbox / explore）能通过 get_current_request() 取出，
    # 在 astream 循环中检测 is_disconnected() 来响应客户端断开（停止按钮触发）。
    # 异步 generator 的 ContextVar 在 with 块退出时自动清理。
    cv_token = set_current_request(request)

    # 2026-07-06 新增：注册 abort_event（按 session_id 索引）
    # 主动 abort 通道：用户点"停止"按钮时，前端调 POST /api/agent/{session_id}/abort
    # → trigger_abort(session_id) → abort_event.set() → 工具下次 check 感知
    # 与 ContextVar 是互补关系：
    #   - abort_event：主动 abort（用户显式点停止）
    #   - is_disconnected：兜底（浏览器关闭、网络异常等非主动关闭）
    abort_event = register_abort_signal(session_id)

    # 构建执行配置（recursion_limit=100 与原 map_router 保持一致，支持更多轮次的工具调用）
    execute_config = ExecuteConfig(
        configurable={"thread_id": session_id},
        recursion_limit=100,
    )

    try:
        # 2026-06-22 改造：精确延迟中断（disconnect 标记 + tools 节点完成时真正断开）
        # 背景：原实现检测到客户端断开立即 return，导致 LangGraph astream 协程被取消，
        #       子智能体（sandbox / explore）来不及返回 ToolMessage，导致 checkpoint 中存在
        #       orphan tool_calls（AIMessage 含 tool_calls 但无对应 ToolMessage），
        #       下次会话恢复时 LLM API 报 "tool call result does not follow tool call"。
        # 改造语义：
        #   1. 检测到 disconnect → 仅标记 disconnect_requested = True，不 return
        #   2. 跳过 messages 模式（不推 LLM token 给已断开的前端）
        #   3. 继续消费 updates 模式，检测 "tools" 节点完成 chunk
        #      （data["tools"]["messages"] 包含 ToolMessage 时）
        #   4. 当前工具/子智能体完成 ToolMessage 后，break 真正中断
        #   5. 依赖 LangGraph ToolNode 的"全或无"语义（asyncio.gather 等所有 tool_calls
        #      完成才 yield），多工具并行时所有工具都跑完才中断
        disconnect_requested = False
        disconnect_executed = False

        async for chunk in agent.stream(
            input_state,
            context=context,
            config=execute_config,
            stream_mode=["updates", "custom", "messages"],
        ):
            # 2026-06-22 改造：客户端断开检测（停止按钮触发）
            # 2026-07-06 增强：检测到 disconnect 时同时 trigger_abort（双保险）
            # 检测到 disconnect → 标记 disconnect_requested = True，但不 return。
            # 让 LangGraph 自然跑完当前工具/子智能体（产生 ToolMessage 写入 state），
            # 然后在 updates chunk 中检测到 "tools" 节点完成时真正断开。
            # 之前立即 return 的逻辑会导致子智能体被粗暴取消，ToolMessage 永远丢失。
            if not disconnect_requested and request is not None:
                try:
                    if await request.is_disconnected():
                        logger.info(
                            f"[Chat] session_id={session_id} 客户端已断开，"
                            f"延迟中断：等待当前工具/子智能体完成 ToolMessage 后再断开"
                        )
                        disconnect_requested = True
                        # 2026-07-06 新增：双保险——reader 关闭也触发 abort_event
                        # 场景：前端 reader 关闭（无论是否调 /abort），都让工具感知停止
                        trigger_abort(session_id)
                        # 向已断开的前端发一个标记（前端可能已收不到，仅作日志）
                        yield f"data: {json.dumps({'type': 'client_disconnected', 'data': {'message': '已记录停止信号，当前工具完成后停止'}}, ensure_ascii=False)}\n\n"
                except Exception as e:
                    logger.warning(f"[Chat] is_disconnected 检测异常: {e}")

            # ===== 中断检测（多模式兼容） =====
            # interrupt() 在不同 stream_mode 下输出格式不同：
            # - stream_mode="updates" 时：直接输出 {"__interrupt__": [...]}
            # - 组合模式时：可能直接输出 {"__interrupt__": [...]}，
            #   也可能以 ("updates", {"node_name": {"__interrupt__": [...]}}) 形式出现
            #   还可能以 ("updates", {"__interrupt__": [...]}) 形式出现（data 直接包含）
            interrupt_data = None

            # 情况1：直接字典包含 __interrupt__（所有 stream_mode 都可能出现）
            if isinstance(chunk, dict) and "__interrupt__" in chunk:
                interrupt_data = chunk["__interrupt__"]

            # 情况2：组合模式 (mode, data) 元组，检查 updates 模式下是否嵌套中断
            elif isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk
                if mode == "updates" and isinstance(data, dict):
                    # 检测 data 直接包含 __interrupt__ 的情况
                    if "__interrupt__" in data:
                        interrupt_data = data["__interrupt__"]
                    else:
                        for node_name, node_data in data.items():
                            if isinstance(node_data, dict) and "__interrupt__" in node_data:
                                interrupt_data = node_data["__interrupt__"]
                                break

            if interrupt_data is not None:
                # 解析 Interrupt 对象为结构化数据，避免 default=str 导致前端收到 Python repr 字符串
                structured_requests = _extract_interrupt_requests(interrupt_data)
                # 向前端发送标准化中断事件，结束当前 SSE 流
                yield f"data: {json.dumps({'type': 'interrupt', 'data': {'requests': structured_requests}}, ensure_ascii=False)}\n\n"
                return  # 中断后结束流，等待前端 resume

            # ===== 原有处理逻辑 =====
            # 处理组合模式的输出
            # chunk 的格式为 (mode, data)
            if isinstance(chunk, tuple) and len(chunk) == 2:
                mode, data = chunk

                if mode == "updates":
                    # 2026-06-22 改造：精确延迟中断 - 检测 "tools" 节点完成
                    # 当 "tools" 节点刚完成时，data 格式为 {"tools": {"messages": [ToolMessage, ...]}}
                    # 依赖 LangGraph ToolNode 的"全或无"语义（asyncio.gather 等所有 tool_calls 完成才 yield），
                    # 所以检测到 "tools" 节点完成时，所有并行的 tool_calls 都已执行完，
                    # ToolMessage 全部写入 state，可以真正断开。
                    if disconnect_requested and isinstance(data, dict):
                        for node_name, node_data in data.items():
                            if node_name == "tools" and isinstance(node_data, dict):
                                messages_in_update = node_data.get("messages", [])
                                # 检查是否包含 ToolMessage（兼容 Mock）
                                tool_messages = [
                                    m for m in messages_in_update
                                    if m is not None
                                    and m.__class__.__name__ in ("ToolMessage", "MockToolMessage", "_MockToolMessage")
                                ]
                                if tool_messages:
                                    # 当前工具/子智能体已完成（ToolMessage 已写入 state）
                                    logger.info(
                                        f"[Chat] session_id={session_id} 延迟中断触发："
                                        f"当前 {len(tool_messages)} 个工具/子智能体完成 ToolMessage 后真正断开"
                                    )
                                    disconnect_executed = True
                                    # 把这个工具完成事件 yield 给前端（如果还能收到）
                                    update_payload = {
                                        "type": "update",
                                        "data": data,
                                        "thread_id": "",
                                        "langgraph_node": node_name,
                                    }
                                    yield f"data: {json.dumps(update_payload, ensure_ascii=False, default=str)}\n\n"
                                    break  # 跳出内层 for
                        if disconnect_executed:
                            break  # 跳出外层 async for，真正中断
                    if disconnect_executed:
                        break  # 防御性 break，防止上面嵌套逻辑遗漏
                    # 节点状态更新
                    # data 格式: {node_name: {state_updates}}
                    # 2026-06-14-2 新增：与 custom / message 事件格式统一，附加 thread_id / langgraph_node
                    # thread_id 在 updates 模式下无法精确获取子线程 ID，统一置空；langgraph_node 取节点名。
                    # 老客户端忽略顶层字段，向后兼容。
                    update_payload = {
                        "type": "update",
                        "data": data,
                        "thread_id": "",
                        "langgraph_node": next(iter(data.keys()), "") if isinstance(data, dict) else "",
                    }
                    yield f"data: {json.dumps(update_payload, ensure_ascii=False, default=str)}\n\n"

                elif mode == "custom":
                    # 自定义数据
                    # data 格式: 自定义的数据结构（一般是 ToolEvent，含 data.data.thread_id）
                    # 2026-06-13 新增：把 subagent 的 thread_id 透传到 SSE 顶层
                    # 老客户端只读 data，忽略顶层 thread_id，行为不变
                    custom_data = data if isinstance(data, dict) else {}
                    inner_data = custom_data.get("data") or {}
                    custom_thread_id = (
                        (inner_data.get("thread_id") if isinstance(inner_data, dict) else None)
                        or custom_data.get("tool_call_id")
                        or ""
                    )
                    custom_payload = {
                        "type": "custom",
                        "data": data,
                        "thread_id": custom_thread_id,
                    }
                    yield "data: " + json.dumps(custom_payload, ensure_ascii=False, default=str) + "\n\n"

                elif mode == "messages":
                    # 2026-06-22 改造：客户端已断开时跳过 LLM token（不浪费带宽 + 防止用户看到不完整文本）
                    if disconnect_requested:
                        continue
                    if isinstance(data, tuple) and len(data) == 2:
                        message_chunk, metadata = data
                        if isinstance(message_chunk, ToolMessage):
                            continue
                        content = stream_format_context.format_message(message_chunk, metadata)
                        if content is None:
                            continue
                        yield f"data: {json.dumps({'type': 'message', 'content': content, 'metadata': metadata}, ensure_ascii=False, default=str)}\n\n"
                    else:
                        # 如果数据格式不符合预期，直接序列化
                        yield f"data: {json.dumps({'type': 'message', 'data': data}, ensure_ascii=False, default=str)}\n\n"
            else:
                # 处理非组合模式的输出（向后兼容）
                # 2026-06-22 改造：客户端已断开时不再 yield 业务事件
                if disconnect_requested:
                    continue
                yield f"data: {json.dumps({'type': 'unknown', 'data': chunk}, ensure_ascii=False, default=str)}\n\n"

        # 2026-06-22 新增：延迟中断完成日志
        if disconnect_executed:
            logger.info(
                f"[Chat] session_id={session_id} 精确延迟中断完成："
                f"ToolMessage 已写入 state，真正断开 SSE"
            )

        # 发送结束信号
        yield f"data: {json.dumps({'type': 'end', 'message': '会话结束'}, ensure_ascii=False)}\n\n"

    except Exception as e:
        # 捕获异常并将错误信息转换为 SSE 格式发送给前端
        import traceback
        logger.error(f"[ERROR] generate_stream_response 异常: {e}")
        logger.error(f"[ERROR] 异常堆栈: {traceback.format_exc()}")
        yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
    finally:
        # 2026-06-15 新增：清理 ContextVar，避免后续请求继承到错误的 request 引用。
        # 即使 generate_stream_response 因 is_disconnected() return 提前退出，也保证清理。
        try:
            reset_current_request(cv_token)
        except Exception as reset_error:
            logger.warning(f"[Chat] reset_current_request 异常: {reset_error}")
        # 2026-07-06 新增：清理 abort_signal，避免全局 dict 内存泄漏。
        # 即使流提前 return / 抛异常，也保证清理。
        try:
            unregister_abort_signal(session_id)
        except Exception as unregister_error:
            logger.warning(f"[Chat] unregister_abort_signal 异常: {unregister_error}")


def _extract_interrupt_requests(interrupt_data):
    """
    从 interrupt 数据中提取结构化的请求列表

    LangGraph 的 interrupt() 返回的 Interrupt 对象包含 value 属性，
    本函数将 Interrupt 对象解析为前端可直接使用的结构化字典。

    Args:
        interrupt_data (list): interrupt 数据列表，元素可能是 Interrupt 对象或字典

    Returns:
        list: 结构化的请求列表，每个元素为 dict
    """
    requests = []
    for item in interrupt_data:
        if hasattr(item, 'value'):
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
            requests.append(item)
        else:
            requests.append({"data": str(item)})
    return requests
