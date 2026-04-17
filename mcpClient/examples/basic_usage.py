#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
MCPClient 基本使用示例
"""

from mcpClient.core.mcp_client import MCPClient, get_mcp_client


def main():
    print("=== MCPClient 基本使用示例 ===\n")
    
    # 方式 1: 直接创建客户端
    print("方式 1: 直接创建客户端")
    client = MCPClient("http://localhost:10001")
    
    # 健康检查
    if client.health_check():
        print("[OK] 服务连接正常")
        
        # 列出服务器
        servers = client.list_servers()
        print(f"\n已连接的服务器: {len(servers)} 个")
        for s in servers:
            print(f"  - {s['name']}: {len(s['tools'])} 个工具")
        
        # 列出工具
        tools = client.get_all_tools()
        print(f"\n可用工具: {len(tools)} 个")
        for t in tools[:5]:
            print(f"  - {t['server']}.{t['name']}")
        
        # 调用工具示例 1: 地理编码
        print("\n示例 1: 地理编码 (maps_geo)")
        result = client.call_tool(
            "高德地图mcp",
            "maps_geo",
            {"address": "北京市天安门"}
        )
        if result.get("success"):
            import json
            content = json.loads(result["result"]["content"][0]["text"])
            for item in content.get("results", []):
                print(f"  地址: {item.get('province', '')}{item.get('city', '')}")
                print(f"  坐标: {item.get('location', '')}")
        
        # 调用工具示例 2: 天气查询
        print("\n示例 2: 天气查询 (maps_weather)")
        result = client.call_tool(
            "高德地图mcp",
            "maps_weather",
            {"city": "北京"}
        )
        if result.get("success"):
            import json
            content = json.loads(result["result"]["content"][0]["text"])
            city = content.get("city", "")
            forecasts = content.get("forecasts", [])
            if forecasts:
                today = forecasts[0]
                print(f"  {city} 今天天气:")
                print(f"    白天: {today.get('dayweather', '')}, {today.get('daytemp', '')}°C")
                print(f"    夜间: {today.get('nightweather', '')}, {today.get('nighttemp', '')}°C")
    else:
        print("[FAIL] 服务连接失败，请确保服务已启动")
        print("  启动命令: python -m mcpClient.main")
    
    # 方式 2: 使用单例模式
    print("\n\n方式 2: 使用单例模式")
    client1 = get_mcp_client("http://localhost:10001")
    client2 = get_mcp_client("http://localhost:10001")
    print(f"client1 is client2: {client1 is client2}")
    
    print("\n=== 示例完成 ===")


if __name__ == "__main__":
    main()
