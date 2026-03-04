#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Base64 文件上传 API 测试脚本

用于测试新增的 base64 文件上传功能
"""
import requests
import base64
import json

BASE_URL = "http://127.0.0.1:8000"

def test_base64_upload():
    """测试 base64 文件上传功能"""
    
    # 创建一个简单的测试文件内容（例如：一个文本文件）
    test_content = b"This is a test file content for base64 upload testing."
    test_filename = "test_file.txt"
    
    # 将文件内容编码为 base64
    base64_data = base64.b64encode(test_content).decode('utf-8')
    
    # 构建请求数据
    upload_data = {
        "files": [
            {
                "filename": test_filename,
                "base64_data": base64_data
            }
        ]
    }
    
    # 设置请求头
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": "test-session-001"  # 可选的会话 ID
    }
    
    try:
        # 发送 POST 请求
        response = requests.post(
            f"{BASE_URL}/api/files/upload-base64",
            json=upload_data,
            headers=headers
        )
        
        # 打印响应结果
        print(f"状态码：{response.status_code}")
        print(f"响应内容：{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("\n✓ Base64 文件上传成功！")
            result = response.json()
            print(f"  - 上传文件数量：{result['count']}")
            for file_info in result['fileids']:
                print(f"  - 文件 ID: {file_info['id']}, 文件名：{file_info['filename']}")
        else:
            print(f"\n✗ Base64 文件上传失败")
            
    except requests.exceptions.ConnectionError:
        print("错误：无法连接到服务器，请确保服务器正在运行")
    except Exception as e:
        print(f"错误：{str(e)}")

def test_multiple_base64_upload():
    """测试批量上传多个 base64 文件"""
    
    # 创建多个测试文件
    files_data = [
        {
            "filename": "file1.txt",
            "content": b"Content of file 1"
        },
        {
            "filename": "file2.txt", 
            "content": b"Content of file 2"
        },
        {
            "filename": "document.pdf",
            "content": b"%PDF-1.4 fake pdf content"  # 模拟 PDF 文件
        }
    ]
    
    # 编码为 base64
    upload_files = []
    for file_info in files_data:
        base64_data = base64.b64encode(file_info["content"]).decode('utf-8')
        upload_files.append({
            "filename": file_info["filename"],
            "base64_data": base64_data
        })
    
    upload_data = {"files": upload_files}
    
    headers = {
        "Content-Type": "application/json",
        "X-Session-ID": "test-session-001"
    }
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/files/upload-base64",
            json=upload_data,
            headers=headers
        )
        
        print(f"\n批量上传测试 - 状态码：{response.status_code}")
        print(f"响应内容：{json.dumps(response.json(), indent=2, ensure_ascii=False)}")
        
        if response.status_code == 200:
            print("\n✓ 批量 Base64 文件上传成功！")
            result = response.json()
            print(f"  - 上传文件数量：{result['count']}")
        else:
            print(f"\n✗ 批量 Base64 文件上传失败")
            
    except Exception as e:
        print(f"错误：{str(e)}")

if __name__ == "__main__":
    print("=" * 60)
    print("Base64 文件上传 API 测试")
    print("=" * 60)
    print("\n[测试 1] 单个文件上传")
    print("-" * 60)
    test_base64_upload()
    
    print("\n[测试 2] 批量文件上传")
    print("-" * 60)
    test_multiple_base64_upload()
    
    print("\n" + "=" * 60)
    print("测试完成")
    print("=" * 60)
