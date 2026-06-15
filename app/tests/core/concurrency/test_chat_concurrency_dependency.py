# -*- coding:utf-8 -*-
"""
chat_concurrency_dependency 集成测试
"""

import asyncio
import httpx
import pytest
from fastapi import FastAPI, Depends
from httpx import ASGITransport

from app.core.concurrency.agent_concurrency_queue import AgentConcurrencyQueue
from app.core.concurrency.chat_concurrency_dependency import chat_concurrency_dependency


@pytest.fixture
def reset_singleton():
    """重置单例"""
    AgentConcurrencyQueue.reset_instance()
    yield
    AgentConcurrencyQueue.reset_instance()


@pytest.fixture
def app_fixture(reset_singleton):
    """创建测试用 FastAPI 应用"""
    app = FastAPI()
    app.state.second_started = asyncio.Event()

    @app.get("/chat")
    async def chat(dep=Depends(chat_concurrency_dependency)):
        # 依赖已获取队列许可，设置事件表示本请求已开始执行
        app.state.second_started.set()
        await asyncio.sleep(0.05)
        return {"ok": True}

    return app


@pytest.mark.asyncio
async def test_dependency_blocks_when_full(app_fixture):
    """测试并发满时后续请求排队"""
    queue = AgentConcurrencyQueue(max_concurrency=1)
    second_started = app_fixture.state.second_started

    async def slow_holder():
        async with queue:
            await asyncio.sleep(0.2)

    # 先占住唯一并发位
    task = asyncio.create_task(slow_holder())
    # 等待 holder 获取到许可
    await asyncio.sleep(0.01)

    async with httpx.AsyncClient(
        transport=ASGITransport(app=app_fixture), base_url="http://test"
    ) as client:
        try:
            # 此时 /chat 应该等待
            response_task = asyncio.create_task(client.get("/chat"))
            # 在 holder 未释放前，第二个请求不应开始执行
            await asyncio.sleep(0.05)
            assert not second_started.is_set()

            response = await response_task
            assert response.status_code == 200
            # holder 释放后，/chat 应获取许可并执行
            assert second_started.is_set()
        finally:
            await task
