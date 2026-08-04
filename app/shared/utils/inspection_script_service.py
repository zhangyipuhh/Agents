#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InspectionScriptService - DevOps 巡检脚本库统一管理服务（2026-08-03 新增）

职责：
    - 管理 ``inspection_scripts`` 表（统一巡检脚本库），按「平台 + 版本」维度
      集中存放 bash / powershell 巡检脚本与字段规则。
    - YAML 配置入口：项目根 ``data/devops/inspection_scripts.yaml``（可通过
      ``settings`` 覆盖），由 ``scan_and_upsert`` 扫描入库。
    - 内存缓存：``self._cache: Dict[name, rec]`` 与 ``self._id_cache: Dict[id, rec]``；
      写路径持 ``self._write_lock``，避免并发扫描造成快照不一致。
    - ``resolve_script_for_server(server_type, script_name)``：根据
      server_type 与可选 script_name 返回脚本库 id，供 DevOpsServerService
      在 ``_normalize_entry`` 与 ``_upsert_one_returning`` 阶段使用。

设计要点：
    - 单例（``set_instance`` / ``get_instance`` / ``reset``）由 lifespan
      注入到 ``app.state.inspection_script_service``。
    - 写路径（``preload_all`` / ``scan_and_upsert``）持锁；读路径无锁。
    - 列表端点 ``list_scripts`` 严格白名单返回（不暴露脚本原文）；
      详情端点 ``get_script_detail`` 按需返回完整字段（含脚本原文）。
    - 字段规则校验复用 ``app/shared/utils/inspection/parser.py::normalize_inspection_fields``。

调用关系：
    - lifespan → InspectionScriptService(db, path).preload_all() →
      app.state.inspection_script_service
    - admin router → service.scan_and_upsert() / list_scripts() /
      get_script_detail()
    - DevOpsServerService._normalize_entry / _upsert_one_returning →
      service.get_script_by_name() / resolve_script_for_server()
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml

from app.shared.utils.inspection.parser import normalize_inspection_fields


logger = logging.getLogger(__name__)


# 列表白名单（不暴露 inspection_script / inspection_fields）
_LIST_FIELDS = (
    "id",
    "name",
    "display_name",
    "platform",
    "version",
    "inspection_parser",
    "updated_at",
)

# 详情白名单（含脚本原文与字段规则）
_DETAIL_FIELDS = (
    "id",
    "name",
    "display_name",
    "platform",
    "version",
    "inspection_parser",
    "inspection_script",
    "inspection_fields",
    "created_at",
    "updated_at",
)

# server_type → 默认脚本 name 的映射
_DEFAULT_SCRIPT_NAMES = {
    "linux": "linux-bash",
    "windows": "windows-ps-5.1",
}

# 合法 parser 枚举
_VALID_PARSERS = ("json", "kv", "csv", "raw")


class InspectionScriptService:
    """DevOps 巡检脚本库统一管理服务（单例）。

    Attributes:
        db: asyncpg 连接池；测试可传 MagicMock 替身。
        config_path: ``inspection_scripts.yaml`` 文件路径。
        _cache: 内存缓存，键为脚本 ``name``，值为完整记录 dict。
        _id_cache: 内存缓存，键为脚本 ``id``，值为完整记录 dict（用于按 id 查）。
        _write_lock: ``asyncio.Lock``，保护 ``_cache`` / ``_id_cache`` 写入。
    """

    _instance: Optional["InspectionScriptService"] = None

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @classmethod
    def set_instance(cls, instance: "InspectionScriptService") -> None:
        """设置全局单例。

        Args:
            instance: InspectionScriptService 实例

        Returns:
            None
        """
        cls._instance = instance

    @classmethod
    def get_instance(cls) -> "InspectionScriptService":
        """获取全局单例。

        Returns:
            InspectionScriptService: 单例实例

        Raises:
            RuntimeError: 单例尚未初始化时抛出
        """
        if cls._instance is None:
            raise RuntimeError("InspectionScriptService singleton not initialized")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置全局单例（主要用于测试）。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, db: Any, config_path: str) -> None:
        """构造服务。

        Args:
            db: asyncpg 连接池；测试可传 ``MagicMock(name="db_pool_stub")``。
            config_path: ``inspection_scripts.yaml`` 路径；不存在时
                ``scan_and_upsert`` 安全返回 0。

        Returns:
            None
        """
        self.db = db
        self.config_path = str(config_path)
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._id_cache: Dict[int, Dict[str, Any]] = {}
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Preload from DB
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """从 DB 读取全部 ``inspection_scripts`` 行到 ``self._cache`` / ``self._id_cache``。

        Returns:
            None
        """
        rows = await self.db.fetch(
            "SELECT id, name, display_name, platform, version, "
            "inspection_parser, inspection_script, inspection_fields, "
            "created_at, updated_at "
            "FROM inspection_scripts ORDER BY id"
        )
        new_cache: Dict[str, Dict[str, Any]] = {}
        new_id_cache: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            script_id = data.get("id")
            name = data.get("name")
            if not name or script_id is None:
                continue
            # inspection_fields 还原（jsonb codec 兼容）
            raw_fields = data.get("inspection_fields")
            if isinstance(raw_fields, str):
                try:
                    parsed = json.loads(raw_fields)
                except (json.JSONDecodeError, TypeError):
                    parsed = []
                data["inspection_fields"] = parsed
            elif isinstance(raw_fields, list):
                data["inspection_fields"] = raw_fields
            else:
                data["inspection_fields"] = []
            # 缺失 inspection_script 时统一为 None
            if data.get("inspection_script") is not None and not isinstance(
                data["inspection_script"], (str, type(None))
            ):
                data["inspection_script"] = None
            new_cache[name] = data
            new_id_cache[script_id] = data
        async with self._write_lock:
            self._cache = new_cache
            self._id_cache = new_id_cache
        logger.info(
            "[inspection_script_service] preloaded %d script(s)",
            len(self._cache),
        )

    # ------------------------------------------------------------------
    # Scan & upsert
    # ------------------------------------------------------------------

    async def scan_and_upsert(self) -> Dict[str, int]:
        """读取 YAML 脚本库配置，规范化后 INSERT 写入 DB（编辑优先）。

        输入形态：
            - 顶层 ``{ "inspection_scripts": [ {...}, {...} ] }``（计划示例形式）；
            - 顶层直接 ``[ {...}, {...} ]``（YAML ``-`` 序列形式）；
            - 其它顶层结构 → failed=1（不抛异常）。

        写入策略（2026-08-04 改造为「编辑优先」）：
            - 计数：``scanned`` 是输入条目数；``inserted`` 是 DB 中首次出现的
              name；``skipped`` 是与缓存中已有 name 重合的条目数（**不调用
              DB upsert，保留人工编辑**）；``updated`` 保留为 0（编辑优先模式
              下不触发 ON CONFLICT DO UPDATE）；``failed`` 是校验失败 / DB
              写入异常 / 重复 name 的总数。
            - **重复 name 直接拒绝并计入 failed**（同 YAML 内重复）。
            - 失败条目不进入缓存；不抛异常上抛。
            - 缓存与 DB 同步：insert 成功后用 RETURNING 行更新
              ``self._cache`` / ``self._id_cache``，避免再读一次 DB。

        Returns:
            Dict[str, int]: 严格只含
            ``{"scanned": int, "inserted": int, "updated": int, "failed": int, "skipped": int}``
        """
        stats = {"scanned": 0, "inserted": 0, "updated": 0, "failed": 0, "skipped": 0}
        cfg_path = Path(self.config_path)
        if not cfg_path.exists():
            return stats

        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            logger.warning(
                "[inspection_script_service] 无法读取 inspection_scripts.yaml，type=%s",
                type(e).__name__,
            )
            return stats

        if isinstance(raw, dict):
            raw = raw.get("inspection_scripts")
        if not isinstance(raw, list):
            stats["failed"] += 1
            return stats

        # 重复 name 拒绝
        normalized_per_name: Dict[str, Dict[str, Any]] = {}
        order: List[str] = []
        seen_names: set = set()
        for entry in raw:
            stats["scanned"] += 1
            try:
                normalized = self._normalize_entry(entry)
            except ValueError:
                stats["failed"] += 1
                continue
            name = normalized["name"]
            if name in seen_names:
                stats["failed"] += 1
                continue
            seen_names.add(name)
            order.append(name)
            normalized_per_name[name] = normalized

        for name in order:
            # 2026-08-04 改造：编辑优先——DB 中已存在 name 跳过更新，保留人工编辑
            if name in self._cache:
                stats["skipped"] += 1
                continue
            normalized = normalized_per_name[name]
            try:
                inserted, row = await self._upsert_one_returning(name, normalized)
            except Exception:
                stats["failed"] += 1
                continue

            row_data = dict(row) if row else {}
            script_id = row_data.get("id")
            if script_id is None:
                stats["failed"] += 1
                continue
            # inspection_fields JSON 字符串还原
            raw_fields = row_data.get("inspection_fields")
            if isinstance(raw_fields, str):
                try:
                    parsed = json.loads(raw_fields)
                except (json.JSONDecodeError, TypeError):
                    parsed = []
                row_data["inspection_fields"] = parsed
            elif isinstance(raw_fields, list):
                row_data["inspection_fields"] = raw_fields
            else:
                row_data["inspection_fields"] = []
            async with self._write_lock:
                self._cache[name] = row_data
                self._id_cache[script_id] = row_data
            if inserted:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

        return stats

    # ------------------------------------------------------------------
    # Update script detail
    # ------------------------------------------------------------------

    async def update_script_detail(
        self,
        script_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """按 id 更新脚本详情（白名单字段 + 字段规则），同步缓存（2026-08-04 新增）。

        Args:
            script_id: ``inspection_scripts.id``
            payload: 业务字段 dict，含 ``name``（仅用于缓存定位）/ ``display_name`` /
                ``platform`` / ``version`` / ``inspection_parser`` /
                ``inspection_script`` / ``inspection_fields``

        Returns:
            Optional[Dict[str, Any]]: 更新后的完整记录（_DETAIL_FIELDS 字段）；
            script_id 缺失 / 入参非法 / DB 无返回行时返回 ``None``（不抛异常）
        """
        if script_id is None or not isinstance(script_id, int) or script_id <= 0:
            return None
        if not isinstance(payload, dict):
            return None

        # name 不参与请求体；写缓存时从 DB 返回行（record）回填
        display_name = payload.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            return None
        display_name = display_name.strip()

        platform = (payload.get("platform") or "linux").strip().lower()
        if platform not in ("linux", "windows"):
            return None

        version = payload.get("version")
        version = version.strip() if isinstance(version, str) else ""

        inspection_parser = (payload.get("inspection_parser") or "json").strip().lower()
        if inspection_parser not in _VALID_PARSERS:
            return None

        script_raw = payload.get("inspection_script")
        if script_raw is None:
            inspection_script: Optional[str] = None
        else:
            try:
                inspection_script = str(script_raw).rstrip("\n")
            except Exception:
                return None
            if not inspection_script.strip():
                inspection_script = None

        raw_fields = payload.get("inspection_fields") or []
        if not isinstance(raw_fields, list):
            return None
        try:
            rules = normalize_inspection_fields(raw_fields)
        except Exception:
            return None
        fields_payload = [
            {
                "key": r.key,
                "name_zh": r.name_zh,
                "unit": r.unit,
                "direction": r.direction,
                "warn": r.warn,
                "crit": r.crit,
            }
            for r in rules
        ]

        try:
            row = await self.db.fetchrow(
                "UPDATE inspection_scripts SET "
                "display_name = $2, platform = $3, version = $4, "
                "inspection_parser = $5, inspection_script = $6, "
                "inspection_fields = $7::jsonb, updated_at = NOW() "
                "WHERE id = $1 "
                "RETURNING id, name, display_name, platform, version, "
                "inspection_parser, inspection_script, inspection_fields, "
                "created_at, updated_at",
                int(script_id),
                display_name,
                platform,
                version,
                inspection_parser,
                inspection_script,
                json.dumps(fields_payload, ensure_ascii=False),
            )
        except Exception:
            logger.exception(
                "[inspection_script_service] update_script_detail failed, id=%s",
                script_id,
            )
            return None
        if not row:
            return None

        record = dict(row)
        if isinstance(record.get("inspection_fields"), str):
            try:
                record["inspection_fields"] = json.loads(record["inspection_fields"])
            except (json.JSONDecodeError, TypeError):
                record["inspection_fields"] = []
        elif not isinstance(record.get("inspection_fields"), list):
            record["inspection_fields"] = []

        async with self._write_lock:
            record_name = record.get("name")
            if isinstance(record_name, str) and record_name.strip():
                self._cache[record_name] = record
            self._id_cache[int(script_id)] = record
        return {k: record.get(k) for k in _DETAIL_FIELDS}

    # ------------------------------------------------------------------
    # Delete script
    # ------------------------------------------------------------------

    async def delete_script(self, script_id: int) -> bool:
        """按 ``id`` 删除脚本库条目，同步清理内存缓存（2026-08-04 新增）。

        行为：
            - 入参非法（``None`` / 非 int / ``<=0``）→ 返回 ``False``（不抛）。
            - DB 无匹配行（``DELETE 0``）→ 返回 ``False``，不动缓存。
            - DB 异常（连接 / FK 等）→ ``logger.exception`` 后返回 ``False``。
            - 删除成功 → 持 ``_write_lock`` 同时移除
              ``_id_cache[script_id]`` 与 ``_cache[name]``，返回 ``True``。
            - 由于 ``devops_servers.inspection_script_id`` 外键定义为
              ``ON DELETE SET NULL``，删除脚本不会阻塞 / 级联删除服务器行，
              而是自动解绑；本函数无需手动清理 devops_servers。

        Args:
            script_id: ``inspection_scripts.id``

        Returns:
            bool: 已删除返回 ``True``；不存在 / 入参非法 / DB 异常返回 ``False``
        """
        if script_id is None or not isinstance(script_id, int) or script_id <= 0:
            return False

        # 先读取当前 name，便于删除成功后同步 _cache；非锁定读，避免长时间持锁
        cached = self._id_cache.get(int(script_id))
        cached_name: Optional[str] = None
        if isinstance(cached, dict):
            name_val = cached.get("name")
            if isinstance(name_val, str) and name_val.strip():
                cached_name = name_val

        try:
            result = await self.db.execute(
                "DELETE FROM inspection_scripts WHERE id = $1",
                int(script_id),
            )
        except Exception:
            logger.exception(
                "[inspection_script_service] delete_script failed, id=%s",
                script_id,
            )
            return False

        # asyncpg 返回 "DELETE <n>" 形式的 status 字符串
        if not isinstance(result, str) or not result.startswith("DELETE"):
            logger.warning(
                "[inspection_script_service] delete_script unexpected result=%r",
                result,
            )
            return False

        try:
            affected = int(result.split()[1])
        except (IndexError, ValueError):
            affected = 0
        if affected == 0:
            return False

        async with self._write_lock:
            self._id_cache.pop(int(script_id), None)
            if cached_name:
                # 仅当 _cache 中该 name 对应同一 id 时才移除，避免误删
                existing = self._cache.get(cached_name)
                if isinstance(existing, dict) and existing.get("id") == int(script_id):
                    self._cache.pop(cached_name, None)
        return True

    # ------------------------------------------------------------------
    # Public read APIs
    # ------------------------------------------------------------------

    def list_scripts(self) -> List[Dict[str, Any]]:
        """返回脚本库白名单字段列表（不暴露脚本原文）。

        Returns:
            List[Dict[str, Any]]: 每项仅含 ``_LIST_FIELDS`` 字段
        """
        result: List[Dict[str, Any]] = []
        for rec in self._cache.values():
            result.append({k: rec.get(k) for k in _LIST_FIELDS})
        return result

    def get_script_detail(self, script_id: int) -> Optional[Dict[str, Any]]:
        """按 ``id`` 取完整脚本详情（含脚本原文与字段规则）。

        Args:
            script_id: inspection_scripts 主键 id

        Returns:
            Optional[Dict[str, Any]]: 命中时含 ``_DETAIL_FIELDS`` 字段；
            未命中时 ``None``
        """
        rec = self._id_cache.get(script_id)
        if rec is None:
            return None
        return {k: rec.get(k) for k in _DETAIL_FIELDS}

    def get_script_by_id(self, script_id: int) -> Optional[Dict[str, Any]]:
        """按 ``id`` 取完整记录（内部使用，含完整字段）。

        Args:
            script_id: inspection_scripts 主键 id

        Returns:
            Optional[Dict[str, Any]]: 命中时返回完整记录；未命中 ``None``
        """
        return self._id_cache.get(script_id)

    def get_script_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """按 ``name`` 取完整记录（内部使用，含完整字段）。

        Args:
            name: 脚本库条目的唯一 name

        Returns:
            Optional[Dict[str, Any]]: 命中时返回完整记录；未命中 ``None``
        """
        if not name:
            return None
        return self._cache.get(name)

    def resolve_script_for_server(
        self,
        server_type: str,
        script_name: Optional[str] = None,
    ) -> Optional[int]:
        """根据 server_type + 可选 script_name 解析脚本库 id。

        解析规则：
            1. 显式 ``script_name`` 非空 → 按 name 查 cache，命中返回 id；
               未命中返回 ``None``（不静默回退，避免外部误以为找到了）。
            2. ``script_name`` 为空 → 按 ``server_type`` 匹配默认脚本名
               （``linux → linux-bash``，``windows → windows-ps-5.1``）；
               默认脚本未注册返回 ``None``。

        Args:
            server_type: ``linux`` 或 ``windows``
            script_name: 可选脚本库 name

        Returns:
            Optional[int]: 命中时返回 inspection_scripts.id；未命中 ``None``
        """
        if script_name:
            rec = self.get_script_by_name(script_name)
            if rec is not None:
                return rec.get("id")
            return None
        default_name = _DEFAULT_SCRIPT_NAMES.get((server_type or "").lower())
        if not default_name:
            return None
        rec = self.get_script_by_name(default_name)
        if rec is None:
            return None
        return rec.get("id")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_entry(self, entry: Any) -> Dict[str, Any]:
        """把 YAML entry 规范化为业务字段；非法时抛 ``ValueError``。

        Args:
            entry: 原始 YAML 条目（dict）

        Returns:
            Dict[str, Any]: 规范化后含 ``name`` / ``display_name`` /
            ``platform`` / ``version`` / ``inspection_parser`` /
            ``inspection_script`` / ``inspection_fields``

        Raises:
            ValueError: 缺少必填字段或取值非法时抛出（不携带敏感信息）
        """
        if not isinstance(entry, dict):
            raise ValueError("entry must be a dict")

        # name（必填，唯一）
        name = entry.get("name")
        if not name or not isinstance(name, str):
            raise ValueError("missing name")
        name = name.strip()
        if not name:
            raise ValueError("empty name")

        # display_name（必填）
        display_name = entry.get("display_name")
        if not display_name or not isinstance(display_name, str):
            raise ValueError("missing display_name")
        display_name = display_name.strip()
        if not display_name:
            raise ValueError("empty display_name")

        # platform（默认 linux）
        platform = (entry.get("platform") or "linux").lower()
        if platform not in ("linux", "windows"):
            raise ValueError(f"invalid platform: {platform!r}")

        # version（默认空字符串）
        version = entry.get("version") or ""
        if not isinstance(version, str):
            raise ValueError("version must be string")
        version = version.strip()

        # inspection_parser（默认 json；枚举校验）
        parser_raw = entry.get("inspection_parser", "json")
        if not isinstance(parser_raw, str):
            raise ValueError("inspection_parser must be string")
        inspection_parser = parser_raw.strip().lower() or "json"
        if inspection_parser not in _VALID_PARSERS:
            raise ValueError(
                f"invalid inspection_parser: {parser_raw!r} "
                f"(must be one of {', '.join(_VALID_PARSERS)})"
            )

        # inspection_script（可选，None / str）
        script_raw = entry.get("inspection_script")
        if script_raw is None:
            inspection_script: Optional[str] = None
        else:
            try:
                inspection_script = str(script_raw)
            except Exception as e:
                raise ValueError(f"inspection_script 不可序列化: {e}") from e
            if not inspection_script or not inspection_script.strip():
                inspection_script = None
            else:
                inspection_script = inspection_script.rstrip("\n")

        # inspection_fields（复用 normalize_inspection_fields）
        raw_fields = entry.get("inspection_fields", []) or []
        if not isinstance(raw_fields, list):
            # 兼容直接给字符串 / 字典的异常形态
            raise ValueError("inspection_fields must be list")
        rules = normalize_inspection_fields(raw_fields)
        inspection_fields = [
            {
                "key": r.key,
                "name_zh": r.name_zh,
                "unit": r.unit,
                "direction": r.direction,
                "warn": r.warn,
                "crit": r.crit,
            }
            for r in rules
        ]

        return {
            "name": name,
            "display_name": display_name,
            "platform": platform,
            "version": version,
            "inspection_parser": inspection_parser,
            "inspection_script": inspection_script,
            "inspection_fields": inspection_fields,
        }

    async def _upsert_one_returning(
        self,
        name: str,
        normalized: Dict[str, Any],
    ) -> tuple[bool, Any]:
        """单条 upsert，并返回 ``(inserted, row)``。

        使用 ``INSERT ... ON CONFLICT (name) DO UPDATE ... RETURNING *,
        (xmax = 0) AS inserted`` 一次往返完成。

        Args:
            name: 脚本库条目 name（唯一）
            normalized: 规范化后的字段

        Returns:
            Tuple[bool, Any]: ``(是否新插入, DB 返回行)``

        Raises:
            Exception: DB 写入失败时抛出（由调用方捕获并计入 failed）
        """
        row = await self.db.fetchrow(
            "INSERT INTO inspection_scripts "
            "(name, display_name, platform, version, "
            " inspection_parser, inspection_script, inspection_fields, "
            " created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, NOW(), NOW()) "
            "ON CONFLICT (name) DO UPDATE SET "
            "display_name = EXCLUDED.display_name, "
            "platform = EXCLUDED.platform, "
            "version = EXCLUDED.version, "
            "inspection_parser = EXCLUDED.inspection_parser, "
            "inspection_script = EXCLUDED.inspection_script, "
            "inspection_fields = EXCLUDED.inspection_fields, "
            "updated_at = NOW() "
            "RETURNING *, (xmax = 0) AS inserted",
            normalized["name"],
            normalized["display_name"],
            normalized["platform"],
            normalized["version"],
            normalized["inspection_parser"],
            normalized["inspection_script"],
            json.dumps(normalized["inspection_fields"], ensure_ascii=False),
        )
        inserted = bool(row and row.get("inserted"))
        return inserted, row