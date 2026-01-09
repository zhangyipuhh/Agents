#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Test script to verify the API endpoint with streaming output
"""

import requests
import json
import time

def test_agent_api():
    """Test the agent API with streaming output"""
    url = "http://localhost:8000/api/agent/chat"
    headers = {"Content-Type": "application/json"}
    
    # 测试消息
    test_message = "民法的作用，中国民法典的由来"
    
    print(f"发送请求: {test_message}")
    print("=" * 60)
    
    try:
        # 发送 POST 请求，启用流式响应
        response = requests.post(
            url,
            headers=headers,
            json={"message": test_message},
            stream=True
        )
        
        # 检查响应状态码
        if response.status_code != 200:
            print(f"❌ 请求失败，状态码: {response.status_code}")
            print(f"错误信息: {response.text}")
            return False
        
        print("✅ 服务器连接成功，开始接收流式输出:")
        print("=" * 60)
        
        # 逐行读取流式响应
        for line in response.iter_lines():
            if line:
                # 解码响应行
                decoded_line = line.decode('utf-8')
                
                # 处理 Server-Sent Events 格式
                if decoded_line.startswith('data: '):
                    # 提取数据部分
                    data = decoded_line[6:]
                    print(f"📩 {data}")
        
        print("=" * 60)
        print("✅ 流式输出接收完成")
        return True
        
    except requests.exceptions.ConnectionError:
        print("❌ 连接失败，请确保服务器正在运行")
        print("使用 'python -m uvicorn app.MainServer:app --reload' 启动服务器")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {str(e)}")
        return False


if __name__ == "__main__":
    print("正在测试 AI Agent API 流式输出...")
    print("")
    
    test_agent_api()
    
    print("")
    print("测试完成!")