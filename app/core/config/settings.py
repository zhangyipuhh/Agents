#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
配置管理模块

使用 Pydantic BaseSettings 管理应用配置，自动从 .env 文件加载配置。
支持类型验证、默认值、环境变量覆盖等功能。

Date: 2026-04-07
Author: 张镒谱
"""

from typing import Dict, Literal, Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from mcpClient.shared.config_loader import load_mcp_config


class LLMSettings(BaseSettings):
    """
    大语言模型配置

    从环境变量加载 LLM 相关配置，支持多种模型服务商。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    model_type: str = Field(
        default="openai", description="模型类型，如 'openai', 'deepseek', 'ollama' 等"
    )
    model_name: str = Field(
        default="",
        description="模型名称，如 'gpt-4', 'deepseek-chat', 'qwen3-vl:30b' 等",
    )
    model_api_key: str = Field(default="", description="API 密钥，用于访问远程模型服务")
    model_api_base: str = Field(
        default="", description="API 基础 URL，指定模型服务的地址"
    )
    model_temperature: float = Field(
        default=0.0,
        ge=0.0,
        le=2.0,
        description="模型温度参数，控制生成多样性，取值范围 0-2",
    )
    is_multimodal: bool = Field(
        default=False, description="是否开启多模态，支持同时处理文本和图片等多模态输入"
    )
    parallel_tool_calls: Optional[bool] = Field(
        default=None,
        description="是否启用并行工具调用，none表示不传参，true/false显式设置",
    )
    ollama_reasoning: Optional[bool] = Field(
        default=True,
        description="Ollama模型是否启用推理功能，仅对Ollama模型有效",
    )
    ollama_timeout: int = Field(
        default=120,
        ge=1,
        description="Ollama模型请求超时时间（秒），仅对Ollama模型有效",
    )

    @field_validator("parallel_tool_calls", mode="before")
    @classmethod
    def parse_parallel_tool_calls(cls, v):
        """将字符串转换为布尔值，none表示不传参"""
        if v is None:
            return None
        if isinstance(v, str):
            if v.lower() == "none":
                return None
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("is_multimodal", mode="before")
    @classmethod
    def parse_bool(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("ollama_reasoning", mode="before")
    @classmethod
    def parse_ollama_reasoning(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


class VisionLLMSettings(BaseSettings):
    """
    视觉大语言模型配置

    专门用于视觉模型的配置，与通用 LLM 配置分离。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    model_type_vision: str = Field(default="openai", description="视觉模型类型")
    model_name_vision: str = Field(default="", description="视觉模型名称")
    model_api_key_vision: str = Field(default="", description="视觉模型 API 密钥")
    model_api_base_vision: str = Field(default="", description="视觉模型 API 基础 URL")
    model_temperature_vision: float = Field(
        default=0.0, ge=0.0, le=2.0, description="视觉模型温度参数"
    )


class WordOutputSettings(BaseSettings):
    """
    Word 输出配置

    管理 Word 文档输出的相关配置。
    """

    highlight_color: str = Field(
        default="FF0000", description="高亮颜色，十六进制格式，默认红色"
    )
    output_dir: str = Field(
        default="app/agents/data/output", description="输出目录路径"
    )


class MCPSettings(BaseSettings):
    """
    MCP 服务器配置

    管理 MCP（Model Context Protocol）服务器相关配置，
    包括配置文件路径和配置加载功能。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    mcp_config_path: str = Field(
        default="app/shared/tools/mcp/config.yaml", description="MCP 服务器配置文件路径"
    )

    def get_mcp_config(self) -> Dict[str, dict]:
        """
        加载并返回 MCP 服务器配置

        从 YAML 配置文件加载 MCP 服务器配置，支持环境变量插值。

        Returns:
            Dict[str, dict]: MCP 服务器配置字典，键为服务器名称，值为服务器配置
        """
        from pathlib import Path

        config_path = Path(self.mcp_config_path)
        return load_mcp_config(config_path)


class FileParserSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    file_parser_enabled: bool = Field(
        default=False, description="是否启用远程文件解析服务"
    )
    file_parser_server_url: str = Field(
        default="http://mineru-openai-server:30000", description="远程解析服务地址"
    )
    file_parser_output_format: str = Field(
        default="json", description="输出格式，可选 json 或 md"
    )
    file_parser_api_url: str = Field(
        default="/api/v1/parse", description="解析服务 API 地址"
    )
    file_parser_max_retries: int = Field(
        default=60, description="最大轮询重试次数"
    )
    file_parser_poll_interval: float = Field(
        default=2.0, description="轮询间隔（秒）"
    )
    file_parser_timeout: int = Field(
        default=300, description="请求超时时间（秒）"
    )

    @field_validator("file_parser_enabled", mode="before")
    @classmethod
    def parse_bool(cls, v):
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("file_parser_output_format", mode="before")
    @classmethod
    def validate_output_format(cls, v):
        if v not in ("json", "md"):
            raise ValueError("file_parser_output_format must be 'json' or 'md'")
        return v


class DatabaseSettings(BaseSettings):
    """
    数据库配置

    从环境变量加载数据库相关配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    database_url: str = Field(
        default="postgresql://postgres:postgres@localhost:5432/feature_agent",
        description="PostgreSQL 连接字符串"
    )
    auth_storage_mode: str = Field(
        default="memory",
        description="认证存储模式：memory 或 postgres"
    )


class PortalAuthSettings(BaseSettings):
    """
    门户子 Refresh Token 配置

    管理门户导航场景下颁发给第三方 iframe 的"子 refresh_token"相关参数。
    父页（门户导航页）通过 /api/auth/issue-portal-refresh-token 接口申请
    子 token，经 postMessage 推送给第三方；第三方用它反复换 access_token。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    portal_refresh_token_ttl_seconds: int = Field(
        default=86400,
        ge=60,
        description="门户子 refresh_token 有效期（秒），默认 86400 = 24 小时。"
                    "与主 refresh_token TTL 保持一致；可由环境变量 PORTAL_REFRESH_TOKEN_TTL_SECONDS 覆盖。",
    )


class DemonstrationSettings(BaseSettings):
    """
    演示测试配置

    管理演示报告生成相关配置。
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    demonstration_report_enabled: bool = Field(
        default=True, description="是否开启演示报告生成，为true时开启"
    )

    @field_validator("demonstration_report_enabled", mode="before")
    @classmethod
    def parse_bool(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


class SandboxSettings(BaseSettings):
    """
    沙箱容器化部署配置（2026-06-12 新增）

    管理 Docker 沙箱在容器化场景下的运行参数，支持 4 种部署模式：
        - local:  本地直接跑（应用进程 = 宿主机），路径无需投影
        - socket: 应用容器挂载宿主机 /var/run/docker.sock，路径需通过
                  sandbox_host_workspace_prefix 投影到宿主机视角
        - dind:   Docker-in-Docker（应用容器内嵌 daemon），路径与 local 相同
        - k8s:    通过 K8s API 创建 Pod（占位，未实现）

    路径双视角：
        - workspace（应用进程视角）：用于 os.makedirs / upload_files / download_files
        - host_workspace（宿主机视角）：用于 Docker volume bind mount
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
        protected_namespaces=("settings_",),
    )

    sandbox_docker_mode: Literal["local", "socket", "dind", "k8s"] = Field(
        default="local",
        description="沙箱部署模式：local(本地) / socket(挂docker.sock) / dind / k8s",
    )
    sandbox_docker_host: str = Field(
        default="",
        description="Docker daemon URL，socket 模式用 unix:///var/run/docker.sock",
    )
    sandbox_image: str = Field(
        default="python:3.12-alpine",
        description="沙箱镜像名",
    )
    sandbox_max_memory_mb: int = Field(
        default=512,
        ge=64,
        description="容器内存限制（MB），下限 64",
    )
    sandbox_max_cpu_percent: int = Field(
        default=100,
        ge=10,
        le=100,
        description="容器 CPU 限制（百分比），10-100",
    )
    sandbox_network_enabled: bool = Field(
        default=False,
        description="是否启用容器网络",
    )
    sandbox_default_timeout: int = Field(
        default=60,
        ge=1,
        description="命令默认超时（秒）",
    )
    sandbox_container_workspace: str = Field(
        default="/workspace",
        description="容器内工作目录（bind mount target）",
    )
    sandbox_host_workspace_prefix: str = Field(
        default="",
        description=(
            "宿主机视角工作目录前缀，socket 模式专用。"
            "例：容器内 /app/data 对应宿主机 /host/app/data，则填 /host/app/data"
        ),
    )
    sandbox_k8s_namespace: str = Field(
        default="default",
        description="K8s 模式命名空间（占位，未实现）",
    )
    sandbox_fallback_to_local: bool = Field(
        default=True,
        description=(
            "Docker 不可用时是否降级到本地文件系统执行。"
            "true: 使用 LocalShellBackend 在本地 workspace 继续运行（失去 Docker 隔离，仅限开发/可信环境）；"
            "false: 仅返回清晰错误，保持安全边界。"
        ),
    )

    @field_validator("sandbox_network_enabled", mode="before")
    @classmethod
    def parse_bool(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("sandbox_fallback_to_local", mode="before")
    @classmethod
    def parse_fallback_bool(cls, v):
        """将字符串转换为布尔值"""
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)


class Settings(BaseSettings):
    """
    应用总配置

    整合所有配置模块，提供统一的配置访问接口。
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    llm: LLMSettings = Field(default_factory=LLMSettings)
    vision_llm: VisionLLMSettings = Field(default_factory=VisionLLMSettings)
    word_output: WordOutputSettings = Field(default_factory=WordOutputSettings)
    mcp: MCPSettings = Field(default_factory=MCPSettings)
    file_parser: FileParserSettings = Field(default_factory=FileParserSettings)
    database: DatabaseSettings = Field(default_factory=DatabaseSettings)
    demonstration: DemonstrationSettings = Field(default_factory=DemonstrationSettings)
    portal_auth: PortalAuthSettings = Field(default_factory=PortalAuthSettings)
    sandbox: SandboxSettings = Field(default_factory=SandboxSettings)
    agent_chat_max_concurrency: int = Field(
        default=1,
        ge=1,
        description="Agent 聊天接口最大并发数，超出时进入内存队列等待；环境变量 AGENT_CHAT_MAX_CONCURRENCY",
    )

    def get_llm_config(self) -> dict:
        """
        获取 LLM 配置字典

        Returns:
            dict: LLM 配置字典，兼容旧代码
        """
        return {
            "model_name": self.llm.model_name,
            "api_key": self.llm.model_api_key,
            "base_url": self.llm.model_api_base,
            "model_type": self.llm.model_type,
            "temperature": self.llm.model_temperature,
            "is_multimodal": self.llm.is_multimodal,
            "parallel_tool_calls": self.llm.parallel_tool_calls,
            "ollama_reasoning": self.llm.ollama_reasoning,
            "ollama_timeout": self.llm.ollama_timeout,
        }

    def get_vision_llm_config(self) -> dict:
        """
        获取视觉 LLM 配置字典

        Returns:
            dict: 视觉 LLM 配置字典，兼容旧代码
        """
        return {
            "model_name": self.vision_llm.model_name_vision,
            "api_key": self.vision_llm.model_api_key_vision,
            "base_url": self.vision_llm.model_api_base_vision,
            "model_type": self.vision_llm.model_type_vision,
            "temperature": self.vision_llm.model_temperature_vision,
        }

    def get_word_output_config(self) -> dict:
        """
        获取 Word 输出配置字典

        Returns:
            dict: Word 输出配置字典，兼容旧代码
        """
        return {
            "highlight_color": self.word_output.highlight_color,
            "output_dir": self.word_output.output_dir,
        }

    def get_file_parser_config(self) -> dict:
        return {
            "enabled": self.file_parser.file_parser_enabled,
            "server_url": self.file_parser.file_parser_server_url,
            "output_format": self.file_parser.file_parser_output_format,
            "api_url": self.file_parser.file_parser_api_url,
            "max_retries": self.file_parser.file_parser_max_retries,
            "poll_interval": self.file_parser.file_parser_poll_interval,
            "timeout": self.file_parser.file_parser_timeout,
        }

    def get_demonstration_config(self) -> dict:
        """
        获取演示测试配置字典

        Returns:
            dict: 演示测试配置字典，兼容旧代码
        """
        return {
            "demonstration_report_enabled": self.demonstration.demonstration_report_enabled,
        }

    def get_portal_auth_config(self) -> dict:
        """
        获取门户子 Refresh Token 配置字典

        Returns:
            dict: 门户子 refresh_token 配置字典，兼容旧代码
        """
        return {
            "portal_refresh_token_ttl_seconds": self.portal_auth.portal_refresh_token_ttl_seconds,
        }

    def get_sandbox_config(self) -> dict:
        """
        获取沙箱容器化部署配置字典

        Returns:
            dict: 沙箱配置扁平字典，供 DockerSandboxMiddleware 透传
        """
        return {
            "docker_mode": self.sandbox.sandbox_docker_mode,
            "docker_host": self.sandbox.sandbox_docker_host,
            "image": self.sandbox.sandbox_image,
            "max_memory_mb": self.sandbox.sandbox_max_memory_mb,
            "max_cpu_percent": self.sandbox.sandbox_max_cpu_percent,
            "network_enabled": self.sandbox.sandbox_network_enabled,
            "default_timeout": self.sandbox.sandbox_default_timeout,
            "container_workspace": self.sandbox.sandbox_container_workspace,
            "host_workspace_prefix": self.sandbox.sandbox_host_workspace_prefix,
            "k8s_namespace": self.sandbox.sandbox_k8s_namespace,
            "fallback_to_local": self.sandbox.sandbox_fallback_to_local,
        }


settings = Settings()
