# -*- coding:utf-8 -*-
"""
第三方执行器端点注册表（2026-08-03 新增）。

职责：
    - 从 ``app.core.config.settings.settings.third_party_executor`` 加载端点配置
    - 启动期校验：URL 必须为 https、公钥 PEM 可解析、name 唯一
    - 提供 ``get(name)`` / ``names()`` 接口供 ``third_party_executor`` 调度

设计要点：
    - 单例（_instance）由 ``app.core.server.lifespan`` 在第一次访问时懒加载
    - 配置缺失时返回空注册表，不抛错；调用方按 ``name`` 取不到时抛
      ``ThirdPartyExecutorError(ERR_CONFIG_MISSING)``
    - 不持久化状态，仅在内存中缓存 ``_endpoints`` dict

Date: 2026-08-03
Author: AI Assistant
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from app.shared.utils.crypto.rsa_aes import _load_public_key
from app.shared.utils.executor.errors import (
    ERR_CONFIG_MISSING,
    ThirdPartyExecutorError,
)


logger = logging.getLogger(__name__)


def _read_env_file_endpoints_fallback() -> str:
    """兜底读取 ``.env`` 文件中的 ``THIRD_PARTY_EXECUTOR_ENDPOINTS`` 原始值。

    2026-08-05 新增：pydantic-settings 的环境变量优先级高于 ``.env`` 文件，
    当运行环境（IDE 调试配置 / shell profile / 编排平台）里存在**空值或脏值**
    的 ``THIRD_PARTY_EXECUTOR_ENDPOINTS`` 时，``settings.endpoints_json`` 会
    被覆盖为空，导致端点注册表加载 0 个端点、报 ``third_party endpoint 'X' 未配置``。
    此函数直接从项目根 ``.env`` 文件读取原始值，作为全局懒加载路径的兜底。

    Returns:
        str: ``.env`` 中该键的原始值（去除首尾空白）；读取失败或无键时返回空串
    """
    try:
        from dotenv import dotenv_values

        from app.core.config.settings import _ENV_FILE_PATH

        values = dotenv_values(_ENV_FILE_PATH)
        return str(values.get("THIRD_PARTY_EXECUTOR_ENDPOINTS") or "").strip()
    except Exception:  # noqa: BLE001 - 兜底失败不阻断主流程
        return ""


@dataclass(frozen=True)
class ThirdPartyEndpoint:
    """第三方端点配置。

    Attributes:
        name: 端点唯一标识（在 ``runtime.context["third_party_endpoint_name"]`` 中使用）
        url: HTTPS URL（启动期强制 https://）
        public_key_pem: 接收方 RSA 公钥 PEM
        timeout_seconds: HTTP 调用超时（秒）
        enabled: 是否启用
    """

    name: str
    url: str
    public_key_pem: str
    timeout_seconds: int = 30
    enabled: bool = True


class ThirdPartyEndpointRegistry:
    """第三方端点注册表（懒加载单例）。"""

    def __init__(self) -> None:
        """初始化注册表（默认无端点）。"""
        self._endpoints: Dict[str, ThirdPartyEndpoint] = {}
        self._loaded: bool = False

    @classmethod
    def get_instance(cls) -> "ThirdPartyEndpointRegistry":
        """获取全局单例。

        Returns:
            ThirdPartyEndpointRegistry: 单例对象
        """
        global _instance
        try:
            inst = _instance
        except NameError:
            inst = None
        if inst is None:
            inst = cls()
            try:
                globals()["_instance"] = inst
            except Exception:  # noqa: BLE001
                pass
        return inst

    @classmethod
    def reset_instance(cls) -> None:
        """重置单例（仅测试使用）。"""
        global _instance
        _instance = None  # type: ignore[assignment]

    def load_from_settings(self, settings: Optional[object] = None, allow_insecure: Optional[bool] = None) -> None:
        """从全局 ``settings.third_party_executor`` 加载并校验端点。

        配置缺失时保持空注册表；解析失败 / 校验失败时记录 warning 并跳过该端点。

        Args:
            settings: 可选外部注入的 settings 对象；为 None 时从全局模块懒加载
                （便于测试用 monkeypatch 注入，避免循环依赖）。
            allow_insecure: 可选外部覆盖；为 None 时从 ``settings.third_party_executor
                .allow_insecure`` 读取（默认 False → 强制 https）。

        Returns:
            None
        """
        # 优先使用外部注入的 settings，便于测试；否则延迟导入避免循环（settings → endpoints）
        if settings is None:
            import importlib

            settings_module = importlib.import_module("app.core.config.settings")
            settings_obj = getattr(settings_module, "settings", None)
        else:
            settings_obj = settings

        cfg = getattr(settings_obj, "third_party_executor", None) if settings_obj else None
        if cfg is None:
            self._loaded = True
            return
        # 2026-08-03 新增：从 settings 读取 allow_insecure 透传给 _parse_endpoint，
        # 用于 dev / 测试 / 内网环境下放行 http:// 端点。
        # 优先级：函数参数 > settings.third_party_executor.allow_insecure > False
        if allow_insecure is None:
            allow_insecure = bool(getattr(cfg, "allow_insecure", False))

        raw = (cfg.endpoints_json or "").strip()
        self._load_raw(raw, allow_insecure=allow_insecure)
        # 2026-08-05 兜底（增强）：仅全局懒加载路径（settings 未注入）时，若
        # settings 未解析出任何端点，则从项目根 .env 文件读取原始值重载。
        # 触发场景：os.environ 存在污染值 THIRD_PARTY_EXECUTOR_ENDPOINTS
        # （空串 / 空数组 [] / 非法 JSON / 无 primary 的配置），其优先级高于
        # .env 文件（pydantic-settings env > dotenv），导致注册表空、报
        # "third_party endpoint 'X' 未配置"。测试注入 settings 的场景不触发，
        # 保持测试可控。
        if not self._endpoints and settings is None:
            fallback_raw = _read_env_file_endpoints_fallback()
            if fallback_raw and fallback_raw != raw:
                logger.warning(
                    "[ThirdPartyEndpointRegistry] settings 未解析出端点且与 .env "
                    "文件不一致（疑似 os.environ 污染），改用 .env 文件配置重载"
                )
                self._endpoints = {}
                self._load_raw(fallback_raw, allow_insecure=allow_insecure)
        self._loaded = True
        logger.info(
            "[ThirdPartyEndpointRegistry] loaded %d endpoint(s)",
            len(self._endpoints),
        )

    def _load_raw(self, raw: str, *, allow_insecure: bool) -> None:
        """解析 ``raw`` JSON 端点列表到 ``self._endpoints``（不重置 ``_loaded``）。

        Args:
            raw: 端点 JSON 数组字符串（可能为空）。
            allow_insecure: 是否允许 http:// 端点，透传给 ``_parse_endpoint``。

        Returns:
            None：解析失败 / 非法输入时记 warning 并静默返回。
        """
        if not raw:
            return
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            logger.warning(
                "[ThirdPartyEndpointRegistry] THIRD_PARTY_EXECUTOR_ENDPOINTS "
                "JSON 解析失败: %s",
                exc,
            )
            return

        if not isinstance(data, list):
            logger.warning(
                "[ThirdPartyEndpointRegistry] 端点配置必须为 JSON 数组，忽略"
            )
            return

        for item in data:
            try:
                ep = self._parse_endpoint(
                    item, allow_insecure=allow_insecure
                )
            except (ValueError, Exception) as exc:  # noqa: BLE001
                # 捕获 PEM 解析的 RSAEncryptError 等所有解析类错误
                logger.warning(
                    "[ThirdPartyEndpointRegistry] 跳过非法端点: %s",
                    exc,
                )
                continue
            self._endpoints[ep.name] = ep

    @staticmethod
    def _parse_endpoint(item: Dict, allow_insecure: bool = False) -> ThirdPartyEndpoint:
        """解析并校验单个端点配置。

        Args:
            item: 端点 dict
            allow_insecure: 是否允许 http:// 端点（关闭 HTTPS 强制校验）；
                默认 False（生产安全）。仅当 ``settings.third_party_executor.
                allow_insecure=True`` 时透传为 True。

        Returns:
            ThirdPartyEndpoint: 校验通过的端点

        Raises:
            ValueError: 必填字段缺失或格式非法
        """
        if not isinstance(item, dict):
            raise ValueError("端点项必须是 dict")

        name = str(item.get("name") or "").strip()
        if not name:
            raise ValueError("name 必填且不可为空")
        url = str(item.get("url") or "").strip()
        if not url:
            raise ValueError(f"{name}: url 必填")
        if not url.startswith("https://"):
            if allow_insecure and url.startswith("http://"):
                # 仅在显式开启 allow_insecure 时放行 http://（dev / 内网 / 测试）
                logger.warning(
                    "[ThirdPartyEndpointRegistry] 端点 %s 使用 http://（allow_insecure=True，"
                    "请求体加密仍生效，但失去传输层保护）",
                    name,
                )
            else:
                raise ValueError(f"{name}: url 必须为 https:// （防中间人）")
        public_key_pem = str(item.get("public_key_pem") or "").strip()
        if not public_key_pem:
            raise ValueError(f"{name}: public_key_pem 必填")
        # 解析校验公钥（确保可被 cryptography 加载）
        _load_public_key(public_key_pem)
        try:
            timeout_seconds = int(item.get("timeout_seconds") or 30)
        except (TypeError, ValueError):
            timeout_seconds = 30
        timeout_seconds = max(1, min(timeout_seconds, 300))
        enabled = bool(item.get("enabled", True))
        return ThirdPartyEndpoint(
            name=name,
            url=url,
            public_key_pem=public_key_pem,
            timeout_seconds=timeout_seconds,
            enabled=enabled,
        )

    def get(self, name: str) -> ThirdPartyEndpoint:
        """根据端点名取端点配置。

        Args:
            name: 端点名

        Returns:
            ThirdPartyEndpoint: 端点

        Raises:
            ThirdPartyExecutorError: 未配置 / 已禁用 / 端点名不存在
        """
        if not self._loaded:
            self.load_from_settings()
        ep = self._endpoints.get(name)
        if ep is None:
            raise ThirdPartyExecutorError(
                error_code=ERR_CONFIG_MISSING,
                reason=f"third_party endpoint '{name}' 未配置",
                user_message=f"第三方端点 {name} 未配置",
            )
        if not ep.enabled:
            raise ThirdPartyExecutorError(
                error_code=ERR_CONFIG_MISSING,
                reason=f"third_party endpoint '{name}' 已禁用",
                user_message=f"第三方端点 {name} 已禁用",
            )
        return ep

    def names(self) -> List[str]:
        """列出所有已加载端点名。

        Returns:
            List[str]: 端点名列表
        """
        if not self._loaded:
            self.load_from_settings()
        return list(self._endpoints.keys())

    def diagnostic_summary(self) -> List[Dict[str, Any]]:
        """返回每个已加载端点的 ``[{"name", "enabled", "url"}]`` 摘要,供 SSHTools 日志可观测性使用。

        2026-08-05 新增:第三方调用失败时,SSHTools 把此摘要写入审计日志 metadata,
        让运维能从日志直接区分「JSON 未加载(name/PEM/URL 校验失败导致整条 skip)」vs
        「加载了但 name 拼错」vs「加载了但 enabled=False」。返回字段**不**包含
        ``public_key_pem``(敏感密钥材料)。

        Returns:
            List[Dict[str, Any]]: 端点摘要列表。
        """
        if not self._loaded:
            self.load_from_settings()
        return [
            {"name": ep.name, "enabled": ep.enabled, "url": ep.url}
            for ep in self._endpoints.values()
        ]


# 模块级单例占位（首次访问时初始化）
_instance: Optional[ThirdPartyEndpointRegistry] = None