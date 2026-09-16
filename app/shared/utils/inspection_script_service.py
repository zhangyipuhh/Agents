#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InspectionScriptService - DevOps 巡检脚本库统一管理服务（2026-08-03 新增；2026-09-16 重构）

职责：
    - 管理 ``inspection_scripts`` 表（统一巡检脚本库），按「平台 + 版本」维度
      集中存放 bash / powershell 巡检脚本与字段规则。
    - 分段表 ``inspection_script_segments``（FK CASCADE）：一组脚本可拆为有序分段
      （disk-usage / disk-io / memory / cpu），单 SSH 连接循环执行后由
      ``app/shared/utils/inspection/merger.py::merge_inspection_fragments`` 按 D1 合并。
    - 默认脚本通过代码资产 ``app/shared/utils/inspection/default_scripts.py`` 发布，
      lifespan 阶段 ``seed_default_groups()`` 幂等播种（只插不改，保留人工编辑）。
    - 内存缓存：``self._cache: Dict[name, rec]`` 与 ``self._id_cache: Dict[id, rec]``；
      两份字典共享同一 rec 对象，``rec["segments"]`` 字段保存分段列表。
      写路径持 ``self._write_lock``，避免并发扫描造成快照不一致。

设计要点：
    - 单例（``set_instance`` / ``get_instance`` / ``reset``）由 lifespan
      注入到 ``app.state.inspection_script_service``。
    - 写路径（``preload_all`` / ``upsert_segment`` / ``delete_segment`` /
      ``seed_default_groups``）持锁；读路径无锁。
    - 列表端点 ``list_scripts`` 严格白名单返回（不暴露脚本原文）；
      详情端点 ``get_script_detail`` 按需返回完整字段（含脚本原文 + 分段）。
    - 字段规则校验复用 ``app/shared/utils/inspection/parser.py::normalize_inspection_fields``。
    - D3 parser 约束：分段模式仅支持 ``json``；三层防护在
      ``upsert_segment`` / ``update_script_detail`` / ``get_connection_config`` 落点。

调用关系：
    - lifespan → InspectionScriptService(db).preload_all() → seed_default_groups() →
      app.state.inspection_script_service
    - admin router → service.list_scripts() / get_script_detail() /
      list_segments() / upsert_segment() / delete_segment() / delete_script()
    - DevOpsServerService._normalize_entry / _upsert_one_returning →
      service.get_script_by_name() / resolve_script_for_server()
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

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

# 分段白名单字段(分段 CRUD 响应 / 详情 segments 键使用)
_SEGMENT_FIELDS = (
    "id",
    "script_id",
    "segment_key",
    "display_name",
    "sort_order",
    "script",
    "enabled",
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

# 分段键正则:小写字母数字 + 下划线短横线,首字符必须字母数字,长度 1-64
_SEGMENT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_\-]{0,63}$")


class InspectionScriptService:
    """DevOps 巡检脚本库统一管理服务(单例)。

    Attributes:
        db: asyncpg 连接池;测试可传 MagicMock 替身。
        _cache: 内存缓存,键为脚本 ``name``,值为完整记录 dict(含 ``segments`` 列表)。
        _id_cache: 内存缓存,键为脚本 ``id``,与 _cache 共享同一 dict 对象。
        _write_lock: ``asyncio.Lock``,保护 ``_cache`` / ``_id_cache`` 写入。
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
        """重置全局单例(主要用于测试)。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, db: Any) -> None:
        """构造服务(2026-09-16:去除 YAML 路径入参)。

        Args:
            db: asyncpg 连接池;测试可传 ``MagicMock(name="db_pool_stub")``。

        Returns:
            None
        """
        self.db = db
        self._cache: Dict[str, Dict[str, Any]] = {}
        self._id_cache: Dict[int, Dict[str, Any]] = {}
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Preload from DB
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """从 DB 读取全部 ``inspection_scripts`` 行 + 全部分段到内存缓存。

        Returns:
            None
        """
        rows = await self.db.fetch(
            "SELECT id, name, display_name, platform, version, "
            "inspection_parser, inspection_script, inspection_fields, "
            "created_at, updated_at "
            "FROM inspection_scripts ORDER BY id"
        )
        seg_rows = await self.db.fetch(
            "SELECT id, script_id, segment_key, display_name, sort_order, "
            "script, enabled, created_at, updated_at "
            "FROM inspection_script_segments "
            "ORDER BY script_id, sort_order, segment_key, id"
        )
        # 按 script_id 聚合分段
        segments_by_script: Dict[int, List[Dict[str, Any]]] = {}
        for seg_row in seg_rows:
            seg_data = dict(seg_row)
            sid = seg_data.get("script_id")
            if sid is None:
                continue
            segments_by_script.setdefault(sid, []).append(seg_data)

        new_cache: Dict[str, Dict[str, Any]] = {}
        new_id_cache: Dict[int, Dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            script_id = data.get("id")
            name = data.get("name")
            if not name or script_id is None:
                continue
            # inspection_fields 还原(jsonb codec 兼容)
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
            # 2026-09-16:挂载分段列表(共享同一 dict 引用,后续 _reload_segments 原地更新)
            data["segments"] = segments_by_script.get(script_id, [])
            new_cache[name] = data
            new_id_cache[script_id] = data
        async with self._write_lock:
            self._cache = new_cache
            self._id_cache = new_id_cache
        logger.info(
            "[inspection_script_service] preloaded %d script(s) / %d segment(s)",
            len(self._cache), sum(len(v) for v in segments_by_script.values()),
        )

    # ------------------------------------------------------------------
    # Update script detail
    # ------------------------------------------------------------------

    async def update_script_detail(
        self,
        script_id: int,
        payload: Dict[str, Any],
    ) -> Optional[Dict[str, Any]]:
        """按 id 更新脚本详情(白名单字段 + 字段规则),同步缓存。

        Args:
            script_id: ``inspection_scripts.id``
            payload: 业务字段 dict,含 ``display_name`` / ``platform`` /
                ``version`` / ``inspection_parser`` / ``inspection_script`` /
                ``inspection_fields``

        Returns:
            Optional[Dict[str, Any]]: 更新后的完整记录(_DETAIL_FIELDS 字段);
            script_id 缺失 / 入参非法 / DB 无返回行 / D3 约束拒绝时返回 ``None``(不抛异常)
        """
        if script_id is None or not isinstance(script_id, int) or script_id <= 0:
            return None
        if not isinstance(payload, dict):
            return None

        # 2026-09-16 D3 防御:组存在 enabled 分段时,禁止切到非 json parser
        inspection_parser = (payload.get("inspection_parser") or "json").strip().lower()
        if inspection_parser not in _VALID_PARSERS:
            return None
        if inspection_parser != "json":
            existing = self._id_cache.get(int(script_id)) or {}
            if any(
                seg.get("enabled") for seg in existing.get("segments") or []
            ):
                logger.info(
                    "[inspection_script_service] update_script_detail rejected: "
                    "script_id=%d 已存在 enabled 分段,禁止切到 parser=%s",
                    int(script_id), inspection_parser,
                )
                return None

        display_name = payload.get("display_name")
        if not isinstance(display_name, str) or not display_name.strip():
            return None
        display_name = display_name.strip()

        platform = (payload.get("platform") or "linux").strip().lower()
        if platform not in ("linux", "windows"):
            return None

        version = payload.get("version")
        version = version.strip() if isinstance(version, str) else ""

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
                "ssd_warn": r.ssd_warn,
                "ssd_crit": r.ssd_crit,
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
            # 保留原 segments 列表(本方法不管理分段)
            original = self._id_cache.get(int(script_id))
            if isinstance(original, dict):
                record["segments"] = original.get("segments") or []
            else:
                record["segments"] = []
            record_name = record.get("name")
            if isinstance(record_name, str) and record_name.strip():
                self._cache[record_name] = record
            self._id_cache[int(script_id)] = record
        return {k: record.get(k) for k in _DETAIL_FIELDS}

    # ------------------------------------------------------------------
    # Delete script
    # ------------------------------------------------------------------

    async def delete_script(self, script_id: int) -> bool:
        """按 ``id`` 单事务删除脚本库条目并清理缓存。

        行为：
            - 入参非法(None / 非 int / <=0)→ 返回 ``False``(不调 DB)。
            - 单事务内依次执行：
              1. ``SELECT name FROM inspection_scripts WHERE id=$1 FOR UPDATE``
                 锁住脚本行,拿到权威 name(DB 真实事实,不依赖删除前的缓存);
              2. ``UPDATE devops_servers SET inspection_script_id=NULL
                 WHERE inspection_script_id=$1``(业务层显式解绑服务器外键);
              3. ``DELETE FROM inspection_script_segments WHERE script_id=$1``
                 显式清理分段(FK CASCADE 兜底之外,提高可观察性);
              4. ``DELETE FROM inspection_scripts WHERE id=$1`` 真正删除脚本行。
            - DB 无匹配行(SELECT 未命中 / DELETE 0)→ 返回 False,缓存保持原样。
            - DB 异常 → 异常向上抛出,由路由层映射为通用 500;缓存保持原样。
            - 事务成功提交后持 ``_write_lock`` 清理缓存:
              移除 ``_id_cache[script_id]``;若 ``_cache[name]`` 仍指向该 id,移除;
              清理同 name 漂移到其它 id 的残留。

        Args:
            script_id: ``inspection_scripts.id``

        Returns:
            bool: 已删除返回 ``True``;不存在 / 入参非法返回 ``False``;
            DB 异常向上抛出。
        """
        if script_id is None or not isinstance(script_id, int) or script_id <= 0:
            return False

        name_to_clear: Optional[str] = None
        async with self.db.acquire() as conn:  # type: ignore[attr-defined]
            async with conn.transaction():
                row = await conn.fetchrow(
                    "SELECT name FROM inspection_scripts WHERE id = $1 FOR UPDATE",
                    int(script_id),
                )
                if row is None:
                    return False
                row_data = dict(row) if not isinstance(row, dict) else row
                name_val = row_data.get("name")
                if isinstance(name_val, str) and name_val.strip():
                    name_to_clear = name_val.strip()

                await conn.execute(
                    "UPDATE devops_servers SET inspection_script_id = NULL "
                    "WHERE inspection_script_id = $1",
                    int(script_id),
                )
                # 2026-09-16 新增:显式清理 segments(FK CASCADE 兜底之外)
                await conn.execute(
                    "DELETE FROM inspection_script_segments WHERE script_id = $1",
                    int(script_id),
                )
                result = await conn.execute(
                    "DELETE FROM inspection_scripts WHERE id = $1",
                    int(script_id),
                )
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
            if name_to_clear:
                existing = self._cache.get(name_to_clear)
                if isinstance(existing, dict) and existing.get("id") == int(script_id):
                    self._cache.pop(name_to_clear, None)
                stale_ids = [
                    k for k, v in self._id_cache.items()
                    if isinstance(v, dict)
                    and v.get("name") == name_to_clear
                    and k != int(script_id)
                ]
                for sid in stale_ids:
                    self._id_cache.pop(sid, None)
        return True

    # ------------------------------------------------------------------
    # Segment CRUD (2026-09-16 新增)
    # ------------------------------------------------------------------

    def list_segments(self, script_id: int) -> Optional[List[Dict[str, Any]]]:
        """列出组的全部分段(含 disabled,按 sort_order 升序)。

        参数:
            script_id: inspection_scripts 主键 id

        返回:
            Optional[List[Dict[str, Any]]]: 组存在时分段列表(白名单字段);
            组不存在返回 None
        """
        rec = self._id_cache.get(int(script_id))
        if rec is None:
            return None
        return [
            {k: seg.get(k) for k in _SEGMENT_FIELDS}
            for seg in rec.get("segments") or []
        ]

    async def upsert_segment(
        self,
        script_id: int,
        payload: Dict[str, Any],
        segment_id: Optional[int] = None,
    ) -> Optional[Dict[str, Any]]:
        """创建或更新分段(校验 + DB + 缓存同步)。

        参数:
            script_id: 所属组 id
            payload: segment_key / display_name / sort_order / script / enabled
            segment_id: None=创建;非 None=更新该分段

        返回:
            Optional[Dict[str, Any]]: 成功返回分段白名单 dict;组不存在返回 None

        异常:
            ValueError: 组 parser != 'json' / segment_key 非法 / script 空白 /
                payload 类型非法时抛出(消息不含脚本原文)
        """
        rec = self._id_cache.get(int(script_id))
        if rec is None:
            return None
        if (rec.get("inspection_parser") or "json") != "json":
            raise ValueError("仅 json 解析器的脚本组支持分段")
        if not isinstance(payload, dict):
            raise ValueError("payload must be dict")
        segment_key = str(payload.get("segment_key") or "").strip()
        if not _SEGMENT_KEY_RE.match(segment_key):
            raise ValueError(
                "segment_key 非法(须匹配 ^[a-z0-9][a-z0-9_-]{0,63}$)"
            )
        script = payload.get("script")
        if not isinstance(script, str) or not script.strip():
            raise ValueError("script 不能为空")
        script = script.rstrip("\n")
        display_name = str(payload.get("display_name") or "").strip()
        sort_order = payload.get("sort_order", 0)
        if not isinstance(sort_order, int) or isinstance(sort_order, bool):
            raise ValueError("sort_order must be int")
        enabled = bool(payload.get("enabled", True))

        if segment_id is None:
            row = await self.db.fetchrow(
                "INSERT INTO inspection_script_segments "
                "(script_id, segment_key, display_name, sort_order, script, "
                " enabled, created_at, updated_at) "
                "VALUES ($1, $2, $3, $4, $5, $6, NOW(), NOW()) "
                "ON CONFLICT (script_id, segment_key) DO UPDATE SET "
                "display_name = EXCLUDED.display_name, "
                "sort_order = EXCLUDED.sort_order, "
                "script = EXCLUDED.script, "
                "enabled = EXCLUDED.enabled, updated_at = NOW() "
                "RETURNING id",
                int(script_id), segment_key, display_name, sort_order,
                script, enabled,
            )
        else:
            row = await self.db.fetchrow(
                "UPDATE inspection_script_segments SET "
                "segment_key = $3, display_name = $4, sort_order = $5, "
                "script = $6, enabled = $7, updated_at = NOW() "
                "WHERE id = $1 AND script_id = $2 RETURNING id",
                int(segment_id), int(script_id), segment_key, display_name,
                sort_order, script, enabled,
            )
        if not row:
            return None
        await self._reload_segments(int(script_id))
        # 在刷新的 segments 中查找匹配 id 的段返回白名单字段
        new_id = row["id"] if not isinstance(row, dict) else row.get("id")
        rec = self._id_cache.get(int(script_id)) or {}
        for seg in rec.get("segments") or []:
            if seg.get("id") == new_id:
                return {k: seg.get(k) for k in _SEGMENT_FIELDS}
        return None

    async def delete_segment(self, script_id: int, segment_id: int) -> bool:
        """删除分段并同步缓存。

        参数:
            script_id: 所属组 id;segment_id: 分段 id

        返回:
            bool: 删除成功 True;不存在 False
        """
        result = await self.db.execute(
            "DELETE FROM inspection_script_segments WHERE id = $1 AND script_id = $2",
            int(segment_id), int(script_id),
        )
        affected = 0
        if isinstance(result, str) and result.startswith("DELETE"):
            try:
                affected = int(result.split()[1])
            except (IndexError, ValueError):
                affected = 0
        if affected == 0:
            return False
        await self._reload_segments(int(script_id))
        return True

    async def _reload_segments(self, script_id: int) -> None:
        """按 script_id 重查分段并刷新共享缓存对象。

        参数:
            script_id: inspection_scripts 主键 id

        返回:
            None
        """
        rows = await self.db.fetch(
            "SELECT id, script_id, segment_key, display_name, sort_order, "
            "script, enabled, created_at, updated_at "
            "FROM inspection_script_segments WHERE script_id = $1 "
            "ORDER BY sort_order, segment_key, id",
            int(script_id),
        )
        segments = [dict(r) for r in rows]
        async with self._write_lock:
            rec = self._id_cache.get(int(script_id))
            if rec is not None:
                rec["segments"] = segments

    # ------------------------------------------------------------------
    # Default scripts seeding (2026-09-16 新增)
    # ------------------------------------------------------------------

    async def seed_default_groups(self) -> Dict[str, int]:
        """空库幂等播种默认巡检组与分段(只插不改,保留人工编辑)。

        对 DEFAULT_INSPECTION_GROUPS 每组:
            1. 组名不在缓存 → INSERT 组行(ON CONFLICT DO NOTHING),
               RETURNING 行同步缓存;
            2. 组 segments 为空 → 逐段 INSERT ... ON CONFLICT DO NOTHING,
               完成后 _reload_segments。

        返回:
            Dict[str, int]: {"groups_inserted", "segments_inserted", "skipped"}
        """
        from app.shared.utils.inspection.default_scripts import (
            DEFAULT_INSPECTION_GROUPS,
        )

        stats = {"groups_inserted": 0, "segments_inserted": 0, "skipped": 0}
        for group in DEFAULT_INSPECTION_GROUPS:
            name = group["name"]
            rec = self.get_script_by_name(name)
            if rec is None:
                row = await self.db.fetchrow(
                    "INSERT INTO inspection_scripts "
                    "(name, display_name, platform, version, "
                    " inspection_parser, inspection_script, inspection_fields, "
                    " created_at, updated_at) "
                    "VALUES ($1, $2, $3, $4, $5, NULL, $6::jsonb, NOW(), NOW()) "
                    "ON CONFLICT (name) DO NOTHING "
                    "RETURNING id, name, display_name, platform, version, "
                    "inspection_parser, inspection_script, inspection_fields, "
                    "created_at, updated_at",
                    name,
                    group["display_name"],
                    group["platform"],
                    group["version"],
                    group["inspection_parser"],
                    json.dumps(group["inspection_fields"], ensure_ascii=False),
                )
                if row is not None:
                    row_data = dict(row)
                    raw_fields = row_data.get("inspection_fields")
                    if isinstance(raw_fields, str):
                        try:
                            row_data["inspection_fields"] = json.loads(raw_fields)
                        except (json.JSONDecodeError, TypeError):
                            row_data["inspection_fields"] = []
                    row_data["segments"] = []
                    async with self._write_lock:
                        self._cache[name] = row_data
                        self._id_cache[row_data["id"]] = row_data
                    stats["groups_inserted"] += 1
                rec = self.get_script_by_name(name)
            if rec is None:
                continue
            # 2026-09-16:每次播种前重读最新 segments(幂等判定走"当前 DB 真实状态"),
            # 避免上次 reload 返回 [] 而误判为可播种。
            await self._reload_segments(int(rec["id"]))
            rec = self.get_script_by_name(name) or {}
            if rec.get("segments"):
                stats["skipped"] += 1
                continue
            for seg in group["segments"]:
                await self.db.execute(
                    "INSERT INTO inspection_script_segments "
                    "(script_id, segment_key, display_name, sort_order, script, "
                    " enabled, created_at, updated_at) "
                    "VALUES ($1, $2, $3, $4, $5, TRUE, NOW(), NOW()) "
                    "ON CONFLICT (script_id, segment_key) DO NOTHING",
                    int(rec["id"]), seg["segment_key"], seg["display_name"],
                    int(seg["sort_order"]), seg["script"],
                )
                stats["segments_inserted"] += 1
            await self._reload_segments(int(rec["id"]))
        return stats

    # ------------------------------------------------------------------
    # Public read APIs
    # ------------------------------------------------------------------

    def list_scripts(self) -> List[Dict[str, Any]]:
        """返回脚本库白名单字段列表(不暴露脚本原文)。

        Returns:
            List[Dict[str, Any]]: 每项仅含 ``_LIST_FIELDS`` 字段
        """
        result: List[Dict[str, Any]] = []
        for rec in self._cache.values():
            result.append({k: rec.get(k) for k in _LIST_FIELDS})
        return result

    def get_script_detail(self, script_id: int) -> Optional[Dict[str, Any]]:
        """按 ``id`` 取完整脚本详情(含脚本原文、字段规则、分段列表)。

        Args:
            script_id: inspection_scripts 主键 id

        Returns:
            Optional[Dict[str, Any]]: 命中时含 ``_DETAIL_FIELDS`` + ``segments``;
            未命中时 ``None``
        """
        rec = self._id_cache.get(int(script_id))
        if rec is None:
            return None
        result = {k: rec.get(k) for k in _DETAIL_FIELDS}
        result["segments"] = [
            {k: seg.get(k) for k in _SEGMENT_FIELDS}
            for seg in rec.get("segments") or []
        ]
        return result

    def get_script_by_id(self, script_id: int) -> Optional[Dict[str, Any]]:
        """按 ``id`` 取完整记录(内部使用,含完整字段)。

        Args:
            script_id: inspection_scripts 主键 id

        Returns:
            Optional[Dict[str, Any]]: 命中时返回完整记录;未命中 ``None``
        """
        return self._id_cache.get(int(script_id))

    def get_script_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """按 ``name`` 取完整记录(内部使用,含完整字段)。

        Args:
            name: 脚本库条目的唯一 name

        Returns:
            Optional[Dict[str, Any]]: 命中时返回完整记录;未命中 ``None``
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

        解析规则:
            1. 显式 ``script_name`` 非空 → 按 name 查 cache,命中返回 id;
               未命中返回 ``None``(不静默回退,避免外部误以为找到了)。
            2. ``script_name`` 为空 → 按 ``server_type`` 匹配默认脚本名
               (``linux → linux-bash``,``windows → windows-ps-5.1``);
               默认脚本未注册返回 ``None``。

        Args:
            server_type: ``linux`` 或 ``windows``
            script_name: 可选脚本库 name

        Returns:
            Optional[int]: 命中时返回 inspection_scripts.id;未命中 ``None``
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
