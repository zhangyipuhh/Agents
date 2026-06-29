#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
SkillRegistryService 模块

Skill 注册中心服务：从 DB skills 表加载 skill 元数据，提供 skill 的 CRUD、
内存缓存与文件系统未注册扫描能力，供 admin router 与 AgentConfigService 使用。

核心职责：
1. preload_all：启动时从 DB 读取所有 skills 记录，构造 SkillRow 后缓存到内存。
2. 读方法（list_skills / get_skill_by_name）：优先读缓存，缓存为空或未命中时回退 DB。
3. 写方法（create_skill / update_skill / delete_skill / set_skill_enabled）：写 DB 后
   同步刷新/失效缓存。
4. scan_unregistered：调用 SkillDiscovery.scan() 扫描默认根与用户扩展路径下的 SKILL.md，
   与 DB 已注册 skill 对比，返回未注册 skill 列表。

设计决策：
- 缓存是 DB 的完整镜像（含禁用项），减少运行时查询。
- skill 不关联运行时实例，SkillRow 仅保存元数据。
- JSONB 字段不存在于 skills 表，因此无需防御性反序列化；保留 _decode_jsonb 工具方法
  供后续扩展使用。
- 用户扩展路径解析由本服务完成：支持绝对路径、~/ 缩写、相对项目根。

Date: 2026-06-29
Author: AI Assistant
"""

import asyncio
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.core.config.settings import settings
from app.core.skills.loader import SkillDiscovery

logger = logging.getLogger(__name__)

# 项目根目录：skill_service.py 位于 app/shared/utils/agent/skill_service.py，
# 向上 4 级 parents[4] 到达项目根目录
_PROJECT_ROOT = Path(__file__).resolve().parents[4]


@dataclass
class SkillRow:
    """Skill 数据行（与 DB skills 表对应）。

    Attributes:
        name: skill 唯一标识名（来自 SKILL.md frontmatter）
        display_name: 展示名称（管理界面用）
        category: skill 分类
        description: skill 描述
        location: SKILL.md 文件绝对路径
        base_dir: SKILL.md 所在目录绝对路径
        content: 去除 frontmatter 后的正文
        enabled: 是否启用
        sort_order: 排序权重
    """
    name: str
    display_name: str
    category: str
    description: str
    location: str
    base_dir: str
    content: str
    enabled: bool
    sort_order: int


class SkillNotFoundError(Exception):
    """Skill 未找到时抛出。"""


class SkillAlreadyExistsError(Exception):
    """Skill 名称重复时抛出。"""


class SkillRegistryService:
    """Skill 注册中心服务。

    负责 DB skills 表的 CRUD + 内存缓存 + 文件系统扫描，供 admin router 与
    AgentConfigService 使用。

    参数:
        db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法（asyncpg 风格）
    """

    def __init__(self, db: Any) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池，需支持 fetch / fetchrow / execute 异步方法
        """
        self._db = db
        self._cache: Dict[str, SkillRow] = {}
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
        return dict(row)

    @staticmethod
    def _skill_row_to_dict(row: SkillRow) -> Dict[str, Any]:
        """将 SkillRow 转为字典。

        参数:
            row: SkillRow 实例

        返回:
            Dict[str, Any]: skill 元数据字典
        """
        return {
            "name": row.name,
            "display_name": row.display_name,
            "category": row.category,
            "description": row.description,
            "location": row.location,
            "base_dir": row.base_dir,
            "content": row.content,
            "enabled": row.enabled,
            "sort_order": row.sort_order,
        }

    def _build_skill_row(self, row_dict: Dict[str, Any]) -> SkillRow:
        """从 DB 行字典构造 SkillRow。

        参数:
            row_dict: 已经过 _decode_row 的 DB 行字典

        返回:
            SkillRow: Skill 数据行实例
        """
        return SkillRow(
            name=row_dict.get("name", ""),
            display_name=row_dict.get("display_name", ""),
            category=row_dict.get("category", ""),
            description=row_dict.get("description", ""),
            location=row_dict.get("location", ""),
            base_dir=row_dict.get("base_dir", ""),
            content=row_dict.get("content", ""),
            enabled=row_dict.get("enabled", True),
            sort_order=row_dict.get("sort_order", 0),
        )

    async def _ensure_lock(self) -> asyncio.Lock:
        """延迟创建 asyncio.Lock，避免无事件循环时报错。

        返回:
            asyncio.Lock: 缓存锁实例
        """
        if self._cache_lock is None:
            self._cache_lock = asyncio.Lock()
        return self._cache_lock

    # ==================== 路径解析 ====================

    @staticmethod
    def _resolve_skill_paths(
        project_root: Path, raw_paths: List[str]
    ) -> List[Path]:
        """解析用户扩展 skill 扫描路径。

        支持绝对路径、~/ 缩写、相对 project_root 的路径。不存在的路径会保留，
        由 SkillDiscovery.scan() 自行记录 warning 并跳过。

        参数:
            project_root: 项目根目录
            raw_paths: 来自 settings.skills.to_skills_config().paths 的原始路径字符串列表

        返回:
            List[Path]: 已解析为绝对路径的 Path 列表
        """
        resolved: List[Path] = []
        for p in raw_paths:
            path = Path(p).expanduser()
            if not path.is_absolute():
                path = project_root / path
            resolved.append(path.resolve())
        return resolved

    # ==================== preload_all ====================

    async def preload_all(self) -> None:
        """预加载所有 skill 到缓存。

        从 DB 读取所有 skills 记录（含禁用项），构造 SkillRow 后原子替换缓存。

        参数:
            无

        返回:
            None

        异常:
            不主动抛出异常；DB 查询失败时由调用方处理
        """
        rows = await self._db.fetch(
            "SELECT * FROM skills ORDER BY sort_order, name"
        )

        new_cache: Dict[str, SkillRow] = {}
        for row in rows:
            decoded = self._decode_row(row)
            skill_row = self._build_skill_row(decoded)
            new_cache[skill_row.name] = skill_row

        lock = await self._ensure_lock()
        async with lock:
            self._cache = new_cache
        logger.info("Preloaded %d skills into cache", len(new_cache))

    # ==================== 读方法（优先读缓存） ====================

    async def list_skills(self) -> List[Dict[str, Any]]:
        """列出所有 skills（优先读缓存）。

        缓存命中时返回缓存中所有 skill 的字典列表；缓存为空时回退 DB 查询所有 skill（含禁用项）。

        参数:
            无

        返回:
            List[Dict[str, Any]]: skill 元数据列表，每项包含
                name / display_name / category / description / location /
                base_dir / content / enabled / sort_order
        """
        if self._cache:
            return [
                self._skill_row_to_dict(row) for row in self._cache.values()
            ]

        rows = await self._db.fetch(
            "SELECT * FROM skills ORDER BY sort_order, name"
        )
        return [self._decode_row(r) for r in rows]

    async def get_skill_by_name(self, name: str) -> Optional[SkillRow]:
        """获取单个 skill（优先读缓存）。

        缓存命中时直接返回 SkillRow；缓存未命中时查 DB 并回填缓存。

        参数:
            name: skill 名称（唯一标识）

        返回:
            Optional[SkillRow]: Skill 数据行实例；不存在时返回 None
        """
        if name in self._cache:
            return self._cache[name]

        row = await self._db.fetchrow(
            "SELECT * FROM skills WHERE name = $1", name
        )
        if not row:
            return None

        skill_row = self._build_skill_row(self._decode_row(row))
        lock = await self._ensure_lock()
        async with lock:
            self._cache[name] = skill_row
        return skill_row

    # ==================== 写方法（写 DB + 同步缓存） ====================

    async def create_skill(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """注册新 skill（写 DB + 刷新缓存）。

        参数:
            config: skill 配置字典，必须包含:
                - name (str): skill 唯一名称
              可选键:
                - display_name: 展示名称（默认空字符串）
                - category: 分类（默认空字符串）
                - description: 描述（默认空字符串）
                - location: SKILL.md 绝对路径（默认空字符串）
                - base_dir: SKILL.md 所在目录绝对路径（默认空字符串）
                - content: 去除 frontmatter 后的正文（默认空字符串）
                - enabled: 是否启用（默认 True）
                - sort_order: 排序权重（默认 0）

        返回:
            Dict[str, Any]: 新创建的 skill 记录

        异常:
            KeyError: 缺少必需键 name 时抛出
            SkillAlreadyExistsError: name 已存在时抛出
        """
        if "name" not in config:
            raise KeyError("create_skill 缺少必需键: name")

        existing = await self._db.fetchrow(
            "SELECT name FROM skills WHERE name = $1", config["name"]
        )
        if existing:
            raise SkillAlreadyExistsError(
                f"Skill '{config['name']}' already exists"
            )

        row = await self._db.fetchrow(
            """
            INSERT INTO skills (name, display_name, category, description,
                                location, base_dir, content,
                                enabled, sort_order)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            RETURNING *
            """,
            config["name"],
            config.get("display_name", ""),
            config.get("category", ""),
            config.get("description", ""),
            config.get("location", ""),
            config.get("base_dir", ""),
            config.get("content", ""),
            config.get("enabled", True),
            config.get("sort_order", 0),
        )
        result = self._decode_row(row)

        await self._refresh_cache(config["name"])
        logger.info("Created skill: %s", config["name"])
        return result

    async def update_skill(self, name: str, config: Dict[str, Any]) -> Dict[str, Any]:
        """更新 skill 配置（写 DB + 刷新缓存）。

        全量更新 skill 的所有可变字段（display_name / category / description /
        location / base_dir / content / enabled / sort_order）。

        参数:
            name: skill 名称
            config: skill 配置字典（字段同 create_skill，但 name 不可改）

        返回:
            Dict[str, Any]: 更新后的 skill 记录

        异常:
            SkillNotFoundError: skill 不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE skills SET
                display_name = $2,
                category = $3,
                description = $4,
                location = $5,
                base_dir = $6,
                content = $7,
                enabled = $8,
                sort_order = $9,
                updated_at = CURRENT_TIMESTAMP
            WHERE name = $1
            RETURNING *
            """,
            name,
            config.get("display_name", ""),
            config.get("category", ""),
            config.get("description", ""),
            config.get("location", ""),
            config.get("base_dir", ""),
            config.get("content", ""),
            config.get("enabled", True),
            config.get("sort_order", 0),
        )
        if not row:
            raise SkillNotFoundError(f"Skill '{name}' not found")
        result = self._decode_row(row)

        await self._refresh_cache(name)
        logger.info("Updated skill: %s", name)
        return result

    async def delete_skill(self, name: str) -> None:
        """删除 skill（写 DB + 失效缓存）。

        参数:
            name: skill 名称

        返回:
            None

        异常:
            SkillNotFoundError: skill 不存在时抛出
        """
        existing = await self._db.fetchrow(
            "SELECT name FROM skills WHERE name = $1", name
        )
        if not existing:
            raise SkillNotFoundError(f"Skill '{name}' not found")

        await self._db.execute("DELETE FROM skills WHERE name = $1", name)
        await self._invalidate_cache(name)
        logger.info("Deleted skill: %s", name)

    async def set_skill_enabled(self, name: str, enabled: bool) -> Dict[str, Any]:
        """启用/禁用 skill（写 DB + 刷新缓存）。

        参数:
            name: skill 名称
            enabled: True 启用 / False 禁用

        返回:
            Dict[str, Any]: 更新后的 skill 记录

        异常:
            SkillNotFoundError: skill 不存在时抛出
        """
        row = await self._db.fetchrow(
            """
            UPDATE skills SET enabled = $2, updated_at = CURRENT_TIMESTAMP
            WHERE name = $1 RETURNING *
            """,
            name, enabled,
        )
        if not row:
            raise SkillNotFoundError(f"Skill '{name}' not found")
        result = self._decode_row(row)

        await self._refresh_cache(name)
        logger.info("Set skill %s enabled=%s", name, enabled)
        return result

    # ==================== scan_unregistered ====================

    async def scan_unregistered(self) -> List[Dict[str, Any]]:
        """扫描文件系统，返回未在 DB 注册的 skill 列表。

        调用 SkillDiscovery.scan() 扫描默认根（app/skills、.agents/skills）以及
        settings.skills.to_skills_config().paths 配置的用户扩展路径，与 DB 已注册
        skill 名对比，返回未注册的 skill 信息。

        参数:
            无

        返回:
            List[Dict[str, Any]]: 未注册 skill 列表，每项包含:
                - name (str): skill 名称
                - description (str | None): skill 描述
                - location (str): SKILL.md 绝对路径
                - base_dir (str): SKILL.md 所在目录绝对路径

        异常:
            不主动抛出异常；扫描失败时记录 warning 并继续
        """
        registered_skills = await self.list_skills()
        registered_names = {s["name"] for s in registered_skills}

        skills_config = settings.skills.to_skills_config()
        extra_paths = self._resolve_skill_paths(_PROJECT_ROOT, skills_config.paths)

        discovery = SkillDiscovery()
        discovered = discovery.scan(_PROJECT_ROOT, extra_paths)

        results: List[Dict[str, Any]] = []
        for info in discovered.values():
            if info.name not in registered_names:
                results.append({
                    "name": info.name,
                    "description": info.description,
                    "location": info.location,
                    "base_dir": info.base_dir,
                })

        logger.info("Scan found %d unregistered skills", len(results))
        return results

    # ==================== 私有缓存方法 ====================

    async def _refresh_cache(self, name: str) -> None:
        """重新从 DB 加载单个 skill 到缓存。

        从 DB 查询指定 name 的 skill 记录：
        - 记录存在：构造 SkillRow 并写入缓存
        - 记录不存在：从缓存中移除

        参数:
            name: skill 名称

        返回:
            None
        """
        row = await self._db.fetchrow(
            "SELECT * FROM skills WHERE name = $1", name
        )

        lock = await self._ensure_lock()
        async with lock:
            if not row:
                self._cache.pop(name, None)
                return
            skill_row = self._build_skill_row(self._decode_row(row))
            self._cache[name] = skill_row

    async def _invalidate_cache(self, name: str) -> None:
        """从缓存移除单个 skill。

        参数:
            name: skill 名称

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
