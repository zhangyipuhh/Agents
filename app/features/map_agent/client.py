#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
地图智能体客户端

本模块提供命令行交互界面，用于与地图智能体进行流式对话。
主要功能包括：
- 流式聊天对话：使用 SSE 协议实时接收智能体响应
- 颜色输出区分：工具调用(红色)、模型回复(白色)、节点更新(蓝色)
- Markdown 渲染：支持渲染 Markdown 格式的文本
- 会话管理：支持多轮对话和会话状态保持

Date: 2026-04-14
Author: AI Assistant
"""

import os
import sys
import json
import ast
import re
import logging
import argparse
from datetime import datetime
from typing import Optional, Dict, Any, Generator, List
from pathlib import Path

import requests
from requests.exceptions import RequestException

try:
    from rich.console import Console
    from rich.markdown import Markdown
    from rich.panel import Panel
    from rich.style import Style
    from rich.text import Text
    RICH_AVAILABLE = True
except ImportError:
    RICH_AVAILABLE = False

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)


class ColorPrinter:
    """
    颜色输出工具类

    使用 ANSI 转义码或 Rich 库实现终端彩色输出和 Markdown 渲染。
    """

    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BLACK = '\033[30m'
    RESET = '\033[0m'
    BOLD = '\033[1m'
    BG_RED = '\033[41m'
    BG_BLUE = '\033[44m'

    def __init__(self):
        if RICH_AVAILABLE:
            self.console = Console()
        else:
            self.console = None

    @classmethod
    def _enable_windows_ansi(cls):
        if sys.platform == 'win32':
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)

    def print_tool(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="bold red", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BOLD}{self.RED}{text}{self.RESET}", end=end, flush=True)

    def print_model(self, text: str, end: str = ''):
        if self.console:
            self.console.print(text, style="bold white", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BOLD}{text}{self.RESET}", end=end, flush=True)

    def print_model_markdown(self, text: str):
        if '\n' in text:
            if hasattr(self, '_md_buffer') and self._md_buffer:
                buffer = self._md_buffer + text
                self._md_buffer = ""
                if self.console:
                    md = Markdown(buffer)
                    self.console.print(md)
                else:
                    self._enable_windows_ansi()
                    print(f"{self.BOLD}{buffer}{self.RESET}")
            else:
                if self.console:
                    md = Markdown(text)
                    self.console.print(md)
                else:
                    self._enable_windows_ansi()
                    print(f"{self.BOLD}{text}{self.RESET}")
        else:
            if not hasattr(self, '_md_buffer'):
                self._md_buffer = ""
            self._md_buffer += text

    def print_node(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="bold cyan", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BOLD}{self.CYAN}{text}{self.RESET}", end=end, flush=True)

    def print_error(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="bold red on white", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BG_WHITE}{self.BOLD}{self.RED}{text}{self.RESET}", end=end, flush=True)

    def print_info(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="bold green", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BOLD}{self.GREEN}{text}{self.RESET}", end=end, flush=True)

    def print_custom(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="bold magenta", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.BOLD}{self.MAGENTA}{text}{self.RESET}", end=end, flush=True)

    def print_thinking(self, text: str, end: str = '\n'):
        if self.console:
            self.console.print(text, style="dim italic yellow", end=end)
        else:
            self._enable_windows_ansi()
            print(f"{self.YELLOW}{text}{self.RESET}", end=end, flush=True)

    def print_panel(self, text: str, title: str = "", style: str = "blue"):
        if self.console:
            self.console.print(Panel(text, title=title, border_style=style))
        else:
            self._enable_windows_ansi()
            print(f"\n{'='*50}")
            if title:
                print(f"[{title}]")
            print(text)
            print('='*50)


class ContentParser:
    """
    内容解析器

    解析模型回复中的复杂 JSON 格式数据，支持 Python 字典格式。
    """

    @staticmethod
    def parse_content(content) -> Dict[str, Any]:
        result = {
            "thinking": [],
            "text": [],
            "raw": content
        }

        if not content:
            return result

        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type == "thinking":
                        thinking_text = item.get("thinking", "")
                        if thinking_text:
                            result["thinking"].append(thinking_text)
                    elif item_type == "text":
                        text_content = item.get("text", "")
                        if text_content:
                            result["text"].append(text_content)
                elif isinstance(item, str):
                    result["text"].append(item)
            return result

        if not isinstance(content, str):
            content = str(content)

        parsed = None

        try:
            parsed = json.loads(content)
        except (json.JSONDecodeError, TypeError):
            try:
                parsed = ast.literal_eval(content)
            except (ValueError, SyntaxError):
                pass

        if parsed is not None and isinstance(parsed, list):
            for item in parsed:
                if isinstance(item, dict):
                    item_type = item.get("type", "")
                    if item_type == "thinking":
                        thinking_text = item.get("thinking", "")
                        if thinking_text:
                            result["thinking"].append(thinking_text)
                    elif item_type == "text":
                        text_content = item.get("text", "")
                        if text_content:
                            result["text"].append(text_content)
            return result

        thinking_matches = re.findall(r"\{'thinking':\s*'([^']*(?:\\'[^']*)*)'", content)
        for match in thinking_matches:
            result["thinking"].append(match.replace("\\'", "'").replace("\\n", "\n"))

        text_matches = re.findall(r"\{'text':\s*'([^']*(?:\\'[^']*)*)'", content)
        for match in text_matches:
            result["text"].append(match.replace("\\'", "'").replace("\\n", "\n"))

        if result["thinking"] or result["text"]:
            return result

        result["text"].append(content)
        return result

    @staticmethod
    def extract_text_from_chunks(content: str) -> str:
        if not content:
            return ""

        text_parts = []

        try:
            parsed = ast.literal_eval(content)
            if isinstance(parsed, list):
                for item in parsed:
                    if isinstance(item, dict) and item.get("type") == "text":
                        text_parts.append(item.get("text", ""))
                return "".join(text_parts)
        except (ValueError, SyntaxError):
            pass

        if content.startswith('[') and content.endswith(']'):
            try:
                pattern = r"\{'text':\s*'([^']*(?:\\'[^']*)*)'"
                matches = re.findall(pattern, content)
                if matches:
                    return ''.join(m.replace("\\'", "'").replace("\\n", "\n") for m in matches)
            except Exception:
                pass

        return content


class MapAgentClient:
    """
    地图智能体 API 客户端类

    封装地图智能体的所有接口调用方法，支持流式输出。
    """

    def __init__(self, base_url: str = "http://localhost:8000", username: str = "admin", password: str = "123456"):
        self.base_url = base_url
        self.username = username
        self.password = password
        self.token: Optional[str] = None
        self.session_id: Optional[str] = None
        self.headers: Dict[str, str] = {}
        
        self.session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=10,
            pool_maxsize=20,
            max_retries=3,
            pool_block=False
        )
        self.session.mount('http://', adapter)
        self.session.mount('https://', adapter)
        
        self.session.headers.update({
            'Connection': 'keep-alive',
            'Keep-Alive': 'timeout=600, max=100'
        })

    def set_auth(self, token: str, session_id: str) -> None:
        self.token = token
        self.session_id = session_id
        self.headers = {
            "Authorization": f"Bearer {token}",
            "X-Session-ID": session_id
        }

    def refresh_token(self) -> Optional[str]:
        try:
            login_result = self.session.post(
                f"{self.base_url}/api/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=600
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
        if not self.token:
            self.refresh_token()

        if not self.token:
            logger.error("无法创建会话：token 为空")
            return None

        try:
            session_result = self.session.post(
                f"{self.base_url}/api/session/create",
                headers={"Authorization": f"Bearer {self.token}"},
                timeout=600
            )
            session_result.raise_for_status()
            session_id = session_result.json().get("session_id")
            if session_id:
                self.session_id = session_id
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
        self.refresh_token()
        headers = {}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
            headers["X-Session-ID"] = session_id or self.session_id or ""
        return headers

    def chat_stream(
        self,
        message: str,
        session_id: Optional[str] = None
    ) -> Generator[Dict[str, Any], None, None]:
        data = {"message": message}
        if session_id:
            data["session_id"] = session_id

        headers = self._get_auth_headers(session_id=session_id)
        headers["Accept"] = "text/event-stream"
        headers["Cache-Control"] = "no-cache"

        url = f"{self.base_url}/api/map/chat"

        try:
            with self.session.post(
                url,
                json=data,
                headers=headers,
                stream=True,
                timeout=600
            ) as response:
                response.raise_for_status()

                buffer = ""
                for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                    if chunk:
                        buffer += chunk

                        while "\n\n" in buffer:
                            line, buffer = buffer.split("\n\n", 1)
                            line = line.strip()

                            if line.startswith("data: "):
                                json_str = line[6:]
                                try:
                                    parsed_data = json.loads(json_str)
                                    yield parsed_data
                                except json.JSONDecodeError as e:
                                    logger.error(f"JSON 解析错误: {e}, 数据: {json_str}")
                                    yield {"type": "error", "message": f"JSON 解析错误: {e}"}

        except RequestException as e:
            logger.error(f"请求失败: {e}")
            yield {"type": "error", "message": str(e)}


class StreamOutputHandler:
    """
    流式输出处理器

    处理不同类型的流式数据，并使用颜色区分输出。
    """

    def __init__(self):
        self.printer = ColorPrinter()
        self.parser = ContentParser()
        self.current_tool_name = None
        self.accumulated_text = ""
        self.accumulated_thinking = ""
        self.current_node = None

    def process_stream_data(self, data: Dict[str, Any]) -> None:
        data_type = data.get("type")

        if data_type == "update":
            self._handle_update(data.get("data", {}))

        elif data_type == "message":
            self._handle_message(data)

        elif data_type == "custom":
            self._handle_custom(data.get("data", {}))

        elif data_type == "end":
            self._handle_end(data)

        elif data_type == "error":
            self._handle_error(data)

        else:
            self._handle_unknown(data)

    def _handle_update(self, data: Dict[str, Any]) -> None:
        for node_name, node_data in data.items():
            if hasattr(self.printer, '_md_buffer') and self.printer._md_buffer:
                if self.printer.console:
                    md = Markdown(self.printer._md_buffer)
                    self.printer.console.print(md)
                else:
                    self.printer._enable_windows_ansi()
                    print(f"{self.BOLD}{self.printer._md_buffer}{self.RESET}")
                self.printer._md_buffer = ""
            self.current_node = node_name
            self.printer.print_node(f"\n[节点更新] {node_name}")

            if isinstance(node_data, dict):
                if "messages" in node_data:
                    messages = node_data["messages"]
                    if messages:
                        last_message = messages[-1] if isinstance(messages, list) else messages
                        if hasattr(last_message, 'content'):
                            content = last_message.content
                        elif isinstance(last_message, dict):
                            content = last_message.get('content', str(last_message))
                        else:
                            content = str(last_message)

                        if content and not self._is_tool_related(node_name):
                            parsed = self.parser.parse_content(str(content))
                            if parsed["text"]:
                                self.printer.print_node(f"  内容预览: {parsed['text'][0][:100]}...")

                if "tool_calls" in node_data:
                    tool_calls = node_data["tool_calls"]
                    for tool_call in tool_calls:
                        tool_name = tool_call.get("name", "未知工具")
                        tool_args = tool_call.get("args", {})
                        self.printer.print_tool(f"  [工具调用] {tool_name}")
                        args_str = json.dumps(tool_args, ensure_ascii=False, indent=4)
                        self.printer.print_tool(f"    参数:\n{self._indent_text(args_str, 6)}")

                if "tool_call_id" in node_data or "name" in node_data:
                    tool_name = node_data.get("name", "未知工具")
                    self.printer.print_tool(f"  [工具结果] {tool_name}")

    def _handle_message(self, data: Dict[str, Any]) -> None:
        content = data.get("content", "")

        if content:
            parsed = self.parser.parse_content(content)

            if parsed["thinking"]:
                for thinking in parsed["thinking"]:
                    self.accumulated_thinking += thinking

            if parsed["text"]:
                if self.accumulated_thinking:
                    if hasattr(self.printer, '_md_buffer') and self.printer._md_buffer:
                        if self.printer.console:
                            md = Markdown(self.printer._md_buffer)
                            self.printer.console.print(md)
                        else:
                            self.printer._enable_windows_ansi()
                            print(f"{self.BOLD}{self.printer._md_buffer}{self.RESET}")
                        self.printer._md_buffer = ""
                    print()
                    self.printer.print_thinking(f"[思考中...] {self.accumulated_thinking}")
                    print()
                    self.accumulated_thinking = ""

                for text in parsed["text"]:
                    self.accumulated_text += text
                    self.printer.print_model_markdown(text)

    def _handle_custom(self, data: Dict[str, Any]) -> None:
        if hasattr(self.printer, '_md_buffer') and self.printer._md_buffer:
            if self.printer.console:
                md = Markdown(self.printer._md_buffer)
                self.printer.console.print(md)
            else:
                self.printer._enable_windows_ansi()
                print(f"{self.BOLD}{self.printer._md_buffer}{self.RESET}")
            self.printer._md_buffer = ""
        self.printer.print_custom(f"\n[自定义数据]")
        data_str = json.dumps(data, ensure_ascii=False, indent=2)
        self.printer.print_custom(self._indent_text(data_str, 2))

    def _handle_end(self, data: Dict[str, Any]) -> None:
        if hasattr(self.printer, '_md_buffer') and self.printer._md_buffer:
            if self.printer.console:
                md = Markdown(self.printer._md_buffer)
                self.printer.console.print(md)
            else:
                self.printer._enable_windows_ansi()
                print(f"{self.BOLD}{self.printer._md_buffer}{self.RESET}")
            self.printer._md_buffer = ""
        print()
        self.printer.print_info(f"[会话结束] {data.get('message', '')}")
        self.is_first_token = True

    def _handle_error(self, data: Dict[str, Any]) -> None:
        self.printer.print_error(f"\n[错误] {data.get('message', '未知错误')}")

    def _handle_unknown(self, data: Dict[str, Any]) -> None:
        self.printer.print_info(f"\n[未知数据] {json.dumps(data, ensure_ascii=False)}")

    def _is_tool_related(self, node_name: str) -> bool:
        tool_keywords = ["tool", "action", "execute", "call"]
        return any(keyword in node_name.lower() for keyword in tool_keywords)

    def _indent_text(self, text: str, spaces: int) -> str:
        indent = " " * spaces
        return "\n".join(f"{indent}{line}" for line in text.split("\n"))

    def reset(self):
        self.current_tool_name = None
        self.accumulated_text = ""
        self.accumulated_thinking = ""
        self.current_node = None


class MapAgentChatClient:
    """
    地图智能体聊天客户端

    提供命令行交互界面，整合流式输出和颜色显示功能。
    """

    def __init__(self, base_url: str = "http://localhost:8002", username: str = "admin", password: str = "123456", session_id: Optional[str] = None):
        self.api_client = MapAgentClient(base_url, username, password)
        self.output_handler = StreamOutputHandler()
        self.printer = ColorPrinter()
        self.is_running = True
        self.chat_count = 0
        self.username = username
        self.password = password
        if session_id:
            self.api_client.session_id = session_id

    def display_header(self) -> None:
        print("\n" + "=" * 60)
        self.printer.print_info("        地图智能体流式聊天客户端")
        print("=" * 60)
        self.printer.print_info(f"当前对话: 第 {self.chat_count} 轮")
        if self.api_client.session_id:
            self.printer.print_info(f"会话 ID: {self.api_client.session_id}")
        print("=" * 60)
        self.printer.print_node("● 蓝色 - 节点更新")
        self.printer.print_tool("● 红色 - 工具调用")
        self.printer.print_model("● 白色 - 模型回复")
        self.printer.print_thinking("● 黄色 - 思考过程")
        print("=" * 60)

    def display_menu(self) -> None:
        print("\n请选择操作:")
        print("  1. 发送消息")
        print("  2. 查看帮助")
        print("  0. 退出")

    def handle_chat(self) -> None:
        print("\n进入聊天模式 (输入 'back' 返回主菜单)")
        print("-" * 50)

        while True:
            message = input("\n请输入消息: ").strip()

            if message.lower() == 'back':
                break

            if not message:
                continue

            try:
                self.chat_count += 1
                self.output_handler.reset()

                self.printer.print_info(f"\n[用户] {message}")
                self.printer.print_info("[智能体正在思考...]")

                for stream_data in self.api_client.chat_stream(message):
                    self.output_handler.process_stream_data(stream_data)

            except Exception as e:
                self.printer.print_error(f"\n发送失败: {e}")

    def handle_help(self) -> None:
        print("\n" + "=" * 60)
        self.printer.print_info("帮助信息")
        print("=" * 60)
        help_text = """
本客户端用于与地图智能体进行流式对话。

功能说明:
  - 流式输出: 实时显示智能体的响应过程
  - 颜色区分:
    * 蓝色 - 节点状态更新
    * 红色 - 工具调用信息
    * 白色 - 模型回复内容
    * 绿色 - 系统提示信息
    * 黄色 - 思考过程
    * 洋红色 - 自定义数据

支持的操作:
  - 定位地图到指定位置
  - 添加地图标记
  - 查询地理信息
  - 其他地图相关操作

示例对话:
  - "定位到北京"
  - "在地图上标记天安门"
  - "搜索附近的餐厅"
"""
        print(help_text)
        print("=" * 60)

    def run(self) -> None:
        print("\n正在初始化...")

        if not self._initialize():
            self.printer.print_error("初始化失败，请检查服务器连接")
            return

        while self.is_running:
            self.display_header()
            self.display_menu()

            choice = input("\n请输入选项编号: ").strip()

            if choice == "0":
                self.is_running = False
                self.printer.print_info("\n感谢使用，再见！")
            elif choice == "1":
                self.handle_chat()
            elif choice == "2":
                self.handle_help()
            else:
                self.printer.print_error("无效选项，请重新输入")

    def _initialize(self) -> bool:
        try:
            print("正在连接服务器...")

            login_result = self.api_client.session.post(
                f"{self.api_client.base_url}/api/auth/login",
                json={"username": self.username, "password": self.password},
                timeout=600
            )
            login_result.raise_for_status()
            token = login_result.json().get("access_token")

            if not token:
                self.printer.print_error("登录失败：未获取到令牌")
                return False

            self.printer.print_info("登录成功")

            # 如果已经指定了 session_id，则不再创建新会话
            if self.api_client.session_id:
                self.printer.print_info(f"使用已有会话: {self.api_client.session_id}")
                self.api_client.set_auth(token, self.api_client.session_id)
                return True

            session_result = self.api_client.session.post(
                f"{self.api_client.base_url}/api/session/create",
                headers={"Authorization": f"Bearer {token}"},
                timeout=600
            )
            session_result.raise_for_status()
            session_id = session_result.json().get("session_id")

            if not session_id:
                self.printer.print_error("创建会话失败：未获取到会话 ID")
                return False

            self.printer.print_info(f"会话创建成功: {session_id}")

            self.api_client.set_auth(token, session_id)

            return True

        except Exception as e:
            self.printer.print_error(f"初始化失败: {e}")
            return False


def main():
    parser = argparse.ArgumentParser(description="地图智能体流式聊天客户端")
    parser.add_argument(
        "-u", "--url",
        default=os.environ.get("API_BASE_URL", "http://localhost:8002"),
        help="API 服务器地址 (默认: http://localhost:8002 或环境变量 API_BASE_URL)"
    )
    parser.add_argument(
        "--username",
        default="admin",
        help="登录用户名 (默认: admin)"
    )
    parser.add_argument(
        "--password",
        default="123456",
        help="登录密码 (默认: 123456)"
    )
    parser.add_argument(
        "--session-id",
        default=None,
        help="指定会话 ID (可选，将使用现有会话而非创建新会话)"
    )
    args = parser.parse_args()

    base_url = args.url
    
    print(f"正在连接到: {base_url}")
    print(f"用户名: {args.username}")
    
    client = MapAgentChatClient(base_url, args.username, args.password, args.session_id)
    client.run()


if __name__ == "__main__":
    main()
