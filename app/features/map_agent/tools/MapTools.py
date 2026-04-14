#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MapTools - 地图控制Agent工具模块

该模块定义了地图控制Agent可用的工具函数，包括地图定位、标记管理、路径规划等功能。

工具清单：
1. set_map_center - 设置地图中心点
2. set_map_zoom - 设置地图缩放级别
3. add_map_marker - 添加地图标记
4. remove_map_marker - 移除地图标记
5. clear_map_markers - 清除所有标记
6. get_map_state - 获取当前地图状态
7. draw_map_polygon - 绘制地图多边形
8. set_map_layer - 设置地图图层

Date: 2026-04-14
Author: AI Assistant
"""

import json
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from typing import List, Dict, Any, Optional


@tool
def set_map_center(latitude: float, longitude: float, runtime: ToolRuntime) -> Command:
    """
    【设置地图中心】将地图中心点移动到指定经纬度位置。
    
    调用时机：
    - 用户说"定位到某地"、"移动到某位置"、"查看某地"时
    - 用户说"地图中心移动到..."、"跳转到..."时
    - 需要查看特定地理位置时
    
    Args:
        latitude: 纬度，范围 -90 到 90
        longitude: 经度，范围 -180 到 180
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "center_set" - 中心点已设置
            - center: {"latitude": 纬度, "longitude": 经度}
    """
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def set_map_zoom(zoom_level: int, runtime: ToolRuntime) -> Command:
    """
    【设置地图缩放】调整地图的缩放级别。
    
    调用时机：
    - 用户说"放大地图"、"缩小地图"、"调整缩放"时
    - 用户说"地图缩放到..."、"查看更大范围"时
    - 需要调整地图视野范围时
    
    Args:
        zoom_level: 缩放级别，范围 1-20（1=世界视图，20=街道视图）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "zoom_set" - 缩放级别已设置
            - zoom_level: 缩放级别值
    """
    # 确保缩放级别在有效范围内
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def add_map_marker(
    latitude: float,
    longitude: float,
    title: str,
    description: str = "",
    marker_id: Optional[str] = None,
    runtime: ToolRuntime = None
) -> Command:
    """
    【添加地图标记】在地图上添加一个标记点。
    
    调用时机：
    - 用户说"在地图上标记..."、"添加标记"、"标注位置"时
    - 用户说"标记这个位置"、"这里有个点"时
    - 需要在地图上标注特定位置时
    
    Args:
        latitude: 纬度，范围 -90 到 90
        longitude: 经度，范围 -180 到 180
        title: 标记标题
        description: 标记描述（可选）
        marker_id: 标记ID（可选，不传则自动生成）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "marker_added" - 标记已添加
            - marker: 标记信息对象
    """
    import uuid
    
    # 生成标记ID
    if not marker_id:
        marker_id = str(uuid.uuid4())
    
    marker = {
        "id": marker_id,
        "latitude": latitude,
        "longitude": longitude,
        "title": title,
        "description": description
    }
    
    # 获取当前标记列表
    current_markers = runtime.state.get("map_markers", [])
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def remove_map_marker(marker_id: str, runtime: ToolRuntime) -> Command:
    """
    【移除地图标记】从地图上移除指定的标记点。
    
    调用时机：
    - 用户说"删除标记"、"移除标记"、"取消标记"时
    - 用户说"删除第X个标记"、"移除这个点"时
    - 需要移除地图上的特定标记时
    
    Args:
        marker_id: 要移除的标记ID
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "marker_removed" - 标记已移除
            - marker_id: 被移除的标记ID
    """
    current_markers = runtime.state.get("map_markers", [])
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def clear_map_markers(runtime: ToolRuntime) -> Command:
    """
    【清除所有标记】清除地图上的所有标记点。
    
    调用时机：
    - 用户说"清除所有标记"、"清空地图"、"删除所有标记"时
    - 用户说"重置地图标记"时
    - 需要清空地图上的所有标记时
    
    Args:
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "markers_cleared" - 所有标记已清除
            - cleared_count: 清除的标记数量
    """
    current_markers = runtime.state.get("map_markers", [])
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def get_map_state(runtime: ToolRuntime) -> Command:
    """
    【获取地图状态】获取当前地图的状态信息。
    
    调用时机：
    - 用户说"当前地图状态"、"地图信息"、"查看地图"时
    - 用户说"地图中心在哪"、"有多少标记"时
    - 需要查看当前地图配置时
    
    Args:
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "state_retrieved" - 状态已获取
            - map_state: 地图状态对象，包含中心点、缩放级别、标记列表等
    """
    map_state = {
        "center": runtime.state.get("map_center", {"latitude": 0, "longitude": 0}),
        "zoom": runtime.state.get("map_zoom", 10),
        "markers": runtime.state.get("map_markers", []),
        "layer": runtime.state.get("map_layer", "standard"),
        "polygons": runtime.state.get("map_polygons", [])
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def draw_map_polygon(
    coordinates: List[Dict[str, float]],
    title: str = "",
    color: str = "#FF0000",
    runtime: ToolRuntime = None
) -> Command:
    """
    【绘制地图多边形】在地图上绘制一个多边形区域。
    
    调用时机：
    - 用户说"画一个区域"、"绘制多边形"、"标注范围"时
    - 用户说"圈出这块区域"、"标记这个范围"时
    - 需要在地图上标注特定区域时
    
    Args:
        coordinates: 多边形顶点坐标列表，每个点包含 latitude 和 longitude
        title: 多边形标题（可选）
        color: 多边形颜色，十六进制格式（可选，默认红色）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "polygon_drawn" - 多边形已绘制
            - polygon: 多边形信息对象
    """
    import uuid
    
    polygon = {
        "id": str(uuid.uuid4()),
        "coordinates": coordinates,
        "title": title,
        "color": color
    }
    
    # 获取当前多边形列表
    current_polygons = runtime.state.get("map_polygons", [])
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )


@tool
def set_map_layer(layer_type: str, runtime: ToolRuntime) -> Command:
    """
    【设置地图图层】切换地图的显示图层类型。
    
    调用时机：
    - 用户说"切换到卫星图"、"显示卫星地图"、"查看卫星视图"时
    - 用户说"切换到地形图"、"显示地形"时
    - 需要切换地图显示模式时
    
    Args:
        layer_type: 图层类型，可选值：
            - "standard": 标准地图
            - "satellite": 卫星地图
            - "terrain": 地形地图
            - "hybrid": 混合地图（卫星+标注）
        runtime: 工具运行时上下文
    
    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "layer_set" - 图层已设置
            - layer_type: 当前图层类型
    """
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
                    tool_call_id=runtime.tool_call_id
                )
            ]
        }
    )
