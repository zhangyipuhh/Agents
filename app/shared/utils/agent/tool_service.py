#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ToolRegistryService 模块

工具注册中心服务：从 DB tools 表加载工具元数据 + 动态导入工具模块获取 @tool 实例，
提供工具的 CRUD、缓存、未注册扫描能力，供 admin router 和 AgentConfigService 使用。

核心职责：
1. preload_all：启动时动态导入 app/core/tools/ 和 app/shared/tools/skills/ 下所有 .py 模块，
   触发 @register_tool + @tool 装饰器执行，从 ToolRegistry._tools 获取工具实例，
   与 DB tools 表按 name 关联后缓存到内存。
2. 读方法（list_tools / get_tool_by_name / get_tools_by_names）：优先读缓存，缓存未命中回退 DB。
3. 写方法（create_tool / update_tool / delete_tool / set_tool_enabled）：写 DB 后同步刷新/失效缓存。
4. scan_unregistered：用 ast.parse 扫描源码目录，找出未在 DB 注册的 @tool 函数。

设计决策：
- 缓存仅存 enabled=TRUE 的工具（preload_all 过滤），减少运行时内存占用。
- tool_instance 可为 None（DB 有记录但 ToolRegistry 未注册的场景，如纯 @tool 未加 @register_tool）。
- JSONB 字段（args_schema）使用 _decode_jsonb 防御性反序列化，兼容 asyncpg 未注册 codec 的场景。
- 动态导入模块失败时 try/except 记录日志，不中断整个 preload 过程。

Date: 2026-06-25
Author: AI Assistant
"""

import ast
import asyncio
import importlib
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# 工具源码根目录（相对项目根），preload_all 和 scan_unregistered 共用
_TOOL_ROOTS = [
    "app/core/tools",
    "app/shared/tools/skills",
]

# 项目根目录：tool_service.py 位于 app/shared/utils/agent/tool_service.py，
# 向上 4 级 parents[4] 到达项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[4]

# 框架注入参数，扫描时从 args_schema 中排除（这些参数由 LangGraph 运行时注入，不暴露给 LLM）
_FRAMEWORK_PARAMS = {"runtime", "self", "cls"}


@dataclass
class ToolInfo:
    """工具信息数据类（DB 元数据 + 运行时工具实例）。

    Attributes:
        name: 工具唯一标识（与 @tool 函数名 / DB name 一致）
        display_name: 展示名称（管理界面用）
        category: 工具分类（如 filesystem / sandbox / mcp / map 等）
        description: 工具描述（来自 docstring 摘要）
        module_path: Python 模块路径（如 app.core.tools.BaseTools）
        file_path: 源文件相对路径（如 app/core/tools/BaseTools.py，使用正斜杠）
        args_schema: 参数 schema 字典，格式 {param_name: {"type": str, "required": bool, "default": str?}}
        return_description: 返回值类型描述（从 ast.returns 提取的注解字符串）
        function_description: 函数完整描述（docstring 全文）
        enabled: 是否启用
        tool_instance: @tool 装饰的函数实例（DB 有记录但 ToolRegistry 未注册时为 None）
    """
    name: str
    display_name: str
    category: str
    description: str
    module_path: str
    file_path: str
    args_schema: Dict[str, Any]
    return_description: str
    function_description: str
    enabled: bool
    tool_instance: Optional[Any] = None


class ToolNotFoundError(Exception):
    """工具未找到时抛出。"""


class ToolAlreadyExistsError(Exception):
    """工具名称重复时抛出。"""


class ToolRegistryService:
    """工具注册中心服务。

    负责 DB tools 表的 CRUD + 内存缓存 + 源码扫描，供 admin router 和
    AgentConfigService 使用。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法（asyncpg 风格）
    """

    # JSONB 字段：args_schema 需要在读出时防御性反序列化
    _JSONB_FIELDS = ("args_schema",)

    def __init__(self, db: Any) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
        """
        self._db = db
        self._cache: Dict[str, ToolInfo] = {}
        # asyncio.Lock 延迟初始化：避免在无事件循环时创建报错，
        # 同时兼容 asyncio.run() 每次创建新事件循环的测试场景
        self._cache_lock: Optional[asyncio.Lock] = None

    # ==================== 工具方法 ====================

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

    def _decode_row(self, row: Any) -> Optional[Dict[str, Any]]:
        """将 DB row 转 dict 并反序列化 JSONB 字段。

        参数:
            row: asyncpg 的 Record 对象，可能为 None

        返回:
            Optional[Dict]: 反序列化后的字典；row 为 None 时返回 None
        """
        if row is None:
            return None
        result = dict(row)
        for f in self._JSONB_FIELDS:
            if f in result:
                result[f] = self._decode_jsonb(result[f], {})
        return result

    @staticmethod
    def _get_tool_instance_from_module(module_path: str, name: str) -> Optional[Any]:
        """从已导入的模块路径中动态获取 @tool 装饰后的工具实例。

        当 ToolRegistry 中未找到 @register_tool 注册记录时，
        通过 module_path 定位模块并 getattr 获取工具实例，
        补偿仅有 @tool 而无 @register_tool 的内置工具。

        参数:
            module_path: Python 模块路径（如 app.core.tools.BaseTools）
            name: 工具函数名（如 get_current_time）

        返回:
            Optional[Any]: @tool 装饰后的工具实例；获取失败时返回 None
        """
        if not module_path or not name:
            return None
        try:
            mod = importlib.import_module(module_path)
            obj = getattr(mod, name, None)
            if obj is not None:
                return obj
        except Exception as e:
            logger.debug(
                "Failed to get tool instance from module %s: %s", module_path, e
            )
        return None

    def _build_tool_info(
        self, row_dict: Dict[str, Any], registered: Dict[str, dict]
    ) -> ToolInfo:
        """从 DB row dict + ToolRegistry 已注册字典构造 ToolInfo。

        参数:
            row_dict: 已经过 _decode_row 反序列化的 DB 行字典
            registered: ToolRegistry.list_all() 返回的工具注册字典，
                key=tool_name，value={"func", "agent", "description", "module_path"}

        返回:
            ToolInfo: 工具信息实例（含 tool_instance，未注册时尝试从模块动态获取）
        """
        name = row_dict.get("name", "")
        reg_entry = registered.get(name)
        if reg_entry:
            tool_instance = reg_entry["func"]
        else:
            tool_instance = self._get_tool_instance_from_module(
                row_dict.get("module_path", ""), name
            )
        return ToolInfo(
            name=name,
            display_name=row_dict.get("display_name", ""),
            category=row_dict.get("category", ""),
            description=row_dict.get("description", ""),
            module_path=row_dict.get("module_path", ""),
            file_path=row_dict.get("file_path", ""),
            args_schema=row_dict.get("args_schema") or {},
            return_description=row_dict.get("return_description", ""),
            function_description=row_dict.get("function_description", ""),
            enabled=row_dict.get("enabled", True),
            tool_instance=tool_instance,
        )

    @staticmethod
    def _tool_info_to_dict(info: ToolInfo) -> Dict[str, Any]:
        """将 ToolInfo 转为字典（不含 tool_instance，避免不可序列化）。

        参数:
            info: ToolInfo 实例

        返回:
            Dict[str, Any]: 工具元数据字典
        """
        return {
            "name": info.name,
            "display_name": info.display_name,
            "category": info.category,
            "description": info.description,
            "module_path": info.module_path,
            "file_path": info.file_path,
            "args_schema": info.args_schema,
            "return_description": info.return_description,
            "function_description": info.function_description,
            "enabled": info.enabled,
        }

    async def _ensure_lock(self) -> asyncio.Lock:
        """延迟创建 asyncio.Lock，避免无事件循环时报错。

        返回:
            asyncio.Lock: 缓存锁实例
        """
        if self._cache_lock is None:
            self._cache_lock = asyncio.Lock()
        return self._cache_lock

    # ==================== SubTask 2.3: preload_all ====================

    async def preload_all(self) -> None:
        """预加载所有工具到缓存。

        流程：
        1. 动态导入 app/core/tools/ 和 app/shared/tools/skills/ 下所有 .py 模块，
           触发 @register_tool + @tool 装饰器执行。
        2. 从 ToolRegistry._tools 获取已注册的工具实例字典。
        3. 从 DB 读取所有 tools 记录（含禁用项）。
        4. 按 name 关联 DB 记录与 ToolRegistry 实例，构造 ToolInfo。
        5. 原子替换整个缓存。

        参数:
            无

        返回:
            None

        异常:
            不主动抛出异常；动态导入模块失败时记录 warning 并继续
        """
        # 1. 动态导入所有工具模块，触发装饰器注册
        await self._import_tool_modules()

        # 2. 从 ToolRegistry 获取已注册的工具实例
        from app.shared.tools.registry import ToolRegistry
        registered = ToolRegistry.list_all()

        # 3. 从 DB 读取所有工具记录（含禁用项，确保缓存是 DB 完整镜像）
        rows = await self._db.fetch(
            "SELECT * FROM tools ORDER BY sort_order, name"
        )

        # 4. 构建新缓存（先在锁外构建，减少锁持有时间）
        new_cache: Dict[str, ToolInfo] = {}
        for row in rows:
            decoded = self._decode_row(row)
            info = self._build_tool_info(decoded, registered)
            new_cache[info.name] = info

        # 5. 原子替换缓存
        lock = await self._ensure_lock()
        async with lock:
            self._cache = new_cache
        logger.info("Preloaded %d tools into cache", len(new_cache))

    async def _import_tool_modules(self) -> None:
        """动态导入工具模块根目录下所有 .py 文件。

        遍历 _TOOL_ROOTS 中配置的目录，递归查找 .py 文件并 importlib.import_module，
        触发 @register_tool + @tool 装饰器执行，使工具注册到 ToolRegistry._tools。

        跳过 __init__.py 文件；导入失败时记录 warning 不中断。

        参数:
            无

        返回:
            None

        异常:
            不主动抛出异常；单个模块导入失败时记录日志并继续
        """
        for root_rel in _TOOL_ROOTS:
            root_abs = _PROJECT_ROOT / root_rel
            if not root_abs.exists():
                logger.warning("Tool root directory not found: %s", root_abs)
                continue

            for py_file in sorted(root_abs.rglob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                # 计算模块路径：相对项目根，去掉 .py 后缀，目录分隔符转为 .
                rel_path = py_file.relative_to(_PROJECT_ROOT)
                module_path = ".".join(rel_path.with_suffix("").parts)
                try:
                    importlib.import_module(module_path)
                except Exception as e:
                    logger.warning(
                        "Failed to import tool module %s: %s", module_path, e
                    )

    # ==================== SubTask 2.4: 读方法（优先读缓存） ====================

    async def list_tools(self) -> List[Dict[str, Any]]:
        """列出所有工具（优先读缓存）。

        缓存命中时返回缓存中所有工具的元数据字典（不含 tool_instance）；
        缓存为空时回退 DB 查询所有工具（含禁用项）。

        参数:
            无

        返回:
            List[Dict[str, Any]]: 工具元数据列表，每项包含
                name / display_name / category / description / module_path /
                file_path / args_schema / return_description /
                function_description / enabled
        """
        # 优先读缓存
        if self._cache:
            return [
                self._tool_info_to_dict(info) for info in self._cache.values()
            ]

        # 缓存为空，回退 DB 查询（含禁用项，供 admin 查看）
        rows = await self._db.fetch(
            "SELECT * FROM tools ORDER BY sort_order, name"
        )
        return [self._decode_row(r) for r in rows]

    async def get_tool_by_name(self, name: str) -> Optional[ToolInfo]:
        """获取单个工具（优先读缓存）。

        缓存命中时直接返回 ToolInfo；缓存未命中时查 DB 并回填缓存。

        参数:
            name: 工具名称（唯一标识）

        返回:
            Optional[ToolInfo]: 工具信息实例（含 tool_instance）；
                不存在时返回 None
        """
        # 优先读缓存
        if name in self._cache:
            return self._cache[name]

        # 缓存未命中，查 DB
        row = await self._db.fetchrow(
            "SELECT * FROM tools WHERE name = $1", name
        )
        if not row:
            return None

        from app.shared.tools.registry import ToolRegistry
        registered = ToolRegistry.list_all()
        info = self._build_tool_info(self._decode_row(row), registered)

        # 回填缓存
        lock = await self._ensure_lock()
        async with lock:
            self._cache[name] = info
        return info

    async def get_tools_by_names(self, names: List[str]) -> List[Any]:
        """批量获取工具实例（@tool 装饰的函数）。

        遍历 names 列表，对每个名称获取 ToolInfo，提取 tool_instance。
        跳过不存在、tool_instance 为 None 或已禁用的工具（记录 warning）。

        参数:
            names: 工具名称列表

        返回:
            List[Any]: 工具实例列表（@tool 装饰的函数）；
                不存在、未注册或已禁用的工具被跳过
        """
        result: List[Any] = []
        for name in names:
            info = await self.get_tool_by_name(name)
            if info is None:
                logger.warning("Tool not found: %s", name)
                continue
            if not info.enabled:
                logger.info("Tool '%s' is disabled, skip loading", name)
                continue
            if info.tool_instance is None:
                logger.warning(
                    "Tool '%s' has no registered instance (missing @register_tool?)",
                    name,
                )
                continue
            result.append(info.tool_instance)
        return result

    # ==================== SubTask 2.5: 写方法（写 DB + 同步缓存） ====================

    async def create_tool(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """注册新工具（写 DB + 刷新缓存）。

        参数:
            config: 工具配置字典，必须包含:
                - name (str): 工具唯一名称
                - category (str): 工具分类
                - module_path (str): Python 模块路径
                - file_path (str): 源文件相对路径
              可选键:
                - display_name: 展示名称（默认空字符串）
                - description: 工具描述
                - args_schema: 参数 schema 字典
                - return_description: 返回值描述
                - function_description: 函数完整描述
                - enabled: 是否启用（默认 True）
                - sort_order: 排序权重（默认 0）

        返回:
            Dict[str, Any]: 新创建的工具记录（含反序列化后的 args_schema）

        异常:
            KeyError: 缺少必需键 name 时抛出
            ToolAlreadyExistsError: name 已存在时抛出
        """
        if "name" not in config:
            raise KeyError("create_tool 缺少必需键: name")

        # 检查 name 是否已存在
        existing = await self._db.fetchrow(
            "SELECT name FROM tools WHERE name = $1", config["name"]
        )
        if existing:
            raise ToolAlreadyExistsError(
                f"Tool '{config['name']}' already exists"
            )

        row = await self._db.fetchrow(
            """
            INSERT INTO tools (name, display_name, category, description,
                               module_path, file_path, args_schema,
                               return_description, function_description,
                               enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
            RETURNING *
            """,
            config["name"],
            config.get("display_name", ""),
            config.get("category", ""),
            config.get("description", ""),
            config.get("module_path", ""),
            config.get("file_path", ""),
            json.dumps(config.get("args_schema", {})),
            config.get("return_description", ""),
            config.get("function_description", ""),
            config.get("enabled", True),
            config.get("sort_order", 0),
        )
        result = self._decode_row(row)

        # 刷新缓存（若新工具 enabled=TRUE 则加入缓存）
        await self._refresh_cache(config["name"])
        logger.info("Created tool: %s", config["name"])
        return result

    async def update_tool(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """更新工具配置（写 DB + 刷新缓存）。

        部分更新：仅覆盖 config 中显式传入的字段，未传入字段保持数据库原值。

        参数:
            name: 工具名称
            config: 工具配置字典（字段同 create_tool，但 name 不可改）

        返回:
            Dict[str, Any]: 更新后的工具记录

        异常:
            ToolNotFoundError: 工具不存在时抛出
        """
        existing = await self._db.fetchrow(
            "SELECT * FROM tools WHERE name = $1", name
        )
        if not existing:
            raise ToolNotFoundError(f"Tool '{name}' not found")

        merged = dict(existing)
        merged.update(config)

        row = await self._db.fetchrow(
            """
            UPDATE tools SET
                display_name = $2,
                category = $3,
                description = $4,
                module_path = $5,
                file_path = $6,
                args_schema = $7,
                return_description = $8,
                function_description = $9,
                enabled = $10,
                sort_order = $11,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            RETURNING *
            """,
            name,
            merged.get("display_name", ""),
            merged.get("category", ""),
            merged.get("description", ""),
            merged.get("module_path", ""),
            merged.get("file_path", ""),
            json.dumps(merged.get("args_schema", {})),
            merged.get("return_description", ""),
            merged.get("function_description", ""),
            merged.get("enabled", True),
            merged.get("sort_order", 0),
        )
        result = self._decode_row(row)

        # 刷新缓存（enabled 变化时 _refresh_cache 会自动处理）
        await self._refresh_cache(name)
        logger.info("Updated tool: %s", name)
        return result

    async def delete_tool(self, name: str) -> None:
        """删除工具（写 DB + 失效缓存）。

        参数:
            name: 工具名称

        返回:
            None

        异常:
            ToolNotFoundError: 工具不存在时抛出
        """
        existing = await self._db.fetchrow(
            "SELECT name FROM tools WHERE name = $1", name
        )
        if not existing:
            raise ToolNotFoundError(f"Tool '{name}' not found")

        await self._db.execute("DELETE FROM tools WHERE name = $1", name)
        await self._invalidate_cache(name)
        logger.info("Deleted tool: %s", name)

    async def set_tool_enabled(self, name: str, enabled: bool) -> Dict[str, Any]:
        """启用/禁用工具（写 DB + 刷新缓存）。

        参数:
            name: 工具名称
            enabled: True 启用 / False 禁用

        返回:
            Dict[str, Any]: 更新后的工具记录

        异常:
            ToolNotFoundError: 工具不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE tools SET enabled = $2, updated_at = CURRENT_TIMESTAMP
            WHERE name = $1 RETURNING *
            """,
            name, enabled,
        )
        if not row:
            raise ToolNotFoundError(f"Tool '{name}' not found")
        result = self._decode_row(row)

        # 刷新缓存：enabled=TRUE 时加入缓存，enabled=FALSE 时 _refresh_cache
        # 发现 DB 记录存在但 enabled=FALSE，会从缓存移除
        await self._refresh_cache(name)
        logger.info("Set tool %s enabled=%s", name, enabled)
        return result

    # ==================== SubTask 2.6: scan_unregistered ====================

    async def scan_unregistered(self) -> List[Dict[str, Any]]:
        """扫描源码目录，返回未在 DB 注册的 @tool 函数列表。

        用 ast.parse 解析 _TOOL_ROOTS 下所有 .py 文件，找出 @tool 装饰的函数节点，
        提取函数名、参数签名、返回值注解、docstring，与 DB 已注册工具名对比，
        返回未注册的工具信息列表。

        参数:
            无

        返回:
            List[Dict[str, Any]]: 未注册工具列表，每项包含:
                - name (str): 函数名
                - file_path (str): 源文件相对路径（正斜杠）
                - module_path (str): Python 模块路径
                - args_schema (dict): 参数 schema
                - return_description (str): 返回值类型注解字符串
                - function_description (str): docstring 全文

        异常:
            不主动抛出异常；单个文件解析失败时记录 warning 并继续
        """
        # 1. 获取已注册工具名集合
        registered_tools = await self.list_tools()
        registered_names = {t["name"] for t in registered_tools}

        # 2. 扫描源码目录
        results: List[Dict[str, Any]] = []
        for root_rel in _TOOL_ROOTS:
            root_abs = _PROJECT_ROOT / root_rel
            if not root_abs.exists():
                continue

            for py_file in sorted(root_abs.rglob("*.py")):
                if py_file.name == "__init__.py":
                    continue
                tools_in_file = self._scan_file_for_tools(py_file)
                for t in tools_in_file:
                    if t["name"] not in registered_names:
                        results.append(t)

        logger.info("Scan found %d unregistered tools", len(results))
        return results

    def _scan_file_for_tools(self, py_file: Path) -> List[Dict[str, Any]]:
        """用 ast.parse 扫描单个文件中的 @tool 装饰函数。

        解析文件 AST，遍历所有 FunctionDef / AsyncFunctionDef 节点，
        判断是否有 @tool 装饰器（支持 @tool 和 @tool(...) 两种形式），
        提取函数名、参数签名、返回值注解、docstring。

        参数:
            py_file: 源文件绝对路径

        返回:
            List[Dict[str, Any]]: 该文件中的 @tool 函数信息列表
        """
        try:
            source = py_file.read_text(encoding="utf-8")
            tree = ast.parse(source, filename=str(py_file))
        except Exception as e:
            logger.warning("Failed to parse %s: %s", py_file, e)
            return []

        # 计算相对路径和模块路径（正斜杠，跨平台一致）
        rel_path = py_file.relative_to(_PROJECT_ROOT)
        file_path = str(rel_path).replace("\\", "/")
        module_path = ".".join(rel_path.with_suffix("").parts)

        results: List[Dict[str, Any]] = []
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not self._has_tool_decorator(node):
                continue
            results.append({
                "name": node.name,
                "file_path": file_path,
                "module_path": module_path,
                "args_schema": self._extract_args_schema(node),
                "return_description": self._extract_return_description(node),
                "function_description": ast.get_docstring(node) or "",
                "decorator_description": self._extract_tool_description(node) or "",
            })
        return results

    @staticmethod
    def _has_tool_decorator(node: ast.FunctionDef) -> bool:
        """判断函数节点是否有 @tool 装饰器。

        支持以下形式：
        - @tool（ast.Name，id="tool"）
        - @tool(...)（ast.Call，func 为 ast.Name，id="tool"）
        - @langchain.tools.tool(...)（ast.Call，func 为 ast.Attribute，attr="tool"）

        参数:
            node: AST 函数定义节点

        返回:
            bool: 有 @tool 装饰器返回 True，否则 False
        """
        for dec in node.decorator_list:
            # @tool（无括号）
            if isinstance(dec, ast.Name) and dec.id == "tool":
                return True
            # @tool(...) 或 @xxx.tool(...)
            if isinstance(dec, ast.Call):
                func = dec.func
                if isinstance(func, ast.Name) and func.id == "tool":
                    return True
                if isinstance(func, ast.Attribute) and func.attr == "tool":
                    return True
        return False

    @staticmethod
    def _extract_tool_description(node: ast.FunctionDef) -> str:
        """从函数节点的装饰器列表中提取 ``@tool(description="...")`` 的 description 字符串。

        支持的装饰器形态：
          - ``@tool(description="...")``         → ast.Call，值为 ast.Constant
          - ``@tool(description=("..."))``       → ast.Call，值为 ast.Tuple + ast.Constant
          - ``@tool``                            → ast.Name（无 description）
          - ``@xxx.tool(...)``                   → ast.Call，func 为 ast.Attribute

        参数:
            node: AST 函数定义节点

        返回:
            str: description 字符串字面量；未找到返回空字符串
        """
        for dec in node.decorator_list:
            call = None
            if isinstance(dec, ast.Call):
                call = dec
            elif isinstance(dec, ast.Attribute) and isinstance(dec.value, ast.Name):
                continue

            if call is None:
                continue

            func_node = call.func
            is_tool_decorator = (
                (isinstance(func_node, ast.Name) and func_node.id == "tool")
                or (isinstance(func_node, ast.Attribute) and func_node.attr == "tool")
            )
            if not is_tool_decorator:
                continue

            for kw in call.keywords:
                if kw.arg == "description":
                    value = kw.value
                    # 单字符串字面量（含三引号多行）
                    if isinstance(value, ast.Constant) and isinstance(value.value, str):
                        return value.value
                    # f-string 拼接（ast.JoinedStr）
                    if isinstance(value, ast.JoinedStr):
                        parts = []
                        for v in value.values:
                            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                                parts.append(v.value)
                        if parts:
                            return "".join(parts)
                    # 字符串字面量拼接（"a" + "b" 形式 → ast.BinOp）
                    if isinstance(value, ast.BinOp):
                        parts = []
                        def _collect(_node):
                            if isinstance(_node, ast.Constant) and isinstance(_node.value, str):
                                parts.append(_node.value)
                            elif isinstance(_node, ast.BinOp):
                                _collect(_node.left)
                                _collect(_node.right)
                        _collect(value)
                        if parts:
                            return "".join(parts)
                    # 元组包裹 description=(...) — LangChain ``@tool(description=("a", "b"))``
                    if isinstance(value, ast.Tuple):
                        parts = []
                        for elt in value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                parts.append(elt.value)
                        if parts:
                            return "".join(parts)
            # 找到 @tool 装饰器但无 description → 返回空字符串
            return ""
        return ""

    @staticmethod
    def _extract_args_schema(node: ast.FunctionDef) -> Dict[str, Any]:
        """从函数节点提取参数 schema。

        遍历 ast.arguments 中的 posonlyargs / args / kwonlyargs，
        提取参数名、类型注解、是否必需、默认值。跳过框架注入参数
        （runtime / self / cls）。

        参数:
            node: AST 函数定义节点

        返回:
            Dict[str, Any]: 参数 schema 字典，格式:
                {
                    "param_name": {
                        "type": "注解字符串",      # 无注解时为 "Any"
                        "required": True/False,    # 有默认值时为 False
                        "default": "默认值字符串"  # 仅当有默认值时存在
                    }
                }
        """
        args = node.args
        schema: Dict[str, Any] = {}

        # 收集所有位置参数名（posonlyargs + args）
        pos_args = list(args.posonlyargs) + list(args.args)
        pos_arg_names = [a.arg for a in pos_args]

        # 构建默认值映射：args.defaults 对齐到 pos_args 末尾
        defaults_map: Dict[str, ast.expr] = {}
        n_pos = len(pos_args)
        n_defaults = len(args.defaults)
        for i, default in enumerate(args.defaults):
            arg_idx = n_pos - n_defaults + i
            if 0 <= arg_idx < n_pos:
                defaults_map[pos_arg_names[arg_idx]] = default

        # kwonlyargs 的默认值在 args.kw_defaults（None 表示无默认值）
        for arg, default in zip(args.kwonlyargs, args.kw_defaults):
            if default is not None:
                defaults_map[arg.arg] = default

        # 遍历所有参数，构建 schema
        all_args = pos_args + list(args.kwonlyargs)
        for arg in all_args:
            if arg.arg in _FRAMEWORK_PARAMS:
                continue
            param_info: Dict[str, Any] = {
                "type": ast.unparse(arg.annotation) if arg.annotation else "Any",
                "required": arg.arg not in defaults_map,
            }
            if arg.arg in defaults_map:
                param_info["default"] = ast.unparse(defaults_map[arg.arg])
            schema[arg.arg] = param_info

        return schema

    @staticmethod
    def _extract_return_description(node: ast.FunctionDef) -> str:
        """从函数节点提取返回值类型注解字符串。

        参数:
            node: AST 函数定义节点

        返回:
            str: 返回值注解字符串（如 "Command" / "str"）；
                无注解时返回空字符串
        """
        if node.returns:
            try:
                return ast.unparse(node.returns)
            except Exception:
                return ""
        return ""

    # ==================== SubTask 2.7: 私有缓存方法 ====================

    async def _refresh_cache(self, name: str) -> None:
        """重新从 DB 加载单个工具到缓存。

        从 DB 查询指定 name 的工具记录：
        - 记录存在：构造 ToolInfo 并写入缓存（无论 enabled 状态）
        - 记录不存在：从缓存中移除

        参数:
            name: 工具名称

        返回:
            None
        """
        row = await self._db.fetchrow(
            "SELECT * FROM tools WHERE name = $1", name
        )

        from app.shared.tools.registry import ToolRegistry
        registered = ToolRegistry.list_all()

        lock = await self._ensure_lock()
        async with lock:
            if not row:
                # DB 中不存在，从缓存移除
                self._cache.pop(name, None)
                return
            info = self._build_tool_info(self._decode_row(row), registered)
            self._cache[name] = info

    async def _invalidate_cache(self, name: str) -> None:
        """从缓存移除单个工具。

        参数:
            name: 工具名称

        返回:
            None
        """
        lock = await self._ensure_lock()
        async with lock:
            self._cache.pop(name, None)

    async def _clear_cache(self) -> None:
        """清空所有缓存（供测试用）。

        参数:
            无

        返回:
            None
        """
        lock = await self._ensure_lock()
        async with lock:
            self._cache.clear()
