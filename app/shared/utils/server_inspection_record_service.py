#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
服务器采集结果落库服务（2026-08-05 新增）。

负责把 ``run_server_ops`` 返回的 ``ServerOpsReport``（或同形结构）按
物理服务器维度持久化到 ``server_inspection_records`` 历史表与
``server_latest_snapshot`` 快照表，供运维控制台（ops-console）按
``OwnershipScope`` 展示最新采集状态。

设计要点：
    * 双表**同事务**写入（``pool.acquire() + conn.transaction()``，
      与项目既有的 ``InspectionScriptService.delete_script`` 事务模式
      一致），杜绝快照与历史不一致；
    * **不**维护内存缓存（与 ``DevOpsServerService`` / ``ApiConfigService``
      不同）：写入读出均直查 DB；``devops_server_service`` 与
      ``inspection_script_service`` 仅在写入阶段被消费（用于 name → id
      映射），由 lifespan 注入；
    * ``db=None``（内存降级模式）对齐 ``ApiConfigService`` 语义：
      读返回空列表，写抛 ``RuntimeError("数据库未启用")``；
    * 数据按物理服务器（``devops_servers.id``）归属，多用户共享同一份
      采集数据（指标是服务器事实，不随用户变）；手动采集记录的触发人
      写入 ``created_by_user_id`` 供审计。

依赖注入：
    * ``devops_server_service`` —— 注入以取 ``business_name → id`` 映射
      与 ``id → business_name`` 映射（基于 ``list_public_servers()``
      内存缓存，零 DB IO）；
    * ``inspection_script_service`` —— 注入以反查 ``inspection_script_id``
      （按 ``inspection_script_name`` 反查，records 表该列可空）；
    * ``user_server_service`` —— ``list_latest`` 普通用户分支依赖其
      ``list_nodes(scope)`` 内存缓存（按 ``OwnershipScope`` 过滤）。
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence

from app.shared.utils.auth.ownership_scope import OwnershipScope


logger = logging.getLogger(__name__)


# 服务器采集状态 → ops-console LED 三态 映射
_STATUS_OK = "ok"
_STATUS_ERR = "err"
_STATUS_UNKNOWN = "unknown"

# inspection_status 取值集合（与 server_inspection_records CHECK 对齐）
_VALID_INSPECTION_STATUS = {"pass", "warn", "crit", "unassessed", "skipped"}


class ServerInspectionNotFoundError(LookupError):
    """服务器或采集记录不存在/越权时抛出（路由层映射为 404）。"""


class ServerInspectionPermissionError(PermissionError):
    """调用方无权采集目标服务器时抛出（路由层映射为 403）。"""


@dataclass
class _ServerOpsItemLike:
    """``ServerOpsItem`` 兼容协议 —— service 只读这些字段，避免耦合 dataclass。

    Attributes:
        business_name: 业务名（``devops_servers.business_name``）。
        success: SSH 执行成功与否（退出码 0 = True；未执行 = None）。
        skipped: 是否跳过（脚本未关联 / 业务名未注册等）。
        exit_code: 远端进程退出码。
        duration_ms: 耗时毫秒。
        inspection_status: 巡检总体状态（pass/warn/crit/unassessed/skipped）。
        inspection_script_name: 关联脚本库条目的 name（如 linux-bash）。
        error_message: 错误摘要。
        inspection_error: 巡检阶段错误。
        parsed_values: 解析得到的原始值（dict 或 raw 透传）。
        field_results: 字段评估结果列表（``InspectionFieldResult.vars()``）。
    """

    business_name: str
    success: Optional[bool] = None
    skipped: bool = False
    exit_code: Optional[int] = None
    duration_ms: Optional[int] = None
    inspection_status: str = "unassessed"
    inspection_script_name: Optional[str] = None
    error_message: str = ""
    inspection_error: str = ""
    parsed_values: Any = None
    field_results: List[Dict[str, Any]] = None  # type: ignore[assignment]


class ServerInspectionRecordService:
    """服务器采集结果落库与查询服务。

    唯一落库入口 ``save_inspection_result``；运维控制台 ``GET /latest`` 与
    ``GET /records`` 走 ``list_latest`` / ``list_records``，手动采集入口
    ``POST /collect`` 走 ``resolve_collect_targets`` 校验 + 上述三方法
    串联。

    参数:
        db: 数据库连接池（asyncpg.Pool 或兼容接口）；``None`` 表示内存降级
            模式（读返回空，写抛 ``RuntimeError``）。
        devops_server_service: 可选 ``DevOpsServerService`` 实例，未注入时
            写入无法解析 ``server_id``（除业务名已注册外无影响）；不阻塞
            读取。
        user_server_service: 可选 ``UserServerService`` 实例；``list_latest``
            普通用户分支按 ``OwnershipScope`` 过滤依赖其内存缓存。
        inspection_script_service: 可选 ``InspectionScriptService`` 实例；
            写入阶段反查 ``inspection_script_id``，未注入时该列留 NULL。
    """

    def __init__(
        self,
        db: Any = None,
        *,
        devops_server_service: Any = None,
        user_server_service: Any = None,
        inspection_script_service: Any = None,
    ) -> None:
        """初始化服务。

        参数:
            db: 数据库连接池；``None`` 时进入降级模式。
            devops_server_service: 见类注释。
            user_server_service: 见类注释。
            inspection_script_service: 见类注释。
        """
        self._db = db
        self._devops_server_service = devops_server_service
        self._user_server_service = user_server_service
        self._inspection_script_service = inspection_script_service

    # ------------------------------------------------------------------
    # 写入（唯一落库入口）
    # ------------------------------------------------------------------

    async def save_inspection_result(
        self,
        report: Any,
        *,
        schedule_id: Optional[int] = None,
        run_id: Optional[int] = None,
        created_by_user_id: Optional[int] = None,
    ) -> int:
        """把 ``ServerOpsReport.items`` 逐台写入历史与快照。

        调用时机：
            * ``ops_inspection_sweep`` 在 ``run_server_ops`` 返回后
              （fail-soft 包装）；参数 ``schedule_id=context.schedule_id``
              ``run_id=context.run_id``。
            * ``POST /api/admin/server-inspection/collect`` 合成 context
              跑完 ``run_server_ops`` 后；参数
              ``created_by_user_id=scope.user_id``，
              ``schedule_id=None`` ``run_id=None``。

        业务规则：
            * 业务名未在 ``devops_servers`` 注册 → 记 warning + 跳过该台，
              不中断整体；其余成功行仍落库。
            * 全局同事务，``INSERT records`` + ``UPSERT snapshot`` 在同一
              ``conn.transaction()`` 内执行；任一行失败整体回滚。

        参数:
            report: ``ServerOpsReport`` 或 ``items`` 字段为可迭代对象的兼容结构。
            schedule_id: 触发本次采集的定时任务 ID；手动采集为 ``None``。
            run_id: 触发本次采集的执行记录 ID；手动采集为 ``None``。
            created_by_user_id: 手动采集触发人 ID；定时采集为 ``None``。

        返回:
            int: 成功落库台数（成功 INSERT 的 records 行数）。

        异常:
            RuntimeError: db 为 None 时抛出。
        """
        if self._db is None:
            raise RuntimeError("数据库未启用")

        items = self._extract_items(report)
        if not items:
            return 0

        # business_name → server_id 映射（基于内存缓存，零 DB IO）
        name_to_id: Dict[str, int] = {}
        if self._devops_server_service is not None:
            try:
                for row in self._devops_server_service.list_public_servers() or []:
                    bn = row.get("business_name")
                    sid = row.get("id")
                    if bn and sid is not None:
                        name_to_id[bn] = int(sid)
            except Exception as exc:
                logger.warning(
                    "save_inspection_result: devops_server_service.list_public_servers 失败: %s",
                    exc,
                )

        # 同事务内所有行共用同一 collected_at
        collected_at = datetime.now()
        saved = 0
        records_sql = """
            INSERT INTO server_inspection_records (
                server_id, business_name, collected_at,
                schedule_id, run_id, inspection_script_id, created_by_user_id,
                success, skipped, exit_code, duration_ms,
                inspection_status, error_message, inspection_error,
                parsed_values, field_results
            ) VALUES (
                $1, $2, $3,
                $4, $5, $6, $7,
                $8, $9, $10, $11,
                $12, $13, $14,
                $15::jsonb, $16::jsonb
            )
            RETURNING id
        """
        snapshot_sql = """
            INSERT INTO server_latest_snapshot (
                server_id, record_id, business_name, collected_at,
                success, inspection_status, duration_ms, error_message,
                parsed_values, field_results
            ) VALUES (
                $1, $2, $3, $4,
                $5, $6, $7, $8,
                $9::jsonb, $10::jsonb
            )
            ON CONFLICT (server_id) DO UPDATE SET
                record_id         = EXCLUDED.record_id,
                business_name     = EXCLUDED.business_name,
                collected_at      = EXCLUDED.collected_at,
                success           = EXCLUDED.success,
                inspection_status = EXCLUDED.inspection_status,
                duration_ms       = EXCLUDED.duration_ms,
                error_message     = EXCLUDED.error_message,
                parsed_values     = EXCLUDED.parsed_values,
                field_results     = EXCLUDED.field_results,
                updated_at        = NOW()
        """

        async with self._db.acquire() as conn:
            async with conn.transaction():
                for item in items:
                    like = self._coerce_item(item)
                    server_id = name_to_id.get(like.business_name)
                    if server_id is None:
                        logger.warning(
                            "save_inspection_result: 业务名 %s 未在 devops_servers 注册，跳过",
                            like.business_name,
                        )
                        continue

                    inspection_script_id = self._resolve_script_id(like.inspection_script_name)
                    parsed_values_json = self._dump_jsonb(like.parsed_values)
                    field_results_json = self._dump_jsonb(like.field_results or [])

                    row = await conn.fetchrow(
                        records_sql,
                        server_id,
                        like.business_name,
                        collected_at,
                        schedule_id,
                        run_id,
                        inspection_script_id,
                        created_by_user_id,
                        like.success,
                        like.skipped,
                        like.exit_code,
                        like.duration_ms,
                        like.inspection_status,
                        like.error_message or None,
                        like.inspection_error or None,
                        parsed_values_json,
                        field_results_json,
                    )
                    record_id = int(row["id"])

                    await conn.execute(
                        snapshot_sql,
                        server_id,
                        record_id,
                        like.business_name,
                        collected_at,
                        like.success,
                        like.inspection_status,
                        like.duration_ms,
                        like.error_message or None,
                        parsed_values_json,
                        field_results_json,
                    )
                    saved += 1
        return saved

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    async def list_latest(self, scope: OwnershipScope) -> List[Dict[str, Any]]:
        """列出每个可见服务器的最新采集快照（供运维控制台首页）。

        数据归属：
            * admin / system → 全量 ``devops_servers``（LEFT JOIN snapshot）；
            * 普通用户 → 通过 ``user_server_service.list_nodes(scope)`` 拿
              可见节点集，过滤 ``node_type=='server'``，按 ``server_id``
              去重（最小 ``node_id`` 的节点名胜出），按
              ``sort_order, node_id`` 排序。

        每行派生：
            * ``status``：``pass`` → ok；``warn/crit/success=False`` → err；
              其余（含 ``skipped`` / ``unassessed`` / 无快照）→ unknown。
            * ``metrics.cpu``：linux 取 ``100 - cpu_idle_pct``；windows 取
              ``cpu_used_pct``；缺失 → ``None``。
            * ``metrics.mem``：``mem_used_pct``；缺失 → ``None``。
            * ``metrics.disk``：``disks[]`` 中系统盘（linux ``/``，windows
              ``C:\\`` / ``C:`` / ``C:/``）的 ``disk_used_pct``；找不到则
              取第一块可用盘；仍无 → ``None``。

        返回字段白名单（不含 ``ip`` / ``port`` / ``password`` 等敏感字段）：
            ``node_id / node_name / server_id / business_name / server_type /
            status / inspection_status / collected_at / duration_ms /
            metrics / disks / parsed_values / field_results / error_message``
            （2026-08-16 新增 ``field_results``：每字段评估结果数组，供前端
            卡片智能选异常盘符；无快照时为空列表）

        参数:
            scope: 调用方归属上下文。

        返回:
            List[Dict[str, Any]]: 每行对应一台可见服务器的最新快照。
        """
        if self._db is None:
            return []

        if scope.is_admin or scope.system:
            return await self._list_latest_admin()

        nodes = self._collect_user_server_nodes(scope)
        return await self._list_latest_user(nodes)

    async def list_records(
        self,
        server_id: int,
        scope: OwnershipScope,
        *,
        start: Optional[datetime] = None,
        end: Optional[datetime] = None,
        limit: int = 100,
    ) -> Optional[List[Dict[str, Any]]]:
        """列出指定服务器的采集历史。

        可见性校验：admin / system → 服务器存在即可；普通用户 → server_id
        必须在自己的 ``user_server_nodes`` 可见集内。缺失/越权统一返回
        ``None``（router 映射 404，不回显 id）。

        参数:
            server_id: ``devops_servers.id``。
            scope: 调用方归属上下文。
            start: 起始时间（含），为 ``None`` 时不限下界。
            end: 截止时间（含），为 ``None`` 时不限上界。
            limit: 最大返回条数（默认 100，最大 1000）。

        返回:
            Optional[List[Dict[str, Any]]]: 历史记录列表（``collected_at DESC``）；
            不可见时返回 ``None``。

        异常:
            ValueError: ``limit`` 不在 1~1000 区间时抛出（router 映射 400）。
        """
        if self._db is None:
            return []
        if limit < 1 or limit > 1000:
            raise ValueError("limit must be between 1 and 1000")

        if not await self._is_server_visible(server_id, scope):
            return None

        # 动态拼 SQL 占位符（start / end 各自可空）
        where_parts = ["server_id = $1"]
        params: List[Any] = [server_id]
        next_idx = 2
        if start is not None:
            where_parts.append(f"collected_at >= ${next_idx}")
            params.append(start)
            next_idx += 1
        if end is not None:
            where_parts.append(f"collected_at <= ${next_idx}")
            params.append(end)
            next_idx += 1
        params.append(limit)
        where_sql = " AND ".join(where_parts)
        sql = (
            f"SELECT * FROM server_inspection_records "
            f"WHERE {where_sql} ORDER BY collected_at DESC LIMIT ${next_idx}"
        )
        rows = await self._db.fetch(sql, *params)
        return [self._row_to_history_record(dict(r)) for r in rows]

    def resolve_collect_targets(
        self,
        server_ids: Sequence[int],
        scope: OwnershipScope,
    ) -> List[str]:
        """手动采集入口的可见性 + 存在性校验，返回业务名列表。

        校验规则：
            * 任一 ``server_id`` 在 ``devops_servers`` 中不存在 → 返回
              ``None``（router 映射 404，不回显 id）；
            * 普通用户任一 ``server_id`` 不在自己可见节点集内 → 抛
              ``ServerInspectionPermissionError``（router 映射 403）；
            * admin / system 全量放行；
            * ``server_ids`` 去重保持输入顺序，重复 id 仅一次。

        参数:
            server_ids: ``devops_servers.id`` 列表。
            scope: 调用方归属上下文。

        返回:
            List[str]: 业务名列表（按 ``server_ids`` 去重后的输入顺序）。

        异常:
            ServerInspectionPermissionError: 普通用户越权。
            ServerInspectionNotFoundError: 任一 id 在 devops_servers 不存在。
            RuntimeError: db 未启用。
        """
        if self._db is None:
            raise RuntimeError("数据库未启用")

        # 去重保序
        seen: set = set()
        ordered_ids: List[int] = [int(sid) for sid in server_ids if not (sid in seen or seen.add(sid))]

        id_to_name, visible_ids = self._build_id_indexes(scope)

        # 存在性校验
        missing = [sid for sid in ordered_ids if sid not in id_to_name]
        if missing:
            raise ServerInspectionNotFoundError("采集目标不存在")

        # 归属校验（非 admin）
        if not (scope.is_admin or scope.system):
            unauthorized = [sid for sid in ordered_ids if sid not in visible_ids]
            if unauthorized:
                raise ServerInspectionPermissionError("采集目标不属于当前用户")

        return [id_to_name[sid] for sid in ordered_ids if sid in id_to_name]

    # ------------------------------------------------------------------
    # 派生 helper（私有）
    # ------------------------------------------------------------------

    @staticmethod
    def _derive_status(
        success: Optional[bool],
        skipped: bool,
        inspection_status: str,
    ) -> str:
        """派生 LED 三态。

        规则：
            * ``skipped`` → unknown（视为未执行）；
            * ``success is None`` → unknown（采集事实缺失，无法判定）；
            * ``success is False`` → err（SSH 失败）；
            * ``inspection_status == 'pass'`` → ok；
            * ``inspection_status in {'warn','crit'}`` → err；
            * 其余（``unassessed`` 或异常值）→ unknown。

        参数:
            success: SSH 退出码 0 = True；未执行 = None。
            skipped: 是否跳过本台。
            inspection_status: 巡检总体状态字符串。

        返回:
            str: ``ok`` / ``err`` / ``unknown``。
        """
        if skipped:
            return _STATUS_UNKNOWN
        if success is None:
            return _STATUS_UNKNOWN
        if success is False:
            return _STATUS_ERR
        if inspection_status == "pass":
            return _STATUS_OK
        if inspection_status in ("warn", "crit"):
            return _STATUS_ERR
        return _STATUS_UNKNOWN

    @staticmethod
    def _derive_metrics(
        server_type: str,
        parsed_values: Any,
    ) -> Dict[str, Optional[float]]:
        """派生 cpu/mem/disk/load 四项指标。

        参数:
            server_type: ``linux`` / ``windows`` / 其他。
            parsed_values: ``run_server_ops`` 解析得到的 dict（可能为 None）。

        返回:
            Dict[str, Optional[float]]: ``{cpu, mem, disk, load}``，缺失字段为 None。
            ``load`` 仅 linux 取自 ``parsed_values.load_1m``（1 分钟平均负载，
            非百分比），windows / 其他平台返回 ``None`` 让前端按需隐藏。
        """
        empty = {"cpu": None, "mem": None, "disk": None, "load": None}
        if not isinstance(parsed_values, dict):
            return empty
        pv = parsed_values
        cpu = ServerInspectionRecordService._derive_cpu(server_type, pv)
        mem = ServerInspectionRecordService._coerce_float(pv.get("mem_used_pct"))
        disk = ServerInspectionRecordService._pick_root_disk_pct(
            pv.get("disks") or [], server_type,
        )
        # load 仅 linux 取值；windows 脚本无该字段，避免误读其他键名
        load: Optional[float] = None
        if str(server_type).lower() == "linux":
            load = ServerInspectionRecordService._coerce_float(pv.get("load_1m"))
        return {"cpu": cpu, "mem": mem, "disk": disk, "load": load}

    @staticmethod
    def _derive_cpu(server_type: str, pv: Dict[str, Any]) -> Optional[float]:
        """派生 cpu 使用率（百分比）。linux: 100 - cpu_idle_pct；windows: cpu_used_pct。"""
        if server_type == "windows":
            return ServerInspectionRecordService._coerce_float(pv.get("cpu_used_pct"))
        # linux / 其它：优先 100 - cpu_idle_pct
        idle = ServerInspectionRecordService._coerce_float(pv.get("cpu_idle_pct"))
        if idle is not None:
            try:
                return round(100.0 - idle, 2)
            except TypeError:
                return None
        # 兜底：脚本直出 cpu_used_pct
        return ServerInspectionRecordService._coerce_float(pv.get("cpu_used_pct"))

    @staticmethod
    def _pick_root_disk_pct(
        disks: Iterable[Any],
        server_type: str,
    ) -> Optional[float]:
        """选系统盘占用率。linux: '/'；windows: 'C:\\' / 'C:' / 'C:/'。

        找不到系统盘时取第一块可用盘；都不可用 → ``None``。

        参数:
            disks: 解析值中 ``disks`` 数组（可能为 None）。
            server_type: ``linux`` / ``windows``。

        返回:
            Optional[float]: 占用率（0-100）；不可用 → ``None``。
        """
        items = list(disks) if isinstance(disks, list) else []
        # 1) 系统盘优先
        for d in items:
            if not isinstance(d, dict):
                continue
            mount = d.get("mount")
            if mount is None:
                continue
            if ServerInspectionRecordService._is_root_mount(str(mount), server_type):
                v = ServerInspectionRecordService._coerce_float(d.get("disk_used_pct"))
                if v is not None:
                    return v
        # 2) fallback：第一块可用盘
        for d in items:
            if not isinstance(d, dict):
                continue
            v = ServerInspectionRecordService._coerce_float(d.get("disk_used_pct"))
            if v is not None:
                return v
        return None

    @staticmethod
    def _is_root_mount(mount: str, server_type: str) -> bool:
        """判定是否为系统盘挂载点。

        参数:
            mount: 挂载点字符串。
            server_type: ``linux`` / ``windows``。

        返回:
            bool: 是否为系统盘。
        """
        m = mount.strip()
        if server_type == "windows":
            mu = m.upper().rstrip("\\").rstrip("/").rstrip(":")
            return mu in ("C", "C:")
        return m == "/"

    @staticmethod
    def _coerce_float(value: Any) -> Optional[float]:
        """安全转换为 float；非数字（含 bool/字符串/None）→ ``None``。"""
        if value is None:
            return None
        if isinstance(value, bool):
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # 内部 helper
    # ------------------------------------------------------------------

    def _resolve_script_id(self, script_name: Optional[str]) -> Optional[int]:
        """按 ``inspection_script_name`` 反查 ``inspection_scripts.id``。"""
        if not script_name or self._inspection_script_service is None:
            return None
        try:
            rec = self._inspection_script_service.get_script_by_name(script_name)
        except Exception as exc:
            logger.warning(
                "save_inspection_result: inspection_script_service.get_script_by_name 失败: %s",
                exc,
            )
            return None
        if rec is None:
            return None
        sid = rec.get("id")
        if sid is None:
            return None
        try:
            return int(sid)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dump_jsonb(value: Any) -> str:
        """安全 JSON 序列化（``ensure_ascii=False``，失败降级为 ``repr``）。"""
        if value is None:
            return "null"
        try:
            return json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return json.dumps(repr(value), ensure_ascii=False)

    @staticmethod
    def _extract_items(report: Any) -> List[Any]:
        """从 ``report`` 中提取 items 列表；空 report → 空列表。"""
        if report is None:
            return []
        items = getattr(report, "items", None)
        if items is None and isinstance(report, dict):
            items = report.get("items")
        if not items:
            return []
        return list(items)

    @staticmethod
    def _coerce_item(item: Any) -> _ServerOpsItemLike:
        """把 ``ServerOpsItem`` 或 dict 统一归一化为 ``_ServerOpsItemLike``。"""
        if isinstance(item, dict):
            return _ServerOpsItemLike(
                business_name=str(item.get("business_name") or ""),
                success=item.get("success"),
                skipped=bool(item.get("skipped") or False),
                exit_code=item.get("exit_code"),
                duration_ms=item.get("duration_ms"),
                inspection_status=str(item.get("inspection_status") or "unassessed"),
                inspection_script_name=item.get("inspection_script_name"),
                error_message=str(item.get("error_message") or ""),
                inspection_error=str(item.get("inspection_error") or ""),
                parsed_values=item.get("parsed_values"),
                field_results=item.get("field_results") or [],
            )
        # dataclass / pydantic 兼容：用 getattr 取值
        def _g(name: str, default: Any = None) -> Any:
            return getattr(item, name, default)

        return _ServerOpsItemLike(
            business_name=str(_g("business_name") or ""),
            success=_g("success"),
            skipped=bool(_g("skipped") or False),
            exit_code=_g("exit_code"),
            duration_ms=_g("duration_ms"),
            inspection_status=str(_g("inspection_status") or "unassessed"),
            inspection_script_name=_g("inspection_script_name"),
            error_message=str(_g("error_message") or ""),
            inspection_error=str(_g("inspection_error") or ""),
            parsed_values=_g("parsed_values"),
            field_results=_g("field_results") or [],
        )

    async def _list_latest_admin(self) -> List[Dict[str, Any]]:
        """admin / system 分支：``devops_servers`` LEFT JOIN snapshot。"""
        rows = await self._db.fetch(
            """
            SELECT
                NULL::INTEGER         AS node_id,
                ds.business_name      AS node_name,
                ds.id                 AS server_id,
                ds.business_name      AS business_name,
                ds.server_type        AS server_type,
                s.collected_at        AS collected_at,
                s.success             AS success,
                s.inspection_status   AS inspection_status,
                s.duration_ms         AS duration_ms,
                s.error_message       AS error_message,
                s.parsed_values       AS parsed_values,
                s.field_results       AS field_results
            FROM devops_servers ds
            LEFT JOIN server_latest_snapshot s ON s.server_id = ds.id
            ORDER BY ds.id
            """
        )
        return [self._row_to_view(dict(r)) for r in rows]

    async def _list_latest_user(
        self,
        nodes: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """普通用户分支：按可见节点集去重后 LEFT JOIN snapshot。"""
        if not nodes:
            return []

        # 同一 server_id 在多个文件夹下重复：取 sort_order 最小、id 最小节点的名
        by_server: Dict[int, Dict[str, Any]] = {}
        for n in nodes:
            sid = n.get("source_devops_server_id")
            if sid is None:
                continue
            existing = by_server.get(int(sid))
            if existing is None:
                by_server[int(sid)] = n
                continue
            # 比较 (sort_order, node_id) 字典序
            sk = (existing.get("sort_order") or 0, existing.get("id") or 0)
            nk = (n.get("sort_order") or 0, n.get("id") or 0)
            if nk < sk:
                by_server[int(sid)] = n

        server_ids = sorted(by_server.keys())
        if not server_ids:
            return []

        snapshot_rows = await self._db.fetch(
            """
            SELECT
                server_id,
                business_name      AS snapshot_business_name,
                collected_at,
                success,
                inspection_status,
                duration_ms,
                error_message,
                parsed_values,
                field_results
            FROM server_latest_snapshot
            WHERE server_id = ANY($1::int[])
            """,
            server_ids,
        )
        snapshot_by_id: Dict[int, Dict[str, Any]] = {int(r["server_id"]): dict(r) for r in snapshot_rows}

        out: List[Dict[str, Any]] = []
        for sid in server_ids:
            node = by_server[sid]
            snap = snapshot_by_id.get(sid)
            merged = self._merge_user_view(node, snap)
            out.append(merged)
        return out

    def _collect_user_server_nodes(self, scope: OwnershipScope) -> List[Dict[str, Any]]:
        """收集普通用户可见的 server 类型节点。"""
        if self._user_server_service is None:
            return []
        try:
            nodes = self._user_server_service.list_nodes(scope) or []
        except Exception as exc:
            logger.warning(
                "list_latest: user_server_service.list_nodes 失败: %s", exc,
            )
            return []
        return [n for n in nodes if n.get("node_type") == "server" and n.get("source_devops_server_id")]

    async def _is_server_visible(
        self,
        server_id: int,
        scope: OwnershipScope,
    ) -> bool:
        """``server_id`` 对当前 scope 是否可见（admin: devops_servers 存在即可；普通用户: 在可见节点集内）。"""
        exists = await self._server_exists(server_id)
        if not exists:
            return False
        if scope.is_admin or scope.system:
            return True
        nodes = self._collect_user_server_nodes(scope)
        return any(int(n.get("source_devops_server_id") or -1) == int(server_id) for n in nodes)

    async def _server_exists(self, server_id: int) -> bool:
        if self._db is None:
            return False
        val = await self._db.fetchval(
            "SELECT EXISTS(SELECT 1 FROM devops_servers WHERE id = $1)",
            server_id,
        )
        return bool(val)

    def _build_id_indexes(
        self,
        scope: OwnershipScope,
    ) -> tuple[Dict[int, str], set]:
        """构建 ``id → business_name`` 与可见 server_id 集合（用于 resolve_collect_targets）。"""
        id_to_name: Dict[int, str] = {}
        visible_ids: set = set()

        if self._devops_server_service is not None:
            try:
                for row in self._devops_server_service.list_public_servers() or []:
                    sid = row.get("id")
                    bn = row.get("business_name")
                    if sid is not None and bn:
                        id_to_name[int(sid)] = bn
            except Exception as exc:
                logger.warning(
                    "resolve_collect_targets: devops_server_service.list_public_servers 失败: %s",
                    exc,
                )

        if scope.is_admin or scope.system:
            visible_ids = set(id_to_name.keys())
        else:
            nodes = self._collect_user_server_nodes(scope)
            for n in nodes:
                sid = n.get("source_devops_server_id")
                if sid is not None:
                    visible_ids.add(int(sid))

        return id_to_name, visible_ids

    @staticmethod
    def _decode_jsonb(value: Any) -> Any:
        """防御性反序列化 JSONB 字段（str → object；其余原样）。"""
        if value is None or isinstance(value, (dict, list)):
            return value
        if isinstance(value, (bytes, bytearray)):
            try:
                value = value.decode("utf-8")
            except Exception:
                return None
        if isinstance(value, str):
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                return None
        return None

    @classmethod
    def _row_to_view(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """将一行（admin JOIN 结果）映射为视图 dict。"""
        server_id = row.get("server_id")
        server_type = row.get("server_type") or ""
        collected_at = row.get("collected_at")
        snapshot_present = collected_at is not None
        parsed_values = cls._decode_jsonb(row.get("parsed_values"))
        field_results = cls._decode_jsonb(row.get("field_results")) or []
        status = cls._derive_status(
            row.get("success"),
            bool(row.get("skipped")),
            row.get("inspection_status") or "unassessed",
        )
        metrics = cls._derive_metrics(server_type, parsed_values)
        disks = parsed_values.get("disks") if isinstance(parsed_values, dict) else None
        return {
            "node_id": row.get("node_id"),
            "node_name": row.get("node_name") or row.get("business_name"),
            "server_id": int(server_id) if server_id is not None else None,
            "business_name": row.get("business_name"),
            "server_type": server_type,
            "status": status,
            "inspection_status": row.get("inspection_status") if snapshot_present else None,
            "collected_at": collected_at.isoformat() if collected_at else None,
            "duration_ms": row.get("duration_ms"),
            "metrics": metrics,
            "disks": disks if isinstance(disks, list) else [],
            "parsed_values": parsed_values if parsed_values is not None else {},
            # 2026-08-16 透出：每字段评估结果（由 inspection_scripts.yaml 中
            # warn/crit 评估后的 pass/warn/crit/unassessed 状态），供前端卡片
            # 智能选异常盘符。无快照时降级为空列表（避免前端访问 .length 报错）。
            "field_results": field_results if snapshot_present else [],
            "error_message": row.get("error_message"),
        }

    @classmethod
    def _merge_user_view(
        cls,
        node: Dict[str, Any],
        snap: Optional[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """普通用户分支：节点 + snapshot 合并为视图 dict。"""
        if snap is None:
            return {
                "node_id": node.get("id"),
                "node_name": node.get("name"),
                "server_id": int(node.get("source_devops_server_id")),
                "business_name": node.get("business_name"),
                "server_type": node.get("server_type"),
                "status": _STATUS_UNKNOWN,
                "inspection_status": None,
                "collected_at": None,
                "duration_ms": None,
                "metrics": {"cpu": None, "mem": None, "disk": None, "load": None},
                "disks": [],
                "parsed_values": {},
                "field_results": [],
                "error_message": None,
            }

        server_type = node.get("server_type") or ""
        parsed_values = cls._decode_jsonb(snap.get("parsed_values"))
        field_results = cls._decode_jsonb(snap.get("field_results")) or []
        status = cls._derive_status(
            snap.get("success"),
            bool(snap.get("skipped")),
            snap.get("inspection_status") or "unassessed",
        )
        metrics = cls._derive_metrics(server_type, parsed_values)
        disks = parsed_values.get("disks") if isinstance(parsed_values, dict) else None
        collected_at = snap.get("collected_at")
        return {
            "node_id": node.get("id"),
            "node_name": node.get("name"),
            "server_id": int(node.get("source_devops_server_id")),
            "business_name": node.get("business_name"),
            "server_type": server_type,
            "status": status,
            "inspection_status": snap.get("inspection_status"),
            "collected_at": collected_at.isoformat() if collected_at else None,
            "duration_ms": snap.get("duration_ms"),
            "metrics": metrics,
            "disks": disks if isinstance(disks, list) else [],
            "parsed_values": parsed_values if parsed_values is not None else {},
            # 2026-08-16 透出：每字段评估结果（与 admin 分支一致）。
            "field_results": field_results,
            "error_message": snap.get("error_message"),
        }

    @classmethod
    def _row_to_history_record(cls, row: Dict[str, Any]) -> Dict[str, Any]:
        """历史记录行 → API 响应 dict（白名单键）。"""
        row = dict(row)
        row["parsed_values"] = cls._decode_jsonb(row.get("parsed_values"))
        row["field_results"] = cls._decode_jsonb(row.get("field_results")) or []
        if isinstance(row.get("collected_at"), datetime):
            row["collected_at"] = row["collected_at"].isoformat()
        if isinstance(row.get("created_at"), datetime):
            row["created_at"] = row["created_at"].isoformat()
        return row