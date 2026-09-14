# -*- coding:utf-8 -*-
"""SystemConfigService 系统配置服务

职责:
- seed_from_settings: 空表 seed(用 settings 现值,敏感字段加密)
- load_all: lifespan 启动时 DB → settings 单例(解密敏感字段)
- get_group: 读单组(返回脱敏 config)
- list_groups: 按 tab 分组返回所有组
- update_group: 更新单组(校验 + 加密敏感字段 + 落库 + 审计)
- reset_group: 重置为 pydantic default

异常:
- KeyError: group_key 未注册
- ValueError: pydantic 校验失败
- RuntimeError: Fernet 加解密失败
"""
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import ValidationError

from app.core.config.settings_crypto import decrypt_value, encrypt_value, mask_value
from app.core.services.system_config_registry import (
    FieldSpec,
    GroupMeta,
    SystemConfigRegistry,
)


class SystemConfigService:
    """系统配置服务

    Args:
        pool: asyncpg Pool(或测试用 _FakePool)
        settings: Settings 单例(或测试用 MagicMock)
        log_service: LogService 实例(可选,审计用;测试可传 None)
    """

    def __init__(self, pool: Any, settings: Any, log_service: Optional[Any] = None):
        self._pool = pool
        self._settings = settings
        self._log_service = log_service

    # ---------- 内部工具 ----------

    def _settings_attr_name(self, group_key: str) -> str:
        """group_key → settings 属性名映射

        约定: group_key 与 settings 顶层属性名一致(如 'llm' → settings.llm);
              'mcp_sampling' → settings.mcp;'mcp_tags' → settings.mcp;
              其他特殊情况在 registry 注册时用 field_specs 处理。
        """
        if group_key == "mcp_sampling" or group_key == "mcp_tags":
            return "mcp"
        return group_key

    def _read_settings_values(self, meta: GroupMeta) -> Dict[str, Any]:
        """从 settings 单例读该组当前值"""
        if meta.settings_cls is not None:
            attr_name = self._settings_attr_name(meta.group_key)
            sub = getattr(self._settings, attr_name, None)
            if sub is None:
                return {}
            # 只取该 Settings 子类定义的字段
            return {
                k: getattr(sub, k)
                for k in type(sub).model_fields.keys()
                if hasattr(sub, k)
            }
        # field_specs
        return {
            spec.name: spec.getter(self._settings)
            for spec in (meta.field_specs or [])
        }

    def _write_settings_values(self, meta: GroupMeta, values: Dict[str, Any]) -> None:
        """把值写回 settings 单例"""
        if meta.settings_cls is not None:
            attr_name = self._settings_attr_name(meta.group_key)
            sub = getattr(self._settings, attr_name, None)
            if sub is None:
                return
            for k, v in values.items():
                if hasattr(sub, k):
                    setattr(sub, k, v)
        else:
            spec_map = {s.name: s for s in (meta.field_specs or [])}
            for k, v in values.items():
                if k in spec_map:
                    spec_map[k].setter(self._settings, v)

    def _encrypt_sensitive(self, meta: GroupMeta, config: Dict[str, Any]) -> Dict[str, Any]:
        """敏感字段加密"""
        result = dict(config)
        for field_name in meta.sensitive_fields:
            if field_name in result and result[field_name]:
                value = result[field_name]
                if isinstance(value, str) and not value.startswith("fernet:"):
                    result[field_name] = encrypt_value(value)
        return result

    def _decrypt_sensitive(self, meta: GroupMeta, config: Dict[str, Any]) -> Dict[str, Any]:
        """敏感字段解密"""
        result = dict(config)
        for field_name in meta.sensitive_fields:
            if field_name in result and result[field_name]:
                value = result[field_name]
                if isinstance(value, str):
                    result[field_name] = decrypt_value(value)
        return result

    def _mask_sensitive(self, meta: GroupMeta, config: Dict[str, Any]) -> Dict[str, Any]:
        """敏感字段脱敏"""
        result = dict(config)
        for field_name in meta.sensitive_fields:
            if field_name in result:
                result[field_name] = mask_value(str(result[field_name] or ""))
        return result

    def _validate_config(self, meta: GroupMeta, config: Dict[str, Any]) -> Dict[str, Any]:
        """pydantic 校验

        Raises:
            ValueError: 校验失败
        """
        if meta.settings_cls is not None:
            try:
                # 用 Settings 子类校验,但不读 env(只传 config)
                instance = meta.settings_cls(**config)
                return instance.model_dump()
            except ValidationError as exc:
                raise ValueError(f"配置校验失败: {exc}") from exc
        # field_specs: 简单类型校验
        spec_map = {s.name: s for s in (meta.field_specs or [])}
        result = {}
        for k, v in config.items():
            if k in spec_map:
                try:
                    result[k] = spec_map[k].field_type(v)
                except (TypeError, ValueError) as exc:
                    raise ValueError(f"字段 {k} 类型错误: {exc}") from exc
        return result

    # ---------- 公共 API ----------

    async def seed_from_settings(self) -> None:
        """空表 seed:把 settings 现值写入 DB(敏感字段加密)

        已存在的组行跳过(不覆盖)。
        """
        for group_key, meta in SystemConfigRegistry.all().items():
            async with self._pool.acquire() as conn:
                row = await conn.fetchrow(
                    "SELECT group_key FROM system_settings_groups WHERE group_key = $1",
                    group_key,
                )
            if row is not None:
                continue
            values = self._read_settings_values(meta)
            encrypted = self._encrypt_sensitive(meta, values)
            async with self._pool.acquire() as conn:
                await conn.execute(
                    """
                    INSERT INTO system_settings_groups (group_key, config, updated_by)
                    VALUES ($1, $2::jsonb, $3)
                    ON CONFLICT (group_key) DO NOTHING
                    """,
                    group_key,
                    json.dumps(encrypted, ensure_ascii=False, default=str),
                    "system-seed",
                )

    async def load_all(self) -> None:
        """从 DB 读所有组 → 覆盖 settings 单例(解密敏感字段)

        未注册的 group_key 跳过(向后兼容)。
        """
        async with self._pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT group_key, config FROM system_settings_groups"
            )
        for row in rows:
            group_key = row["group_key"]
            if not SystemConfigRegistry.has(group_key):
                continue
            meta = SystemConfigRegistry.get(group_key)
            config = row["config"]
            if isinstance(config, str):
                config = json.loads(config)
            decrypted = self._decrypt_sensitive(meta, config)
            self._write_settings_values(meta, decrypted)

    async def get_group(self, group_key: str) -> Dict[str, Any]:
        """读单组(返回脱敏 config)

        若 DB 无行 → 返回 settings 现值脱敏版。

        Raises:
            KeyError: group_key 未注册
        """
        meta = SystemConfigRegistry.get(group_key)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT group_key, config, updated_at, updated_by FROM system_settings_groups WHERE group_key = $1",
                group_key,
            )
        if row is None:
            values = self._read_settings_values(meta)
            return {
                "group_key": group_key,
                "tab": meta.tab,
                "label": meta.label,
                "config": self._mask_sensitive(meta, values),
                "updated_at": None,
                "updated_by": None,
            }
        config = row["config"]
        if isinstance(config, str):
            config = json.loads(config)
        return {
            "group_key": group_key,
            "tab": meta.tab,
            "label": meta.label,
            "config": self._mask_sensitive(meta, config),
            "updated_at": row["updated_at"].isoformat() if row["updated_at"] else None,
            "updated_by": row["updated_by"],
        }

    async def list_groups(self) -> List[Dict[str, Any]]:
        """按 tab 分组返回所有组(脱敏)"""
        result = []
        for group_key in SystemConfigRegistry.all().keys():
            result.append(await self.get_group(group_key))
        return result

    async def update_group(
        self, group_key: str, config: Dict[str, Any], operator: str
    ) -> Dict[str, Any]:
        """更新单组

        敏感字段处理:
        - 传 '****' 前缀或空串 → 保持 DB 原值
        - 传非 '****' 明文 → 加密落库

        Args:
            group_key: 组 key
            config: 新配置(部分字段)
            operator: 操作人 username

        Returns:
            Dict: 更新后的脱敏 config

        Raises:
            KeyError: group_key 未注册
            ValueError: pydantic 校验失败
        """
        meta = SystemConfigRegistry.get(group_key)

        # 读 DB 现值(用于敏感字段 '****' 保持)
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                "SELECT config FROM system_settings_groups WHERE group_key = $1",
                group_key,
            )
        existing_config: Dict[str, Any] = {}
        if row is not None:
            existing_config = row["config"]
            if isinstance(existing_config, str):
                existing_config = json.loads(existing_config)

        # 处理敏感字段 '****' 保持
        merged = dict(existing_config)
        for k, v in config.items():
            if k in meta.sensitive_fields:
                if isinstance(v, str) and (v.startswith("****") or v == ""):
                    continue  # 保持原值
            merged[k] = v

        # 校验
        validated = self._validate_config(meta, merged)
        # 加密
        encrypted = self._encrypt_sensitive(meta, validated)

        # 落库
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_settings_groups (group_key, config, updated_by)
                VALUES ($1, $2::jsonb, $3)
                ON CONFLICT (group_key)
                DO UPDATE SET config = EXCLUDED.config,
                              updated_at = CURRENT_TIMESTAMP,
                              updated_by = EXCLUDED.updated_by
                """,
                group_key,
                json.dumps(encrypted, ensure_ascii=False, default=str),
                operator,
            )

        # 审计(fail-soft)
        if self._log_service is not None:
            try:
                await self._log_service.emit(
                    event_type="system_settings_update",
                    user_id=None,
                    username=operator,
                    metadata={"group_key": group_key},
                )
            except Exception:
                pass

        return await self.get_group(group_key)

    async def reset_group(self, group_key: str, operator: str) -> Dict[str, Any]:
        """重置为 pydantic default

        Raises:
            KeyError: group_key 未注册
        """
        meta = SystemConfigRegistry.get(group_key)
        if meta.settings_cls is not None:
            defaults = meta.settings_cls().model_dump()
        else:
            defaults = {s.name: s.default for s in (meta.field_specs or [])}
        encrypted = self._encrypt_sensitive(meta, defaults)
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO system_settings_groups (group_key, config, updated_by)
                VALUES ($1, $2::jsonb, $3)
                ON CONFLICT (group_key)
                DO UPDATE SET config = EXCLUDED.config,
                              updated_at = CURRENT_TIMESTAMP,
                              updated_by = EXCLUDED.updated_by
                """,
                group_key,
                json.dumps(encrypted, ensure_ascii=False, default=str),
                operator,
            )
        if self._log_service is not None:
            try:
                await self._log_service.emit(
                    event_type="system_settings_reset",
                    user_id=None,
                    username=operator,
                    metadata={"group_key": group_key},
                )
            except Exception:
                pass
        return await self.get_group(group_key)
