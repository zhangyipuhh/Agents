#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
MapAgent 测试运行脚本

快速运行地图智能体测试的便捷脚本

Date: 2026-04-14
Author: AI Assistant
"""

import sys
import asyncio
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest


def run_all_tests():
    """运行所有测试"""
    print("=" * 80)
    print("🚀 开始运行 MapAgent 测试套件")
    print("=" * 80)
    print()

    # 运行测试
    exit_code = pytest.main([
        __file__.replace("run_map_agent_tests.py", "test_map_agent.py"),
        "-v",  # 详细输出
        "-s",  # 显示 print 输出
        "--tb=short",  # 简短的错误追踪
        "--color=yes",  # 彩色输出
        "-x",  # 遇到第一个失败就停止
    ])

    print()
    print("=" * 80)
    if exit_code == 0:
        print("✅ 所有测试通过!")
    else:
        print("❌ 测试失败,请检查错误信息")
    print("=" * 80)

    return exit_code


def run_specific_test(test_class=None, test_method=None):
    """运行特定的测试"""
    test_file = __file__.replace("run_map_agent_tests.py", "test_map_agent.py")

    if test_class and test_method:
        test_path = f"{test_file}::{test_class}::{test_method}"
    elif test_class:
        test_path = f"{test_file}::{test_class}"
    else:
        test_path = test_file

    print(f"🎯 运行测试: {test_path}")
    print("=" * 80)

    exit_code = pytest.main([
        test_path,
        "-v",
        "-s",
        "--tb=short",
        "--color=yes",
    ])

    return exit_code


def run_tool_tests():
    """只运行工具测试"""
    print("🔧 运行地图工具测试")
    print("=" * 80)
    return run_specific_test("TestMapTools")


def run_streaming_tests():
    """只运行流式测试"""
    print("📡 运行流式调用测试")
    print("=" * 80)
    return run_specific_test("TestMapAgentStreaming")


def run_error_tests():
    """只运行错误处理测试"""
    print("⚠️  运行错误处理测试")
    print("=" * 80)
    return run_specific_test("TestMapAgentErrorHandling")


def run_sse_tests():
    """只运行 SSE 格式测试"""
    print("📨 运行 SSE 格式测试")
    print("=" * 80)
    return run_specific_test("TestSSEFormat")


def run_integration_tests():
    """只运行集成测试"""
    print("🔗 运行集成测试")
    print("=" * 80)
    return run_specific_test("TestMapAgentIntegration")


def print_usage():
    """打印使用说明"""
    print("""
MapAgent 测试运行脚本

用法:
    python run_map_agent_tests.py [选项]

选项:
    all          - 运行所有测试 (默认)
    tools        - 只运行工具测试
    streaming    - 只运行流式调用测试
    error        - 只运行错误处理测试
    sse          - 只运行 SSE 格式测试
    integration  - 只运行集成测试
    help         - 显示此帮助信息

示例:
    python run_map_agent_tests.py              # 运行所有测试
    python run_map_agent_tests.py tools        # 只运行工具测试
    python run_map_agent_tests.py streaming    # 只运行流式调用测试
    """)


if __name__ == "__main__":
    # 解析命令行参数
    if len(sys.argv) > 1:
        option = sys.argv[1].lower()

        if option == "help":
            print_usage()
            sys.exit(0)
        elif option == "tools":
            exit_code = run_tool_tests()
        elif option == "streaming":
            exit_code = run_streaming_tests()
        elif option == "error":
            exit_code = run_error_tests()
        elif option == "sse":
            exit_code = run_sse_tests()
        elif option == "integration":
            exit_code = run_integration_tests()
        elif option == "all":
            exit_code = run_all_tests()
        else:
            print(f"❌ 未知选项: {option}")
            print_usage()
            sys.exit(1)
    else:
        # 默认运行所有测试
        exit_code = run_all_tests()

    sys.exit(exit_code)
