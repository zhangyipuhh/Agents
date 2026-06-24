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


class AgentConfigService:
    """Agent 配置加载服务。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
        agents_md_loader: AGENTS.md 加载器
    """

    def __init__(self, db: Any, agents_md_loader: AgentsMdLoader) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
            agents_md_loader: AGENTS.md 加载器实例
        """
        self._db = db
        self._loader = agents_md_loader

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
        for key in ("config_schema", "state_schema", "context_schema", "mcp_tags"):
            default = {} if key.endswith("_schema") else []
            row_dict[key] = self._decode_jsonb(row_dict.get(key), default)
        return row_dict

    async def get_agent_config(self, agent_name: Optional[str] = None) -> UnifiedAgentConfig:
        """根据 agent_name 加载完整配置。

        当 agent_name 为空（None / ''）时，返回框架默认配置：
        - 使用 AgentState / AgentContext 基类
        - system_prompt 为空字符串（Agent 内部会回退到 BASE_SYSTEM_PROMPT）
        - 不绑定任何工具或 skill

        流程（非空 agent_name）：
        1. 从 agents 表查询记录（含 enabled 校验）
        2. 通过 AgentsMdLoader 加载 AGENTS.md 内容作为 system_prompt
        3. 解析 config_schema（三层嵌套），回退到旧 state_schema + context_schema
        4. 通过 dynamic_schema 构建 state_class / context_class
        5. 从 agent_tool_bindings 加载启用的工具列表
        6. 从 agent_skill_bindings 加载启用的 skill 列表

        参数:
            agent_name: 智能体名称，为空时返回默认配置

        返回:
            UnifiedAgentConfig: 完整配置实例（含 agent_config_overrides）

        异常:
            AgentNotFoundError: agent 不存在或已禁用时抛出（仅针对非空 agent_name）
            FileNotFoundError: agents_md_path 指向的 AGENTS.md 文件不存在时抛出
        """
        if not agent_name:
            from app.core.agent.AgentConfig import AgentState
            from app.core.agent.AgentContext import AgentContext
            logger.info("Using default agent config (no agent_name provided)")
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
            )

        row = await self._db.fetchrow(
            "SELECT * FROM agents WHERE name = $1",
            agent_name,
        )
        if not row or not row.get("enabled", False):
            logger.warning("Agent not found or disabled: %s", agent_name)
            raise AgentNotFoundError(f"Agent {agent_name} not found or disabled")

        system_prompt = self._loader.load(row["agents_md_path"])

        # 2026-06-24 重构：优先读 config_schema，回退旧 state_schema + context_schema
        config_schema = self._decode_jsonb(row.get("config_schema"), {})
        if not config_schema:
            # 回退：合并旧字段
            state_schema = self._decode_jsonb(row.get("state_schema"), {})
            context_schema = self._decode_jsonb(row.get("context_schema"), {})
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
            display_name=row.get("display_name", ""),
            description=row.get("description", ""),
            system_prompt=system_prompt,
            state_class=state_class,
            context_class=context_class,
            agent_config_overrides=parsed["agent_config_overrides"],
            mcp_tags=self._decode_jsonb(row.get("mcp_tags"), []),
            enabled_tool_names=[
                r["tool_name"] for r in tool_bindings
                if r.get("is_enabled") and "tool_name" in r
            ],
            enabled_skill_names=[
                r["skill_name"] for r in skill_bindings
                if r.get("is_enabled") and "skill_name" in r
            ],
            agents_md_path=row["agents_md_path"],
            config_schema=config_schema,
        )

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
                "name 必须由小写字母 / 数字 / 下划线组成，长度 3-50 字符"
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
