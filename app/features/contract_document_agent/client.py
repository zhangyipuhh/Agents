#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DocAgent 客户端测试页面

本模块提供命令行交互界面，用于直接测试 DocAgent 的对话功能。
主要功能包括：
- 直接调用：绕过网络层，直接调用 DocAgent 类
- 对话功能：与 DocAgent 进行多轮对话
- 聊天历史：查看和管理聊天记录
- Markdown 渲染：终端内优雅的 Markdown 输出

Date: 2026-03-25
Author: 张镒谱
"""

import asyncio
import uuid
import logging
from datetime import datetime
from typing import Optional, List, Dict, Any

from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from langgraph.store.memory import InMemoryStore

from app.features.contract_document_agent.DocAgent import DocAgent
from app.shared.utils.memory import get_async_checkpointer


logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

console = Console()


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
        显示聊天历史（使用 Markdown 渲染）
        """
        if not self.history:
            console.print("[yellow]暂无聊天历史[/yellow]")
            return
        
        console.print(Panel("聊天历史记录", style="bold blue"))
        console.print()
        
        for msg in self.history:
            role_name = "用户" if msg["role"] == "user" else "智能体"
            role_style = "green" if msg["role"] == "user" else "cyan"
            
            console.print(f"[bold {role_style}]{role_name}[/bold {role_style}] - {msg['timestamp']}")
            
            try:
                md = Markdown(msg["content"])
                console.print(md)
            except:
                console.print(msg["content"])
            console.print()
        
        console.print("─" * 50)
    
    def clear_history(self) -> None:
        """
        清空聊天历史
        """
        self.history = []
        console.print("[yellow]聊天历史已清空[/yellow]")


class DocClient:
    """
    DocAgent 客户端类
    
    直接调用 DocAgent 类进行对话，绕过网络层。
    """
    
    def __init__(self):
        """
        初始化 DocClient
        """
        self.checkpointer = None
        self.store = InMemoryStore()
        self.store_id = str(uuid.uuid4())
        self.session_id = str(uuid.uuid4())
        self.host_session_id = str(uuid.uuid4())
        self.doc_agent: Optional[DocAgent] = None
        self.cycle_count = 0
        
    async def _ensure_agent(self) -> DocAgent:
        """
        确保 DocAgent 已初始化

        Returns:
            DocAgent 实例
        """
        if self.doc_agent is None:
            logger.info("正在初始化 DocAgent...")
            # 延迟初始化 checkpointer
            if self.checkpointer is None:
                self.checkpointer = await get_async_checkpointer()
            self.doc_agent = DocAgent(
                model_type="ollama",
                model_name="qwen3-vl:30b",
                api_key="11111",
                base_url="http://172.26.160.50:9001",
                temperature=0.2,
                checkpointer=self.checkpointer,
                store=self.store,
                store_id=self.store_id,
            )
            logger.info("DocAgent 初始化完成")
        return self.doc_agent
    
    async def chat(
        self, 
        message: str,
        session_id: Optional[str] = None,
        host_session_id: Optional[str] = None,
        image_ids: Optional[List[str]] = None
    ) -> str:
        """
        调用 DocAgent 进行对话
        
        Args:
            message: 用户消息
            session_id: 可选的会话 ID
            host_session_id: 可选的发起会话 ID
            image_ids: 可选的图片 ID 列表
            
        Returns:
            Agent 的响应
        """
        agent = await self._ensure_agent()
        
        use_session_id = session_id or self.session_id
        use_host_session_id = host_session_id or self.host_session_id
        
        logger.info(f"会话 ID: {use_session_id}")
        logger.info(f"主会话 ID: {use_host_session_id}")
        
        try:
            result = await agent.invoke(
                user_input=message,
                session_id=use_session_id,
                host_session_id=use_host_session_id,
                image_ids=image_ids,
            )
            
            if isinstance(result, dict):
                response = result.get("messages", ["无响应"])[-1] if result.get("messages") else "无响应"
                if hasattr(response, 'content'):
                    return response.content
                return str(response)
            elif isinstance(result, str):
                return result
            else:
                return str(result)
                
        except Exception as e:
            logger.error(f"对话出错: {e}")
            raise


class DocTestPage:
    """
    DocAgent 测试页面主类
    
    提供命令行交互界面，用于测试文档处理对话功能。
    """
    
    MENU_OPTIONS = {
        "1": "继续交流",
        "2": "查看聊天历史",
        "3": "清空聊天历史",
        "0": "退出"
    }
    
    def __init__(self):
        """
        初始化测试页面
        """
        self.doc_client = DocClient()
        self.chat_history = ChatHistory()
        self.is_running = True
    
    def display_header(self) -> None:
        """
        显示页面头部信息
        """
        console.print()
        console.print(Panel.fit(
            "[bold cyan]📄 文档处理对话测试页面[/bold cyan]",
            border_style="blue"
        ))
        
        table = Table(show_header=False, box=None, padding=(0, 2))
        table.add_column(style="cyan")
        table.add_column(style="white")
        
        table.add_row("当前循环", f"第 {self.doc_client.cycle_count} 轮")
        table.add_row("会话 ID", f"[dim]{self.doc_client.session_id}[/dim]")
        table.add_row("主会话 ID", f"[dim]{self.doc_client.host_session_id}[/dim]")
        
        console.print(table)
        console.print()
    
    def display_menu(self) -> None:
        """
        显示操作菜单
        """
        console.print("[bold]请选择下一步操作:[/bold]")
        for key, value in self.MENU_OPTIONS.items():
            if key == "0":
                console.print(f"  [red]{key}[/red]. {value}")
            else:
                console.print(f"  [blue]{key}[/blue]. {value}")
    
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
    
    async def handle_chat_async(self) -> None:
        """
        处理继续交流功能（异步）
        """
        console.print(Panel.fit(
            "[bold]💬 进入聊天模式[/bold]\n[dim]输入 'back' 返回主菜单[/dim]",
            border_style="green"
        ))
        console.print()
        
        while True:
            message = input("\n[bold green]👤 你:[/bold green] ").strip()
            
            if message.lower() == 'back':
                break
            
            if not message:
                continue
            
            try:
                self.chat_history.add_message("user", message)
                console.print("[cyan]🤖 智能体正在思考...[/cyan]")
                
                response = await self.doc_client.chat(
                    message=message,
                    session_id=str(uuid.uuid4()),
                    host_session_id=self.doc_client.host_session_id,
                )
                
                self.chat_history.add_message("assistant", response)
                
                console.print()
                console.print("[bold cyan]🤖 智能体:[/bold cyan]")
                console.print()
                try:
                    md = Markdown(response)
                    console.print(md)
                except Exception as md_error:
                    console.print(response)
                
            except Exception as e:
                console.print(f"[bold red]❌ 发送失败:[/bold red] {e}")
                import traceback
                console.print(f"[dim]{traceback.format_exc()}[/dim]")
    
    def handle_chat(self) -> None:
        """
        处理继续交流功能（同步包装）
        """
        asyncio.run(self.handle_chat_async())
    
    def handle_history(self) -> None:
        """
        处理查看聊天历史功能
        """
        self.chat_history.display_history()
    
    def handle_clear_history(self) -> None:
        """
        处理清空聊天历史功能
        """
        self.chat_history.clear_history()
    
    def run(self) -> None:
        """
        运行测试页面主循环
        """
        console.print("[cyan]🔄 正在初始化...[/cyan]")

        if not asyncio.run(self._initialize_async()):
            console.print("[bold red]❌ 初始化失败[/bold red]")
            return
        
        while self.is_running:
            self.doc_client.cycle_count += 1
            self.display_header()
            self.display_menu()
            
            choice = self.get_user_choice()
            
            if choice == "0":
                self.is_running = False
                console.print(Panel.fit(
                    "[bold green]👋 感谢使用，再见！[/bold green]",
                    border_style="green"
                ))
            elif choice == "1":
                self.handle_chat()
            elif choice == "2":
                self.handle_history()
            elif choice == "3":
                self.handle_clear_history()
    
    async def _initialize_async(self) -> bool:
        """
        异步初始化连接

        Returns:
            初始化是否成功
        """
        try:
            console.print("[cyan]🔧 正在初始化 DocAgent...[/cyan]")

            checkpointer = await get_async_checkpointer()
            store = InMemoryStore()

            self.doc_client.checkpointer = checkpointer
            self.doc_client.store = store
            self.doc_client.store_id = str(uuid.uuid4())
            self.doc_client.session_id = str(uuid.uuid4())
            self.doc_client.host_session_id = str(uuid.uuid4())

            console.print("[bold green]✅ 初始化完成[/bold green]")
            
            table = Table(show_header=False, box=None, padding=(0, 2))
            table.add_column(style="cyan")
            table.add_column(style="white")
            
            table.add_row("Store ID", f"[dim]{self.doc_client.store_id}[/dim]")
            table.add_row("Session ID", f"[dim]{self.doc_client.session_id}[/dim]")
            table.add_row("Host Session ID", f"[dim]{self.doc_client.host_session_id}[/dim]")
            
            console.print(table)
            
            return True
            
        except Exception as e:
            console.print(f"[bold red]❌ 初始化失败:[/bold red] {e}")
            return False


def main():
    """
    主函数入口
    """
    test_page = DocTestPage()
    test_page.run()


if __name__ == "__main__":
    main()
