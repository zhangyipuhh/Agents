#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AgentConfigService 模块

从数据库 agents 表 + AGENTS.md 文件加载完整 Agent 配置，
封装为 UnifiedAgentConfig 实例供 agent_router 使用。

2026-06-24 重构：支持三层嵌套 config_schema（含 AgentConfig 字段覆盖）。
- get_agent_config() 优先读 config_schema，回退旧 state_schema / context_schema
- 新增 update_agent_config_schema / add_agent_config_field /
  delete_agent_config_field / create_agent / delete_agent / set_agent_enabled

Date: 2026-06-23 / 2026-06-24 重构
Author: AI Assistant
"""

import asyncio
import json
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from app.shared.utils.agent.dynamic_schema import (
    build_agent_state,
    build_agent_context,
    parse_config_schema,
    RESERVED_CONFIG_FIELDS,
)
from app.shared.utils.agent.agents_md_loader import AgentsMdLoader


logger = logging.getLogger(__name__)


class AgentNotFoundError(Exception):
    """智能体未找到或已禁用时抛出。"""


class AgentAlreadyExistsError(Exception):
    """新增智能体时名称重复时抛出。"""


@dataclass
class UnifiedAgentConfig:
    """统一智能体配置（从数据库 + AGENTS.md 加载）。

    Attributes:
        name: 智能体名称（唯一标识）
        display_name: 展示名称（中文）
        description: 智能体描述
        system_prompt: 从 AGENTS.md 加载的系统提示词
        state_class: 动态生成的 AgentState 子类（可调用包装器）
        context_class: 动态生成的 AgentContext 子类（可调用包装器）
        agent_config_overrides: AgentConfig dataclass 字段覆盖
            （如 {"temperature": 0.7, "max_tokens": 4096}）
            由 parse_config_schema 从 config_schema 顶层字段提取
        mcp_tags: MCP 标签列表，用于匹配 MCP server
        enabled_tool_names: 启用的工具名称列表
        enabled_skill_names: 启用的 skill 名称列表
        agents_md_path: AGENTS.md 文件路径
        config_schema: 完整的 config_schema 三层嵌套字典（供 admin API 返回）
        tools: 工具实例列表（@tool 装饰的函数 / MCPToolToLangChainAdapter 实例）；
            None 表示尚未加载（延迟加载语义），由 _load_tools 填充；
            空列表表示已加载但无工具绑定
        _agent_row: 原始 DB 行字典（含 tool_bindings / mcp_tags 等字段），
            供 _load_tools 延迟加载工具时使用；repr=False 避免打印大量数据
    """
    name: str
    display_name: str
    description: str
    system_prompt: str
    state_class: Callable
    context_class: Callable
    agent_config_overrides: Dict[str, Any] = field(default_factory=dict)
    mcp_tags: List[str] = field(default_factory=list)
    enabled_tool_names: List[str] = field(default_factory=list)
    enabled_skill_names: List[str] = field(default_factory=list)
    agents_md_path: str = ""
    config_schema: Dict[str, Any] = field(default_factory=dict)
    tools: Optional[List[Any]] = None
    _agent_row: Dict = field(default_factory=dict, repr=False)


class AgentConfigService:
    """Agent 配置加载服务。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
        agents_md_loader: AGENTS.md 加载器

    缓存设计（2026-06-25 新增）:
        _cache: agent_name -> UnifiedAgentConfig 的进程内缓存，
            启动时由 preload_all() 预加载，读方法优先读缓存，
            写方法写 DB 后同步刷新或失效缓存。
        _default_config: 框架默认配置缓存（agent_name 为空时使用）。
        _cache_lock: asyncio.Lock，保护 _cache 字典写操作的并发安全。
        _tools_lock: asyncio.Lock，保护工具延迟加载（防止并发重复加载）。
        _tool_service / _mcp_registry: 由 lifespan 注入的外部依赖，
            供 _load_tools 加载内置工具和 MCP 工具实例。
    """

    def __init__(self, db: Any, agents_md_loader: AgentsMdLoader) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
            agents_md_loader: AGENTS.md 加载器实例

        说明:
            缓存字段 _cache / _default_config 在此初始化为空，
            需调用 preload_all() 预加载；未预加载时读方法会回退到 DB。
            _tool_service / _mcp_registry 默认为 None，需由 lifespan
            调用 set_tool_service / set_mcp_registry 注入。
        """
        self._db = db
        self._loader = agents_md_loader
        # agent_name -> UnifiedAgentConfig 的进程内缓存（tools=None 表示未加载工具）
        self._cache: Dict[str, UnifiedAgentConfig] = {}
        # 框架默认配置缓存（agent_name 为空时使用）
        self._default_config: Optional[UnifiedAgentConfig] = None
        # 保护 _cache 写操作的异步锁
        self._cache_lock = asyncio.Lock()
        # 保护工具延迟加载的异步锁（防止并发重复加载）
        self._tools_lock = asyncio.Lock()
        # 由 lifespan 注入的 ToolRegistryService 实例
        self._tool_service: Optional[Any] = None
        # 由 lifespan 注入的 MCPToolsRegistry 实例
        self._mcp_registry: Optional[Any] = None

    # ==================== 依赖注入 setter（由 lifespan 调用） ====================

    def set_tool_service(self, tool_service: Any) -> None:
        """注入 ToolRegistryService 实例（由 lifespan 调用）。

        参数:
            tool_service: ToolRegistryService 实例，供 _load_tools
                按 tool_name 加载内置 @register_tool 工具实例

        返回:
            None
        """
        self._tool_service = tool_service

    def set_mcp_registry(self, registry: Any) -> None:
        """注入 MCPToolsRegistry 实例（由 lifespan 调用）。

        参数:
            registry: MCPToolsRegistry 实例，供 _load_tools
                按 tool_name / mcp_tags 加载 MCP server 工具实例

        返回:
            None
        """
        self._mcp_registry = registry

    @staticmethod
    def _decode_jsonb(value: Any, default: Any) -> Any:
        """防御性反序列化 JSONB 字段。

        asyncpg 默认不注册 JSONB codec，从数据库读出的 JSONB 字段是 str
        类型；如果将来连接池注册了 codec，则直接是 dict/list。两种情况
        都需兼容：str 用 json.loads 解析，dict/list 原样返回，None 走默认。

        参数:
            value: 数据库返回的字段值，可能为 None / str / dict / list
            default: 当 value 为 None 时返回的默认值

        返回:
            Any: 反序列化后的 Python 对象（dict / list / 默认值）
        """
        if value is None:
            return default
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                logger.warning("Failed to decode JSONB value, fallback to default")
                return default
        return value

    def _decode_agent_row(self, row_dict: dict) -> dict:
        """对 agents 表行中的 JSONB 字段进行防御性解码并写回。

        参数:
            row_dict: 从 asyncpg Record 转换来的字典

        返回:
            dict: 已解码的字典（原地修改并返回同一对象）
        """
        for key in ("config_schema", "state_schema", "context_schema", "mcp_tags",
                     "tool_bindings"):
            default = {} if key.endswith("_schema") else []
            row_dict[key] = self._decode_jsonb(row_dict.get(key), default)
        return row_dict

    # ==================== 缓存层方法（2026-06-25 新增） ====================

    async def preload_all(self) -> None:
        """预加载所有启用的 agent 配置到缓存。

        启动时由 lifespan 调用，将 DB 中所有 enabled=TRUE 的 agent 配置
        加载到 _cache。加载的配置 tools 字段设为 None（延迟加载，保持
        MCP 懒加载语义），首次 get_agent_config 时才触发 _load_tools。

        参数:
            无

        返回:
            None

        异常:
            数据库异常会向上抛出（由调用方处理）；
            单个 agent 加载失败时记录 warning 并跳过，不中断整体预加载
        """
        rows = await self._db.fetch(
            "SELECT name FROM agents WHERE enabled = TRUE ORDER BY sort_order, name"
        )
        new_cache: Dict[str, UnifiedAgentConfig] = {}
        for row in rows:
            name = row["name"]
            try:
                config = await self._load_from_db(name)
                new_cache[name] = config
            except AgentNotFoundError:
                # 理论上不会发生（已过滤 enabled=TRUE），防御性跳过
                logger.warning("Agent disappeared during preload: %s", name)
        async with self._cache_lock:
            self._cache = new_cache
        logger.info("Preloaded %d agent config(s)", len(new_cache))

    async def _refresh_cache(self, agent_name: str) -> None:
        """重新从 DB 加载单个 agent 配置到缓存。

        写方法（create / update / bind 等）写 DB 后调用此方法同步缓存。
        重新加载的配置 tools 设为 None（延迟加载），下次 get_agent_config
        时触发 _load_tools。若 DB 中该 agent 已不存在或已禁用，则从缓存移除。

        参数:
            agent_name: 智能体名称

        返回:
            None

        异常:
            不主动抛出异常；agent 不存在或已禁用时静默从缓存移除
        """
        try:
            config = await self._load_from_db(agent_name)
        except AgentNotFoundError:
            async with self._cache_lock:
                self._cache.pop(agent_name, None)
            return
        async with self._cache_lock:
            self._cache[agent_name] = config

    async def _invalidate_cache(self, agent_name: str) -> None:
        """从缓存移除单个 agent。

        delete_agent / set_agent_enabled(enabled=False) 写 DB 后调用此方法
        使缓存失效，避免读到已删除或已禁用的配置。

        参数:
            agent_name: 智能体名称

        返回:
            None
        """
        async with self._cache_lock:
            self._cache.pop(agent_name, None)

    async def invalidate_all_cache(self) -> None:
        """清空所有缓存（含 _default_config），供 MCP 变更时调用。

        当 MCP server 配置发生变更（新增/删除/更新/启停）时，所有 agent
        的工具列表可能受影响，需清空全部缓存强制下次重新加载。

        参数:
            无

        返回:
            None
        """
        async with self._cache_lock:
            self._cache.clear()
        self._default_config = None
        logger.info("Invalidated all agent config cache")

    async def get_agent_config(self, agent_name: Optional[str] = None) -> UnifiedAgentConfig:
        """根据 agent_name 加载完整配置（带缓存 + 工具延迟加载）。

        缓存策略：
        1. agent_name 为空时查 _default_config 缓存，未命中调 _load_from_db
        2. 命名 agent 先查 _cache，未命中调 _load_from_db 并写入缓存
        3. 缓存命中但 tools=None 时，用 _tools_lock 保护触发 _load_tools
           （double-check 模式防止并发重复加载）

        当 agent_name 为空（None / ''）时，返回框架默认配置：
        - 使用 AgentState / AgentContext 基类
        - system_prompt 为空字符串（Agent 内部会回退到 BASE_SYSTEM_PROMPT）
        - 不绑定任何工具或 skill

        参数:
            agent_name: 智能体名称，为空时返回默认配置

        返回:
            UnifiedAgentConfig: 完整配置实例（含 tools 工具实例列表）

        异常:
            AgentNotFoundError: agent 不存在或已禁用时抛出（仅针对非空 agent_name）
            FileNotFoundError: agents_md_path 指向的 AGENTS.md 文件不存在时抛出
        """
        # 1. 默认配置路径
        if not agent_name:
            if self._default_config is not None and self._default_config.tools is not None:
                logger.info("[get_agent_config] return cached default config (tools already loaded, count=%d)", len(self._default_config.tools or []))
                return self._default_config
            logger.info("[get_agent_config] loading default config from DB")
            config = await self._load_from_db(None)
            if config.tools is None:
                async with self._tools_lock:
                    if config.tools is None:
                        logger.info("[get_agent_config] default config tools is None, triggering _load_tools")
                        config.tools = await self._load_tools(config._agent_row)
            self._default_config = config
            return config

        # 2. 命名 agent 路径：先查缓存
        if agent_name in self._cache:
            config = self._cache[agent_name]
            logger.info("[get_agent_config] cache hit for agent=%s, tools_loaded=%s", agent_name, config.tools is not None)
            if config.tools is None:
                async with self._tools_lock:
                    if config.tools is None:
                        logger.info("[get_agent_config] agent=%s tools is None, triggering _load_tools", agent_name)
                        config.tools = await self._load_tools(config._agent_row)
            return config

        # 3. 未命中缓存：从 DB 加载并写入缓存
        logger.info("[get_agent_config] cache miss for agent=%s, loading from DB", agent_name)
        config = await self._load_from_db(agent_name)
        async with self._cache_lock:
            self._cache[agent_name] = config
        if config.tools is None:
            async with self._tools_lock:
                if config.tools is None:
                    logger.info("[get_agent_config] agent=%s tools is None after DB load, triggering _load_tools", agent_name)
                    config.tools = await self._load_tools(config._agent_row)
        return config

    # ============================================================
    # 2026-06-29 新增：统一 Agent 构造入口 build_agent_instance()
    # ============================================================
    async def build_agent_instance(
        self,
        agent_name: Optional[str],
        session_id: str,
        message: Optional[str] = None,
        context_overrides: Optional[Dict[str, Any]] = None,
        resume: Optional[Dict[str, Any]] = None,
        state_class_kwargs: Optional[Dict[str, Any]] = None,
        system_prompt_override: Optional[str] = None,
    ):
        """统一构造入口：取配置 → 构造 context/state → 构造 AgentConfig → 初始化 Agent。

        封装 agent_router 等 chat 路由原本散落的 5 步构造流程。
        调用方只需传入业务参数，无需关心 checkpointer / store /
        AgentConfig 字段覆盖 / HumanMessage 构造等底层细节。

        参数:
            agent_name: 智能体名称（None 时使用框架默认配置）
            session_id: 会话 ID
            message: 用户消息（resume 场景可为空字符串）
            context_overrides: context 字段覆盖字典；
                保留字段（如 session_id / store_id）会被自动过滤
            resume: HITL 恢复参数；传入时构造 Command(resume=...) 而非 state_class
            state_class_kwargs: 透传给 state_class 的额外 kwargs
                （如 error_limit / limit / agent_name）
            system_prompt_override: 覆盖 config.system_prompt
                （如 KNOWLEDGE_SYSTEM_PROMPT）

        返回:
            Tuple[Agent, AgentContext, Union[AgentState, Command]]: 三元组
            - agent: 已 __ainit__ 的 Agent 实例
            - context_instance: 已填充的 AgentContext 实例
            - input_state: 已构造的 input_state
              （state_class 实例或 Command(resume=...)）

        异常:
            AgentNotFoundError: agent 不存在或已禁用（由 get_agent_config 抛出）
            RuntimeError: checkpointer / store 初始化失败
            Exception: AgentConfig 实例化或 Agent.__ainit__ 失败时透传

        说明:
            2026-06-29 引入，作为 agent_router 简化重构的统一入口。
            knowledge_router 暂未迁移（需要 HumanMessage.additional_kwargs
            注入 attachments，超出本方法能力范围）。
        """
        # 1. 取配置（继承现有缓存机制；agent 不存在时抛 AgentNotFoundError）
        config = await self.get_agent_config(agent_name)

        # 2. 构造 context_instance（保留字段过滤逻辑从 router 移到这里）
        from app.shared.utils.agent.dynamic_schema import RESERVED_CONTEXT_FIELDS
        safe_overrides = {
            k: v for k, v in (context_overrides or {}).items()
            if k not in RESERVED_CONTEXT_FIELDS
        }
        context_instance = config.context_class(
            session_id=session_id or "default",
            **safe_overrides,
        )

        # 3. 构造 input_state（HumanMessage 固定为 HumanMessage(content=message)）
        from langchain_core.messages import HumanMessage
        from langgraph.types import Command

        if resume:
            input_state = Command(resume=resume)
        else:
            human_message = HumanMessage(content=message or "")
            state_kwargs: Dict[str, Any] = {"messages": [human_message]}
            if state_class_kwargs:
                state_kwargs.update(state_class_kwargs)
            input_state = config.state_class(**state_kwargs)

        # 4. 构造 AgentConfig（保留字段如 checkpointer / store 由 service 注入）
        from app.core.agent.AgentConfig import AgentConfig
        from app.shared.utils.memory import get_async_checkpointer, get_async_store

        checkpointer = await get_async_checkpointer()
        store = await get_async_store()

        agent_config_overrides = config.agent_config_overrides or {}
        agent_config = AgentConfig(
            name=config.name,
            system_prompt=system_prompt_override or config.system_prompt,
            state_class=config.state_class,
            context_class=config.context_class,
            checkpointer=checkpointer,
            store=store,
            tools=config.tools,
            **agent_config_overrides,
        )

        # 5. 初始化 Agent（失败时由调用方负责捕获并转换为 HTTPException）
        from app.core.agent.agent import Agent
        agent = Agent(agent_config)
        await agent.__ainit__()

        logger.info(
            "[build_agent_instance] agent=%s session_id=%s resume=%s "
            "overrides_keys=%s state_kwargs_keys=%s tools_count=%d",
            config.name, session_id, bool(resume),
            list((context_overrides or {}).keys()),
            list((state_class_kwargs or {}).keys()),
            len(config.tools or []),
        )

        return agent, context_instance, input_state

    async def _load_from_db(self, agent_name: Optional[str]) -> UnifiedAgentConfig:
        """从数据库加载单个 agent 配置（不含工具实例，tools=None）。

        将原 get_agent_config 的 DB 加载逻辑抽取为私有方法，供缓存层调用。
        返回的 UnifiedAgentConfig.tools 为 None（延迟加载语义），
        _agent_row 保存原始 DB 行字典供 _load_tools 使用。

        流程（非空 agent_name）：
        1. 从 agents 表查询记录（含 enabled 校验）
        2. 通过 AgentsMdLoader 加载 AGENTS.md 内容作为 system_prompt
        3. 解析 config_schema（三层嵌套），回退到旧 state_schema + context_schema
        4. 通过 dynamic_schema 构建 state_class / context_class
        5. 从 agent_tool_bindings 加载启用的工具名称列表
        6. 从 agent_skill_bindings 加载启用的 skill 名称列表

        参数:
            agent_name: 智能体名称，为空（None / ''）时返回框架默认配置

        返回:
            UnifiedAgentConfig: 完整配置实例（tools=None，_agent_row=原始 DB 行）

        异常:
            AgentNotFoundError: agent 不存在或已禁用时抛出（仅针对非空 agent_name）
            FileNotFoundError: agents_md_path 指向的 AGENTS.md 文件不存在时抛出
        """
        # 默认配置路径
        if not agent_name:
            from app.core.agent.AgentConfig import AgentState
            from app.core.agent.AgentContext import AgentContext
            logger.info("Loading default agent config (no agent_name provided)")
            return UnifiedAgentConfig(
                name="",
                display_name="默认智能体",
                description="",
                system_prompt="",
                state_class=AgentState,
                context_class=AgentContext,
                agent_config_overrides={},
                mcp_tags=[],
                enabled_tool_names=[],
                enabled_skill_names=[],
                agents_md_path="",
                config_schema={},
                tools=None,
                _agent_row={},
            )

        row = await self._db.fetchrow(
            "SELECT * FROM agents WHERE name = $1",
            agent_name,
        )
        if not row or not row.get("enabled", False):
            logger.warning("Agent not found or disabled: %s", agent_name)
            raise AgentNotFoundError(f"Agent {agent_name} not found or disabled")

        # 解码 DB 行（含 tool_bindings / mcp_tags 等 JSONB 字段）
        row_dict = self._decode_agent_row(dict(row))

        system_prompt = self._loader.load(row_dict["agents_md_path"])

        # 2026-06-24 重构：优先读 config_schema，回退旧 state_schema + context_schema
        config_schema = row_dict.get("config_schema") or {}
        if not config_schema:
            # 回退：合并旧字段
            state_schema = row_dict.get("state_schema") or {}
            context_schema = row_dict.get("context_schema") or {}
            config_schema = {
                "state_fields": state_schema,
                "context_fields": context_schema,
            }
        parsed = parse_config_schema(config_schema)
        state_class = build_agent_state(agent_name, parsed["state_schema"])
        context_class = build_agent_context(agent_name, parsed["context_schema"])

        tool_bindings = await self._db.fetch(
            "SELECT tool_name, is_enabled FROM agent_tool_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )
        skill_bindings = await self._db.fetch(
            "SELECT skill_name, is_enabled FROM agent_skill_bindings "
            "WHERE agent_name = $1 ORDER BY sort_order",
            agent_name,
        )

        logger.info("Loaded config for agent: %s", agent_name)
        return UnifiedAgentConfig(
            name=agent_name,
            display_name=row_dict.get("display_name", ""),
            description=row_dict.get("description", ""),
            system_prompt=system_prompt,
            state_class=state_class,
            context_class=context_class,
            agent_config_overrides=parsed["agent_config_overrides"],
            mcp_tags=row_dict.get("mcp_tags", []),
            enabled_tool_names=[
                r["tool_name"] for r in tool_bindings
                if r.get("is_enabled") and "tool_name" in r
            ],
            enabled_skill_names=[
                r["skill_name"] for r in skill_bindings
                if r.get("is_enabled") and "skill_name" in r
            ],
            agents_md_path=row_dict["agents_md_path"],
            config_schema=config_schema,
            tools=None,
            _agent_row=row_dict,
        )

    async def _load_tools(self, agent_row: Dict) -> List[Any]:
        """加载 agent 的工具列表（内置 + MCP）。

        工具加载优先级：
        1. tool_bindings 直接绑定（高优先级）：遍历 agents.tool_bindings JSONB
           字段，按 tool_type 分发到 ToolRegistryService（builtin）或
           MCPToolsRegistry（mcp）加载工具实例。
        2. mcp_tags 过滤回退（低优先级）：当 tool_bindings 未加载到任何工具时，
           回退到 mcp_tags 标签过滤 MCP server 工具，保持向后兼容。

        无默认工具：tool_bindings 和 mcp_tags 都为空时返回空列表。

        MCP 工具命名约定（server.method 复合名）：
        - tool_bindings[].tool_name 格式为 "server_name.method_name"
        - 例：tool_name="amap.search" → server="amap", method="search"
        - 解析后调用 mcp_registry.get_tools_with_server(server="amap", names=["search"])
        - 同一 server 的不同 method 可独立绑定，避免跨 server 命名冲突

        参数:
            agent_row: agent 的原始 DB 行字典（含 tool_bindings / mcp_tags 字段），
                通常来自 UnifiedAgentConfig._agent_row

        返回:
            List[Any]: 工具实例列表（@tool 装饰的函数或
                MCPToolToLangChainAdapter 实例）；无工具时返回空列表

        异常:
            不主动抛出异常；工具加载失败时记录日志并跳过
        """
        agent_name = agent_row.get("name", "<unknown>")
        tools: List[Any] = []

        # 1. 加载直接绑定的工具（高优先级）
        tool_bindings = self._decode_jsonb(agent_row.get("tool_bindings"), [])
        logger.info(
            "[_load_tools] agent=%s | tool_bindings count=%d | _tool_service is None=%s | _mcp_registry is None=%s",
            agent_name,
            len(tool_bindings),
            self._tool_service is None,
            self._mcp_registry is None,
        )
        if tool_bindings:
            logger.info("[_load_tools] agent=%s | tool_bindings raw=%s", agent_name, tool_bindings)

        for binding in tool_bindings:
            if not binding.get("enabled", True):
                logger.info("[_load_tools] agent=%s | skip disabled binding=%s", agent_name, binding)
                continue
            tool_name = binding.get("tool_name")
            if not tool_name:
                logger.warning("[_load_tools] agent=%s | skip binding without tool_name: %s", agent_name, binding)
                continue
            tool_type = binding.get("tool_type", "builtin")
            logger.info(
                "[_load_tools] agent=%s | processing binding: tool_name=%s, tool_type=%s, enabled=%s",
                agent_name, tool_name, tool_type, binding.get("enabled", True),
            )
            if tool_type == "builtin" and self._tool_service:
                tool_info = await self._tool_service.get_tool_by_name(tool_name)
                if tool_info and tool_info.enabled and tool_info.tool_instance:
                    tools.append(tool_info.tool_instance)
                    logger.info(
                        "[_load_tools] agent=%s | loaded builtin tool: %s (instance=%s)",
                        agent_name, tool_name, type(tool_info.tool_instance).__name__,
                    )
                else:
                    logger.warning(
                        "[_load_tools] agent=%s | builtin tool '%s' not found or has no instance (tool_info=%s)",
                        agent_name, tool_name, tool_info,
                    )
            elif tool_type == "mcp" and self._mcp_registry:
                # 解析 server.method 复合名
                server_name, method_name = self._parse_mcp_tool_name(tool_name)
                logger.info(
                    "[_load_tools] agent=%s | parsed mcp tool: server=%s, method=%s",
                    agent_name, server_name, method_name,
                )
                if not method_name:
                    logger.warning(
                        "[_load_tools] agent=%s | MCP tool binding '%s' missing server prefix (expect 'server.method')",
                        agent_name, tool_name,
                    )
                    continue
                mcp_tools = await self._mcp_registry.get_tools_with_server_async(
                    server=server_name, names=[method_name] if method_name else None
                )
                if not mcp_tools:
                    logger.info(
                        "[_load_tools] agent=%s | no mcp tools returned for server=%s, method=%s (server may be disabled or method not found)",
                        agent_name, server_name, method_name,
                    )
                else:
                    logger.info(
                        "[_load_tools] agent=%s | mcp_registry returned %d tool(s) for server=%s, method=%s",
                        agent_name, len(mcp_tools), server_name, method_name,
                    )
                for adapted_tool, _, _ in mcp_tools:
                    tools.append(adapted_tool)
            else:
                logger.warning(
                    "[_load_tools] agent=%s | skip binding: tool_type=%s, _tool_service=%s, _mcp_registry=%s",
                    agent_name, tool_type, self._tool_service is not None, self._mcp_registry is not None,
                )

        # 2. 如果没有直接绑定，回退到 mcp_tags 过滤（保持现有逻辑）
        if not tools:
            mcp_tags = self._decode_jsonb(agent_row.get("mcp_tags"), [])
            logger.info(
                "[_load_tools] agent=%s | no tools from bindings, fallback to mcp_tags=%s",
                agent_name, mcp_tags,
            )
            if mcp_tags and self._mcp_registry:
                mcp_tools = await self._mcp_registry.get_tools_with_server_async(tags=mcp_tags)
                logger.info(
                    "[_load_tools] agent=%s | mcp_tags fallback returned %d tool(s)",
                    agent_name, len(mcp_tools),
                )
                for adapted_tool, _, _ in mcp_tools:
                    tools.append(adapted_tool)

        tool_names = [getattr(t, "name", str(t)) for t in tools]
        logger.info(
            "[_load_tools] agent=%s | completed: total=%d, tool_names=%s",
            agent_name, len(tools), tool_names,
        )
        return tools

    @staticmethod
    def _parse_mcp_tool_name(tool_name: str) -> tuple:
        """解析 MCP 工具绑定的 server.method 复合名。

        参数:
            tool_name: tool_bindings 中的 tool_name 字段值

        返回:
            tuple[str, str]: (server_name, method_name)；
            无 server 前缀时返回 (tool_name, "")，调用方应回退或跳过
        """
        if "." in tool_name:
            server, _, method = tool_name.partition(".")
            return server, method
        return tool_name, ""

    async def list_agents(self) -> List[Dict[str, Any]]:
        """列出所有启用的智能体。

        返回:
            List[Dict[str, Any]]: 智能体摘要列表，每项包含
            name / display_name / description 字段
        """
        rows = await self._db.fetch(
            "SELECT name, display_name, description FROM agents "
            "WHERE enabled = TRUE ORDER BY sort_order"
        )
        return [dict(r) for r in rows]

    async def list_all_agents_admin(self) -> List[Dict[str, Any]]:
        """Admin 端点专用：列出所有智能体（含禁用项），返回全字段。

        与 ``list_agents`` 的区别：
        - 不带 ``WHERE enabled = TRUE`` 过滤，包含已禁用的智能体
        - 返回全部数据库字段（含 config_schema / mcp_tags / sort_order 等）
        - 排序与 ``agent_admin_router`` 保持一致：先 ``sort_order``，再 ``name``

        用途：供 ``GET /api/admin/agents`` 列表端点使用，前端需要看到禁用项才能做启用/禁用切换。

        参数:
            无

        返回:
            List[Dict[str, Any]]: 智能体列表，每项包含 name / display_name /
                description / agents_md_path / state_schema / context_schema /
                config_schema / mcp_tags / enabled / sort_order / created_at /
                updated_at

        异常:
            无（数据库异常由调用方处理）
        """
        rows = await self._db.fetch(
            "SELECT name, display_name, description, agents_md_path, "
            "state_schema, context_schema, config_schema, mcp_tags, "
            "enabled, sort_order, created_at, updated_at "
            "FROM agents ORDER BY sort_order, name"
        )
        return [self._decode_agent_row(dict(r)) for r in rows]

    async def get_agent_admin(self, agent_name: str) -> Dict[str, Any]:
        """Admin 端点专用：获取单个智能体完整配置。

        与 ``get_agent_config`` 的区别：
        - 不校验 ``enabled`` 字段（admin 端点允许查看已禁用项）
        - 不加载 AGENTS.md、不构造 state_class / context_class（避免无谓 IO）
        - 直接返回 dict，并在 result 中追加 ``agent_config_overrides`` 拆分结果

        用途：供 ``GET /api/admin/agents/{name}`` 详情端点使用。

        参数:
            agent_name: 智能体名称（唯一标识）

        返回:
            Dict[str, Any]: 智能体完整记录 + ``agent_config_overrides`` 字段
                （由 ``parse_config_schema`` 从 ``config_schema`` 顶层字段提取）

        异常:
            AgentNotFoundError: 智能体不存在时抛出
        """
        row = await self._db.fetchrow(
            "SELECT name, display_name, description, agents_md_path, "
            "state_schema, context_schema, config_schema, mcp_tags, "
            "enabled, sort_order, created_at, updated_at "
            "FROM agents WHERE name = $1",
            agent_name,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        result = dict(row)
        # 防御性反序列化：asyncpg 未注册 JSONB codec 时，config_schema 可能是 str
        self._decode_agent_row(result)
        config_schema = result.get("config_schema") or {}
        if not isinstance(config_schema, dict):
            config_schema = {}
            result["config_schema"] = config_schema
        # 函数内延迟 import，与 agent_admin_router.get_agent 历史 import 模式保持一致
        from app.shared.utils.agent.dynamic_schema import parse_config_schema
        parsed = parse_config_schema(config_schema)
        result["agent_config_overrides"] = parsed["agent_config_overrides"]
        return result

    async def create_agent(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """Admin 创建智能体（2026-06-24 支持 config_schema）。

        参数:
            config: 智能体配置字典，必须包含以下键：
                - name (str): 智能体名称（唯一，符合 [a-z0-9_]+）
                - display_name (str): 显示名
                - agents_md_path (str): AGENTS.md 文件路径（文件必须存在）
              可选键：
                - description: 智能体描述
                - config_schema: 三层嵌套字典（含 state_fields / context_fields /
                  顶层 AgentConfig 字段覆盖）
                - mcp_tags: MCP 标签列表
                - enabled: 是否启用（默认 True）
                - sort_order: 排序值（默认 0）

        返回:
            Dict[str, Any]: 新创建的智能体记录

        异常:
            KeyError: 缺少必需键时抛出
            ValueError: name 格式非法 / agents_md_path 不存在 / config_schema 包含保留字段
            AgentAlreadyExistsError: name 已存在时抛出
            FileNotFoundError: AGENTS.md 文件不存在时抛出
        """
        required_keys = ["name", "display_name", "agents_md_path"]
        for key in required_keys:
            if key not in config:
                raise KeyError(f"create_agent 缺少必需键: {key}")

        # name 格式校验
        import re as _re
        if not _re.match(r"^[a-z0-9_]{3,50}$", config["name"]):
            raise ValueError(
                "name 必须由小写字母 / 下划线组成（数字可选），长度 3-50 字符"
            )

        # agents_md_path 文件存在性校验
        from pathlib import Path as _Path
        if not _Path(config["agents_md_path"]).is_file():
            raise FileNotFoundError(
                f"AGENTS.md 文件不存在: {config['agents_md_path']}"
            )

        # config_schema 校验
        config_schema = config.get("config_schema") or {}
        if not isinstance(config_schema, dict):
            raise ValueError("config_schema 必须是 dict")
        for reserved in RESERVED_CONFIG_FIELDS:
            if reserved in config_schema:
                raise ValueError(
                    f"config_schema 顶层不能包含保留字段 '{reserved}'"
                )

        # 检查 name 是否已存在
        existing = await self._db.fetchrow(
            "SELECT name FROM agents WHERE name = $1",
            config["name"],
        )
        if existing:
            raise AgentAlreadyExistsError(
                f"Agent '{config['name']}' 已存在"
            )

        # 同时写入 config_schema + 旧 state_schema / context_schema（向后兼容）
        parsed = parse_config_schema(config_schema)
        legacy_state = parsed["state_schema"]
        legacy_context = parsed["context_schema"]

        try:
            row = await self._db.fetchrow(
                """
                INSERT INTO agents (name, display_name, description, agents_md_path,
                                    state_schema, context_schema, config_schema,
                                    mcp_tags, enabled, sort_order)
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                RETURNING *
                """,
                config["name"], config["display_name"], config.get("description", ""),
                config["agents_md_path"], json.dumps(legacy_state), json.dumps(legacy_context),
                json.dumps(config_schema), json.dumps(config.get("mcp_tags", [])),
                config.get("enabled", True), config.get("sort_order", 0),
            )
        except Exception as e:
            # asyncpg.UniqueViolationError 等
            err_msg = str(e)
            if "duplicate key" in err_msg.lower() or "unique" in err_msg.lower():
                raise AgentAlreadyExistsError(
                    f"Agent '{config['name']}' 已存在"
                ) from e
            raise

        logger.info("Created agent: %s", config["name"])
        # 写 DB 后同步缓存（tools 设为 None，延迟加载）
        await self._refresh_cache(config["name"])
        return self._decode_agent_row(dict(row))

    async def delete_agent(self, agent_name: str) -> None:
        """删除智能体（级联清理工具/技能绑定）。

        参数:
            agent_name: 智能体名称

        返回:
            None

        异常:
            AgentNotFoundError: 智能体不存在时抛出
        """
        existing = await self._db.fetchrow(
            "SELECT name FROM agents WHERE name = $1", agent_name,
        )
        if not existing:
            raise AgentNotFoundError(f"Agent {agent_name} not found")

        # 级联清理
        await self._db.execute(
            "DELETE FROM agent_tool_bindings WHERE agent_name = $1", agent_name,
        )
        await self._db.execute(
            "DELETE FROM agent_skill_bindings WHERE agent_name = $1", agent_name,
        )
        await self._db.execute(
            "DELETE FROM agents WHERE name = $1", agent_name,
        )
        # 写 DB 后使缓存失效
        await self._invalidate_cache(agent_name)
        logger.info("Deleted agent: %s", agent_name)

    async def set_agent_enabled(self, agent_name: str, enabled: bool) -> Dict[str, Any]:
        """启用 / 禁用单个智能体。

        参数:
            agent_name: 智能体名称
            enabled: True 启用 / False 禁用

        返回:
            Dict[str, Any]: 更新后的记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE agents SET enabled = $2, updated_at = CURRENT_TIMESTAMP
            WHERE name = $1 RETURNING *
            """,
            agent_name, enabled,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        logger.info("Set agent %s enabled=%s", agent_name, enabled)
        # 写 DB 后同步缓存：启用时刷新缓存，禁用时失效缓存
        if enabled:
            await self._refresh_cache(agent_name)
        else:
            await self._invalidate_cache(agent_name)
        return self._decode_agent_row(dict(row))

    async def update_agent_basic_info(
        self, agent_name: str, display_name: str, description: str
    ) -> Dict[str, Any]:
        """更新智能体基本信息（display_name / description）。

        参数:
            agent_name: 智能体名称
            display_name: 新的显示名称
            description: 新的描述

        返回:
            Dict[str, Any]: 更新后的记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE agents SET display_name = $2, description = $3,
                              updated_at = CURRENT_TIMESTAMP
            WHERE name = $1 RETURNING *
            """,
            agent_name, display_name, description,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        logger.info(
            "Updated agent basic info: %s display_name=%s",
            agent_name, display_name,
        )
        await self._refresh_cache(agent_name)
        return self._decode_agent_row(dict(row))

    async def update_agent_config_schema(
        self, agent_name: str, config_schema: Dict[str, Any]
    ) -> Dict[str, Any]:
        """全量替换 config_schema。

        参数:
            agent_name: 智能体名称
            config_schema: 三层嵌套字典

        返回:
            Dict[str, Any]: 更新后的记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
            ValueError: config_schema 校验失败
        """
        if not isinstance(config_schema, dict):
            raise ValueError("config_schema 必须是 dict")
        for reserved in RESERVED_CONFIG_FIELDS:
            if reserved in config_schema:
                raise ValueError(
                    f"config_schema 顶层不能包含保留字段 '{reserved}'"
                )

        parsed = parse_config_schema(config_schema)
        legacy_state = parsed["state_schema"]
        legacy_context = parsed["context_schema"]

        row = await self._db.fetchrow(
            """
            UPDATE agents
            SET config_schema = $2,
                state_schema = $3,
                context_schema = $4,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            RETURNING *
            """,
            agent_name, json.dumps(config_schema), json.dumps(legacy_state), json.dumps(legacy_context),
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        logger.info("Updated config_schema for agent: %s", agent_name)
        # 写 DB 后同步缓存（tools 设为 None，延迟重新加载）
        await self._refresh_cache(agent_name)
        return self._decode_agent_row(dict(row))

    async def add_agent_config_field(
        self, agent_name: str, section: str, field_name: str, field_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        """增量添加 config_schema 字段。

        参数:
            agent_name: 智能体名称
            section: 字段所属 section，可选值：
                - "root"：顶层 AgentConfig 字段覆盖
                - "state_fields"：state 扩展字段
                - "context_fields"：context 扩展字段
            field_name: 字段名
            field_def: 字段定义，如 {"type": "int", "default": 0}

        返回:
            Dict[str, Any]: 更新后的记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
            ValueError: 非法 section / field_def 格式 / 重复字段名 / 保留字段
        """
        if section not in ("root", "state_fields", "context_fields"):
            raise ValueError(
                f"section 必须是 root / state_fields / context_fields 之一，收到: {section}"
            )
        if not isinstance(field_def, dict) or "type" not in field_def:
            raise ValueError("field_def 必须包含 'type' 键")

        # 读取现有 config_schema
        row = await self._db.fetchrow(
            "SELECT config_schema FROM agents WHERE name = $1", agent_name,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")

        config_schema = self._decode_jsonb(row.get("config_schema"), {})
        if not config_schema:
            config_schema = {"state_fields": {}, "context_fields": {}}

        # 校验 section 中的字段冲突（已存在则覆盖，避免前端"先删后加"失败时中断）
        target_section = config_schema if section == "root" else (
            config_schema.setdefault(section, {})
        )
        # root section 校验保留字段
        if section == "root" and field_name in RESERVED_CONFIG_FIELDS:
            raise ValueError(
                f"不能添加保留字段 '{field_name}' 到 root section"
            )

        target_section[field_name] = field_def

        return await self.update_agent_config_schema(agent_name, config_schema)

    async def update_agent_config_field(
        self, agent_name: str, section: str, field_name: str, field_def: Dict[str, Any]
    ) -> Dict[str, Any]:
        """直接覆盖 config_schema 中已存在的字段（无需先删后加）。

        参数:
            agent_name: 智能体名称
            section: 字段所属 section，可选值：
                - "root"：顶层 AgentConfig 字段覆盖
                - "state_fields"：state 扩展字段
                - "context_fields"：context 扩展字段
            field_name: 字段名
            field_def: 字段定义，如 {"type": "int", "default": 0}

        返回:
            Dict[str, Any]: 更新后的记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
            ValueError: 非法 section / field_def 格式 / 保留字段 / 字段不存在
        """
        if section not in ("root", "state_fields", "context_fields"):
            raise ValueError(
                f"section 必须是 root / state_fields / context_fields 之一，收到: {section}"
            )
        if not isinstance(field_def, dict) or "type" not in field_def:
            raise ValueError("field_def 必须包含 'type' 键")

        row = await self._db.fetchrow(
            "SELECT config_schema FROM agents WHERE name = $1", agent_name,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")

        config_schema = self._decode_jsonb(row.get("config_schema"), {})
        if not config_schema:
            config_schema = {"state_fields": {}, "context_fields": {}}

        target_section = config_schema if section == "root" else (
            config_schema.setdefault(section, {})
        )
        if field_name not in target_section:
            raise ValueError(
                f"字段 '{field_name}' 不存在于 section '{section}'，无法修改"
            )
        if section == "root" and field_name in RESERVED_CONFIG_FIELDS:
            raise ValueError(
                f"不能修改保留字段 '{field_name}'"
            )

        target_section[field_name] = field_def

        return await self.update_agent_config_schema(agent_name, config_schema)

    async def delete_agent_config_field(
        self, agent_name: str, section: str, field_name: str
    ) -> Dict[str, Any]:
        """增量删除 config_schema 字段（幂等删除）。

        参数:
            agent_name: 智能体名称
            section: 同 add_agent_config_field
            field_name: 字段名

        返回:
            Dict[str, Any]: 更新后的记录；若字段不存在则直接返回当前记录

        异常:
            AgentNotFoundError: 智能体不存在时抛出
            ValueError: 非法 section
        """
        if section not in ("root", "state_fields", "context_fields"):
            raise ValueError(
                f"section 必须是 root / state_fields / context_fields 之一，收到: {section}"
            )

        row = await self._db.fetchrow(
            "SELECT config_schema FROM agents WHERE name = $1", agent_name,
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")

        config_schema = self._decode_jsonb(row.get("config_schema"), {})
        if not config_schema:
            # config_schema 为空时，目标状态已经是字段不存在，直接返回
            return self._decode_agent_row(dict(row))

        if section == "root":
            target_section = config_schema
        else:
            target_section = config_schema.get(section) or {}

        if field_name not in target_section:
            # 幂等删除：字段不存在视为已成功
            return self._decode_agent_row(dict(row))

        del target_section[field_name]

        return await self.update_agent_config_schema(agent_name, config_schema)

    async def bind_tool(self, agent_name: str, tool_name: str, enabled: bool = True) -> None:
        """绑定/解绑工具。

        参数:
            agent_name: 智能体名称
            tool_name: 工具名称
            enabled: True 表示启用，False 表示禁用

        返回:
            None
        """
        await self._db.execute(
            """
            INSERT INTO agent_tool_bindings (agent_name, tool_name, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (agent_name, tool_name) DO UPDATE SET is_enabled = $3
            """,
            agent_name, tool_name, enabled,
        )
        logger.info("Bound tool %s to agent %s (enabled=%s)", tool_name, agent_name, enabled)
        # 写 DB 后同步缓存（tools 设为 None，延迟重新加载）
        await self._refresh_cache(agent_name)

    async def bind_skill(self, agent_name: str, skill_name: str, enabled: bool = True) -> None:
        """绑定/解绑 skill。

        参数:
            agent_name: 智能体名称
            skill_name: skill 名称
            enabled: True 表示启用，False 表示禁用

        返回:
            None
        """
        await self._db.execute(
            """
            INSERT INTO agent_skill_bindings (agent_name, skill_name, is_enabled)
            VALUES ($1, $2, $3)
            ON CONFLICT (agent_name, skill_name) DO UPDATE SET is_enabled = $3
            """,
            agent_name, skill_name, enabled,
        )
        logger.info("Bound skill %s to agent %s (enabled=%s)", skill_name, agent_name, enabled)
        # 写 DB 后同步缓存（tools 设为 None，延迟重新加载）
        await self._refresh_cache(agent_name)

    async def update_tool_bindings(self, agent_name: str, bindings: List[Dict]) -> Dict:
        """更新 agent 的工具绑定列表（直接写入 agents.tool_bindings JSONB 字段）。

        参数:
            agent_name: 智能体名称
            bindings: 工具绑定列表，格式：
                [{"tool_name": str, "tool_type": str, "enabled": bool,
                  "sort_order": int}, ...]
                - tool_name: 工具唯一标识
                - tool_type: 工具来源类型（"builtin" / "mcp" / "skill"），
                  默认 "builtin"
                - enabled: 是否启用，默认 True
                - sort_order: 排序权重，默认 0

        返回:
            Dict[str, Any]: 更新后的 agent 行字典（含反序列化后的 JSONB 字段）

        异常:
            AgentNotFoundError: agent 不存在时抛出
        """
        row = await self._db.fetchrow(
            "UPDATE agents SET tool_bindings = $2, updated_at = CURRENT_TIMESTAMP "
            "WHERE name = $1 RETURNING *",
            agent_name, json.dumps(bindings),
        )
        if not row:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        # 写 DB 后同步缓存（tools 设为 None，延迟重新加载）
        await self._refresh_cache(agent_name)
        logger.info("Updated tool_bindings for agent: %s", agent_name)
        return self._decode_agent_row(dict(row))

    async def get_tool_bindings(self, agent_name: str) -> List[Dict]:
        """获取 agent 的工具绑定列表（读取 agents.tool_bindings JSONB 字段）。

        参数:
            agent_name: 智能体名称（唯一标识）

        返回:
            List[Dict]: 工具绑定列表，每项格式：
                [{"tool_name": str, "tool_type": str, "enabled": bool,
                  "sort_order": int}, ...]
                agent 不存在或字段为空时返回空列表 []

        异常:
            AgentNotFoundError: agent 不存在时抛出
        """
        row = await self._db.fetchrow(
            "SELECT tool_bindings FROM agents WHERE name = $1",
            agent_name,
        )
        if row is None:
            raise AgentNotFoundError(f"Agent {agent_name} not found")
        return self._decode_jsonb(row.get("tool_bindings"), [])

    async def check_name_unique(self, name: str) -> bool:
        """检查智能体名称是否可用。

        参数:
            name: 待校验名称

        返回:
            bool: True 表示可用，False 表示已存在

        异常:
            无（数据库异常由调用方处理）
        """
        existing = await self._db.fetchrow(
            "SELECT 1 FROM agents WHERE name = $1 LIMIT 1", name,
        )
        return existing is None
