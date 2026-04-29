#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
EncodingSafeFileSearchMiddleware - 多编码兼容的文件搜索中间件。

基于 LangChain AgentMiddleware 规范实现的文件搜索中间件，
提供 glob_search 和 grep_search 两个工具。
与 FilesystemFileSearchMiddleware 功能对等，唯一差异：
    _python_search 对每个文件依次尝试 utf-8 / gbk / cp1252 编码，
    解决 Windows 平台默认 GBK 编码无法读取 UTF-8 文件导致静默跳过的问题。

不依赖 FilesystemFileSearchMiddleware 的任何私有方法。
"""

import fnmatch
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

from langchain.agents.middleware.types import AgentMiddleware
from langchain_core.tools import tool

ENCODING_FALLBACK = ("utf-8", "gbk", "cp1252")


# ---------------------------------------------------------------------------
# 自实现的 include pattern 工具函数（不依赖 langchain 私有 API）
# ---------------------------------------------------------------------------

def _expand_include_patterns(pattern: str) -> list[str] | None:
    """Expand brace patterns like `*.{py,pyi}` into a list of globs."""
    if "}" in pattern and "{" not in pattern:
        return None

    expanded: list[str] = []

    def _expand(current: str) -> None:
        start = current.find("{")
        if start == -1:
            expanded.append(current)
            return

        end = current.find("}", start)
        if end == -1:
            raise ValueError

        prefix = current[:start]
        suffix = current[end + 1:]
        inner = current[start + 1:end]
        if not inner:
            raise ValueError

        for option in inner.split(","):
            _expand(prefix + option + suffix)

    try:
        _expand(pattern)
    except ValueError:
        return None

    return expanded


def _is_valid_include_pattern(pattern: str) -> bool:
    """Validate glob pattern used for include filters."""
    if not pattern:
        return False
    if any(char in pattern for char in ("\x00", "\n", "\r")):
        return False
    expanded = _expand_include_patterns(pattern)
    if expanded is None:
        return False
    try:
        for candidate in expanded:
            re.compile(fnmatch.translate(candidate))
    except re.error:
        return False
    return True


def _match_include_pattern(basename: str, pattern: str) -> bool:
    """Return True if the basename matches the include pattern."""
    expanded = _expand_include_patterns(pattern)
    if not expanded:
        return False
    return any(fnmatch.fnmatch(basename, candidate) for candidate in expanded)


# ---------------------------------------------------------------------------
# 主类
# ---------------------------------------------------------------------------

class EncodingSafeFileSearchMiddleware(AgentMiddleware):
    """Provides Glob and Grep search with multi-encoding file read support.

    Same interface as FilesystemFileSearchMiddleware but _python_search
    tries multiple encodings per file, preventing UTF-8 files from being
    silently skipped on Windows (where default encoding is usually GBK).
    """

    def __init__(
        self,
        *,
        root_path: str,
        use_ripgrep: bool = False,
        max_file_size_mb: int = 10,
    ) -> None:
        self.root_path = Path(root_path).resolve()
        self.use_ripgrep = use_ripgrep
        self.max_file_size_bytes = max_file_size_mb * 1024 * 1024

        @tool
        def glob_search(pattern: str, path: str = "/") -> str:
            """Fast file pattern matching tool that works with any codebase size.

            Supports glob patterns like `**/*.js` or `src/**/*.ts`.

            Returns matching file paths sorted by modification time.

            Use this tool when you need to find files by name patterns.

            Args:
                pattern: The glob pattern to match files against.
                path: The directory to search in. If not specified, searches
                    from root.

            Returns:
                Newline-separated list of matching file paths, sorted by
                modification time (most recently modified first). Returns
                `'No files found'` if no matches.
            """
            try:
                base_full = self._validate_and_resolve_path(path)
            except ValueError:
                return "No files found"

            if not base_full.exists() or not base_full.is_dir():
                return "No files found"

            matching: list[tuple[str, str]] = []
            for match in base_full.glob(pattern):
                if match.is_file():
                    virtual_path = "/" + str(
                        match.relative_to(self.root_path)
                    )
                    stat = match.stat()
                    modified_at = datetime.fromtimestamp(
                        stat.st_mtime, tz=timezone.utc
                    ).isoformat()
                    matching.append((virtual_path, modified_at))

            if not matching:
                return "No files found"

            file_paths = [p for p, _ in matching]
            return "\n".join(file_paths)

        @tool
        def grep_search(
            pattern: str,
            path: str = "/",
            include: str | None = None,
            output_mode: Literal[
                "files_with_matches", "content", "count"
            ] = "files_with_matches",
        ) -> str:
            """Fast content search tool that works with any codebase size.

            Searches file contents using regular expressions. Supports full
            regex syntax and filters files by pattern with the include param.

            Args:
                pattern: The regular expression pattern to search for in file
                    contents.
                path: The directory to search in. If not specified, searches
                    from root.
                include: File pattern to filter (e.g. `'*.js'`).
                output_mode: Output format:
                    - `'files_with_matches'`: Only file paths
                    - `'content'`: `file:line:content` format
                    - `'count'`: Count of matches per file

            Returns:
                Search results formatted according to `output_mode`.
                Returns `'No matches found'` if no results.
            """
            try:
                re.compile(pattern)
            except re.error as e:
                return f"Invalid regex pattern: {e}"

            if include and not _is_valid_include_pattern(include):
                return "Invalid include pattern"

            results = self._python_search(pattern, path, include)

            if not results:
                return "No matches found"

            return self._format_grep_results(results, output_mode)

        self.glob_search = glob_search
        self.grep_search = grep_search
        self.tools = [glob_search, grep_search]

    # -----------------------------------------------------------------------
    # 内部方法
    # -----------------------------------------------------------------------

    def _validate_and_resolve_path(self, path: str) -> Path:
        """Validate and resolve a virtual path to filesystem path."""
        if not path.startswith("/"):
            path = "/" + path

        if ".." in path or "~" in path:
            msg = "Path traversal not allowed"
            raise ValueError(msg)

        relative = path.lstrip("/")
        full_path = (self.root_path / relative).resolve()

        try:
            full_path.relative_to(self.root_path)
        except ValueError:
            msg = f"Path outside root directory: {path}"
            raise ValueError(msg) from None

        return full_path

    def _python_search(
        self, pattern: str, base_path: str, include: str | None
    ) -> dict[str, list[tuple[int, str]]]:
        """Search using Python regex with multi-encoding fallback."""
        try:
            base_full = self._validate_and_resolve_path(base_path)
        except ValueError:
            return {}

        if not base_full.exists():
            return {}

        regex = re.compile(pattern, re.IGNORECASE)
        results: dict[str, list[tuple[int, str]]] = {}

        for file_path in base_full.rglob("*"):
            if not file_path.is_file():
                continue

            if include and not _match_include_pattern(
                file_path.name, include
            ):
                continue

            if file_path.stat().st_size > self.max_file_size_bytes:
                continue

            for encoding in ENCODING_FALLBACK:
                try:
                    content = file_path.read_text(encoding=encoding)
                    break
                except (UnicodeDecodeError, PermissionError):
                    continue
            else:
                continue

            for line_num, line in enumerate(content.splitlines(), 1):
                if regex.search(line):
                    virtual_path = "/" + str(
                        file_path.relative_to(self.root_path)
                    )
                    if virtual_path not in results:
                        results[virtual_path] = []
                    results[virtual_path].append((line_num, line))

        return results

    def _format_grep_results(
        self,
        results: dict[str, list[tuple[int, str]]],
        output_mode: str,
    ) -> str:
        """Format grep results based on output mode."""
        if output_mode == "files_with_matches":
            return "\n".join(sorted(results.keys()))

        if output_mode == "content":
            lines = []
            for file_path in sorted(results.keys()):
                for line_num, line in results[file_path]:
                    lines.append(f"{file_path}:{line_num}:{line}")
            return "\n".join(lines)

        if output_mode == "count":
            lines = []
            for file_path in sorted(results.keys()):
                count = len(results[file_path])
                lines.append(f"{file_path}:{count}")
            return "\n".join(lines)

        return "\n".join(sorted(results.keys()))
