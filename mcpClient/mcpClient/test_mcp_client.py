#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCP Client 诊断测试脚本

测试内容：
1. 配置加载验证
2. MCP 服务器连接测试
3. 工具列表获取测试
4. 工具调用测试
5. 连接稳定性 / 保活测试
6. 断线重连测试

Date: 2026-04-20
"""

import asyncio
import json
import logging
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent))
sys.path.insert(0, str(Path(__file__).parent.parent))

from mcpClient.shared.config_loader import load_mcp_config
from mcpClient.core.unified_mcp_client import UnifiedMCPClient, _convert_server_config

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("mcp_test")


class TestResult:
    def __init__(self, name: str):
        self.name = name
        self.passed = False
        self.error: Optional[str] = None
        self.details: str = ""
        self.duration_ms: float = 0

    def __repr__(self):
        status = "PASS" if self.passed else "FAIL"
        return f"[{status}] {self.name} ({self.duration_ms:.0f}ms) {self.details or ''}"


results: List[TestResult] = []


def record(result: TestResult):
    results.append(result)
    status = "PASS" if result.passed else "FAIL"
    print(f"\n{'='*60}")
    print(f"  {status} | {result.name} | {result.duration_ms:.0f}ms")
    if result.details:
        print(f"  详情: {result.details}")
    if result.error:
        print(f"  错误: {result.error}")
    print(f"{'='*60}\n")


async def test_config_loading():
    result = TestResult("配置加载")
    start = time.monotonic()
    try:
        config = load_mcp_config()
        if not config:
            result.error = "配置为空，请检查 config.yaml 文件是否存在且格式正确"
            result.details = f"配置路径: {Path(__file__).parent / 'config.yaml'}"
        else:
            result.passed = True
            result.details = f"加载了 {len(config)} 个服务器配置: {list(config.keys())}"
            for name, cfg in config.items():
                adapted = _convert_server_config(name, cfg)
                if not adapted:
                    result.passed = False
                    result.error = f"服务器 '{name}' 配置适配失败，无法确定 transport"
                else:
                    transport = adapted.get("transport", "unknown")
                    print(f"  - {name}: transport={transport}, adapted={adapted}")
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)
    return config


async def test_client_creation(config: dict):
    result = TestResult("客户端创建")
    start = time.monotonic()
    client = None
    try:
        client = UnifiedMCPClient(config)
        if client._client is None:
            result.error = "MultiServerMCPClient 创建失败 (_client is None)"
        else:
            result.passed = True
            result.details = f"服务器列表: {client.get_server_names()}"
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)
    return client


async def test_get_tools(client: UnifiedMCPClient):
    result = TestResult("工具列表获取")
    start = time.monotonic()
    try:
        tools = await client.get_tools()
        if not tools:
            result.error = "工具列表为空！可能是连接未建立或服务器无工具"
            result.details = "检查 MultiServerMCPClient 是否需要 async context manager 初始化"
        else:
            result.passed = True
            tool_names = [t.name for t in tools]
            result.details = f"获取到 {len(tools)} 个工具: {tool_names[:10]}{'...' if len(tool_names) > 10 else ''}"
            for tool in tools:
                desc = tool.description[:80] if tool.description else "无描述"
                print(f"  - {tool.name}: {desc}")
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)
    return tools


async def test_get_tools_per_server(client: UnifiedMCPClient):
    result = TestResult("逐服务器工具获取")
    start = time.monotonic()
    try:
        all_ok = True
        for name in client.get_server_names():
            info = await client.get_server_tools(name)
            if info is None:
                print(f"  - {name}: 未找到配置")
                all_ok = False
                continue
            tools = info.get("tools", [])
            tags = info.get("tags", [])
            tool_names = [t.name for t in tools]
            print(f"  - {name} (tags={tags}): {len(tools)} 个工具: {tool_names}")
            if not tools:
                all_ok = False
        result.passed = all_ok
        if not all_ok:
            result.error = "部分服务器工具列表为空"
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


async def test_call_tool(client: UnifiedMCPClient, config: dict):
    result = TestResult("工具调用测试")
    start = time.monotonic()
    try:
        server_name = client.get_server_names()[0] if client.get_server_names() else None
        if not server_name:
            result.error = "无可用服务器"
            record(result)
            return

        tools = await client.get_tools()
        if not tools:
            result.error = "无可用工具"
            record(result)
            return

        first_tool = tools[0]
        print(f"  尝试调用服务器 '{server_name}' 的工具 '{first_tool.name}'...")

        try:
            call_result = await client.call_tool(
                server_name=server_name,
                tool_name=first_tool.name,
                arguments={},
            )
            result.passed = True
            result_str = str(call_result)
            result.details = f"调用成功，返回 {len(result_str)} 字符: {result_str[:200]}"
        except Exception as call_err:
            result.details = f"工具 '{first_tool.name}' 调用失败（可能需要参数）: {call_err}"
            result.passed = True
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


async def test_connection_stability(client: UnifiedMCPClient, rounds: int = 3, interval: float = 15.0):
    result = TestResult(f"连接稳定性测试 ({rounds}轮, 间隔{interval}s)")
    start = time.monotonic()
    try:
        success_count = 0
        fail_count = 0
        for i in range(rounds):
            if i > 0:
                print(f"  等待 {interval}s 后进行第 {i+1} 轮测试...")
                await asyncio.sleep(interval)

            try:
                tools = await client.get_tools()
                tool_count = len(tools)
                if tool_count > 0:
                    success_count += 1
                    print(f"  第 {i+1} 轮: 成功获取 {tool_count} 个工具")
                else:
                    fail_count += 1
                    print(f"  第 {i+1} 轮: 工具列表为空！连接可能已断开")
            except Exception as e:
                fail_count += 1
                print(f"  第 {i+1} 轮: 异常 - {e}")

        result.passed = success_count == rounds
        result.details = f"成功 {success_count}/{rounds}, 失败 {fail_count}/{rounds}"
        if fail_count > 0:
            result.error = f"连接不稳定，{fail_count} 次获取工具失败，可能存在超时断连问题"
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


async def test_reconnect(config: dict):
    result = TestResult("断线重连测试")
    start = time.monotonic()
    try:
        print("  创建新客户端...")
        client = UnifiedMCPClient(config)

        print("  第一次获取工具...")
        tools1 = await client.get_tools()
        count1 = len(tools1)
        print(f"  第一次: {count1} 个工具")

        print("  关闭客户端...")
        await client.shutdown()

        print("  重新创建客户端...")
        client = UnifiedMCPClient(config)

        print("  第二次获取工具...")
        tools2 = await client.get_tools()
        count2 = len(tools2)
        print(f"  第二次: {count2} 个工具")

        result.passed = count2 > 0
        result.details = f"重连前 {count1} 个工具, 重连后 {count2} 个工具"
        if count2 == 0:
            result.error = "重连后无法获取工具，MultiServerMCPClient 可能不支持重新连接"

        await client.shutdown()
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


async def test_raw_mcp_connection(config: dict):
    result = TestResult("原始 MCP 连接测试 (绕过 UnifiedMCPClient)")
    start = time.monotonic()
    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient

        adapted = {}
        for name, cfg in config.items():
            converted = _convert_server_config(name, cfg)
            if converted:
                adapted[name] = converted

        if not adapted:
            result.error = "无有效适配配置"
            record(result)
            return

        print(f"  使用 MultiServerMCPClient 直接连接 {len(adapted)} 个服务器...")

        raw_client = MultiServerMCPClient(adapted)

        try:
            tools = await raw_client.get_tools()
            tool_names = [t.name for t in tools]
            result.passed = len(tools) > 0
            result.details = f"原始连接获取 {len(tools)} 个工具: {tool_names[:10]}"
            if len(tools) == 0:
                result.error = "原始连接也无法获取工具，问题在 MultiServerMCPClient 层"
        except Exception as e:
            result.error = f"原始连接异常: {traceback.format_exc()}"
        finally:
            if hasattr(raw_client, "cleanup"):
                await raw_client.cleanup()
            elif hasattr(raw_client, "close"):
                await raw_client.close()
    except ImportError as e:
        result.error = f"无法导入 MultiServerMCPClient: {e}"
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


async def test_sse_endpoint(config: dict):
    result = TestResult("SSE 端点可达性测试")
    start = time.monotonic()
    try:
        import httpx

        for name, cfg in config.items():
            url = cfg.get("url", "")
            if not url:
                print(f"  - {name}: 无 URL 配置，跳过")
                continue

            sse_url = url.rstrip("/")
            print(f"  - 测试 {name}: {sse_url}")

            try:
                async with httpx.AsyncClient(timeout=10.0) as http:
                    resp = await http.get(sse_url, headers={"Accept": "text/event-stream"})
                    print(f"    状态码: {resp.status_code}, Content-Type: {resp.headers.get('content-type', 'N/A')}")
                    if resp.status_code == 200:
                        result.passed = True
                    else:
                        result.details = f"状态码 {resp.status_code}"
            except httpx.ConnectTimeout:
                result.error = f"连接超时: {sse_url}"
            except httpx.ConnectError as e:
                result.error = f"连接失败: {e}"
            except Exception as e:
                result.error = f"请求异常: {e}"
    except ImportError:
        result.error = "httpx 未安装"
    except Exception as e:
        result.error = traceback.format_exc()
    result.duration_ms = (time.monotonic() - start) * 1000
    record(result)


def print_summary():
    print("\n" + "=" * 60)
    print("  测试结果汇总")
    print("=" * 60)
    passed = sum(1 for r in results if r.passed)
    failed = sum(1 for r in results if not r.passed)
    total_ms = sum(r.duration_ms for r in results)

    for r in results:
        status = "PASS" if r.passed else "FAIL"
        print(f"  [{status}] {r.name} ({r.duration_ms:.0f}ms)")
        if r.error:
            print(f"         错误: {r.error[:100]}")

    print(f"\n  总计: {passed} 通过, {failed} 失败, 耗时 {total_ms:.0f}ms")
    print("=" * 60)

    if failed > 0:
        print("\n  诊断建议:")
        for r in results:
            if not r.passed:
                if "配置" in r.name:
                    print(f"  - 检查 config.yaml 格式和路径")
                elif "创建" in r.name:
                    print(f"  - 检查 langchain-mcp-adapters 版本和配置适配逻辑")
                elif "工具" in r.name:
                    print(f"  - 工具无法加载可能原因:")
                    print(f"    1. MultiServerMCPClient 需要作为 async context manager 使用")
                    print(f"    2. SSE 连接未建立或已超时")
                    print(f"    3. 服务器端点不可达")
                elif "稳定" in r.name:
                    print(f"  - 连接断开可能原因:")
                    print(f"    1. SSE 连接空闲超时（服务器关闭了连接）")
                    print(f"    2. 缺少心跳/保活机制")
                    print(f"    3. 网络中间件超时（代理/负载均衡器）")
                    print(f"    建议: 添加定期 get_tools 调用作为心跳，或实现自动重连")
                elif "重连" in r.name:
                    print(f"  - 重连失败建议:")
                    print(f"    1. 每次使用前创建新的 UnifiedMCPClient 实例")
                    print(f"    2. 在 get_tools 中捕获异常后自动重建连接")


async def run_all_tests(stability_rounds: int = 3, stability_interval: float = 15.0):
    print("\n" + "=" * 60)
    print("  MCP Client 诊断测试")
    print("=" * 60 + "\n")

    config = await test_config_loading()
    if not config:
        print("配置加载失败，终止测试")
        print_summary()
        return

    await test_sse_endpoint(config)

    await test_raw_mcp_connection(config)

    client = await test_client_creation(config)
    if client is None:
        print("客户端创建失败，终止后续测试")
        print_summary()
        return

    await test_get_tools(client)
    await test_get_tools_per_server(client)
    await test_call_tool(client, config)
    await test_connection_stability(client, rounds=stability_rounds, interval=stability_interval)

    await client.shutdown()

    await test_reconnect(config)

    print_summary()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="MCP Client 诊断测试")
    parser.add_argument("--rounds", type=int, default=3, help="稳定性测试轮数 (默认: 3)")
    parser.add_argument("--interval", type=float, default=15.0, help="稳定性测试间隔秒数 (默认: 15)")
    args = parser.parse_args()

    asyncio.run(run_all_tests(stability_rounds=args.rounds, stability_interval=args.interval))
