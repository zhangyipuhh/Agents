#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DevOpsServerService - SSH 服务器配置管理服务（2026-07-15 新增，2026-08-03 改造）

职责：
    - 管理 SSH 远程服务器列表（业务名/IP/端口/用户名/密码/类型/黑白名单）
    - 来源：项目根 data/devops/servers.yaml（可通过 settings.devops.servers_config_path 覆盖）
    - 落库：devops_servers 表（DB 为 source of truth）
    - 内存缓存：self._cache: Dict[business_name, rec]
    - 密码字段：通过 Fernet 对称加密后写入 password_encrypted
    - 巡检脚本：仅保存 ``inspection_script_id`` 外键引用 ``inspection_scripts`` 表；
      实际脚本原文 / 解析器 / 字段规则由 ``InspectionScriptService`` 提供

设计要点：
    - 单例（set_instance / get_instance / reset）由 lifespan 注入到
      app.state.devops_server_service
    - 服务初始化时严格校验 credential_key；为空或非法 base64 一律抛 ValueError
    - scan_and_upsert 返回结构严格只含 scanned/inserted/updated/failed 四个数字，
      不回显原始 YAML 路径 / IP / 密码 / 名单
    - list_public_servers 严格白名单返回 id/business_name/server_type/updated_at
    - get_connection_config(business_name) 内部解密，绝不外泄，仅供 SSHTools 内部使用
      返回结构中 ``inspection_script`` / ``inspection_parser`` / ``inspection_fields``
      由 ``InspectionScriptService`` 间接提供（保持外部报告契约不变）。
    - get_server_detail 仅返回 ``_DETAIL_FIELDS`` 白名单；
      巡检脚本相关字段改为 ``inspection_script_id`` / ``inspection_script_name`` /
      ``inspection_script_display_name``（无脚本原文）。

调用关系：
    - lifespan → InspectionScriptService.preload_all() →
      DevOpsServerService(db, path, key, inspection_script_service).preload_all()
      → app.state.devops_server_service
    - admin router → service.scan_and_upsert() / list_public_servers() /
      server_exists() / delete_server() / get_server_detail()
    - SSHTools (LangChain tool) → service.get_connection_config(business_name)
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml
from cryptography.fernet import Fernet, InvalidToken

from app.shared.utils.inspection.parser import normalize_inspection_fields


def _ensure_list(value: Any) -> List[Any]:
    """防御性还原 JSONB 列值。

    asyncpg 0.31 的 jsonb codec 在某些配置下不会自动反序列化,
    而是返回原始 JSON 字符串。这里做防御性还原:
      - 已经是 list:原样返回
      - 已经是 dict:返回 ``[dict]`` 单元素 list(白/黑名单场景不期望 dict)
      - 是 str 且可被 ``json.loads`` 解析为 list:解析后返回
      - 是 str 且可被 ``json.loads`` 解析为 dict:返回 ``[dict]`` 单元素 list
      - 解析失败或为 None:返回 ``[]``(兜底,保持原 ``list(value or [])`` 行为)

    Args:
        value: 来自 DB row 的 jsonb 字段值,可能是 list / dict / str / None / 其它

    Returns:
        List[Any]: 始终返回 list 类型
    """
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return [value]
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return []
        if isinstance(parsed, list):
            return parsed
        if isinstance(parsed, dict):
            return [parsed]
        return []
    return []


logger = logging.getLogger(__name__)


# 公开字段白名单（严格只含以下字段）
_PUBLIC_FIELDS = ("id", "business_name", "server_type", "updated_at")


class DevOpsServerService:
    """DevOps SSH 服务器配置管理服务（单例）。

    Attributes:
        db: asyncpg 连接池（或 MagicMock 替身，但需提供 fetch / fetchrow / execute）
        config_path: servers.yaml 文件路径
        credential_key: Fernet 对称密钥（44 字节 base64 字符串）
        inspection_script_service: InspectionScriptService 实例（必填，提供脚本库解析）。
            构造时不强校验（允许 ``None`` 用于测试子集，但 ``scan_and_upsert`` /
            ``preload_all`` / ``get_connection_config`` 时必须存在）。
        _cache: 内存缓存，键为 business_name，值为包含 password_encrypted 字节的记录
        _fernet: Fernet 实例（构造时根据 credential_key 创建）
        _write_lock: ``asyncio.Lock``（Bug-6 修复）保护 ``_cache`` 写入（preload_all /
          scan_and_upsert），读路径（``get_connection_config`` /
          ``list_public_servers``）无锁
    """

    _instance: Optional["DevOpsServerService"] = None

    # ------------------------------------------------------------------
    # Singleton helpers
    # ------------------------------------------------------------------

    @classmethod
    def set_instance(cls, instance: "DevOpsServerService") -> None:
        """设置全局单例。

        Args:
            instance: DevOpsServerService 实例

        Returns:
            None
        """
        cls._instance = instance

    @classmethod
    def get_instance(cls) -> "DevOpsServerService":
        """获取全局单例。

        Returns:
            DevOpsServerService: 单例实例

        Raises:
            RuntimeError: 单例尚未初始化时抛出
        """
        if cls._instance is None:
            raise RuntimeError("DevOpsServerService singleton not initialized")
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """重置全局单例（主要用于测试）。"""
        cls._instance = None

    # ------------------------------------------------------------------
    # Construction / validation
    # ------------------------------------------------------------------

    def __init__(
        self,
        db: Any,
        config_path: str,
        credential_key: str,
        inspection_script_service: Any = None,
    ) -> None:
        """构造服务并严格校验 Fernet 密钥。

        Args:
            db: asyncpg 连接池；测试可传 ``MagicMock(name="db_pool_stub")``
            config_path: servers.yaml 路径；不存在时 scan_and_upsert 会安全返回 0
            credential_key: Fernet 密钥（44 字节 base64 字符串）
            inspection_script_service: InspectionScriptService 实例；
                提供脚本库解析。允许 ``None``（用于单测局部路径，
                ``preload_all`` / ``scan_and_upsert`` / ``get_connection_config``
                会按缺失策略处理）。

        Raises:
            ValueError: ``credential_key`` 为空或非法 base64 时抛出
        """
        self.db = db
        self.config_path = str(config_path)
        if not credential_key:
            raise ValueError("credential_key 不能为空（请在 .env 中配置 DEVOPS_CREDENTIAL_KEY）")
        try:
            self._fernet = Fernet(credential_key.encode("ascii"))
        except (ValueError, TypeError) as e:
            # cryptography 抛的可能是 ValueError(salt) 或 Exception；
            # 统一包装为 ValueError 便于 Settings 与 lifespan 捕捉
            raise ValueError(
                f"credential_key 不是合法 Fernet base64 密钥: {e}"
            ) from e
        self._cache: Dict[str, Dict[str, Any]] = {}
        self.credential_key = credential_key
        self.inspection_script_service = inspection_script_service
        # Bug-6 修复:写入路径( preload_all / scan_and_upsert )持锁保证 _cache 快照一致
        self._write_lock: asyncio.Lock = asyncio.Lock()

    # ------------------------------------------------------------------
    # Preload from DB
    # ------------------------------------------------------------------

    async def preload_all(self) -> None:
        """从 DB 读取全部 devops_servers 行到 ``self._cache``。

        - 内存缓存为 ``dict[business_name, rec]``
        - DB 行字段：id / business_name / ip / port / username /
          password_encrypted (bytes 或 str) / server_type /
          blacklist (list) / whitelist (list) / inspection_script_id (int|None) /
          created_at / updated_at
        - business_name 唯一约束 → 同名行以后到为准；本方法按 DB 自然顺序覆盖
        - **Bug-6**：cache 替换段持 ``self._write_lock``,避免并发扫描时读路径拿到半新半旧快照

        Returns:
            None
        """
        # asyncpg JSONB 由 codec 自动反序列化为 Python 对象（list/dict）
        rows = await self.db.fetch(
            "SELECT id, business_name, ip, port, username, password_encrypted, "
            "server_type, blacklist, whitelist, "
            "inspection_script_id, "  # 2026-08-03 改造：旧三列移除，仅保留外键
            "created_at, updated_at "
            "FROM devops_servers ORDER BY id"
        )
        new_cache: Dict[str, Dict[str, Any]] = {}
        for row in rows:
            data = dict(row)
            business_name = data.get("business_name")
            if not business_name:
                continue
            # password_encrypted：asyncpg 自动反序列化 bytes/bytea；
            # 兼容性保险：若已是 str/bytes，统一转为 bytes
            penv = data.get("password_encrypted")
            if isinstance(penv, str):
                penv = penv.encode("ascii")
            data["password_encrypted"] = penv
            # JSONB 防御性还原：asyncpg 0.31 的 jsonb codec 在某些配置下
            # 不会自动反序列化，会返回原始 JSON 字符串。此处统一还原为 list/dict，
            # 避免下游 ``list(str)`` 把字符串拆成字符数组的灾难性 bug。
            data["blacklist"] = _ensure_list(data.get("blacklist"))
            data["whitelist"] = _ensure_list(data.get("whitelist"))
            # 2026-08-03 改造：缓存 inspection_script_id（int|None）
            sid = data.get("inspection_script_id")
            if sid is not None and not isinstance(sid, int):
                try:
                    sid = int(sid)
                except (TypeError, ValueError):
                    sid = None
            data["inspection_script_id"] = sid
            new_cache[business_name] = data
        # Bug-6 修复:cache 替换原子化,读路径快照一致
        async with self._write_lock:
            self._cache = new_cache
        logger.info("[devops_server_service] preloaded %d server(s)", len(self._cache))

    # ------------------------------------------------------------------
    # Public listing (whitelisted fields only)
    # ------------------------------------------------------------------

    def list_public_servers(self) -> List[Dict[str, Any]]:
        """返回公开字段（严格白名单）。

        返回字段固定为 ``id`` / ``business_name`` / ``server_type`` / ``updated_at``，
        绝不包含 ip / port / username / password / blacklist / whitelist /
        inspection_script_id 等。

        Returns:
            List[Dict[str, Any]]: 公开字段列表，每项仅含白名单键
        """
        result: List[Dict[str, Any]] = []
        for business_name, rec in self._cache.items():
            result.append({k: rec.get(k) for k in _PUBLIC_FIELDS})
        return result

    # ------------------------------------------------------------------
    # Detail (whitelist + inspection_script_id by server_id, admin 专用)
    # ------------------------------------------------------------------

    # 详情字段白名单：包含 inspection_script_id / inspection_script_name /
    # inspection_script_display_name（通过 InspectionScriptService 解析），
    # 但**不**返回脚本原文（脚本原文改走 InspectionScriptAdminRouter 详情端点）。
    _DETAIL_FIELDS = (
        "id",
        "business_name",
        "server_type",
        "updated_at",
        "whitelist",
        "inspection_script_id",
        "inspection_script_name",
        "inspection_script_display_name",
    )

    def get_server_detail(self, server_id: int) -> Optional[Dict[str, Any]]:
        """按 ``server_id`` 取详情（白名单 + 巡检脚本外键）。

        命中：从 ``self._cache`` 返回仅含 ``_DETAIL_FIELDS`` 字段的字典；
        未命中：返回 ``None``（HTTP 404 由 router 决定，service 不抛异常）。

        安全边界：绝不返回 ``ip / port / username / password_encrypted /
        blacklist``；脚本原文 / 字段规则改走
        ``GET /api/admin/inspection-scripts/{id}``。

        Args:
            server_id: devops_servers 主键 id

        Returns:
            Optional[Dict[str, Any]]: 命中时含 ``_DETAIL_FIELDS`` 全字段的字典；
            未命中时 ``None``
        """
        for rec in self._cache.values():
            if rec.get("id") == server_id:
                # 巡检脚本：通过 inspection_script_service 解析 name + display_name
                script_id = rec.get("inspection_script_id")
                script_name: Optional[str] = None
                script_display_name: Optional[str] = None
                if script_id is not None and self.inspection_script_service is not None:
                    script_rec = self.inspection_script_service.get_script_by_id(script_id)
                    if script_rec is not None:
                        script_name = script_rec.get("name")
                        script_display_name = script_rec.get("display_name")
                detail = {k: rec.get(k) for k in self._DETAIL_FIELDS if k in (
                    "id", "business_name", "server_type", "updated_at", "whitelist",
                    "inspection_script_id",
                )}
                detail["inspection_script_name"] = script_name
                detail["inspection_script_display_name"] = script_display_name
                return detail
        return None

    # ------------------------------------------------------------------
    # Connection config (decrypted password, internal use only)
    # ------------------------------------------------------------------

    def get_connection_config(self, business_name: str) -> Dict[str, Any]:
        """获取指定业务名的完整 SSH 连接配置（含明文密码 + 巡检脚本内容，内部使用）。

        ⚠️ 该方法返回的是明文 password 与脚本原文；调用方必须自行保证：
            - 不写入 logger；
            - 不进入 ToolMessage / Store；
            - 不回显到 HTTP 响应。

        巡检脚本字段 ``inspection_script`` / ``inspection_parser`` /
        ``inspection_fields`` 仍按既有结构返回（保持外部报告契约不变）：
        - 通过 ``inspection_script_id`` 从 ``InspectionScriptService`` 取脚本原文；
        - ``inspection_fields`` 由 InspectionScriptService 强类型化为
          ``list[InspectionFieldRule]``，service 是序列化/结构化的唯一真相源，
          调用方（脚本侧）**不**重复归一化。

        Args:
            business_name: 业务名（唯一键）

        Returns:
            Dict[str, Any]: 包含 ``ip`` / ``port`` / ``username`` / ``password`` /
            ``server_type`` / ``blacklist`` / ``whitelist`` /
            ``inspection_script`` / ``inspection_parser`` / ``inspection_fields``

        Raises:
            KeyError: 业务名不存在时抛出
            ValueError: 服务器未关联 inspection_script_id，或脚本库条目不存在 /
                InspectionScriptService 未注入
        """
        if business_name not in self._cache:
            raise KeyError(f"unknown business_name: {business_name}")
        rec = self._cache[business_name]
        encrypted = rec.get("password_encrypted")
        if isinstance(encrypted, str):
            encrypted = encrypted.encode("ascii")
        try:
            plaintext = self._fernet.decrypt(encrypted).decode("utf-8") if encrypted else ""
        except InvalidToken as e:
            raise ValueError(
                f"解密失败（Fernet key 与加密时不一致？）: {business_name}"
            ) from e

        # 巡检脚本：通过 inspection_script_service 解析
        script_id = rec.get("inspection_script_id")
        if script_id is None:
            raise ValueError(
                f"服务器未关联巡检脚本（inspection_script_id 为空）: {business_name}"
            )
        if self.inspection_script_service is None:
            raise ValueError(
                f"InspectionScriptService 未注入，无法解析巡检脚本: {business_name}"
            )
        script_rec = self.inspection_script_service.get_script_by_id(script_id)
        if script_rec is None:
            raise ValueError(
                f"巡检脚本库条目不存在或已被删除: {script_id}（server={business_name}）"
            )

        inspection_script = script_rec.get("inspection_script")
        inspection_parser = script_rec.get("inspection_parser") or "json"
        # script_rec.inspection_fields 是 list[dict]，此处**只此一处**调用
        # normalize_inspection_fields 转换为 list[InspectionFieldRule]；
        # service 是序列化/结构化的唯一真相源。
        inspection_fields = list(
            normalize_inspection_fields(script_rec.get("inspection_fields") or [])
        )

        return {
            "ip": rec.get("ip"),
            "port": int(rec.get("port") or 22),
            "username": rec.get("username"),
            "password": plaintext,
            "server_type": rec.get("server_type"),
            "blacklist": list(rec.get("blacklist") or []),
            "whitelist": list(rec.get("whitelist") or []),
            "inspection_script": inspection_script,
            "inspection_parser": inspection_parser,
            "inspection_fields": inspection_fields,
        }

    # ------------------------------------------------------------------
    # Scan & upsert
    # ------------------------------------------------------------------

    async def scan_and_upsert(self) -> Dict[str, int]:
        """读取 YAML 配置、字段规范化、Fernet 加密写入 devops_servers 表。

        输入形态支持两种：
            - 顶层为列表 ``[ {...}, {...} ]``（YAML ``-`` 序列形式）
            - 顶层为 ``{ "servers": [ {...}, {...} ] }``（计划示例形式）

        写入策略：以 ``business_name`` 为唯一键执行单条
        ``INSERT ... ON CONFLICT (business_name) DO UPDATE ...
         RETURNING *, (xmax = 0) AS inserted``；
        - 计数：``scanned`` 是输入条目数；``inserted`` / ``updated`` 视
          RETURNING 行 ``(xmax = 0)`` 标记而定；``failed`` 是校验失败 /
          Fernet 失败 / DB 写入异常 / 重复业务名 / 未找到 inspection_script_id 的总数。
        - **重复 business_name 直接拒绝并计入 failed**（不允许后者覆盖前者）
        - **巡检脚本**：YAML 节点声明 ``inspection_script_name``（字符串）；
          解析流程：先按 ``inspection_script_name`` 命中 InspectionScriptService；
          若未指定，按 ``server_type`` 走默认脚本名（linux-bash / windows-ps-5.1）；
          任意一种方式未命中 → 该条目记 failed（不阻断其他条目）。
        - 失败条目不进入缓存；不抛异常上抛。
        - 缓存与 DB 同步：upsert 成功后用 RETURNING 行（id / updated_at /
          password_encrypted 等真实值）更新 ``self._cache``，避免再读一次 DB。

        Returns:
            Dict[str, int]: 严格只含 ``{"scanned": int, "inserted": int, "updated": int, "failed": int}``
        """
        stats = {"scanned": 0, "inserted": 0, "updated": 0, "failed": 0}
        cfg_path = Path(self.config_path)
        if not cfg_path.exists():
            return stats

        try:
            raw = yaml.safe_load(cfg_path.read_text(encoding="utf-8"))
        except (yaml.YAMLError, OSError) as e:
            logger.warning(
                "[devops_server_service] 无法读取 servers.yaml，type=%s",
                type(e).__name__,
            )
            return stats

        # 兼容顶层为 list / dict（取 ``servers`` 键）
        if isinstance(raw, dict):
            raw = raw.get("servers")
        if not isinstance(raw, list):
            stats["failed"] += 1
            return stats

        # 先按顺序去重（不覆盖）：相同 business_name 视为失败条目
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
            name = normalized["business_name"]
            if name in seen_names:
                stats["failed"] += 1
                continue
            seen_names.add(name)
            order.append(name)
            normalized_per_name[name] = normalized

        for name in order:
            normalized = normalized_per_name[name]
            try:
                encrypted = self._fernet.encrypt(normalized["password"].encode("utf-8"))
            except Exception:
                stats["failed"] += 1
                continue

            try:
                inserted, row = await self._upsert_one_returning(
                    name, normalized, encrypted
                )
            except Exception:
                stats["failed"] += 1
                continue

            # row 已包含 DB 返回的 id / updated_at / password_encrypted 等
            row_data = dict(row) if row else {}
            penv = row_data.get("password_encrypted")
            if isinstance(penv, str):
                penv = penv.encode("ascii")
            # Bug-6 修复:cache 写入原子化,与并发读取串行
            async with self._write_lock:
                self._cache[name] = {
                    "id": row_data.get("id"),
                    "business_name": name,
                    "ip": normalized["ip"],
                    "port": normalized["port"],
                    "username": normalized["username"],
                    "password_encrypted": penv,
                    "server_type": normalized["server_type"],
                    "blacklist": normalized["blacklist"],
                    "whitelist": normalized["whitelist"],
                    "inspection_script_id": normalized["inspection_script_id"],  # 2026-08-03 改造
                    "created_at": row_data.get("created_at"),
                    "updated_at": row_data.get("updated_at"),
                }

            if inserted:
                stats["inserted"] += 1
            else:
                stats["updated"] += 1

        return stats

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _normalize_entry(self, entry: Any) -> Dict[str, Any]:
        """把 YAML entry 规范化为业务字段；非法时抛 ``ValueError``。

        字段别名兼容：``name`` ↔ ``business_name``；``host`` ↔ ``ip``。

        巡检脚本：YAML 中以 ``inspection_script_name``（字符串）引用脚本库条目；
        - 若未指定，按 ``server_type`` 默认匹配（linux → linux-bash，
          windows → windows-ps-5.1）；
        - 通过 ``inspection_script_service.get_script_by_name`` 或
          ``resolve_script_for_server`` 解析为 ``inspection_script_id``；
        - 任意一种方式未命中 → 抛 ``ValueError``，该条目记 failed。

        Args:
            entry: 原始 YAML 条目（dict）

        Returns:
            Dict[str, Any]: 规范化后含 ``business_name``/``ip``/``port``/
            ``username``/``password``/``server_type``/``blacklist``/``whitelist``/
            ``inspection_script_id``

        Raises:
            ValueError: 缺少必填字段或取值非法时抛出（不携带敏感信息）
        """
        if not isinstance(entry, dict):
            raise ValueError("entry must be a dict")

        # business_name
        business_name = entry.get("business_name") or entry.get("name")
        if not business_name or not isinstance(business_name, str):
            raise ValueError("missing business_name")
        business_name = business_name.strip()
        if not business_name:
            raise ValueError("empty business_name")

        # ip
        ip = entry.get("ip") or entry.get("host")
        if not ip or not isinstance(ip, str):
            raise ValueError("missing ip/host")

        # port
        port = entry.get("port", 22)
        try:
            port_i = int(port)
        except (TypeError, ValueError):
            raise ValueError("invalid port type")
        if port_i < 1 or port_i > 65535:
            raise ValueError("port out of range")

        # username
        username = entry.get("username")
        if not username or not isinstance(username, str):
            raise ValueError("missing username")

        # password
        password = entry.get("password")
        if not isinstance(password, str):
            raise ValueError("missing password")

        # server_type
        server_type = (entry.get("server_type") or "linux").lower()
        if server_type not in ("linux", "windows"):
            raise ValueError("invalid server_type")

        # blacklist / whitelist
        blacklist = entry.get("blacklist") or []
        whitelist = entry.get("whitelist") or []
        if not isinstance(blacklist, list) or not isinstance(whitelist, list):
            raise ValueError("blacklist/whitelist must be list")

        # inspection_script_name（2026-08-03 改造：仅保留 name 引用，不再直接接受脚本原文）
        script_name_raw = entry.get("inspection_script_name")
        script_name: Optional[str]
        if script_name_raw is None or script_name_raw == "":
            script_name = None
        else:
            if not isinstance(script_name_raw, str):
                raise ValueError("inspection_script_name must be string")
            script_name = script_name_raw.strip() or None

        # 通过 InspectionScriptService 解析 inspection_script_id
        if self.inspection_script_service is None:
            raise ValueError(
                "InspectionScriptService 未注入，无法解析 inspection_script_name"
            )
        script_id = self.inspection_script_service.resolve_script_for_server(
            server_type, script_name
        )
        if script_id is None:
            hint = script_name if script_name else f"<default for {server_type}>"
            raise ValueError(
                f"未找到巡检脚本（inspection_script_name={hint}）；"
                "请先在 inspection_scripts.yaml 注册或在 InspectionScriptService 缓存中确认"
            )

        return {
            "business_name": business_name,
            "ip": ip,
            "port": port_i,
            "username": username,
            "password": password,
            "server_type": server_type,
            "blacklist": [str(x) for x in blacklist],
            "whitelist": [str(x) for x in whitelist],
            "inspection_script_id": script_id,
        }

    async def _upsert_one_returning(
        self,
        business_name: str,
        normalized: Dict[str, Any],
        encrypted: bytes,
    ) -> Tuple[bool, Any]:
        """单条 upsert，并返回 ``(inserted, row)``。

        使用 ``INSERT ... ON CONFLICT (business_name) DO UPDATE ... RETURNING *,
        (xmax = 0) AS inserted`` 一次往返完成：
            - 插入新行：``inserted=True``（``xmax=0``）
            - 更新已存在行：``inserted=False``
            - 行内含真实 ``id`` / ``created_at`` / ``updated_at`` / ``password_encrypted``，
              调用方据此同步内存缓存，无需再读 DB

        2026-08-03 改造：SQL 不再写 inspection_script / inspection_parser /
        inspection_fields 三列，仅写入 inspection_script_id 外键。

        Args:
            business_name: 业务名
            normalized: 规范化后的字段
            encrypted: Fernet 加密后的密码字节

        Returns:
            Tuple[bool, Any]: ``(是否新插入, DB 返回行)``

        Raises:
            Exception: DB 写入失败时抛出（由调用方捕获并计入 failed）
        """
        row = await self.db.fetchrow(
            "INSERT INTO devops_servers "
            "(business_name, ip, port, username, password_encrypted, "
            " server_type, blacklist, whitelist, "
            " inspection_script_id, "  # 2026-08-03 改造
            " created_at, updated_at) "
            "VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, "
            "        $9, "  # inspection_script_id
            "        NOW(), NOW()) "
            "ON CONFLICT (business_name) DO UPDATE SET "
            "ip = EXCLUDED.ip, port = EXCLUDED.port, username = EXCLUDED.username, "
            "password_encrypted = EXCLUDED.password_encrypted, server_type = EXCLUDED.server_type, "
            "blacklist = EXCLUDED.blacklist, whitelist = EXCLUDED.whitelist, "
            "inspection_script_id = EXCLUDED.inspection_script_id, "  # 2026-08-03 改造
            "updated_at = NOW() "
            "RETURNING *, (xmax = 0) AS inserted",
            business_name,
            normalized["ip"],
            normalized["port"],
            normalized["username"],
            encrypted,
            normalized["server_type"],
            json.dumps(normalized["blacklist"]),
            json.dumps(normalized["whitelist"]),
            normalized["inspection_script_id"],  # 2026-08-03 改造
        )
        inserted = bool(row and row.get("inserted"))
        return inserted, row

    # ------------------------------------------------------------------
    # Existence check (for admin DELETE 404 probe)
    # ------------------------------------------------------------------

    async def server_exists(self, server_id: int) -> bool:
        """判断给定 ``server_id`` 是否存在。

        优先遍历 ``_cache``；cache 未命中时回退 DB ``SELECT 1``。
        HTTP 路由层用于在 DELETE 前判定 404，避免 service 层污染 HTTP 语义。

        Args:
            server_id: devops_servers 主键 id

        Returns:
            bool: 行存在 → True，否则 False
        """
        for rec in self._cache.values():
            if rec.get("id") == server_id:
                return True
        row = await self.db.fetchrow(
            "SELECT 1 FROM devops_servers WHERE id = $1 LIMIT 1",
            server_id,
        )
        return row is not None

    # ------------------------------------------------------------------
    # Delete by server_id
    # ------------------------------------------------------------------

    async def delete_server(self, server_id: int) -> None:
        """按 ``server_id`` 删除一行 devops_servers（admin 专用）。

        契约：
            - 持 ``self._write_lock``，在锁内同时改 ``self._cache`` 与执行
              ``db.execute("DELETE FROM devops_servers WHERE id = $1", server_id)``，
              保证 cache 与 DB 一致性（Bug-6 同款修复）。
            - 按 ``business_name``（``rec.get("business_name")``）定位 cache：
              找到则删除；找不到视为幂等（DB 仍执行 DELETE，404 由 admin router 判）。
            - DB 执行抛异常 → 直接抛；admin router 把异常统一映射为 500 + 通用错误，
              不回显 SQL / 原 detail。
            - service 层**不抛** 404：HTTP 状态码由 router 层决定，service 只负责
              cache + DB 同步。

        Args:
            server_id: devops_servers 主键 id

        Returns:
            None

        Raises:
            Exception: DB 执行失败时抛出（由 admin router 捕获并映射为 500）
        """
        async with self._write_lock:
            target_name: Optional[str] = None
            for name, rec in self._cache.items():
                if rec.get("id") == server_id:
                    target_name = name
                    break
            if target_name is not None:
                self._cache.pop(target_name, None)
            await self.db.execute(
                "DELETE FROM devops_servers WHERE id = $1",
                server_id,
            )