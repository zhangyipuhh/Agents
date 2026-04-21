#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AI辅助编程效果评审客户端

命令行客户端，用于测试评审 API。

Date: 2026-04-21
Author: 张镒谱
"""

import requests
import json
import sys


def review_developer(
    name: str,
    content: list,
    code: list,
    task: list = None,
    base_url: str = "http://localhost:8001",
) -> dict:
    """
    评审开发者数据

    通过 HTTP POST 请求调用评审 API，将开发者数据提交给智能体进行评审。

    Args:
        name: 开发者姓名
        content: 文档内容列表
        code: 代码提交记录列表
        task: 任务列表，默认为 None
        base_url: API 基础 URL，默认为 http://localhost:8001

    Returns:
        dict: 评审结果，成功时包含智能体返回的评审数据，失败时包含错误信息
    """
    # 拼接评审接口的完整 URL
    url = f"{base_url}/api/ai-coding-check/review"
    # 构建请求体，task 为空时使用空列表代替
    payload = {
        "developer_data": {
            "name": name,
            "content": content,
            "code": code,
            "task": task or [],
        }
    }

    try:
        # 发送 POST 请求，设置超时时间为 120 秒以适应评审耗时较长的场景
        response = requests.post(url, json=payload, timeout=120)
        # 检查 HTTP 状态码，非 2xx 时抛出异常
        response.raise_for_status()
        # 请求成功，返回 JSON 格式的评审结果
        return response.json()
    except requests.exceptions.RequestException as e:
        # 捕获网络请求异常（如连接超时、服务端错误等），打印错误信息
        print(f"请求失败: {e}")
        # 返回包含错误信息的默认响应结构
        return {"code": 500, "message": str(e), "data": {}}


# 命令行入口：直接运行此文件时执行示例评审请求
if __name__ == "__main__":
    # 使用示例数据调用评审接口
    result = review_developer(
        name="张三",
        content=["需求文档 v1.0", "API 设计文档"],
        code=["commit: 添加用户模块", "commit: 修复登录 bug"],
        task=["任务1: 实现用户注册", "任务2: 修复登录问题"],
    )
    # 以格式化的 JSON 输出评审结果，ensure_ascii=False 保证中文正常显示
    print(json.dumps(result, ensure_ascii=False, indent=2))
