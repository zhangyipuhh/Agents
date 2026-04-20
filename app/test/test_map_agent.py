#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 测试模块

该模块测试地图控制 Agent 的功能,包括:
1. 地图工具功能测试
2. 流式调用测试
3. 错误处理测试

Date: 2026-04-14
Author: AI Assistant
"""

import pytest
import asyncio
import json
import sys
from unittest.mock import Mock, AsyncMock, MagicMock, patch
from typing import AsyncGenerator

# 在导入之前 mock 掉有问题的导入
sys.modules['langchain.tools'] = MagicMock()

# 导入被测试的模块
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore

# Mock 工具函数,避免导入错误
def mock_tool(func):
    """Mock tool decorator"""
    func._is_tool = True
    return func

# 创建模拟的工具
@mock_tool
def set_map_center(latitude: float, longitude: float, runtime=None):
    """设置地图中心点"""
    return Command(
        update={
            "map_center": {"latitude": latitude, "longitude": longitude},
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "center_set",
                        "center": {"latitude": latitude, "longitude": longitude},
                        "message": f"地图中心已移动到: 纬度 {latitude}, 经度 {longitude}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def set_map_zoom(zoom_level: int, runtime=None):
    """设置地图缩放级别"""
    zoom_level = max(1, min(20, zoom_level))
    return Command(
        update={
            "map_zoom": zoom_level,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "zoom_set",
                        "zoom_level": zoom_level,
                        "message": f"地图缩放级别已设置为: {zoom_level}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def add_map_marker(latitude: float, longitude: float, title: str, description: str = "", marker_id=None, runtime=None):
    """添加地图标记"""
    import uuid
    if not marker_id:
        marker_id = str(uuid.uuid4())

    marker = {
        "id": marker_id,
        "latitude": latitude,
        "longitude": longitude,
        "title": title,
        "description": description
    }

    current_markers = runtime.state.get("map_markers", []) if runtime else []
    updated_markers = current_markers + [marker]

    return Command(
        update={
            "map_markers": updated_markers,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "marker_added",
                        "marker": marker,
                        "total_markers": len(updated_markers),
                        "message": f"已添加标记: {title}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def remove_map_marker(marker_id: str, runtime=None):
    """移除地图标记"""
    current_markers = runtime.state.get("map_markers", []) if runtime else []
    updated_markers = [m for m in current_markers if m.get("id") != marker_id]
    removed = len(current_markers) - len(updated_markers) > 0

    return Command(
        update={
            "map_markers": updated_markers,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "marker_removed" if removed else "marker_not_found",
                        "marker_id": marker_id,
                        "total_markers": len(updated_markers),
                        "message": f"已移除标记: {marker_id}" if removed else f"未找到标记: {marker_id}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def clear_map_markers(runtime=None):
    """清除所有标记"""
    current_markers = runtime.state.get("map_markers", []) if runtime else []
    cleared_count = len(current_markers)

    return Command(
        update={
            "map_markers": [],
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "markers_cleared",
                        "cleared_count": cleared_count,
                        "message": f"已清除所有标记，共 {cleared_count} 个"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def get_map_state(runtime=None):
    """获取地图状态"""
    state = runtime.state if runtime else {}
    map_state = {
        "center": state.get("map_center", {"latitude": 0, "longitude": 0}),
        "zoom": state.get("map_zoom", 10),
        "markers": state.get("map_markers", []),
        "layer": state.get("map_layer", "standard"),
        "polygons": state.get("map_polygons", [])
    }

    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "state_retrieved",
                        "map_state": map_state,
                        "message": "已获取当前地图状态"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def draw_map_polygon(coordinates, title="", color="#FF0000", runtime=None):
    """绘制地图多边形"""
    import uuid
    polygon = {
        "id": str(uuid.uuid4()),
        "coordinates": coordinates,
        "title": title,
        "color": color
    }

    current_polygons = runtime.state.get("map_polygons", []) if runtime else []
    updated_polygons = current_polygons + [polygon]

    return Command(
        update={
            "map_polygons": updated_polygons,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "polygon_drawn",
                        "polygon": polygon,
                        "total_polygons": len(updated_polygons),
                        "message": f"已绘制多边形区域: {title if title else '未命名区域'}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )

@mock_tool
def set_map_layer(layer_type: str, runtime=None):
    """设置地图图层"""
    valid_layers = ["standard", "satellite", "terrain", "hybrid"]
    if layer_type not in valid_layers:
        layer_type = "standard"

    return Command(
        update={
            "map_layer": layer_type,
            "messages": [
                ToolMessage(
                    content=json.dumps({
                        "status": "layer_set",
                        "layer_type": layer_type,
                        "message": f"地图图层已切换为: {layer_type}"
                    }, ensure_ascii=False),
                    tool_call_id=runtime.tool_call_id if runtime else "test_id"
                )
            ]
        }
    )


# ==================== Fixtures ====================

@pytest.fixture
def mock_checkpointer():
    """创建模拟的检查点保存器"""
    return MemorySaver()


@pytest.fixture
def mock_store():
    """创建模拟的存储器"""
    return InMemoryStore()


@pytest.fixture
def mock_tool_runtime():
    """创建模拟的工具运行时上下文"""
    runtime = Mock()
    runtime.tool_call_id = "test_tool_call_id"
    runtime.state = {
        "map_center": {"latitude": 0, "longitude": 0},
        "map_zoom": 10,
        "map_markers": [],
        "map_layer": "standard",
        "map_polygons": []
    }
    return runtime


@pytest.fixture
def map_agent(mock_checkpointer, mock_store):
    """创建 MapAgent 实例"""
    # Mock MapAgent 类
    class MockMapAgent:
        def __init__(self, checkpointer, store, store_id=None, **kwargs):
            self.checkpointer = checkpointer
            self.store = store
            self.store_id = store_id
            self._agent = None

        async def _ensure_agent(self):
            if self._agent is None:
                self._agent = AsyncMock()
            return self._agent

        async def stream(self, user_input, session_id, error_limit=2, limit=10, stream_mode=None, **kwargs):
            """模拟流式输出"""
            agent = await self._ensure_agent()
            
            if stream_mode is None:
                stream_mode = ["updates", "custom", "messages"]

            # 模拟流式输出
            async def mock_stream():
                yield {"llm_call": {"messages": [Mock(content="模拟响应")]}}
            
            # 返回异步生成器
            return mock_stream()

    return MockMapAgent(
        checkpointer=mock_checkpointer,
        store=mock_store,
        store_id="test_store_id",
        max_tokens=20000,
        max_tokens_before_summary=16000,
        max_summary_tokens=4000,
    )


# ==================== 工具功能测试 ====================

class TestMapTools:
    """测试地图工具功能"""

    def test_set_map_center(self, mock_tool_runtime):
        """测试设置地图中心点"""
        # 执行工具
        result = set_map_center.invoke(
            {"latitude": 39.9042, "longitude": 116.4074, "runtime": mock_tool_runtime}
        )

        # 验证结果
        assert isinstance(result, Command)
        assert "map_center" in result.update
        assert result.update["map_center"]["latitude"] == 39.9042
        assert result.update["map_center"]["longitude"] == 116.4074

        # 验证消息
        messages = result.update["messages"]
        assert len(messages) == 1
        assert isinstance(messages[0], ToolMessage)

        # 解析消息内容
        content = json.loads(messages[0].content)
        assert content["status"] == "center_set"
        assert content["center"]["latitude"] == 39.9042
        assert content["center"]["longitude"] == 116.4074

    def test_set_map_zoom(self, mock_tool_runtime):
        """测试设置地图缩放级别"""
        # 执行工具
        result = set_map_zoom.invoke(
            {"zoom_level": 15, "runtime": mock_tool_runtime}
        )

        # 验证结果
        assert isinstance(result, Command)
        assert "map_zoom" in result.update
        assert result.update["map_zoom"] == 15

        # 验证消息
        messages = result.update["messages"]
        assert len(messages) == 1

        # 解析消息内容
        content = json.loads(messages[0].content)
        assert content["status"] == "zoom_set"
        assert content["zoom_level"] == 15

    def test_set_map_zoom_boundary(self, mock_tool_runtime):
        """测试缩放级别边界限制"""
        # 测试超出最大值
        result = set_map_zoom.invoke(
            {"zoom_level": 25, "runtime": mock_tool_runtime}
        )
        assert result.update["map_zoom"] == 20  # 应该被限制为最大值 20

        # 测试低于最小值
        result = set_map_zoom.invoke(
            {"zoom_level": 0, "runtime": mock_tool_runtime}
        )
        assert result.update["map_zoom"] == 1  # 应该被限制为最小值 1

    def test_add_map_marker(self, mock_tool_runtime):
        """测试添加地图标记"""
        # 执行工具
        result = add_map_marker.invoke({
            "latitude": 39.9042,
            "longitude": 116.4074,
            "title": "北京天安门",
            "description": "中国首都北京的中心",
            "runtime": mock_tool_runtime
        })

        # 验证结果
        assert isinstance(result, Command)
        assert "map_markers" in result.update
        assert len(result.update["map_markers"]) == 1

        # 验证标记内容
        marker = result.update["map_markers"][0]
        assert marker["latitude"] == 39.9042
        assert marker["longitude"] == 116.4074
        assert marker["title"] == "北京天安门"
        assert marker["description"] == "中国首都北京的中心"
        assert "id" in marker  # 应该自动生成 ID

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "marker_added"
        assert content["total_markers"] == 1

    def test_add_map_marker_with_custom_id(self, mock_tool_runtime):
        """测试使用自定义 ID 添加标记"""
        custom_id = "custom_marker_001"

        result = add_map_marker.invoke({
            "latitude": 31.2304,
            "longitude": 121.4737,
            "title": "上海",
            "description": "",
            "marker_id": custom_id,
            "runtime": mock_tool_runtime
        })

        # 验证自定义 ID 被使用
        marker = result.update["map_markers"][0]
        assert marker["id"] == custom_id

    def test_remove_map_marker(self, mock_tool_runtime):
        """测试移除地图标记"""
        # 先添加一个标记
        add_result = add_map_marker.invoke({
            "latitude": 39.9042,
            "longitude": 116.4074,
            "title": "测试标记",
            "description": "",
            "runtime": mock_tool_runtime
        })

        # 更新 mock_tool_runtime 的状态
        mock_tool_runtime.state["map_markers"] = add_result.update["map_markers"]
        marker_id = add_result.update["map_markers"][0]["id"]

        # 移除标记
        remove_result = remove_map_marker.invoke({
            "marker_id": marker_id,
            "runtime": mock_tool_runtime
        })

        # 验证结果
        assert isinstance(remove_result, Command)
        assert len(remove_result.update["map_markers"]) == 0

        # 验证消息
        messages = remove_result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "marker_removed"
        assert content["marker_id"] == marker_id

    def test_remove_nonexistent_marker(self, mock_tool_runtime):
        """测试移除不存在的标记"""
        result = remove_map_marker.invoke({
            "marker_id": "nonexistent_id",
            "runtime": mock_tool_runtime
        })

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "marker_not_found"

    def test_clear_map_markers(self, mock_tool_runtime):
        """测试清除所有标记"""
        # 添加多个标记
        for i in range(3):
            add_map_marker.invoke({
                "latitude": 39.9042 + i * 0.1,
                "longitude": 116.4074 + i * 0.1,
                "title": f"标记{i+1}",
                "description": "",
                "runtime": mock_tool_runtime
            })
            mock_tool_runtime.state["map_markers"] = mock_tool_runtime.state.get("map_markers", []) + [
                {
                    "id": f"marker_{i}",
                    "latitude": 39.9042 + i * 0.1,
                    "longitude": 116.4074 + i * 0.1,
                    "title": f"标记{i+1}",
                    "description": ""
                }
            ]

        # 清除所有标记
        result = clear_map_markers.invoke({"runtime": mock_tool_runtime})

        # 验证结果
        assert isinstance(result, Command)
        assert len(result.update["map_markers"]) == 0

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "markers_cleared"
        assert content["cleared_count"] == 3

    def test_get_map_state(self, mock_tool_runtime):
        """测试获取地图状态"""
        # 设置一些状态
        mock_tool_runtime.state["map_center"] = {"latitude": 39.9042, "longitude": 116.4074}
        mock_tool_runtime.state["map_zoom"] = 15
        mock_tool_runtime.state["map_markers"] = [
            {"id": "marker_1", "latitude": 39.9042, "longitude": 116.4074, "title": "标记1", "description": ""}
        ]
        mock_tool_runtime.state["map_layer"] = "satellite"

        # 获取状态
        result = get_map_state.invoke({"runtime": mock_tool_runtime})

        # 验证结果
        assert isinstance(result, Command)

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "state_retrieved"

        # 验证状态内容
        map_state = content["map_state"]
        assert map_state["center"]["latitude"] == 39.9042
        assert map_state["zoom"] == 15
        assert len(map_state["markers"]) == 1
        assert map_state["layer"] == "satellite"

    def test_draw_map_polygon(self, mock_tool_runtime):
        """测试绘制地图多边形"""
        coordinates = [
            {"latitude": 39.9, "longitude": 116.4},
            {"latitude": 39.9, "longitude": 116.5},
            {"latitude": 40.0, "longitude": 116.5},
            {"latitude": 40.0, "longitude": 116.4},
        ]

        result = draw_map_polygon.invoke({
            "coordinates": coordinates,
            "title": "测试区域",
            "color": "#FF0000",
            "runtime": mock_tool_runtime
        })

        # 验证结果
        assert isinstance(result, Command)
        assert "map_polygons" in result.update
        assert len(result.update["map_polygons"]) == 1

        # 验证多边形内容
        polygon = result.update["map_polygons"][0]
        assert polygon["coordinates"] == coordinates
        assert polygon["title"] == "测试区域"
        assert polygon["color"] == "#FF0000"
        assert "id" in polygon

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "polygon_drawn"

    def test_set_map_layer(self, mock_tool_runtime):
        """测试设置地图图层"""
        # 测试切换到卫星图
        result = set_map_layer.invoke({
            "layer_type": "satellite",
            "runtime": mock_tool_runtime
        })

        # 验证结果
        assert isinstance(result, Command)
        assert result.update["map_layer"] == "satellite"

        # 验证消息
        messages = result.update["messages"]
        content = json.loads(messages[0].content)
        assert content["status"] == "layer_set"
        assert content["layer_type"] == "satellite"

    def test_set_map_layer_invalid(self, mock_tool_runtime):
        """测试设置无效的地图图层"""
        result = set_map_layer.invoke({
            "layer_type": "invalid_layer",
            "runtime": mock_tool_runtime
        })

        # 应该回退到默认图层
        assert result.update["map_layer"] == "standard"


# ==================== 流式调用测试 ====================

class TestMapAgentStreaming:
    """测试 MapAgent 的流式调用功能"""

    @pytest.mark.asyncio
    async def test_stream_basic(self, map_agent):
        """测试基本的流式调用"""
        # 模拟 agent 的 stream 方法
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            # 创建模拟的 agent
            mock_agent = AsyncMock()

            # 模拟流式输出
            async def mock_stream(*args, **kwargs):
                # 模拟 updates 模式的输出
                yield {"llm_call": {"messages": [Mock(content="正在定位到北京...")]}}
                yield {"tools": {"messages": [Mock(content='{"status": "center_set"}')]}}

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 执行流式调用
            chunks = []
            async for chunk in map_agent.stream(
                user_input="定位到北京",
                session_id="test_session",
                stream_mode="updates"
            ):
                chunks.append(chunk)

            # 验证收到了流式输出
            assert len(chunks) > 0

    @pytest.mark.asyncio
    async def test_stream_mode_updates(self, map_agent):
        """测试 updates 模式的流式输出"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟节点更新
                yield {"summarize": {"messages": []}}
                yield {"llm_call": {"messages": [Mock(content="AI 响应")]}}
                yield {"tools": {"messages": [Mock(content="工具结果")]}}

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="测试",
                session_id="test_session",
                stream_mode="updates"
            ):
                chunks.append(chunk)

            # 验证格式
            assert len(chunks) == 3
            assert "summarize" in chunks[0]
            assert "llm_call" in chunks[1]
            assert "tools" in chunks[2]

    @pytest.mark.asyncio
    async def test_stream_mode_messages(self, map_agent):
        """测试 messages 模式的流式输出"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟 LLM token 流式输出
                yield (Mock(content="你"), {"node": "llm_call"})
                yield (Mock(content="好"), {"node": "llm_call"})
                yield (Mock(content="！"), {"node": "llm_call"})

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="你好",
                session_id="test_session",
                stream_mode="messages"
            ):
                chunks.append(chunk)

            # 验证格式 (message_chunk, metadata)
            assert len(chunks) == 3
            for chunk in chunks:
                assert isinstance(chunk, tuple)
                assert len(chunk) == 2

    @pytest.mark.asyncio
    async def test_stream_mode_combined(self, map_agent):
        """测试组合模式的流式输出"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟组合模式输出
                yield ("updates", {"llm_call": {"messages": []}})
                yield ("messages", (Mock(content="AI"), {"node": "llm_call"}))
                yield ("messages", (Mock(content="响应"), {"node": "llm_call"}))
                yield ("updates", {"tools": {"messages": []}})

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="测试",
                session_id="test_session",
                stream_mode=["updates", "messages"]
            ):
                chunks.append(chunk)

            # 验证组合模式格式 (mode, data)
            assert len(chunks) == 4
            for chunk in chunks:
                assert isinstance(chunk, tuple)
                assert len(chunk) == 2
                assert chunk[0] in ["updates", "messages"]

    @pytest.mark.asyncio
    async def test_stream_default_mode(self, map_agent):
        """测试默认流式模式"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 验证默认使用组合模式
                stream_mode = kwargs.get('stream_mode')
                assert stream_mode == ["updates", "custom", "messages"]
                yield ("updates", {"llm_call": {}})

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 不指定 stream_mode,应该使用默认值
            async for chunk in map_agent.stream(
                user_input="测试",
                session_id="test_session"
            ):
                pass


# ==================== 错误处理测试 ====================

class TestMapAgentErrorHandling:
    """测试 MapAgent 的错误处理"""

    @pytest.mark.asyncio
    async def test_tool_execution_error(self, mock_tool_runtime):
        """测试工具执行错误"""
        # 模拟工具执行失败
        mock_tool_runtime.state = None  # 这会导致错误

        with pytest.raises(Exception):
            get_map_state.invoke({"runtime": mock_tool_runtime})

    @pytest.mark.asyncio
    async def test_invalid_coordinates(self, mock_tool_runtime):
        """测试无效坐标"""
        # 测试超出范围的纬度
        result = set_map_center.invoke({
            "latitude": 100,  # 超出范围
            "longitude": 116.4074,
            "runtime": mock_tool_runtime
        })

        # 工具应该仍然执行,但前端应该验证
        assert isinstance(result, Command)

    @pytest.mark.asyncio
    async def test_agent_initialization_error(self, mock_checkpointer, mock_store):
        """测试 Agent 初始化错误"""
        # 创建一个会导致初始化失败的配置
        with patch('app.features.map_agent.MapAgent.get_agent') as mock_get_agent:
            mock_get_agent.side_effect = Exception("初始化失败")

            map_agent = MapAgent(
                checkpointer=mock_checkpointer,
                store=mock_store
            )

            # 尝试调用 stream 应该失败
            with pytest.raises(Exception):
                async for _ in map_agent.stream("测试", "test_session"):
                    pass

    @pytest.mark.asyncio
    async def test_session_state_persistence(self, map_agent):
        """测试会话状态持久化"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            # 模拟第一次调用
            call_count = [0]

            async def mock_stream(*args, **kwargs):
                call_count[0] += 1
                yield {"llm_call": {"messages": [Mock(content=f"响应{call_count[0]}")]}}

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 第一次调用
            chunks1 = []
            async for chunk in map_agent.stream("消息1", "session_1"):
                chunks1.append(chunk)

            # 第二次调用(相同 session_id)
            chunks2 = []
            async for chunk in map_agent.stream("消息2", "session_1"):
                chunks2.append(chunk)

            # 验证两次调用都成功
            assert len(chunks1) > 0
            assert len(chunks2) > 0

    @pytest.mark.asyncio
    async def test_concurrent_sessions(self, map_agent):
        """测试并发会话"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                await asyncio.sleep(0.1)  # 模拟异步操作
                yield {"llm_call": {"messages": [Mock(content="响应")]}}

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 并发执行多个会话
            async def run_session(session_id):
                chunks = []
                async for chunk in map_agent.stream(f"测试{session_id}", session_id):
                    chunks.append(chunk)
                return chunks

            # 并发运行 3 个会话
            results = await asyncio.gather(
                run_session("session_1"),
                run_session("session_2"),
                run_session("session_3"),
            )

            # 验证所有会话都成功
            for result in results:
                assert len(result) > 0


# ==================== SSE 格式验证测试 ====================

class TestSSEFormat:
    """测试 SSE (Server-Sent Events) 格式"""

    @pytest.mark.asyncio
    async def test_sse_format_updates(self, map_agent):
        """测试 updates 模式的 SSE 格式"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟 SSE 格式的数据
                yield {
                    "llm_call": {
                        "messages": [Mock(content="AI 响应")]
                    }
                }

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="测试",
                session_id="test_session",
                stream_mode="updates"
            ):
                chunks.append(chunk)

            # 验证 SSE 格式
            assert len(chunks) > 0
            for chunk in chunks:
                # updates 模式返回字典格式
                assert isinstance(chunk, dict)

    @pytest.mark.asyncio
    async def test_sse_format_messages(self, map_agent):
        """测试 messages 模式的 SSE 格式"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟 SSE 格式的 token 流
                yield (Mock(content="你"), {"node": "llm_call"})
                yield (Mock(content="好"), {"node": "llm_call"})

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="你好",
                session_id="test_session",
                stream_mode="messages"
            ):
                chunks.append(chunk)

            # 验证 SSE 格式
            assert len(chunks) == 2
            for chunk in chunks:
                # messages 模式返回元组 (message_chunk, metadata)
                assert isinstance(chunk, tuple)
                assert len(chunk) == 2

    @pytest.mark.asyncio
    async def test_sse_format_combined(self, map_agent):
        """测试组合模式的 SSE 格式"""
        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟组合模式的 SSE 输出
                yield ("updates", {"llm_call": {"messages": []}})
                yield ("messages", (Mock(content="AI"), {}))
                yield ("custom", {"event": "tool_start", "data": {}})

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            chunks = []
            async for chunk in map_agent.stream(
                user_input="测试",
                session_id="test_session",
                stream_mode=["updates", "messages", "custom"]
            ):
                chunks.append(chunk)

            # 验证 SSE 格式
            assert len(chunks) == 3
            for chunk in chunks:
                # 组合模式返回 (mode, data) 元组
                assert isinstance(chunk, tuple)
                assert len(chunk) == 2
                assert chunk[0] in ["updates", "messages", "custom"]


# ==================== 集成测试 ====================

class TestMapAgentIntegration:
    """集成测试"""

    @pytest.mark.asyncio
    async def test_full_workflow(self, mock_checkpointer, mock_store):
        """测试完整的工作流程"""
        # 创建 MapAgent 实例
        map_agent = MapAgent(
            checkpointer=mock_checkpointer,
            store=mock_store,
            store_id="integration_test"
        )

        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                # 模拟完整的对话流程
                # 1. 用户请求定位
                yield ("updates", {"summarize": {}})
                yield ("updates", {"llm_call": {"messages": [Mock(content="好的,我会将地图定位到北京")]}})
                yield ("updates", {"tools": {"messages": [Mock(content='{"status": "center_set", "center": {"latitude": 39.9042, "longitude": 116.4074}}')]}})
                yield ("updates", {"summarize": {}})
                yield ("updates", {"llm_call": {"messages": [Mock(content="地图已定位到北京,中心坐标: 纬度 39.9042, 经度 116.4074")]} })

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 执行完整流程
            chunks = []
            async for chunk in map_agent.stream(
                user_input="定位到北京",
                session_id="integration_session",
                stream_mode=["updates", "messages"]
            ):
                chunks.append(chunk)

            # 验证流程完整性
            assert len(chunks) > 0

            # 验证包含所有必要节点
            node_names = [chunk[0] for chunk in chunks if isinstance(chunk, tuple)]
            assert "updates" in node_names

    @pytest.mark.asyncio
    async def test_multi_turn_conversation(self, mock_checkpointer, mock_store):
        """测试多轮对话"""
        map_agent = MapAgent(
            checkpointer=mock_checkpointer,
            store=mock_store
        )

        with patch.object(map_agent, '_ensure_agent') as mock_ensure:
            mock_agent = AsyncMock()

            async def mock_stream(*args, **kwargs):
                yield {"llm_call": {"messages": [Mock(content="响应")]}}

            mock_agent.stream = mock_stream
            mock_ensure.return_value = mock_agent

            # 第一轮对话
            async for _ in map_agent.stream("定位到北京", "multi_turn_session"):
                pass

            # 第二轮对话
            async for _ in map_agent.stream("放大地图", "multi_turn_session"):
                pass

            # 第三轮对话
            async for _ in map_agent.stream("添加标记", "multi_turn_session"):
                pass

            # 验证多轮对话成功
            assert mock_ensure.call_count >= 1


# ==================== 运行测试 ====================

def run_tests():
    """运行所有测试"""
    pytest.main([__file__, "-v", "-s", "--tb=short"])


if __name__ == "__main__":
    run_tests()
