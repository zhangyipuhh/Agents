#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
API 测试脚本

本脚本用于测试所有 API 接口，包括认证、会话管理和文件操作。
由于 Swagger 文档不方便添加 token，使用此脚本进行测试。

Date: 2026/2/6
Author: 张镒谱
"""
import requests
import json
from pathlib import Path


class APITester:
    """
    API 测试类
    
    提供所有 API 接口的测试方法。
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化 API 测试器
        
        Args:
            base_url (str): API 基础 URL
        """
        self.base_url = base_url
        self.token = None
        self.session_id = None
        self.headers = {
            "Content-Type": "application/json"
        }
    
    def _get_headers(self, include_content_type: bool = True) -> dict:
        """
        获取包含认证信息的请求头
        
        Args:
            include_content_type (bool): 是否包含 Content-Type，默认为 True
                                         上传文件时应设为 False，让 requests 自动设置
        
        Returns:
            dict: 包含 Authorization 和 X-Session-ID 的请求头
        """
        headers = {}
        if include_content_type:
            headers["Content-Type"] = "application/json"
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        if self.session_id:
            headers["X-Session-ID"] = self.session_id
        return headers
    
    def login(self, username: str = "admin", password: str = "123456"):
        """
        登录获取 JWT token
        
        Args:
            username (str): 用户名
            password (str): 密码
            
        Returns:
            dict: 登录响应
        """
        url = f"{self.base_url}/api/auth/login"
        data = {
            "username": username,
            "password": password
        }
        
        try:
            response = requests.post(url, json=data)
            result = response.json()
            
            if response.status_code == 200:
                self.token = result["access_token"]
                print(f"✓ 登录成功！Token: {self.token[:50]}...")
            else:
                print(f"✗ 登录失败: {result}")
        except requests.exceptions.ConnectionError:
            print(f"✗ 连接失败：无法连接到服务器 {self.base_url}")
            return None
        except Exception as e:
            print(f"✗ 登录发生错误: {str(e)}")
            return None
        
        return result
    
    def create_session(self):
        """
        创建新会话
        
        Returns:
            dict: 会话创建响应
        """
        url = f"{self.base_url}/api/session/create"
        
        try:
            response = requests.post(url, headers=self._get_headers())
            result = response.json()
            
            if response.status_code == 200:
                self.session_id = result["session_id"]
                print(f"✓ 会话创建成功！Session ID: {self.session_id}")
            else:
                print(f"✗ 会话创建失败: {result}")
        except requests.exceptions.ConnectionError:
            print(f"✗ 连接失败：无法连接到服务器 {self.base_url}")
            return None
        except Exception as e:
            print(f"✗ 会话创建发生错误: {str(e)}")
            return None
        
        return result
    
    def upload_file(self, file_path: str):
        """
        上传文件
        
        Args:
            file_path (str): 文件路径
            
        Returns:
            dict: 上传响应
        """
        url = f"{self.base_url}/api/files/upload"
        
        file_path_obj = Path(file_path)
        files = {
            "files": (file_path_obj.name, open(file_path, "rb"))
        }
        
        response = requests.post(url, files=files, headers=self._get_headers(include_content_type=False))
        result = response.json()
        
        if response.status_code == 200:
            print(f"✓ 文件上传成功！{result}")
        else:
            print(f"✗ 文件上传失败: {result}")
        
        return result
    
    def list_files(self):
        """
        列出所有文件
        
        Returns:
            dict: 文件列表响应
        """
        url = f"{self.base_url}/api/files/list"
        
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if response.status_code == 200:
            print(f"✓ 文件列表获取成功！共 {result['count']} 个文件")
            for file_info in result["files"]:
                print(f"  - {file_info['filename']} ({file_info['uuid']})")
        else:
            print(f"✗ 文件列表获取失败: {result}")
        
        return result
    
    def download_file(self, file_uuid: str, save_path: str):
        """
        下载文件
        
        Args:
            file_uuid (str): 文件 UUID
            save_path (str): 保存路径
            
        Returns:
            bool: 下载是否成功
        """
        url = f"{self.base_url}/api/files/download/{file_uuid}"
        
        response = requests.get(url, headers=self._get_headers())
        
        if response.status_code == 200:
            with open(save_path, "wb") as f:
                f.write(response.content)
            print(f"✓ 文件下载成功！保存到: {save_path}")
            return True
        else:
            print(f"✗ 文件下载失败: {response.status_code}")
            return False
    
    def get_file_info(self, file_uuid: str):
        """
        获取文件信息
        
        Args:
            file_uuid (str): 文件 UUID
            
        Returns:
            dict: 文件信息响应
        """
        url = f"{self.base_url}/api/files/info/{file_uuid}"
        
        response = requests.get(url, headers=self._get_headers())
        result = response.json()
        
        if response.status_code == 200:
            print(f"✓ 文件信息获取成功！")
            print(f"  - 文件名: {result['filename']}")
            print(f"  - 大小: {result['size']} 字节")
        else:
            print(f"✗ 文件信息获取失败: {result}")
        
        return result
    
    def delete_file(self, file_uuid: str):
        """
        删除文件
        
        Args:
            file_uuid (str): 文件 UUID
            
        Returns:
            dict: 删除响应
        """
        url = f"{self.base_url}/api/files/delete"
        data = {
            "uuids": [file_uuid]
        }
        
        response = requests.delete(url, json=data, headers=self._get_headers())
        result = response.json()
        
        if response.status_code == 200:
            print(f"✓ 文件删除成功！{result}")
        else:
            print(f"✗ 文件删除失败: {result}")
        
        return result
    
    def delete_session(self):
        """
        删除会话
        
        Returns:
            dict: 删除响应
        """
        url = f"{self.base_url}/api/session/delete/{self.session_id}"
        
        response = requests.delete(url, headers=self._get_headers())
        result = response.json()
        
        if response.status_code == 200:
            print(f"✓ 会话删除成功！")
            self.session_id = None
        else:
            print(f"✗ 会话删除失败: {result}")
        
        return result


def run_full_test():
    """
    运行完整的 API 测试流程
    """
    print("=" * 60)
    print("API 完整测试流程")
    print("=" * 60)
    
    tester = APITester()
    
    # 1. 登录
    print("\n[1/8] 登录获取 Token...")
    login_result = tester.login()
    if not tester.token:
        print("\n✗ 登录失败，无法继续测试")
        return
    
    # 2. 创建会话
    print("\n[2/8] 创建会话...")
    session_result = tester.create_session()
    if not tester.session_id:
        print("\n✗ 会话创建失败，无法继续测试")
        return
    
    # 3. 上传文件
    print("\n[3/8] 上传测试文件...")
    test_file = Path(__file__).parent / "test_import.py"
    if test_file.exists():
        upload_result = tester.upload_file(str(test_file))
        if upload_result and "fileids" in upload_result and len(upload_result["fileids"]) > 0:
            file_uuid = upload_result["fileids"][0]["id"]
            
            # 4. 列出文件
            print("\n[4/8] 列出文件...")
            tester.list_files()
            
            # 5. 获取文件信息
            print("\n[5/8] 获取文件信息...")
            tester.get_file_info(file_uuid)
            
            # 6. 下载文件
            print("\n[6/8] 下载文件...")
            download_path = Path(__file__).parent / "downloaded_test.py"
            tester.download_file(file_uuid, str(download_path))
            
            # 7. 删除文件
            print("\n[7/8] 删除文件...")
            tester.delete_file(file_uuid)
        else:
            print("✗ 上传失败，跳过后续测试")
    else:
        print(f"✗ 测试文件不存在: {test_file}")
    
    # 8. 删除会话
    print("\n[8/8] 删除会话...")
    tester.delete_session()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


def run_quick_test():
    """
    运行快速测试（只测试登录和创建会话）
    """
    print("=" * 60)
    print("API 快速测试")
    print("=" * 60)
    
    tester = APITester()
    
    # 1. 登录
    print("\n[1/2] 登录获取 Token...")
    login_result = tester.login()
    if not tester.token:
        print("\n✗ 登录失败，无法继续测试")
        return
    
    # 2. 创建会话
    print("\n[2/2] 创建会话...")
    session_result = tester.create_session()
    if not tester.session_id:
        print("\n✗ 会话创建失败")
        return
    
    print("\n" + "=" * 60)
    print("快速测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    print("\n选择测试模式：")
    print("1. 完整测试（登录、会话、文件操作）")
    print("2. 快速测试（只测试登录和创建会话）")
    
    choice = input("\n请输入选择 (1/2): ").strip()
    
    if choice == "1":
        run_full_test()
    elif choice == "2":
        run_quick_test()
    else:
        print("无效的选择！")
