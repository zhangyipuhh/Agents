#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
综合测试页面 Python 脚本

本模块提供命令行交互界面，用于集成测试 MainServer.py 中 contract_router 定义的所有 API 接口。
主要功能包括：
- 接口集成测试：封装 contract_router 的所有接口调用
- 循环操作选择：用户可选择继续交流、上传文件、解析文件、审批、退出
- 文件上传功能：支持多文件上传和文件类型验证
- 文件解析功能：支持 txt、csv、json 等格式的解析
- 审批流程：提供审批入口，审批逻辑由智能体处理

Date: 2026-03-19
Author: 张镒谱
"""

import os
import sys
import json
import csv
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any
from pathlib import Path

import requests
from requests.exceptions import RequestException


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class APIClient:
    """
    API 客户端类
    
    封装 contract_router 的所有接口调用方法。
    """
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化 API 客户端
        
        Args:
            base_url: API 基础 URL
        """
        self.base_url = base_url
        self.token: Optional[str] = None
        self.session_id: Optional[str] = None
        self.headers: Dict[str, str] = {}
    
    def set_auth(self, token: str, session_id: str) -> None:
        """
        设置认证信息
        
        Args:
            token: JWT 认证令牌
            session_id: 会话 ID
        """
        self.token = token
        self.session_id = session_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Session-ID": session_id
        }
    
    def refresh_token(self) -> Optional[str]:
        """
        重新登录获取新的 token
        
        Returns:
            新的 token，如果失败返回 None
        """
        try:
            login_result = requests.post(
                f"{self.base_url}/api/auth/login",
                json={"username": "admin", "password": "123456"}
            )
            login_result.raise_for_status()
            token = login_result.json().get("access_token")
            if token:
                self.token = token
                logger.info("Token 刷新成功")
            return token
        except Exception as e:
            logger.error(f"Token 刷新失败: {e}")
            return None
    
    def create_session(self) -> Optional[str]:
        """
        创建新会话
        
        Returns:
            新的 session_id，如果失败返回 None
        """
        if not self.token:
            self.refresh_token()
        
        if not self.token:
            logger.error("无法创建会话：token 为空")
            return None
        
        try:
            session_result = requests.post(
                f"{self.base_url}/api/session/create",
                headers={"Authorization": f"Bearer {self.token}"}
            )
            session_result.raise_for_status()
            session_id = session_result.json().get("session_id")
            if session_id:
                self.session_id = session_id
                # 更新 headers 中的 X-Session-ID
                if self.token:
                    self.headers = {
                        "Authorization": f"Bearer {self.token}",
                        "X-Session-ID": session_id
                    }
                logger.info(f"会话创建成功: {session_id}")
            return session_id
        except Exception as e:
            logger.error(f"会话创建失败: {e}")
            return None
    
    def _get_auth_headers(self, session_id: Optional[str] = None) -> Dict[str, str]:
        """
        获取认证请求头，每次都会刷新 token
        
        Args:
            session_id: 可选的会话 ID，如果不提供则使用 self.session_id
            
        Returns:
            包含最新 token 的请求头字典
        """
        self.refresh_token()
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Session-ID"] = session_id or self.session_id or ""
        return headers
    
    def _request(
        self, 
        method: str, 
        endpoint: str, 
        **kwargs
    ) -> Dict[str, Any]:
        """
        发送 HTTP 请求
        
        Args:
            method: HTTP 方法（GET、POST、DELETE 等）
            endpoint: API 端点路径
            **kwargs: 传递给 requests 的其他参数
            
        Returns:
            响应 JSON 数据
            
        Raises:
            RequestException: 请求失败时抛出
        """
        url = f"{self.base_url}{endpoint}"
        # 先使用 self.headers 作为基础，然后用传入的 headers 覆盖
        headers = dict(self.headers)
        headers.update(kwargs.pop('headers', {}))
        
        try:
            response = requests.request(
                method=method,
                url=url,
                headers=headers,
                **kwargs
            )
            response.raise_for_status()
            return response.json()
        except RequestException as e:
            logger.error(f"请求失败: {method} {url}, 错误: {e}")
            # 尝试获取服务器返回的错误详情
            if hasattr(e, 'response') and e.response is not None:
                try:
                    error_detail = e.response.text
                    logger.error(f"服务器错误详情: {error_detail}")
                except:
                    pass
            raise
    
    def upload_contract_files(
        self, 
        files: List[str]
    ) -> Dict[str, Any]:
        """
        上传合同文件
        
        Args:
            files: 文件路径列表
            
        Returns:
            上传结果，包含 fileids、count、image_groups
        """
        files_data = []
        for file_path in files:
            if os.path.exists(file_path):
                files_data.append(
                    ('files', (os.path.basename(file_path), open(file_path, 'rb')))
                )
            else:
                logger.warning(f"文件不存在: {file_path}")
        
        if not files_data:
            return {"fileids": [], "count": 0, "image_groups": []}
        
        try:
            headers = self._get_auth_headers()
            result = self._request(
                "POST",
                "/api/contract/uploadfile",
                files=files_data,
                headers=headers
            )
            return result
        finally:
            for _, file_tuple in files_data:
                file_tuple[1].close()
    
    def chat(
        self, 
        message: str, 
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        合同审批聊天接口
        
        Args:
            message: 用户消息
            session_id: 可选的会话 ID
            
        Returns:
            聊天响应，包含 response、session_id
        """
        data = {"message": message}
        if session_id:
            data["session_id"] = session_id
        
        headers = self._get_auth_headers()
        
        logger.info(f"chat 请求数据: {data}")
        logger.info(f"chat 请求头: {headers}")
        
        return self._request(
            "POST",
            "/api/contract/chat",
            json=data,
            headers=headers
        )
    
    def doc_chat(
        self, 
        message: str, 
        session_id: Optional[str] = None,
        host_session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        文档处理聊天接口
        
        Args:
            message: 用户消息
            session_id: 可选的会话 ID
            host_session_id: 可选的发起会话 ID
            
        Returns:
            文档聊天响应，包含 response、session_id、host_session_id
        """
        data = {"message": message}
        if host_session_id:
            data["host_session_id"] = host_session_id
        
        headers = self._get_auth_headers(session_id=session_id)
        
        logger.info(f"doc_chat 请求数据: {data}")
        logger.info(f"doc_chat 请求头: {headers}")
        
        return self._request(
            "POST",
            "/api/contract/doc_chat",
            json=data,
            headers=headers
        )
    
    def get_store_value(
        self, 
        id: str, 
        session_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        获取 store 中存储的值
        
        Args:
            id: 存储 ID
            session_id: 可选的会话 ID
            
        Returns:
            存储值响应，包含 value、id
        """
        data = {"id": id}
        if session_id:
            data["session_id"] = session_id
        
        headers = self._get_auth_headers(session_id=session_id)
        
        return self._request(
            "POST",
            "/api/contract/store/value",
            json=data,
            headers=headers
        )


class FileUploader:
    """
    文件上传功能模块
    
    提供独立的文件上传方法，支持多文件上传和文件类型验证。
    """
    
    ALLOWED_EXTENSIONS = {'.txt', '.csv', '.json', '.pdf', '.doc', '.docx', '.jpg', '.jpeg', '.png', '.gif'}
    
    def __init__(self, api_client: APIClient):
        """
        初始化文件上传器
        
        Args:
            api_client: API 客户端实例
        """
        self.api_client = api_client
        self.uploaded_files: List[Dict[str, Any]] = []
    
    def validate_file(self, file_path: str) -> bool:
        """
        验证文件类型
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件类型是否有效
        """
        ext = Path(file_path).suffix.lower()
        if ext not in self.ALLOWED_EXTENSIONS:
            logger.warning(f"不支持的文件类型: {ext}")
            return False
        return True
    
    def upload_files(
        self, 
        file_paths: List[str]
    ) -> Dict[str, Any]:
        """
        上传多个文件
        
        Args:
            file_paths: 文件路径列表
            
        Returns:
            上传结果
        """
        valid_files = []
        invalid_files = []
        
        for file_path in file_paths:
            if self.validate_file(file_path):
                valid_files.append(file_path)
            else:
                invalid_files.append(file_path)
        
        if invalid_files:
            print(f"以下文件类型不支持，已跳过: {', '.join(invalid_files)}")
        
        if not valid_files:
            print("没有有效的文件可上传")
            return {"fileids": [], "count": 0, "image_groups": []}
        
        print(f"正在上传 {len(valid_files)} 个文件...")
        
        try:
            result = self.api_client.upload_contract_files(valid_files)
            
            if result.get("fileids"):
                self.uploaded_files.extend(result["fileids"])
                print(f"上传成功！共上传 {result['count']} 个文件")
                for file_info in result["fileids"]:
                    print(f"  - ID: {file_info['id']}, 类型: {file_info['file_type']}")
            
            if result.get("image_groups"):
                print(f"图片转换完成: {len(result['image_groups'])} 组")
            
            self._process_doc_files(result)
            
            return result
        except Exception as e:
            print(f"上传失败: {e}")
            raise
    
    def get_uploaded_files(self) -> List[Dict[str, Any]]:
        """
        获取已上传文件列表
        
        Returns:
            已上传文件列表
        """
        return self.uploaded_files
    
    def clear_uploaded_files(self) -> None:
        """
        清空已上传文件列表
        """
        self.uploaded_files = []
        print("已清空上传文件列表")
    
    def _process_doc_files(self, upload_result: Dict[str, Any]) -> None:
        """
        处理 doc 类型的文件，自动调用 doc_chat 和 get_store_value
        
        Args:
            upload_result: 上传结果，包含 fileids、count、image_groups
        """
        fileids = upload_result.get("fileids", [])
        
        if not fileids:
            return
        
        host_session_id = self.api_client.session_id
        
        if not host_session_id:
            logger.warning("未找到主会话 ID，跳过 doc 文件自动处理")
            return
        
        if not self.api_client.token:
            logger.warning("未找到认证 token，跳过 doc 文件自动处理")
            return
        
        for file_info in fileids:
            file_id = file_info.get("id")
            file_type = file_info.get("file_type")
            
            if file_type != "doc":
                logger.info(f"跳过非文档文件 {file_id}，类型: {file_type}")
                continue
            
            if not file_id:
                logger.info(f"跳过无 ID 的文档文件 {file_id}")
                continue
            
            try:
                doc_session_id = self.api_client.create_session()
                
                if not doc_session_id:
                    logger.error(f"为文档 {file_id} 创建会话失败")
                    continue
                
                logger.info(f"\n正在处理文档文件 (ID: {file_id})...")
                logger.info(f"文档会话 ID: {doc_session_id}")
                
                message = f"识别文档类型并切分全部文档 ，file_id是{file_id}"
                
                doc_chat_result = self.api_client.doc_chat(
                    message=message,
                    session_id=doc_session_id,
                    host_session_id=host_session_id
                )
                
                doc_chat_response = doc_chat_result.get("response", "无响应")
                
                store_result = self.api_client.get_store_value(
                    id=file_id,
                    session_id=doc_session_id
                )
                
                store_value = store_result.get("value")
                
                logger.info(f"\n文档识别完成！")
                logger.info(f"文件 ID: {file_id}")
                logger.info(f"处理结果: {doc_chat_response}")
                logger.info(f"存储值: {store_value}")
                
                if isinstance(store_value, list):
                    self._process_doc_content_list(
                        store_value, 
                        doc_session_id, 
                        host_session_id, 
                        file_id
                    )
                else:
                    logger.info(f"存储值类型不支持循环处理: {type(store_value)}")
                
            except Exception as e:
                logger.error(f"处理文档文件 {file_id} 失败: {e}")
    
    def _process_doc_content_list(
        self, 
        content_list: List[Dict[str, Any]], 
        doc_session_id: str, 
        host_session_id: str,
        file_id: str
    ) -> None:
        """
        处理文档内容列表，循环调用 doc_chat 接口
        
        Args:
            content_list: 文档内容列表，格式 [{'index': 1, 'name': '供地合同', 'content': '...'}, ...]
            doc_session_id: 文档会话 ID
            host_session_id: 主会话 ID
            file_id: 文件 ID
        """
        logger.info(f"\n开始处理文档内容列表，共 {len(content_list)} 条...")
        
        for item in content_list:
            index = item.get("index")
            name = item.get("name", "未知文档")
            content = item.get("content", "")
            
            message = f"{name}信息提取，内容{content}"
            
            logger.info(f"处理第 {index} 条: {name}")
            
            try:
                doc_chat_result = self.api_client.doc_chat(
                    message=message,
                    session_id=doc_session_id,
                    host_session_id=host_session_id
                )
                
                doc_chat_response = doc_chat_result.get("response", "无响应")
                logger.debug(f"处理结果: {doc_chat_response}")
                
            except Exception as e:
                logger.error(f"处理第 {index} 条失败: {e}")
        
        logger.info(f"\n文档内容列表处理完成！文件 ID: {file_id}")


class FileParser:
    """
    文件解析功能模块
    
    支持常见文件格式的解析（txt、csv、json 等）。
    """
    
    def __init__(self):
        """
        初始化文件解析器
        """
        self.parsers = {
            '.txt': self._parse_txt,
            '.csv': self._parse_csv,
            '.json': self._parse_json,
        }
    
    def parse_file(self, file_path: str) -> Dict[str, Any]:
        """
        解析文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            解析结果，包含 content、type、preview
        """
        ext = Path(file_path).suffix.lower()
        
        if ext not in self.parsers:
            return {
                "success": False,
                "error": f"不支持的文件类型: {ext}",
                "content": None,
                "type": ext
            }
        
        try:
            content = self.parsers[ext](file_path)
            preview = self._generate_preview(content, ext)
            
            return {
                "success": True,
                "content": content,
                "type": ext,
                "preview": preview
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e),
                "content": None,
                "type": ext
            }
    
    def _parse_txt(self, file_path: str) -> str:
        """
        解析 txt 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            文件内容
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    
    def _parse_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """
        解析 csv 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            CSV 数据列表
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            return list(reader)
    
    def _parse_json(self, file_path: str) -> Any:
        """
        解析 json 文件
        
        Args:
            file_path: 文件路径
            
        Returns:
            JSON 数据
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def _generate_preview(
        self, 
        content: Any, 
        file_type: str
    ) -> str:
        """
        生成预览内容
        
        Args:
            content: 文件内容
            file_type: 文件类型
            
        Returns:
            预览字符串
        """
        if file_type == '.txt':
            lines = content.split('\n')[:10]
            preview = '\n'.join(lines)
            if len(content.split('\n')) > 10:
                preview += '\n... (更多内容省略)'
            return preview
        
        elif file_type == '.csv':
            if isinstance(content, list) and len(content) > 0:
                preview_lines = []
                for i, row in enumerate(content[:5]):
                    preview_lines.append(f"行 {i+1}: {row}")
                if len(content) > 5:
                    preview_lines.append(f"... (共 {len(content)} 行)")
                return '\n'.join(preview_lines)
            return "空文件"
        
        elif file_type == '.json':
            preview = json.dumps(content, ensure_ascii=False, indent=2)
            lines = preview.split('\n')[:20]
            if len(preview.split('\n')) > 20:
                lines.append('... (更多内容省略)')
            return '\n'.join(lines)
        
        return str(content)[:500]
    
    def display_parse_result(
        self, 
        result: Dict[str, Any]
    ) -> None:
        """
        显示解析结果
        
        Args:
            result: 解析结果
        """
        if not result["success"]:
            print(f"解析失败: {result.get('error', '未知错误')}")
            return
        
        print(f"\n文件类型: {result['type']}")
        print(f"解析成功！")
        print("\n预览内容:")
        print("-" * 50)
        print(result["preview"])
        print("-" * 50)


class ApprovalHandler:
    """
    审批流程功能模块
    
    提供审批入口，审批逻辑由智能体处理。
    """
    
    def __init__(self, api_client: APIClient):
        """
        初始化审批处理器
        
        Args:
            api_client: API 客户端实例
        """
        self.api_client = api_client
    
    def submit_approval(
        self, 
        approval_data: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        """
        提交审批（空方法定义，仅包含方法签名）
        
        Args:
            approval_data: 审批数据
            
        Returns:
            审批结果
        """
        pass
    
    def execute_approval(self) -> Dict[str, Any]:
        """
        执行审批流程
        
        通过调用智能体进行审批处理。
        
        Returns:
            审批结果
        """
        print("\n正在执行审批流程...")
        print("调用智能体进行审批处理...")
        
        try:
            result = self.api_client.chat("请执行审批流程")
            
            print("\n审批结果:")
            print("-" * 50)
            print(result.get("response", "无响应"))
            print("-" * 50)
            
            return result
        except Exception as e:
            print(f"审批失败: {e}")
            raise


class ChatHistory:
    """
    聊天历史记录管理
    
    保存完整的聊天历史记录并支持查看。
    """
    
    def __init__(self):
        """
        初始化聊天历史
        """
        self.history: List[Dict[str, Any]] = []
    
    def add_message(
        self, 
        role: str, 
        content: str, 
        timestamp: Optional[str] = None
    ) -> None:
        """
        添加消息到历史记录
        
        Args:
            role: 角色（user 或 assistant）
            content: 消息内容
            timestamp: 时间戳
        """
        self.history.append({
            "role": role,
            "content": content,
            "timestamp": timestamp or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        })
    
    def get_history(self) -> List[Dict[str, Any]]:
        """
        获取聊天历史
        
        Returns:
            聊天历史列表
        """
        return self.history
    
    def display_history(self) -> None:
        """
        显示聊天历史
        """
        if not self.history:
            print("暂无聊天历史")
            return
        
        print("\n" + "=" * 50)
        print("聊天历史记录")
        print("=" * 50)
        
        for msg in self.history:
            role_name = "用户" if msg["role"] == "user" else "智能体"
            print(f"\n[{msg['timestamp']}] {role_name}:")
            print(msg["content"])
        
        print("\n" + "=" * 50)
    
    def clear_history(self) -> None:
        """
        清空聊天历史
        """
        self.history = []
        print("聊天历史已清空")


class HTTestPage:
    """
    综合测试页面主类
    
    提供命令行交互界面，整合所有功能模块。
    """
    
    MENU_OPTIONS = {
        "1": "继续交流",
        "2": "上传文件",
        "3": "解析文件",
        "4": "审批",
        "5": "查看聊天历史",
        "0": "退出"
    }
    
    def __init__(self, base_url: str = "http://localhost:8000"):
        """
        初始化测试页面
        
        Args:
            base_url: API 基础 URL
        """
        self.api_client = APIClient(base_url)
        self.file_uploader = FileUploader(self.api_client)
        self.file_parser = FileParser()
        self.approval_handler = ApprovalHandler(self.api_client)
        self.chat_history = ChatHistory()
        self.is_running = True
        self.cycle_count = 0
    
    def display_header(self) -> None:
        """
        显示页面头部信息
        """
        logger.info("\n" + "=" * 60)
        logger.info("        合同审批综合测试页面")
        logger.info("=" * 60)
        logger.info(f"当前循环: 第 {self.cycle_count} 轮")
        if self.api_client.session_id:
            logger.info(f"会话 ID: {self.api_client.session_id}")
        logger.info("=" * 60)
    
    def display_menu(self) -> None:
        """
        显示操作菜单
        """
        logger.info("\n请选择下一步操作:")
        for key, value in self.MENU_OPTIONS.items():
            print(f"  {key}. {value}")
    
    def get_user_choice(self) -> str:
        """
        获取用户选择
        
        Returns:
            用户输入的选项
        """
        while True:
            choice = input("\n请输入选项编号: ").strip()
            if choice in self.MENU_OPTIONS:
                return choice
            logger.info("无效选项，请重新输入")
    
    def handle_chat(self) -> None:
        """
        处理继续交流功能
        """
        logger.info("\n进入聊天模式 (输入 'back' 返回主菜单)")
        logger.info("-" * 50)
        
        while True:
            message = input("\n请输入消息: ").strip()
            
            if message.lower() == 'back':
                break
            
            if not message:
                continue
            
            try:
                self.chat_history.add_message("user", message)
                
                logger.info("\n智能体正在思考...")
                result = self.api_client.chat(message)
                
                response = result.get("response", "无响应")
                self.chat_history.add_message("assistant", response)
                
                logger.info(f"\n智能体: {response}")
                
            except Exception as e:
                logger.error(f"\n发送失败: {e}")
    
    def handle_upload(self) -> None:
        """
        处理文件上传功能
        """
        logger.info("\n文件上传")
        logger.info("-" * 50)
        logger.info("支持的文件类型: txt, csv, json, pdf, doc, docx, jpg, jpeg, png, gif")
        logger.info("输入文件路径，多个文件用逗号分隔")
        logger.info("输入 'back' 返回主菜单")
        
        while True:
            file_input = input("\n请输入文件路径: ").strip()
            
            if file_input.lower() == 'back':
                break
            
            if not file_input:
                continue
            
            file_paths = [f.strip() for f in file_input.split(',')]
            
            try:
                self.file_uploader.upload_files(file_paths)
            except Exception as e:
                logger.error(f"上传出错: {e}")
    
    def handle_parse(self) -> None:
        """
        处理文件解析功能
        """
        logger.info("\n文件解析")
        logger.info("-" * 50)
        logger.info("支持的文件类型: txt, csv, json")
        logger.info("输入 'back' 返回主菜单")
        
        while True:
            file_path = input("\n请输入文件路径: ").strip()
            
            if file_path.lower() == 'back':
                break
            
            if not file_path:
                continue
            
            if not os.path.exists(file_path):
                print(f"文件不存在: {file_path}")
                continue
            
            result = self.file_parser.parse_file(file_path)
            self.file_parser.display_parse_result(result)
    
    def handle_approval(self) -> None:
        """
        处理审批功能
        """
        logger.info("\n审批流程")
        logger.info("-" * 50)
        
        try:
            self.approval_handler.execute_approval()
        except Exception as e:
            logger.error(f"审批出错: {e}")
    
    def handle_history(self) -> None:
        """
        处理查看聊天历史功能
        """
        self.chat_history.display_history()
    
    def run(self) -> None:
        """
        运行测试页面主循环
        """
        logger.info("\n正在初始化...")
        
        if not self._initialize():
            logger.error("初始化失败，请检查服务器连接")
            return
        
        while self.is_running:
            self.cycle_count += 1
            self.display_header()
            self.display_menu()
            
            choice = self.get_user_choice()
            
            if choice == "0":
                self.is_running = False
                logger.info("\n感谢使用，再见！")
            elif choice == "1":
                self.handle_chat()
            elif choice == "2":
                self.handle_upload()
            elif choice == "3":
                self.handle_parse()
            elif choice == "4":
                self.handle_approval()
            elif choice == "5":
                self.handle_history()
    
    def _initialize(self) -> bool:
        """
        初始化连接
        
        Returns:
            初始化是否成功
        """
        try:
            print("正在连接服务器...")
            
            login_result = requests.post(
                f"{self.api_client.base_url}/api/auth/login",
                json={"username": "admin", "password": "123456"}
            )
            login_result.raise_for_status()
            token = login_result.json().get("access_token")
            
            if not token:
                logger.error("登录失败：未获取到令牌")
                return False
            
            logger.info("登录成功")
            
            session_result = requests.post(
                f"{self.api_client.base_url}/api/session/create",
                headers={"Authorization": f"Bearer {token}"}
            )
            session_result.raise_for_status()
            session_id = session_result.json().get("session_id")
            
            if not session_id:
                logger.error("创建会话失败：未获取到会话 ID")
                return False
            
            logger.info(f"会话创建成功: {session_id}")
            
            self.api_client.set_auth(token, session_id)
            
            return True
            
        except Exception as e:
            logger.error(f"初始化失败: {e}")
            return False


def main():
    """
    主函数入口
    """
    base_url = os.environ.get("API_BASE_URL", "http://localhost:8000")
    
    test_page = HTTestPage(base_url)
    test_page.run()


if __name__ == "__main__":
    main()
