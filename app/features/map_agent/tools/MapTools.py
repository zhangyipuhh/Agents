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
9. generate_report - 生成报告
10. save_business_info - 保存业务信息

Date: 2026-04-14
Author: AI Assistant
"""

import json
import re
import uuid
import os
from datetime import datetime
from langchain.tools import tool, ToolRuntime
from langchain_core.messages import ToolMessage
from langgraph.types import Command
from langgraph.config import get_stream_writer
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field, field_validator
from app.core.tools.events import create_tool_event
from app.shared.utils.report.word.generator import WordReportGenerator
from app.features.map_agent.config.config import get_report_config, ProjectSiteSelectionCollection
from app.core.config.config import DEMONSTRATION_CONFIG
from app.core.database import DatabasePool, register_schema

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
    tool_name = "set_map_center"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {"latitude": latitude, "longitude": longitude},
            "description": f"开始设置地图中心点: 纬度 {latitude}, 经度 {longitude}"
        }
    )
    writer(dict(start_event))
    
    result_data = {
        "status": "center_set",
        "center": {"latitude": latitude, "longitude": longitude},
        "message": f"地图中心已移动到: 纬度 {latitude}, 经度 {longitude}"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_center": {"latitude": latitude, "longitude": longitude},
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "set_map_zoom"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {"zoom_level": zoom_level},
            "description": f"开始设置地图缩放级别: {zoom_level}"
        }
    )
    writer(dict(start_event))
    
    original_zoom = zoom_level
    zoom_level = max(1, min(20, zoom_level))
    
    result_data = {
        "status": "zoom_set",
        "zoom_level": zoom_level,
        "message": f"地图缩放级别已设置为: {zoom_level}"
    }
    
    if original_zoom != zoom_level:
        result_data["adjusted"] = True
        result_data["original_value"] = original_zoom
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_zoom": zoom_level,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "add_map_marker"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {
                "latitude": latitude,
                "longitude": longitude,
                "title": title,
                "description": description,
                "marker_id": marker_id
            },
            "description": f"开始添加地图标记: {title}"
        }
    )
    writer(dict(start_event))
    
    if not marker_id:
        marker_id = str(uuid.uuid4())
    
    marker = {
        "id": marker_id,
        "latitude": latitude,
        "longitude": longitude,
        "title": title,
        "description": description
    }
    
    current_markers = runtime.state.get("map_markers", [])
    updated_markers = current_markers + [marker]
    
    result_data = {
        "status": "marker_added",
        "marker": marker,
        "total_markers": len(updated_markers),
        "message": f"已添加标记: {title}"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_markers": updated_markers,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "remove_map_marker"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {"marker_id": marker_id},
            "description": f"开始移除地图标记: {marker_id}"
        }
    )
    writer(dict(start_event))
    
    current_markers = runtime.state.get("map_markers", [])
    updated_markers = [m for m in current_markers if m.get("id") != marker_id]
    
    removed = len(current_markers) - len(updated_markers) > 0
    
    result_data = {
        "status": "marker_removed" if removed else "marker_not_found",
        "marker_id": marker_id,
        "total_markers": len(updated_markers),
        "message": f"已移除标记: {marker_id}" if removed else f"未找到标记: {marker_id}"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success" if removed else "warning",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success" if removed else "warning",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_markers": updated_markers,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "clear_map_markers"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {},
            "description": "开始清除所有地图标记"
        }
    )
    writer(dict(start_event))
    
    current_markers = runtime.state.get("map_markers", [])
    cleared_count = len(current_markers)
    
    result_data = {
        "status": "markers_cleared",
        "cleared_count": cleared_count,
        "message": f"已清除所有标记，共 {cleared_count} 个"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_markers": [],
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "get_map_state"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {},
            "description": "开始获取地图状态"
        }
    )
    writer(dict(start_event))
    
    map_state = {
        "center": runtime.state.get("map_center", {"latitude": 0, "longitude": 0}),
        "zoom": runtime.state.get("map_zoom", 10),
        "markers": runtime.state.get("map_markers", []),
        "layer": runtime.state.get("map_layer", "standard"),
        "polygons": runtime.state.get("map_polygons", [])
    }
    
    result_data = {
        "status": "state_retrieved",
        "map_state": map_state,
        "message": "已获取当前地图状态"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "draw_map_polygon"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {
                "coordinates": coordinates,
                "title": title,
                "color": color
            },
            "description": f"开始绘制地图多边形: {title if title else '未命名区域'}"
        }
    )
    writer(dict(start_event))
    
    polygon = {
        "id": str(uuid.uuid4()),
        "coordinates": coordinates,
        "title": title,
        "color": color
    }
    
    current_polygons = runtime.state.get("map_polygons", [])
    updated_polygons = current_polygons + [polygon]
    
    result_data = {
        "status": "polygon_drawn",
        "polygon": polygon,
        "total_polygons": len(updated_polygons),
        "message": f"已绘制多边形区域: {title if title else '未命名区域'}"
    }
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_polygons": updated_polygons,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
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
    tool_name = "set_map_layer"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()
    
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {"layer_type": layer_type},
            "description": f"开始设置地图图层: {layer_type}"
        }
    )
    writer(dict(start_event))
    
    valid_layers = ["standard", "satellite", "terrain", "hybrid"]
    original_layer = layer_type
    
    if layer_type not in valid_layers:
        layer_type = "standard"
    
    result_data = {
        "status": "layer_set",
        "layer_type": layer_type,
        "message": f"地图图层已切换为: {layer_type}"
    }
    
    if original_layer != layer_type:
        result_data["adjusted"] = True
        result_data["original_value"] = original_layer
    
    end_time = datetime.now()
    duration_ms = int((end_time - start_time).total_seconds() * 1000)
    
    stop_event = create_tool_event(
        event_type="tool_stop",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "status": "success",
            "result": result_data,
            "duration_ms": duration_ms
        }
    )
    writer(dict(stop_event))
    
    summary = {
        "status": "success",
        "tool": tool_name,
        "started_at": start_time.timestamp(),
        "ended_at": end_time.timestamp(),
        "duration_ms": duration_ms,
        "events": [dict(start_event), dict(stop_event)],
        "result": result_data
    }
    
    return Command(
        update={
            "map_layer": layer_type,
            "messages": [
                ToolMessage(
                    content=json.dumps(summary, ensure_ascii=False),
                    tool_call_id=tool_call_id
                )
            ]
        }
    )


@tool
def generate_report(runtime: ToolRuntime) -> Command:
    """
    【生成报告】根据当前地图状态和项目信息生成Word报告并返回下载地址。

    调用时机：
    - 用户说"生成报告"、"导出报告"、"下载报告"时
    - 用户说"生成选址报告"、"导出分析报告"时

    该函数使用WordReportGenerator生成真实的Word文档，保存到下载目录，
    并返回可供前端下载的URL路径。

    Args:
        runtime: 工具运行时上下文，用于获取工具调用ID、当前状态和session_id
            - runtime.context: 包含session_id用于构建下载路径
            - runtime.state: 包含地图状态信息（可选，用于报告数据）

    Returns:
        Command: 包含ToolMessage和状态更新的命令对象
            - status: "report_generated" - 报告已生成
            - download_url: 下载地址路径，格式为"/api/core/download/file?path={文件名}.docx"
            - file_name: 实际生成的文件名，格式如"20260512_120000.docx"
            - message: 操作结果描述

    Raises:
        无显式异常抛出，所有错误通过tool_error事件和result状态反馈

    Notes:
        - 报告文件保存路径：app/data/download/{session_id}/{文件名}.docx
        - 如果下载目录不存在，会自动创建
        - 文件名使用当前日期时间生成，确保唯一性
    """
    tool_name = "生成报告"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": {},
            "description": "开始生成报告"
        }
    )
    writer(dict(start_event))

    progress_event_1 = create_tool_event(
        event_type="tool_progress",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "current": 1,
            "total": 3,
            "percentage": 33,
            "message": "正在收集数据"
        }
    )
    writer(dict(progress_event_1))

    # 从runtime.context获取session_id
    session_id = runtime.context.get("session_id", "default_session")

    # 准备报告数据
    current_time = datetime.now()
    #这个地方sheng'cha'enshengchaen
    report_data = {
        "项目名称": runtime.state.get("project_name", "XX项目"),
        "生成日期": current_time.strftime("%Y年%m月%d日"),
        "项目位置": runtime.state.get("project_location", "xx县xx镇"),
        "用地总面积": runtime.state.get("total_area", "100"),
        "农用地面积": runtime.state.get("farmland_area", "80"),
        "林地面积": runtime.state.get("forest_area", "10"),
        "用海面积": runtime.state.get("sea_area", "0"),
    }

    progress_event_2 = create_tool_event(
        event_type="tool_progress",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "current": 2,
            "total": 3,
            "percentage": 66,
            "message": "正在生成报告文件"
        }
    )
    writer(dict(progress_event_2))

    try:
        # 构建项目选址数据集合
        # 从 store 获取 process_data
        store_id = runtime.context.get("store_id", "default")
        namespace = (store_id,)
        existing_result = runtime.store.get(namespace, "process_data")
        process_data = existing_result.value if existing_result else {}
        collection = process_data.get("report_data", None)
        if collection is None:
            collection = ProjectSiteSelectionCollection(
                collection_id="default",
                collection_name="默认集合",
                projects=[],
            )
        elif isinstance(collection, dict):
            # 如果 collection 是字典（从 store 中反序列化），转换为 ProjectSiteSelectionCollection 对象
            # 使用 model_validate 自动忽略未定义的字段（如 context）
            collection = ProjectSiteSelectionCollection.model_validate(collection)

        # 构建报告配置
        config = get_report_config(report_data, collection=collection)

        # 生成Word文档
        generator = WordReportGenerator(config)
        generator.generate()

        # 构建文件名和保存路径
        file_name = current_time.strftime("%Y%m%d_%H%M%S") + ".docx"
        download_dir = os.path.join("app", "data", "download", session_id)
        
        
        file_path = os.path.join(download_dir, file_name)

        # 自动创建目录（如果不存在）
        os.makedirs(download_dir, exist_ok=True)

        # 保存文件
        generator.save(file_path)
        # 演示测试模式下，不保存真实报告
        if DEMONSTRATION_CONFIG["demonstration_report_enabled"]:
            file_name = "沈阳市能源应急输送通道项目天然气高压环线二期（北部城区）自然资源和规划“一点通”服务技术参考.docx"
            download_dir = os.path.join("app", "data", "demonstration", "download")
        # 构建下载URL
        download_url = f"/api/core/download/file?path={file_name}"

        progress_event_3 = create_tool_event(
            event_type="tool_progress",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "current": 3,
                "total": 3,
                "percentage": 100,
                "message": "报告生成完成"
            }
        )
        writer(dict(progress_event_3))

        result_data = {
            "status": "report_generated",
            "download_url": download_url,
            "file_name": file_name,
            "message": "地图报告已生成"
        }

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        stop_event = create_tool_event(
            event_type="tool_stop",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "status": "success",
                "type": "download",
                "result": result_data,
                "duration_ms": duration_ms
            }
        )
        writer(dict(stop_event))

        summary = {
            "status": "success",
            "tool": tool_name,
            "started_at": start_time.timestamp(),
            "ended_at": end_time.timestamp(),
            "duration_ms": duration_ms,
            "result": "报告文件生成完成，根据下载地址下载"
        }

        return Command(
            update={
                "map_report": result_data,
                "messages": [
                    ToolMessage(
                        content=json.dumps(summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        # 处理生成过程中的异常
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        error_event = create_tool_event(
            event_type="tool_error",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "error": str(e),
                "message": f"报告生成失败: {str(e)}"
            }
        )
        writer(dict(error_event))

        result_data = {
            "status": "report_generation_failed",
            "download_url": "",
            "file_name": "",
            "message": f"报告生成失败: {str(e)}"
        }

        summary = {
            "status": "error",
            "tool": tool_name,
            "started_at": start_time.timestamp(),
            "ended_at": end_time.timestamp(),
            "duration_ms": duration_ms,
            "error": str(e)
        }

        return Command(
            update={
                "map_report": result_data,
                "messages": [
                    ToolMessage(
                        content=json.dumps(summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )


# ==================== 业务信息保存工具 ====================

class SaveBusinessInfoInput(BaseModel):
    """
    保存业务信息输入参数

    定义保存业务信息时需要的所有字段及其描述信息。
    所有字段均为必填，具体校验在 save_business_info 函数内部执行。

    Attributes:
        project_name: 项目名称，必填，1-200字符
        unit_name: 建设单位名称，必填，1-200字符
        contact_person: 联系人姓名，必填，1-100字符
        contact_phone: 联系电话，必填，11位中国大陆手机号格式
        unit_address: 单位详细地址，必填，1-500字符
    """
    project_name: Optional[str] = Field(
        default=None,
        description="项目名称，必填，1-200字符"
    )
    unit_name: Optional[str] = Field(
        default=None,
        description="建设单位名称，必填，1-200字符"
    )
    contact_person: Optional[str] = Field(
        default=None,
        description="联系人姓名，必填，1-100字符"
    )
    contact_phone: Optional[str] = Field(
        default=None,
        description="联系电话，必填，11位中国大陆手机号格式（如13800138000）"
    )
    unit_address: Optional[str] = Field(
        default=None,
        description="单位详细地址，必填，1-500字符"
    )


def _validate_business_info(input_data: SaveBusinessInfoInput) -> list[str]:
    """
    验证业务信息输入参数

    对 save_business_info 的输入数据进行逐项校验，返回错误信息列表。
    如果返回空列表，表示验证通过。

    Args:
        input_data: 业务信息输入参数

    Returns:
        list[str]: 错误信息列表，每项描述一个字段的验证失败原因
    """
    errors = []

    # project_name 验证
    if input_data.project_name is None or not str(input_data.project_name).strip():
        errors.append("project_name（项目名称）为空或仅包含空白字符，请提供有效的项目名称（1-200字符）。")
    else:
        project_name = str(input_data.project_name).strip()
        if len(project_name) > 200:
            errors.append(f"project_name（项目名称）长度为{len(project_name)}，超过200字符限制，请缩短项目名称。")

    # unit_name 验证
    if input_data.unit_name is None or not str(input_data.unit_name).strip():
        errors.append("unit_name（建设单位名称）为空或仅包含空白字符，请提供有效的单位名称（1-200字符）。")
    else:
        unit_name = str(input_data.unit_name).strip()
        if len(unit_name) > 200:
            errors.append(f"unit_name（建设单位名称）长度为{len(unit_name)}，超过200字符限制，请缩短单位名称。")

    # contact_person 验证
    if input_data.contact_person is None or not str(input_data.contact_person).strip():
        errors.append("contact_person（联系人姓名）为空或仅包含空白字符，请提供有效的联系人姓名（1-100字符）。")
    else:
        contact_person = str(input_data.contact_person).strip()
        if len(contact_person) > 100:
            errors.append(f"contact_person（联系人姓名）长度为{len(contact_person)}，超过100字符限制，请缩短联系人姓名。")

    # contact_phone 验证
    if input_data.contact_phone is None or not str(input_data.contact_phone).strip():
        errors.append("contact_phone（联系电话）为空，请提供11位中国大陆手机号（如13800138000）。")
    else:
        contact_phone = str(input_data.contact_phone).strip()
        if not re.match(r'^1[3-9]\d{9}$', contact_phone):
            errors.append(f"contact_phone（联系电话）'{contact_phone}'格式不正确，请提供11位中国大陆手机号（如13800138000）。")

    # unit_address 验证
    if input_data.unit_address is None or not str(input_data.unit_address).strip():
        errors.append("unit_address（单位详细地址）为空或仅包含空白字符，请提供有效的详细地址（1-500字符）。")
    else:
        unit_address = str(input_data.unit_address).strip()
        if len(unit_address) > 500:
            errors.append(f"unit_address（单位详细地址）长度为{len(unit_address)}，超过500字符限制，请缩短地址。")

    return errors


@tool(description="""保存业务信息到数据库，自动生成业务编号。

所有字段均为必填：
- project_name: 项目名称，1-200字符
- unit_name: 建设单位名称，1-200字符
- contact_person: 联系人姓名，1-100字符
- contact_phone: 联系电话，11位中国大陆手机号格式（如13800138000）
- unit_address: 单位详细地址，1-500字符

如果参数有误，工具会返回具体的错误提示信息，请根据提示修正后重新调用本工具。
""")
async def save_business_info(input_data: SaveBusinessInfoInput, runtime: ToolRuntime) -> Command:
    """
    【保存业务信息】将项目及建设单位信息保存到数据库，自动生成业务编号。

    调用时机：
    - 用户需要提供项目信息并保存时
    - 需要生成业务编号并保存建设单位资料时
    - 用户说"保存项目信息"、"录入业务信息"、"生成业务编号"时

    Args:
        input_data: 业务信息输入参数（Pydantic模型），包含：
            - project_name: 项目名称（必填，1-200字符）
            - unit_name: 建设单位名称（必填，1-200字符）
            - contact_person: 联系人姓名（必填，1-100字符）
            - contact_phone: 联系电话（必填，11位手机号格式，如13800138000）
            - unit_address: 单位详细地址（必填，1-500字符）
        runtime: 工具运行时上下文

    Returns:
        Command: 包含操作结果和状态更新的命令对象
            - status: "saved" 表示保存成功
            - status: "validation_error" 表示参数验证失败，需根据提示修正后重新调用
            - status: "error" 表示保存过程中发生异常
            - business_no: 生成的业务编号（如 YDT202606040001）
            - project_name: 保存的项目名称
            - message: 操作结果描述

    Raises:
        无显式异常抛出，所有错误通过返回结果状态反馈

    Notes:
        - 所有5个字段均为必填，缺失或格式错误时会返回 validation_error 及具体修正提示
        - 业务编号格式：YDT + YYYYMMDD + 4位每日递增序号（如 YDT202606040001）
        - 序号按每日重置，每天从0001开始
        - 使用数据库原子操作保证并发安全，支持同时叫号
        - session_id 从 runtime.context 中获取
    """
    tool_name = "保存业务信息"
    tool_call_id = runtime.tool_call_id
    start_time = datetime.now()
    writer = get_stream_writer()

    # 发送工具开始事件
    start_event = create_tool_event(
        event_type="tool_start",
        tool=tool_name,
        tool_call_id=tool_call_id,
        data={
            "args": input_data.model_dump(),
            "description": "开始保存业务信息"
        }
    )
    writer(dict(start_event))

    try:
        # 进度1：手动验证参数
        progress_event_1 = create_tool_event(
            event_type="tool_progress",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "current": 1,
                "total": 3,
                "percentage": 33,
                "message": "正在验证参数"
            }
        )
        writer(dict(progress_event_1))

        # 执行参数验证
        validation_errors = _validate_business_info(input_data)
        if validation_errors:
            error_lines = "\n".join(f"{i + 1}. {err}" for i, err in enumerate(validation_errors))
            error_message = (
                f"参数验证失败，请修正以下问题后重新调用 save_business_info 工具：\n{error_lines}\n\n"
                "各字段要求如下：\n"
                "- project_name: 项目名称，必填，1-200字符\n"
                "- unit_name: 建设单位名称，必填，1-200字符\n"
                "- contact_person: 联系人姓名，必填，1-100字符\n"
                "- contact_phone: 联系电话，必填，11位中国大陆手机号格式（如13800138000）\n"
                "- unit_address: 单位详细地址，必填，1-500字符"
            )

            result_data = {
                "status": "validation_error",
                "business_no": "",
                "project_name": input_data.project_name if input_data and input_data.project_name else "",
                "message": error_message
            }

            summary = {
                "status": "validation_error",
                "tool": tool_name,
                "started_at": start_time.timestamp(),
                "ended_at": datetime.now().timestamp(),
                "duration_ms": int((datetime.now() - start_time).total_seconds() * 1000),
                "errors": validation_errors,
                "field_requirements": {
                    "project_name": "项目名称，必填，1-200字符",
                    "unit_name": "建设单位名称，必填，1-200字符",
                    "contact_person": "联系人姓名，必填，1-100字符",
                    "contact_phone": "联系电话，必填，11位中国大陆手机号格式（如13800138000）",
                    "unit_address": "单位详细地址，必填，1-500字符"
                },
                "result": result_data
            }

            return Command(
                update={
                    "business_info": result_data,
                    "messages": [
                        ToolMessage(
                            content=json.dumps(summary, ensure_ascii=False),
                            tool_call_id=tool_call_id
                        )
                    ]
                }
            )

        # 获取session_id
        session_id = runtime.context.get("session_id", "default_session")

        # 进度2：生成业务编号（原子操作，并发安全）
        progress_event_2 = create_tool_event(
            event_type="tool_progress",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "current": 2,
                "total": 3,
                "percentage": 66,
                "message": "正在生成业务编号"
            }
        )
        writer(dict(progress_event_2))

        date_str = datetime.now().strftime("%Y%m%d")
        business_no = ""

        if DatabasePool.is_enabled():
            # 使用原子Upsert获取序号，支持并发安全叫号
            row = await DatabasePool.fetchrow(
                """
                INSERT INTO map_business_no_counter (date_str, current_seq)
                VALUES ($1, 1)
                ON CONFLICT (date_str)
                DO UPDATE SET current_seq = map_business_no_counter.current_seq + 1
                RETURNING current_seq
                """,
                date_str
            )
            seq = row["current_seq"] if row else 1
            business_no = f"YDT{date_str}{seq:04d}"
        else:
            # 内存模式：使用UUID兜底（无数据库时无法保证每日序号）
            business_no = f"YDT{date_str}{str(uuid.uuid4().int)[:4]}"

        # 进度3：保存到数据库
        progress_event_3 = create_tool_event(
            event_type="tool_progress",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "current": 3,
                "total": 3,
                "percentage": 100,
                "message": "正在写入数据库"
            }
        )
        writer(dict(progress_event_3))

        if DatabasePool.is_enabled():
            await DatabasePool.execute(
                """
                INSERT INTO map_business_info
                (business_no, project_name, unit_name, contact_person, contact_phone, unit_address, session_id, created_at)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                """,
                business_no,
                input_data.project_name,
                input_data.unit_name,
                input_data.contact_person,
                input_data.contact_phone,
                input_data.unit_address,
                session_id,
                datetime.now()
            )

        result_data = {
            "status": "saved",
            "business_no": business_no,
            "project_name": input_data.project_name,
            "message": f"业务信息保存成功，业务编号: {business_no}"
        }

        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        stop_event = create_tool_event(
            event_type="tool_stop",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "status": "success",
                "result": result_data,
                "duration_ms": duration_ms
            }
        )
        writer(dict(stop_event))

        summary = {
            "status": "success",
            "tool": tool_name,
            "started_at": start_time.timestamp(),
            "ended_at": end_time.timestamp(),
            "duration_ms": duration_ms,
            "events": [dict(start_event), dict(stop_event)],
            "result": result_data
        }

        return Command(
            update={
                "business_info": result_data,
                "messages": [
                    ToolMessage(
                        content=json.dumps(summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )

    except Exception as e:
        end_time = datetime.now()
        duration_ms = int((end_time - start_time).total_seconds() * 1000)

        error_event = create_tool_event(
            event_type="tool_error",
            tool=tool_name,
            tool_call_id=tool_call_id,
            data={
                "error": str(e),
                "message": f"业务信息保存失败: {str(e)}"
            }
        )
        writer(dict(error_event))

        result_data = {
            "status": "error",
            "business_no": "",
            "project_name": input_data.project_name if input_data else "",
            "message": f"业务信息保存失败: {str(e)}"
        }

        summary = {
            "status": "error",
            "tool": tool_name,
            "started_at": start_time.timestamp(),
            "ended_at": end_time.timestamp(),
            "duration_ms": duration_ms,
            "error": str(e)
        }

        return Command(
            update={
                "business_info": result_data,
                "messages": [
                    ToolMessage(
                        content=json.dumps(summary, ensure_ascii=False),
                        tool_call_id=tool_call_id
                    )
                ]
            }
        )


# ==================== 数据库表结构初始化 ====================

@register_schema
async def init_map_business_info_schema():
    """
    初始化业务信息表及计数器表

    创建 map_business_info 业务信息主表和 map_business_no_counter 计数器表，
    用于支持业务信息的持久化存储和并发安全的业务编号生成。

    Args:
        无

    Returns:
        无

    Raises:
        RuntimeError: 数据库连接池未初始化时抛出
    """
    # 业务信息主表
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS map_business_info (
            id SERIAL PRIMARY KEY,
            business_no VARCHAR(20) UNIQUE NOT NULL,
            project_name VARCHAR(200) NOT NULL,
            unit_name VARCHAR(200) NOT NULL,
            contact_person VARCHAR(100) NOT NULL,
            contact_phone VARCHAR(20) NOT NULL,
            unit_address VARCHAR(500) NOT NULL,
            session_id VARCHAR(100) NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_map_business_session_id ON map_business_info(session_id)
    """)
    await DatabasePool.execute("""
        CREATE INDEX IF NOT EXISTS idx_map_business_created_at ON map_business_info(created_at)
    """)
    # 业务编号计数器表（支持并发安全叫号）
    await DatabasePool.execute("""
        CREATE TABLE IF NOT EXISTS map_business_no_counter (
            date_str VARCHAR(8) PRIMARY KEY,
            current_seq INTEGER DEFAULT 0
        )
    """)
