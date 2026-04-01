#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOpsAgent - DevOps Agent 类

提供可复用的 DevOps 远程命令执行功能，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-30
"""

import json
import yaml
from typing import Optional, Any
from pathlib import Path

from app.core.agent.agent import get_agent
from app.features.DevOps_agent.config.DevOpsAgentConfig import (
    DevOpsAgentConfig,
    DevOpsAgentState,
    DevOpsConfigurableConfig,
    DevOpsExecuteConfig,
)
from app.features.DevOps_agent.config.DevOpsAgentContext import DevOpsAgentContext
from app.features.DevOps_agent.config.prompts import DEFAULT_SYSTEM_PROMPT
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore


class DevOpsAgent:
    """
    DevOps Agent 类

    提供可复用的远程命令执行对话功能，支持多轮对话、工具调用和会话状态管理。

    Attributes:
        checkpointer: LangGraph 检查点保存器
        store: LangGraph 内存存储器
        config: Agent 配置
        _agent: 底层 agent 实例
        _ssh_config: SSH 配置缓存
        _command_blacklist: 命令黑名单缓存
    """

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver,
        store: BaseStore,
        store_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 3000,
        max_tokens_before_summary: int = 1500,
        max_summary_tokens: int = 500,
        config_dir: Optional[str] = None,
    ):
        """
        初始化 DevOpsAgent 实例

        Args:
            checkpointer: LangGraph 检查点保存器，用于持久化会话状态
            store: LangGraph 内存存储器，用于存储上下文信息
            store_id: 存储 ID
            system_prompt: 自定义系统提示词，默认使用 DevOps 专用提示词
            max_tokens: 最大 token 数，默认 6000（适配 8192 token 限制模型）
            max_tokens_before_summary: 触发摘要的 token 阈值，默认 4000
            max_summary_tokens: 摘要最大 token 数，默认 1000
            config_dir: 配置文件目录，默认使用模块所在目录的 config 文件夹
        """
        self.checkpointer = checkpointer
        self.store = store
        self.store_id = store_id
        self.system_prompt = system_prompt or DEFAULT_SYSTEM_PROMPT
        self.max_tokens = max_tokens
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        self._agent = None

        # 加载配置文件
        if config_dir is None:
            config_dir = Path(__file__).parent / "config"
        else:
            config_dir = Path(config_dir)

        self._ssh_config = self._load_ssh_config(config_dir / "ssh_config.yaml")
        self._command_blacklist = self._load_blacklist_config(config_dir / "command_blacklist.yaml")

    def _load_ssh_config(self, config_path: Path) -> dict:
        """
        加载 SSH 配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            dict: SSH 配置字典
        """
        default_config = {
            "servers": []
        }

        if not config_path.exists():
            return default_config

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config if config else default_config
        except Exception as e:
            print(f"加载 SSH 配置文件失败: {e}")
            return default_config

    def _load_blacklist_config(self, config_path: Path) -> list:
        """
        加载命令黑名单配置文件

        Args:
            config_path: 配置文件路径

        Returns:
            list: 黑名单列表
        """
        default_blacklist = []

        if not config_path.exists():
            return default_blacklist

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                config = yaml.safe_load(f)
                return config.get("blacklist", default_blacklist) if config else default_blacklist
        except Exception as e:
            print(f"加载黑名单配置文件失败: {e}")
            return default_blacklist

    def get_server_config(self, server_name: str) -> Optional[dict]:
        """
        获取指定服务器的配置

        Args:
            server_name: 服务器名称

        Returns:
            Optional[dict]: 服务器配置，未找到返回 None
        """
        for server in self._ssh_config.get("servers", []):
            if server.get("name") == server_name:
                return server
        return None

    def list_servers(self) -> list:
        """
        获取所有服务器列表

        Returns:
            list: 服务器配置列表
        """
        return self._ssh_config.get("servers", [])

    async def _ensure_agent(self):
        """确保 agent 已初始化"""
        if self._agent is None:
            config = DevOpsAgentConfig(
                max_tokens=self.max_tokens,
                max_tokens_before_summary=self.max_tokens_before_summary,
                max_summary_tokens=self.max_summary_tokens,
                system_prompt=self.system_prompt,
                checkpointer=self.checkpointer,
                store=self.store,
                state_class=DevOpsAgentState,
                context_class=DevOpsAgentContext,
            )
            self._agent = await get_agent(config)
        return self._agent

    async def invoke(
        self,
        user_input: str,
        session_id: str,
        server_name: Optional[str] = None,
        error_limit: int = 2,
        limit: int = 10,
        resume: bool | dict = False,
        **kwargs,
    ) -> dict:
        """
        执行对话并返回结果

        Args:
            user_input: 用户输入内容
            session_id: 会话ID，用于标识和恢复会话状态
            server_name: 服务器名称，如果指定则使用该服务器的 SSH 配置
            error_limit: 错误限制次数，默认 2
            limit: 最大迭代次数，默认 10
            resume: 恢复执行参数
                - False: 正常执行
                - True: 批准执行（用于 interrupt 后继续）
                - dict: 包含 action 和可选 feedback 的决策字典
            **kwargs: 其他可选参数

        Returns:
            dict: Agent 的处理结果，包含:
                - type: "interrupt" 表示中断等待确认
                - content: 正常结果内容
                - interrupt: 中断信息（如果有）
        """
        from langgraph.types import Command

        agent = await self._ensure_agent()

        config = DevOpsExecuteConfig(
            configurable=DevOpsConfigurableConfig(thread_id=session_id),
            recursion_limit=100  # 增加递归限制，支持更多轮次的工具调用
        )

        state = DevOpsAgentState(
            messages=[user_input] if user_input else [],
            error_limit=error_limit,
            limit=limit,
        )

        # 构建 Context，注入 SSH 配置和黑名单
        context_data = {
            "session_id": session_id,
            "store_id": self.store_id or session_id,
            "command_blacklist": self._command_blacklist,
            "tool_confirmation": {"execute_command": True},  # 默认所有命令需要确认
        }

        # 如果指定了服务器名称，注入对应服务器的 SSH 配置
        if server_name:
            server_config = self.get_server_config(server_name)
            if server_config:
                context_data["ssh_config"] = json.dumps(server_config, ensure_ascii=False)
            else:
                return {"type": "error", "content": f"错误：未找到服务器 '{server_name}' 的配置"}
        else:
            # 默认使用第一个服务器配置
            servers = self.list_servers()
            if servers:
                context_data["ssh_config"] = json.dumps(servers[0], ensure_ascii=False)
            else:
                return {"type": "error", "content": "错误：未配置任何 SSH 服务器"}

        context = DevOpsAgentContext(**context_data)

        # 处理 resume 参数
        if resume is not False:
            resume_command = Command(resume=resume)
            result = await agent.invoke(
                resume_command,
                config=config,
                context=context,
            )
        else:
            result = await agent.invoke(
                config=config,
                input_state=state,
                context=context,
            )

        # 检查是否有中断
        if isinstance(result, dict) and "__interrupt__" in result:
            return {
                "type": "interrupt",
                "interrupt": result["__interrupt__"],
                "session_id": session_id
            }

        # 正常结果
        if isinstance(result, dict) and "messages" in result:
            return {"type": "normal", "content": result["messages"][-1].content}

        return {"type": "normal", "content": str(result)}

    async def execute_command_direct(
        self,
        command: str,
        session_id: str,
        server_name: Optional[str] = None,
        server_type: str = "linux",
        timeout: int = 30,
    ) -> dict:
        """
        直接执行命令（不经过 LLM）

        Args:
            command: 要执行的命令
            session_id: 会话 ID
            server_name: 服务器名称
            server_type: 服务器类型
            timeout: 超时时间

        Returns:
            dict: 命令执行结果
        """
        from app.features.DevOps_agent.tools.SSHTools import execute_command
        from langchain.tools import ToolRuntime

        # 获取服务器配置
        if server_name:
            ssh_config = self.get_server_config(server_name)
            if not ssh_config:
                return {"success": False, "error": f"未找到服务器 '{server_name}' 的配置"}
        else:
            servers = self.list_servers()
            if not servers:
                return {"success": False, "error": "未配置任何 SSH 服务器"}
            ssh_config = servers[0]

        # 构建运行时上下文
        class MockRuntime:
            def __init__(self, context, store, tool_call_id):
                self.context = context
                self.store = store
                self.tool_call_id = tool_call_id

        context = {
            "session_id": session_id,
            "store_id": self.store_id or session_id,
            "ssh_config": json.dumps(ssh_config, ensure_ascii=False),
            "command_blacklist": self._command_blacklist,
        }

        runtime = MockRuntime(
            context=context,
            store=self.store,
            tool_call_id=f"direct_{session_id}"
        )

        # 执行命令
        result = execute_command(
            command=command,
            server_type=server_type,
            timeout=timeout,
            runtime=runtime
        )

        # 解析结果
        if result and result.update and result.update.get("messages"):
            message = result.update["messages"][0]
            if hasattr(message, "content"):
                try:
                    return json.loads(message.content)
                except json.JSONDecodeError:
                    return {"success": False, "error": message.content}

        return {"success": False, "error": "未知错误"}

    async def get_agent(self):
        """
        获取底层 agent 实例

        Returns:
            底层 agent 实例
        """
        return await self._ensure_agent()
