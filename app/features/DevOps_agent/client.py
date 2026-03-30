#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOps CLI Client

交互式命令行客户端，支持服务器选择、命令执行历史记录等功能。

Date: 2026-03-30
"""

import os
import sys
import csv
import uuid
import yaml
import asyncio
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from langgraph.store.memory import InMemoryStore
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.markdown import Markdown

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent.parent.parent))

from app.features.DevOps_agent.DevOpsAgent import DevOpsAgent


class ServerSelector:
    """
    服务器选择器类

    负责加载 SSH 配置、显示服务器列表和处理用户选择。
    """

    def __init__(self, config_path: str = None):
        """
        初始化服务器选择器

        Args:
            config_path: SSH 配置文件路径，默认使用模块目录下的 config/ssh_config.yaml
        """
        if config_path is None:
            config_path = Path(__file__).parent / "config" / "ssh_config.yaml"
        else:
            config_path = Path(config_path)

        self._config_path = config_path
        self._servers: List[Dict[str, Any]] = []
        self._load_config()

    def _load_config(self) -> None:
        """加载 SSH 配置文件"""
        if not self._config_path.exists():
            print(f"警告：配置文件不存在 {self._config_path}")
            return

        try:
            with open(self._config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                self._servers = config.get("servers", []) if config else []
        except Exception as e:
            print(f"加载配置文件失败: {e}")
            self._servers = []

    def display_servers(self) -> None:
        """显示可用服务器列表"""
        if not self._servers:
            print("\n未配置任何服务器，请检查 ssh_config.yaml 文件")
            return

        print("\n" + "=" * 60)
        print("可用服务器列表")
        print("=" * 60)

        for i, server in enumerate(self._servers, 1):
            name = server.get("name", "未命名")
            host = server.get("host", "未知")
            port = server.get("port", 22)
            username = server.get("username", "未知")
            server_type = server.get("server_type", "linux")
            auth_type = "私钥" if server.get("private_key_path") else "密码"

            print(f"\n  [{i}] {name}")
            print(f"      地址: {host}:{port}")
            print(f"      用户: {username}")
            print(f"      类型: {server_type}")
            print(f"      认证: {auth_type}")

        print("\n  [q] 退出程序")
        print("=" * 60)

    def select(self, index: int) -> Optional[Dict[str, Any]]:
        """
        根据索引选择服务器

        Args:
            index: 服务器索引（从 1 开始）

        Returns:
            Optional[Dict[str, Any]]: 服务器配置，无效索引返回 None
        """
        if 1 <= index <= len(self._servers):
            return self._servers[index - 1]
        return None

    def get_server_count(self) -> int:
        """获取服务器数量"""
        return len(self._servers)

    def get_server_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """
        根据名称获取服务器配置

        Args:
            name: 服务器名称

        Returns:
            Optional[Dict[str, Any]]: 服务器配置
        """
        for server in self._servers:
            if server.get("name") == name:
                return server
        return None


class CSVHistoryLogger:
    """
    CSV 历史记录器类

    负责将命令执行历史记录到 CSV 文件。
    """

    CSV_HEADER = ["session_id", "server_name", "command", "output",
                  "blocked", "block_reason", "timestamp", "success"]

    def __init__(self, csv_path: str = None):
        """
        初始化 CSV 历史记录器

        Args:
            csv_path: CSV 文件路径，默认使用 config/command_history.csv
        """
        if csv_path is None:
            csv_path = Path(__file__).parent / "config" / "command_history.csv"
        else:
            csv_path = Path(csv_path)

        self._csv_path = csv_path
        self._ensure_csv_exists()

    def _ensure_csv_exists(self) -> None:
        """确保 CSV 文件存在，不存在则创建并写入表头"""
        if not self._csv_path.exists():
            try:
                self._csv_path.parent.mkdir(parents=True, exist_ok=True)
                with open(self._csv_path, "w", newline="", encoding="utf-8") as f:
                    writer = csv.writer(f)
                    writer.writerow(self.CSV_HEADER)
            except Exception as e:
                print(f"创建 CSV 文件失败: {e}")

    def log(self, record: Dict[str, Any]) -> None:
        """
        记录命令执行结果到 CSV

        Args:
            record: 记录字典，包含 session_id, server_name, command, output, blocked, block_reason, success
        """
        try:
            row = [
                record.get("session_id", ""),
                record.get("server_name", ""),
                record.get("command", ""),
                record.get("output", "")[:500],  # 限制输出长度
                "1" if record.get("blocked", False) else "0",
                record.get("block_reason", ""),
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "1" if record.get("success", False) else "0",
            ]

            with open(self._csv_path, "a", newline="", encoding="utf-8") as f:
                writer = csv.writer(f)
                writer.writerow(row)

        except Exception as e:
            print(f"写入 CSV 失败: {e}")

    def get_history(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        获取历史记录

        Args:
            session_id: 会话 ID，如果指定则只返回该会话的记录

        Returns:
            List[Dict[str, Any]]: 历史记录列表
        """
        history = []

        if not self._csv_path.exists():
            return history

        try:
            with open(self._csv_path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if session_id is None or row.get("session_id") == session_id:
                        history.append({
                            "session_id": row.get("session_id", ""),
                            "server_name": row.get("server_name", ""),
                            "command": row.get("command", ""),
                            "output": row.get("output", ""),
                            "blocked": row.get("blocked", "0") == "1",
                            "block_reason": row.get("block_reason", ""),
                            "timestamp": row.get("timestamp", ""),
                            "success": row.get("success", "0") == "1",
                        })
        except Exception as e:
            print(f"读取 CSV 失败: {e}")

        return history

    def display_history(self, session_id: Optional[str] = None) -> None:
        """
        显示历史记录

        Args:
            session_id: 会话 ID
        """
        history = self.get_history(session_id)

        if not history:
            print("\n暂无历史记录")
            return

        print("\n" + "=" * 80)
        if session_id:
            print(f"会话 {session_id} 的历史记录")
        else:
            print("所有历史记录")
        print("=" * 80)

        for i, record in enumerate(history, 1):
            print(f"\n[{i}] {record['timestamp']}")
            print(f"    服务器: {record['server_name']}")
            print(f"    命令: {record['command']}")

            if record['blocked']:
                print(f"    状态: 被拦截 - {record['block_reason']}")
            elif record['success']:
                print(f"    状态: 成功")
            else:
                print(f"    状态: 失败")

            if record['output']:
                output_preview = record['output'][:100] + "..." if len(record['output']) > 100 else record['output']
                print(f"    输出: {output_preview}")

        print("\n" + "=" * 80)


class DevOpsCLI:
    """
    DevOps CLI 类

    提供交互式命令行界面，整合服务器选择、命令执行和历史记录功能。
    """

    def __init__(self):
        """初始化 DevOps CLI"""
        self._selector = ServerSelector()
        self._history_logger = CSVHistoryLogger()
        self._current_session_id: Optional[str] = None
        self._current_server: Optional[Dict[str, Any]] = None
        self._agent: Optional[DevOpsAgent] = None
        self._checkpointer = MemorySaver()
        self._store = InMemoryStore()
        self._console = Console()

    def _display_welcome(self) -> None:
        """显示欢迎信息"""
        print("\n" + "=" * 60)
        print("       欢迎使用 DevOps Agent CLI")
        print("=" * 60)
        print("\n功能说明：")
        print("  - 选择服务器进行远程命令执行")
        print("  - 支持自然语言描述运维需求")
        print("  - 自动记录命令执行历史")
        print("\n命令：")
        print("  exit / q    - 退出程序")
        print("  history     - 查看当前会话历史")
        print("  help        - 显示帮助信息")
        print("=" * 60)

    def _display_help(self) -> None:
        """显示帮助信息"""
        print("\n" + "=" * 60)
        print("帮助信息")
        print("=" * 60)
        print("\n交互命令：")
        print("  exit, q          - 退出程序")
        print("  history          - 查看当前会话历史记录")
        print("  help             - 显示此帮助信息")
        print("  clear            - 清屏")
        print("\n使用示例：")
        print("  > 查看磁盘使用情况")
        print("  > 查看当前运行的进程")
        print("  > 查看系统日志")
        print("  > 检查网络连接")
        print("=" * 60)

    def _render_markdown(self, content: str) -> None:
        """
        使用 Rich 库渲染 Markdown 格式输出

        Args:
            content: Markdown 格式的字符串内容
        """
        md = Markdown(content)
        self._console.print(md)

    async def _select_server(self) -> bool:
        """
        选择服务器

        Returns:
            bool: 是否成功选择服务器
        """
        while True:
            self._selector.display_servers()

            if self._selector.get_server_count() == 0:
                print("\n没有可用的服务器，请配置 ssh_config.yaml 文件")
                return False

            choice = input("\n请选择服务器 [1-{}] 或输入 'q' 退出: ".format(
                self._selector.get_server_count()
            )).strip().lower()

            if choice in ('q', 'quit', 'exit'):
                return False

            if choice == 'help':
                self._display_help()
                continue

            try:
                index = int(choice)
                server = self._selector.select(index)

                if server:
                    self._current_server = server
                    self._current_session_id = f"devops_{uuid.uuid4().hex[:8]}"

                    # 初始化 Agent
                    self._agent = DevOpsAgent(
                        checkpointer=self._checkpointer,
                        store=self._store,
                        store_id=self._current_session_id,
                    )

                    print(f"\n已选择服务器: {server.get('name')}")
                    print(f"会话 ID: {self._current_session_id}")
                    return True
                else:
                    print("\n无效的选择，请重试")

            except ValueError:
                print("\n请输入数字或 'q' 退出")

    async def _handle_user_input(self, user_input: str) -> bool:
        """
        处理用户输入

        Args:
            user_input: 用户输入内容

        Returns:
            bool: 是否继续会话
        """
        user_input = user_input.strip()

        if not user_input:
            return True

        # 处理特殊命令
        if user_input.lower() in ('exit', 'q', 'quit'):
            print("\n感谢使用，再见！")
            return False

        if user_input.lower() == 'help':
            self._display_help()
            return True

        if user_input.lower() == 'history':
            self._history_logger.display_history(self._current_session_id)
            return True

        if user_input.lower() == 'clear':
            os.system('cls' if os.name == 'nt' else 'clear')
            return True

        if user_input.lower() == 'back':
            print("\n返回服务器选择...")
            return await self._select_server()

        # 执行用户请求
        print("\n正在处理...")

        try:
            # 调用 Agent 处理用户输入
            result = await self._agent.invoke(
                user_input=user_input,
                session_id=self._current_session_id,
                server_name=self._current_server.get("name"),
            )

            self._render_markdown(result)

            # 记录到 CSV（这里简化处理，实际应该从 Agent 返回的结果中提取）
            self._history_logger.log({
                "session_id": self._current_session_id,
                "server_name": self._current_server.get("name", ""),
                "command": user_input,
                "output": result[:500] if result else "",
                "blocked": False,
                "block_reason": "",
                "success": True,
            })

        except Exception as e:
            print(f"\n执行失败: {e}")

            self._history_logger.log({
                "session_id": self._current_session_id,
                "server_name": self._current_server.get("name", ""),
                "command": user_input,
                "output": str(e),
                "blocked": False,
                "block_reason": "",
                "success": False,
            })

        return True

    async def run(self) -> None:
        """运行 CLI 主循环"""
        self._display_welcome()

        # 选择服务器
        if not await self._select_server():
            return

        # 交互循环
        print("\n" + "-" * 60)
        print("进入交互模式（输入 'help' 查看帮助，'exit' 退出）")
        print("-" * 60)

        while True:
            try:
                user_input = input(f"\n[{self._current_server.get('name')}] > ").strip()

                if not await self._handle_user_input(user_input):
                    break

            except KeyboardInterrupt:
                print("\n\n感谢使用，再见！")
                break
            except EOFError:
                print("\n\n输入结束，退出程序")
                break


def main():
    """主函数入口"""
    cli = DevOpsCLI()
    asyncio.run(cli.run())


if __name__ == "__main__":
    main()
