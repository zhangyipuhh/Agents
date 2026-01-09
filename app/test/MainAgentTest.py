#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
测试脚本：验证Agent API的流式输出功能
"""

import requests
import sys
import time


def test_agent_api() -> bool:
    """测试Agent API的流式输出功能
    
    Returns:
        bool: 测试是否成功
    """
    url = "http://localhost:8001/api/agent/chat"
    headers = {"Content-Type": "application/json"}
    
    # 测试消息
    test_message = "民法的作用，中国民法典的由来"
    
    print(f"\n📤 发送请求: {test_message}")
    print("=" * 80)
    
    try:
        # 发送 POST 请求，启用流式响应
        response = requests.post(
            url,
            headers=headers,
            json={"message": test_message},
            stream=True,
            timeout=120
        )
        
        # 检查响应状态码
        if response.status_code != 200:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
        
        print("✅ 服务器连接成功，开始接收流式输出:")
        print("=" * 80)
        
        # 处理Server-Sent Events流式响应
        message_count = 0
        
        # 使用iter_lines逐行读取流式响应
        for line in response.iter_lines(decode_unicode=True):
            if line:
                # 处理事件类型行
                if line.startswith('event: '):
                    event_type = line[7:]
                    print(f"\n📡 事件: {event_type}", end="")
                
                # 处理数据行
                elif line.startswith('data: '):
                    # 提取数据部分，保留原始格式
                    data_part = line[6:]
                    # 直接打印数据部分，不做额外处理，保留换行符
                    if data_part:
                        message_count += 1
                        print(f"{data_part}", end="")
                        # 强制刷新输出缓冲区，确保实时显示
                        sys.stdout.flush()
        
        print("\n" + "=" * 80)
        print(f"✅ 流式输出接收完成，共接收 {message_count} 条消息")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败，请确保服务器正在运行")
        print("💡 提示: 使用 'python -m uvicorn app.MainServer:app --reload' 启动服务器")
        return False
    except requests.exceptions.Timeout:
        print("❌ 请求超时，服务器响应时间过长")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def main():
    """主函数"""
    print("\n" + "=" * 80)
    print("🚀 AI Agent API 流式输出测试")
    print("=" * 80)
    
    success = test_agent_api()
    
    print("\n" + "=" * 80)
    if success:
        print("✅ 测试成功完成!")
    else:
        print("❌ 测试失败，请检查错误信息")
    print("=" * 80)
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())