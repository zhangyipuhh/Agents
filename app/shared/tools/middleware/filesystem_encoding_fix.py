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
import base64
import json
import logging
import re
from pathlib import Path

from deepagents.backends import filesystem as fs_module
from deepagents.backends.protocol import FileData, ReadResult, WriteResult

from app.core.config.paths import resolve_tmp_mirror_path
from app.shared.utils.files import session_path_manager as spm

logger = logging.getLogger(__name__)

# 需要读取 .md 缓存的文档类扩展名集合。
# 当文件路径为这些扩展名时，_patched_read 会把读取请求重定向到 data/tmp/... 下对应的 .md 文件。
_DOC_ONLY_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".md", ".txt"}

# deepagents.backends.utils._EXTENSION_TO_FILE_TYPE 中映射值非 "text" 的扩展名集合。
# 当原始文件路径为这些扩展名时，FilesystemMiddleware 会把 read_result 的 content
# 直接当作 base64 数据包装成多模态 content block，因此 _patched_read 必须返回
# 经过 base64 编码后的内容，以符合 LLM API 的参数校验。
_NON_TEXT_EXTENSIONS = {".pdf"}

_orig_ripgrep_search = fs_module.FilesystemBackend._ripgrep_search
_orig_read = fs_module.FilesystemBackend.read
_orig_write = None
_orig_python_search = None


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


def _patched_read(
    self,
    file_path: str,
    offset: int = 0,
    limit: int = 2000,
) -> ReadResult:
    """将读取请求按扩展名区分：文档类重定向到 .md 缓存，非文档类直接读取原文件。

    deepagents FilesystemMiddleware 传入的 file_path 是以 "/" 开头的虚拟绝对路径
    （如 "/file.docx"、"/reports/annual.pdf"、"/script.py"）。FilesystemBackend._resolve_path 在
    virtual_mode=True 下会将其解析为 self.cwd / vpath.lstrip("/") 。

    规则：
    1. 若文件扩展名属于 _DOC_ONLY_EXTENSIONS（pdf/docx/xlsx/md/txt），
       临时将 self.cwd 从 data/... 映射到 data/tmp/...，解析后把扩展名统一替换为 ".md" 并读取。
    2. 若文件扩展名不属于文档类，直接读取 self.cwd 下的原文件。
    3. 读取完成后恢复原始 self.cwd，确保 ls/glob/grep 仍在源目录工作。

    Args:
        self: FilesystemBackend 实例。
        file_path: 原始传入的虚拟绝对路径。
        offset: 起始行偏移（0-indexed）。
        limit: 最大读取行数。

    Returns:
        ReadResult: 包含文件内容或错误信息。
    """
    original_cwd = self.cwd
    original_ext = Path(file_path).suffix.lower()

    try:
        if original_ext in _DOC_ONLY_EXTENSIONS:
            # 文档类：临时把 self.cwd 从 data/... 映射到 data/tmp/...
            project_root = spm._get_project_root().resolve()
            data_root = (project_root / "data").resolve()
            tmp_data_root = (project_root / "data" / "tmp").resolve()
            try:
                rel = original_cwd.resolve().relative_to(data_root)
                # 避免重复映射：如果 cwd 已经在 data/tmp/ 下，保持原样
                if not original_cwd.resolve().is_relative_to(tmp_data_root):
                    self.cwd = tmp_data_root / rel
            except ValueError:
                # self.cwd 不在 data/ 下（例如已是 data/tmp/ 或其它路径），保持原 cwd
                pass

            # 让后端按 virtual_mode 规则解析虚拟路径
            try:
                abs_target = self._resolve_path(file_path)
            except (ValueError, OSError, RuntimeError) as e:
                return ReadResult(error=f"Error reading file '{file_path}': {e}")

            # 统一改扩展名为 .md
            abs_target = abs_target.with_suffix(".md")

            if not abs_target.exists() or not abs_target.is_file():
                return ReadResult(error=f"File '{file_path}' not found")

            # 读取 .md 文件
            with open(abs_target, "r", encoding="utf-8") as f:
                content = f.read()

            # 若原始文件扩展名是非文本类型（如 .pdf），
            # deepagents FilesystemMiddleware 会把 content 直接作为 base64 字段传给 API。
            # 由于实际读取的是 .md 文本，必须将其 base64 编码以符合 API 参数校验。
            if original_ext in _NON_TEXT_EXTENSIONS:
                content = base64.b64encode(content.encode("utf-8")).decode("ascii")
                file_encoding = "base64"
            else:
                file_encoding = "utf-8"
        else:
            # 非文档类：直接读取原文件
            try:
                abs_target = self._resolve_path(file_path)
            except (ValueError, OSError, RuntimeError) as e:
                return ReadResult(error=f"Error reading file '{file_path}': {e}")

            if not abs_target.exists() or not abs_target.is_file():
                return ReadResult(error=f"File '{file_path}' not found")

            with open(abs_target, "r", encoding="utf-8") as f:
                content = f.read()

            file_encoding = "utf-8"

        lines = content.splitlines(keepends=True)
        start_idx = offset
        end_idx = min(start_idx + limit, len(lines))

        if start_idx >= len(lines):
            return ReadResult(
                error=f"Line offset {offset} exceeds file length ({len(lines)} lines)"
            )

        file_data = FileData(content="".join(lines[start_idx:end_idx]), encoding=file_encoding)
        return ReadResult(file_data=file_data)
    except (OSError, UnicodeDecodeError) as e:
        return ReadResult(error=f"Error reading file '{file_path}': {e}")
    finally:
        # 恢复原始工作空间
        self.cwd = original_cwd


def _patched_write(
    self,
    file_path: str,
    content: str,
) -> WriteResult:
    """写入原文件，并对文档类扩展名同步写入 data/tmp/... 下的 .md 副本。

    当 sandbox 子智能体通过 write_file 工具写入 pdf/docx/xlsx/md/txt 文件时，
    原文件落在 data/upload/... 或 data/project/... 下；本补丁会在写入原文件后，
    将相同内容同步写入 resolve_tmp_mirror_path 计算出的 .md 镜像路径，
    供 explore / query_knowledge 等工具通过 .md 缓存读取。

    Args:
        self: FilesystemBackend 实例。
        file_path: 原始传入的虚拟绝对路径。
        content: 待写入的 UTF-8 文本内容。

    Returns:
        WriteResult: 包含成功路径或错误信息。
    """
    result = _orig_write(self, file_path, content)
    if result.error:
        return result

    original_ext = Path(file_path).suffix.lower()
    if original_ext not in _DOC_ONLY_EXTENSIONS:
        return result

    try:
        abs_target = self._resolve_path(file_path)
        md_path = resolve_tmp_mirror_path(abs_target)
        if md_path is not None:
            md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(md_path, "w", encoding="utf-8", newline="") as f:
                f.write(content)
    except (OSError, UnicodeEncodeError) as e:
        logger.warning("Failed to write .md mirror for %s: %s", file_path, e)

    return result


def _patched_python_search(
    self,
    pattern: str,
    base_path: str,
    include: str | None,
) -> dict[str, list[tuple[int, str]]]:
    """将 grep 搜索重定向到对应的 .md 缓存文件。

    遍历原始目录下的文件，按原始文件名进行 include 过滤，
    但实际读取的是 data/tmp/... 下对应的 .md 缓存文件内容进行正则匹配。
    返回的虚拟路径保持原始文件名（如 /file.pdf）。

    Args:
        self: EncodingSafeFileSearchMiddleware 实例。
        pattern: 正则表达式模式。
        base_path: 搜索的基础虚拟路径。
        include: 可选的文件名过滤模式。

    Returns:
        Dict mapping virtual paths to list of (line_number, line_text) tuples.
    """
    from app.shared.tools.middleware.encoding_safe_file_search import (
        ENCODING_FALLBACK,
        _match_include_pattern,
    )

    # 1. 尝试将 root_path 从 data/... 映射到 data/tmp/...
    project_root = spm._get_project_root().resolve()
    data_root = (project_root / "data").resolve()
    tmp_data_root = (project_root / "data" / "tmp").resolve()

    try:
        rel = self.root_path.resolve().relative_to(data_root)
        tmp_root = tmp_data_root / rel
    except ValueError:
        # root_path 不在 data/ 下（如知识库），回退到原始行为
        return _orig_python_search(self, pattern, base_path, include)

    if not tmp_root.exists():
        return _orig_python_search(self, pattern, base_path, include)

    # 2. 解析 base_path
    try:
        base_full = self._validate_and_resolve_path(base_path)
    except ValueError:
        return {}

    if not base_full.exists():
        return {}

    regex = re.compile(pattern, re.IGNORECASE)
    results: dict[str, list[tuple[int, str]]] = {}

    # 3. 遍历原始目录，但读取对应的 .md 文件
    for file_path in base_full.rglob("*"):
        if not file_path.is_file():
            continue

        # include 过滤在原始文件名上生效
        if include and not _match_include_pattern(file_path.name, include):
            continue

        # 计算对应的 .md 路径
        rel_path = file_path.relative_to(self.root_path)
        md_path = (tmp_root / rel_path).with_suffix(".md")

        if not md_path.exists() or not md_path.is_file():
            continue

        if md_path.stat().st_size > self.max_file_size_bytes:
            continue

        # 读取 .md 文件内容
        for encoding in ENCODING_FALLBACK:
            try:
                content = md_path.read_text(encoding=encoding)
                break
            except (UnicodeDecodeError, PermissionError):
                continue
        else:
            continue

        # 确保 content 不为 None
        if content is None:
            continue

        for line_num, line in enumerate(content.splitlines(), 1):
            if regex.search(line):
                virtual_path = "/" + str(rel_path)
                if virtual_path not in results:
                    results[virtual_path] = []
                results[virtual_path].append((line_num, line))

    return results


def apply_fix() -> None:
    """应用编码修复、read 重定向、write .md 镜像与 grep_search .md 重定向补丁。

    将 FilesystemBackend._ripgrep_search 方法替换为支持 UTF-8 编码的版本，
    将 FilesystemBackend.read 方法替换为按扩展名区分的 .md 缓存重定向版本，
    将 FilesystemBackend.write 方法替换为对文档类文件同步写入 .md 镜像的版本，
    同时将 EncodingSafeFileSearchMiddleware._python_search 方法替换为
    重定向到 .md 缓存文件进行内容搜索的版本。

    注意：此函数应该尽快调用（在 deepagents 被导入之前），以确保修复生效。
    """
    from app.shared.tools.middleware.encoding_safe_file_search import EncodingSafeFileSearchMiddleware

    if fs_module.FilesystemBackend._ripgrep_search is not _patched_ripgrep_search:
        fs_module.FilesystemBackend._ripgrep_search = _patched_ripgrep_search
        logger.info("FilesystemBackend._ripgrep_search 已应用 UTF-8 编码修复")
    else:
        logger.debug("FilesystemBackend._ripgrep_search 修复已应用，跳过")

    if fs_module.FilesystemBackend.read is not _patched_read:
        fs_module.FilesystemBackend.read = _patched_read
        logger.info("FilesystemBackend.read 已应用 .md 重定向补丁")
    else:
        logger.debug("FilesystemBackend.read 修复已应用，跳过")

    global _orig_write
    if _orig_write is None:
        _orig_write = fs_module.FilesystemBackend.write

    if fs_module.FilesystemBackend.write is not _patched_write:
        fs_module.FilesystemBackend.write = _patched_write
        logger.info("FilesystemBackend.write 已应用 .md 镜像补丁")
    else:
        logger.debug("FilesystemBackend.write 修复已应用，跳过")

    global _orig_python_search
    if _orig_python_search is None:
        _orig_python_search = EncodingSafeFileSearchMiddleware._python_search

    if EncodingSafeFileSearchMiddleware._python_search is not _patched_python_search:
        EncodingSafeFileSearchMiddleware._python_search = _patched_python_search
        logger.info("EncodingSafeFileSearchMiddleware._python_search 已应用 .md 重定向补丁")
    else:
        logger.debug("EncodingSafeFileSearchMiddleware._python_search 修复已应用，跳过")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    apply_fix()
    print("编码修复已应用")