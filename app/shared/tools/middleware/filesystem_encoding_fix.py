#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Filesystem Encoding Fix - 修复 Windows 环境下 subprocess UnicodeDecodeError

由于 deepagents 库中的 FilesystemBackend._ripgrep_search 方法使用
subprocess.run 时未指定 encoding 参数，在 Windows 系统上会默认使用 GBK 编码
解码子进程输出。当 ripgrep (rg) 输出包含 UTF-8 编码的中文字符时，GBK 无法
解码这些字节，导致 UnicodeDecodeError。

本模块通过 monkey patch 方式修复此问题，在 subprocess.run 调用中添加
encoding='utf-8' 和 errors='ignore' 参数。

使用方式：
    from app.shared.tools.middleware.filesystem_encoding_fix import apply_fix
    apply_fix()

必须在 deepagents 库被导入之前调用此修复。

Date: 2026-05-08
"""
import json
import logging
from pathlib import Path

from deepagents.backends import filesystem as fs_module

logger = logging.getLogger(__name__)

_orig_ripgrep_search = fs_module.FilesystemBackend._ripgrep_search


def _patched_ripgrep_search(
    self,
    pattern: str,
    base_full: Path,
    include_glob: str | None,
) -> dict[str, list[tuple[int, str]]] | None:
    """修复后的 ripgrep 搜索方法，添加 UTF-8 编码支持。

    Args:
        self: FilesystemBackend 实例
        pattern: 要搜索的模式
        base_full: 搜索的基础路径
        include_glob: 可选的 glob 模式过滤

    Returns:
        Dict mapping file paths to list of (line_number, line_text) tuples.
        Returns None if ripgrep is unavailable or times out.
    """
    cmd = ["rg", "--json", "-F"]
    if include_glob:
        cmd.extend(["--glob", include_glob])
    cmd.extend(["--", pattern, str(base_full)])

    try:
        proc = fs_module.subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=30,
            check=False,
        )
    except (fs_module.subprocess.TimeoutExpired, FileNotFoundError, PermissionError):
        return None

    results: dict[str, list[tuple[int, str]]] = {}
    for line in proc.stdout.splitlines():
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            continue
        if data.get("type") != "match":
            continue
        pdata = data.get("data", {})
        ftext = pdata.get("path", {}).get("text")
        if not ftext:
            continue
        p = Path(ftext)
        if self.virtual_mode:
            try:
                virt = self._to_virtual_path(p)
            except ValueError:
                logger.debug("Skipping grep result outside root: %s", p)
                continue
            except (OSError, RuntimeError):
                logger.warning("Could not resolve grep result path: %s", p, exc_info=True)
                continue
        else:
            virt = str(p)
        ln = pdata.get("line_number")
        lt = pdata.get("lines", {}).get("text", "").rstrip("\n")
        if ln is None:
            continue
        results.setdefault(virt, []).append((int(ln), lt))

    return results


def apply_fix() -> None:
    """应用编码修复。

    将 FilesystemBackend._ripgrep_search 方法替换为支持 UTF-8 编码的版本。

    注意：此函数应该尽快调用（在 deepagents 被导入之前），以确保修复生效。
    """
    if fs_module.FilesystemBackend._ripgrep_search is not _patched_ripgrep_search:
        fs_module.FilesystemBackend._ripgrep_search = _patched_ripgrep_search
        logger.info("FilesystemBackend._ripgrep_search 已应用 UTF-8 编码修复")
    else:
        logger.debug("FilesystemBackend._ripgrep_search 修复已应用，跳过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_fix()
    print("编码修复已应用")