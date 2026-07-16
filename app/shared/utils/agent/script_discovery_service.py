# -*- coding:utf-8 -*-
"""
脚本发现与扫描服务。

职责：
    * 扫描 ``app/scripts/`` 目录下所有 ``.py`` 文件，通过 ``importlib`` 动态加载
      触发 ``@register_script`` 装饰器执行，把脚本元数据登记到全局 registry
    * 容错：单个文件加载失败不中断整体扫描，仅记入 ``failed`` 计数
    * 对外提供 ``list_scripts()``（白名单元数据列表）与 ``get_script()``（含函数引用）

设计要点：
    * 脚本元数据由代码定义，扫描只是触发加载，无需持久化到数据库
    * 服务实例缓存在 ``app.state.script_discovery_service``，避免重复扫描
    * ``scan()`` 返回 ``{scanned, registered, failed}`` 三字段统计，与 DevOps scan 风格对齐

依赖：
    * ``app.scripts.registry`` 的全局注册表 ``_SCRIPT_REGISTRY``
    * ``app.scripts.base`` 的 ``RegisteredScript`` 数据类
"""
from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from app.scripts.base import RegisteredScript
from app.scripts.registry import get_registered_script, get_registered_scripts


logger = logging.getLogger(__name__)


# 扫描时跳过的文件名（不视为脚本）
_SKIP_FILENAMES = {"__init__.py", "base.py", "registry.py"}

# 白名单字段：list_scripts 对外只返回这些字段，不暴露 func 引用
_PUBLIC_FIELDS = ("name", "display_name", "description", "params_schema", "module_path")


class ScriptDiscoveryService:
    """脚本发现与扫描服务。

    参数:
        scripts_dir: 脚本扫描根目录绝对路径（通常为 ``app/scripts/``）。
    """

    def __init__(self, scripts_dir: Path) -> None:
        """初始化脚本发现服务。

        参数:
            scripts_dir: 脚本扫描根目录。不存在时仅记 warning，扫描时返回空结果。
        """
        self._scripts_dir = Path(scripts_dir)
        if not self._scripts_dir.exists():
            logger.warning(
                "[ScriptDiscoveryService] scripts_dir 不存在: %s",
                self._scripts_dir,
            )

    async def scan(self) -> Dict[str, int]:
        """扫描 ``scripts_dir`` 下所有 ``.py`` 文件并加载到 registry。

        扫描规则：
            * 递归遍历所有 ``.py`` 文件
            * 跳过文件名在 ``_SKIP_FILENAMES`` 中的文件
            * 跳过以下划线开头的文件名
            * 用 ``importlib.util.spec_from_file_location`` 动态加载
            * 单个文件加载失败记入 ``failed``，不中断整体扫描

        返回:
            Dict[str, int]: 三字段统计
                * ``scanned``: 扫描的 .py 文件总数（含跳过的）
                * ``registered``: 本次扫描后 registry 中的脚本总数
                * ``failed``: 加载失败的文件数
        """
        scanned = 0
        failed = 0

        if not self._scripts_dir.exists():
            logger.warning(
                "[ScriptDiscoveryService.scan] scripts_dir 不存在，跳过扫描: %s",
                self._scripts_dir,
            )
            return {"scanned": 0, "registered": len(get_registered_scripts()), "failed": 0}

        py_files = sorted(self._scripts_dir.rglob("*.py"))
        for py_file in py_files:
            filename = py_file.name
            if filename in _SKIP_FILENAMES:
                continue
            if filename.startswith("_"):
                continue
            scanned += 1
            try:
                self._load_file(py_file)
            except Exception as exc:  # noqa: BLE001 - 单文件失败不阻断整体扫描
                failed += 1
                logger.warning(
                    "[ScriptDiscoveryService.scan] 加载脚本文件失败 %s: %s",
                    py_file,
                    exc,
                )

        registered = len(get_registered_scripts())
        logger.info(
            "[ScriptDiscoveryService.scan] 扫描完成: scanned=%d, registered=%d, failed=%d",
            scanned,
            registered,
            failed,
        )
        return {"scanned": scanned, "registered": registered, "failed": failed}

    def _load_file(self, py_file: Path) -> None:
        """动态加载单个 Python 文件，触发 ``@register_script`` 装饰器执行。

        加载策略：
            * 用文件路径构造唯一模块名 ``app.scripts.<relative_path_without_ext>``
            * 已加载的模块跳过（避免重复注册抛 ``ValueError``）
            * 加载后保留在 ``sys.modules`` 中，避免下次扫描重复加载

        参数:
            py_file: Python 文件绝对路径。

        异常:
            加载过程中的任何异常向上抛出，由 ``scan`` 容错捕获。
        """
        try:
            rel = py_file.relative_to(self._scripts_dir)
        except ValueError:
            rel = py_file
        # 模块名：app.scripts.examples.hello_script
        parts = list(rel.with_suffix("").parts)
        module_name = "app.scripts." + ".".join(parts) if parts else py_file.stem

        if module_name in sys.modules:
            logger.debug(
                "[ScriptDiscoveryService._load_file] 模块已加载，跳过: %s",
                module_name,
            )
            return

        spec = importlib.util.spec_from_file_location(module_name, str(py_file))
        if spec is None or spec.loader is None:
            raise RuntimeError(f"无法为 {py_file} 构造 import spec")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    def list_scripts(self) -> List[Dict[str, Any]]:
        """列出所有已注册脚本的元数据（白名单字段，不含函数引用）。

        返回:
            List[Dict[str, Any]]: 元数据字典列表，每项严格只含白名单字段。
        """
        result: List[Dict[str, Any]] = []
        for script in get_registered_scripts().values():
            result.append({k: getattr(script, k, None) for k in _PUBLIC_FIELDS})
        return result

    def get_script(self, name: str) -> Optional[RegisteredScript]:
        """按名称查询已注册脚本，返回完整对象（含函数引用）。

        参数:
            name: 脚本唯一标识。

        返回:
            Optional[RegisteredScript]: 找到则返回，否则返回 None。
        """
        return get_registered_script(name)
