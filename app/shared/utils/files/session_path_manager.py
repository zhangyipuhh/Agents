#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Session 上传路径管理器

统一管理 session 上传目录的日期化路径解析，并提供 session_id 到日期目录的索引维护。

目录结构（2026-06-30 新增项目路由）：
    # 默认（无 project 关联）—— 沿用旧行为
    data/upload/{yyyy}/{mm}/{dd}/{session_id}/          # 原文件
    data/tmp/upload/{yyyy}/{mm}/{dd}/{session_id}/      # 解析后的 md 缓存
    data/upload/session_index.json                      # session_id -> "yyyy/mm/dd"

    # 关联项目时 —— 走项目独立目录（与 session_id 无关）
    data/project/yyyy/mm/dd/{project_uuid}/                        # 原文件
    data/tmp/project/yyyy/mm/dd/{project_uuid}/                    # 解析后的 md 缓存

使用方式：
    from app.shared.utils.files.session_path_manager import (
        get_session_upload_dir,
        get_session_tmp_upload_dir,
        register_session_upload_date,
    )
    upload_dir = get_session_upload_dir(session_id, create=True, project_id=5)
    tmp_dir = get_session_tmp_upload_dir(session_id, create=True, project_id=5)

Date: 2026-06-19 (updated 2026-06-30)
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


def _to_filesystem_safe(session_id: Optional[str]) -> str:
    """把 session_id 转换为文件系统安全的目录片段（2026-07-17 新增）。

    飞书 WebSocket 产生的 session_id 形如 ``feishu:p2p:open_id``，含 ``:``
    字符。Windows 不允许 ``:`` 出现在路径中（仅作盘符分隔符），否则
    ``Path.iterdir()`` 会抛 ``OSError [WinError 123]``（参见 2026-07-17
    线上事故：飞书 session 文件抽屉 500）。

    飞书 WS 写文件路径时已经过等价转换（``FeishuWebSocketService.
    _safe_session_marker``，``replace(":", "_")``），本函数把同一转换下沉
    到**读路径入口**，保证读写两侧落到同一目录。普通 session_id 不含
    ``:``，转换是 no-op，不影响非飞书场景。

    此函数不接受空值；空值请走 ``"default"`` 兜底（与 ``get_session_upload_dir``
    历史行为一致）。

    Args:
        session_id: 原始 session_id（可能含 ``:``）。

    Returns:
        str: 文件系统安全标记（``:`` 已替换为 ``_``）。
    """
    if not session_id:
        return "default"
    return str(session_id).replace(":", "_")

_UPLOAD_ROOT = Path("data/upload")
_TMP_UPLOAD_ROOT = Path("data/tmp/upload")
_INDEX_FILE = _UPLOAD_ROOT / "session_index.json"


def _get_project_root() -> Path:
    """获取项目根目录。

    Returns:
        Path: 本文件向上回溯五级到达项目根目录（app/shared/utils/files/ -> 项目根）。
    """
    return Path(__file__).parent.parent.parent.parent.parent


def _load_index() -> dict[str, str]:
    """加载 session 日期索引。

    Returns:
        dict[str, str]: session_id 到 "yyyy/mm/dd" 的映射；索引不存在时返回空字典。
    """
    index_path = _get_project_root() / _INDEX_FILE
    if not index_path.exists():
        return {}
    try:
        with open(index_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return {str(k): str(v) for k, v in data.items()}
        return {}
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("加载 session 日期索引失败: %s", e)
        return {}


def _save_index(index: dict[str, str]) -> None:
    """保存 session 日期索引。

    Args:
        index: session_id 到 "yyyy/mm/dd" 的映射。
    """
    index_path = _get_project_root() / _INDEX_FILE
    index_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)
    except OSError as e:
        logger.warning("保存 session 日期索引失败: %s", e)


def _date_path(d: Optional[date] = None) -> str:
    """生成日期路径字符串。

    Args:
        d: 日期对象，默认为今天。

    Returns:
        str: "yyyy/mm/dd" 格式的日期路径。
    """
    d = d or date.today()
    return f"{d.year}/{d.month:02d}/{d.day:02d}"


def register_session_upload_date(session_id: str, d: Optional[date] = None) -> None:
    """注册 session 的上传日期索引。

    在 session 创建或首次上传时调用，将 session_id 与日期路径写入索引文件。

    Args:
        session_id: 会话 ID。
        d: 指定日期，默认为今天。
    """
    if not session_id:
        return
    index = _load_index()
    index[session_id] = _date_path(d)
    _save_index(index)


def remove_session_upload_date(session_id: str) -> None:
    """从索引中移除 session 记录。

    通常在删除 session 时调用。

    Args:
        session_id: 会话 ID。
    """
    if not session_id:
        return
    index = _load_index()
    if session_id in index:
        del index[session_id]
        _save_index(index)


def _find_session_date_path_by_walk(session_id: str) -> Optional[str]:
    """通过遍历日期目录查找 session_id 对应的日期路径。

    作为索引缺失时的兜底查找方式。

    Args:
        session_id: 会话 ID。

    Returns:
        Optional[str]: 找到时返回 "yyyy/mm/dd"，否则返回 None。
    """
    upload_root = _get_project_root() / _UPLOAD_ROOT
    if not upload_root.exists():
        return None
    try:
        for year_dir in upload_root.iterdir():
            if not year_dir.is_dir() or not year_dir.name.isdigit():
                continue
            for month_dir in year_dir.iterdir():
                if not month_dir.is_dir() or not month_dir.name.isdigit():
                    continue
                for day_dir in month_dir.iterdir():
                    if not day_dir.is_dir() or not day_dir.name.isdigit():
                        continue
                    session_dir = day_dir / session_id
                    if session_dir.exists() and session_dir.is_dir():
                        return f"{year_dir.name}/{month_dir.name}/{day_dir.name}"
    except OSError as e:
        logger.warning("遍历查找 session 日期目录失败: %s", e)
    return None


def resolve_session_date_path(session_id: str) -> Optional[str]:
    """解析 session_id 对应的日期路径。

    优先从索引文件读取；索引不存在时遍历日期目录查找；仍未找到返回 None。

    Args:
        session_id: 会话 ID。

    Returns:
        Optional[str]: "yyyy/mm/dd" 日期路径，找不到时返回 None。
    """
    if not session_id:
        return None
    index = _load_index()
    date_path = index.get(session_id)
    if date_path:
        return date_path
    return _find_session_date_path_by_walk(session_id)


def get_session_upload_dir(
    session_id: str,
    create: bool = False,
    d: Optional[date] = None,
    project_id: Optional[int] = None,
) -> Path:
    """获取 session 原文件上传目录（2026-06-30 扩展支持 project 路由）。

    Args:
        session_id: 会话 ID。
        create: 是否在目录不存在时自动创建并注册索引，默认 False。
        d: 指定日期，默认为今天或索引中已记录的日期。
        project_id: 2026-06-30 新增；非空时走项目独立目录 data/project/yyyy/mm/dd/{project_uuid}/，
                    忽略 session_id 维度。用于项目文件夹语义。

    Returns:
        Path: 原文件目录路径。
              - 有 project_id：data/project/yyyy/mm/dd/{project_uuid}/
              - 无 project_id（默认）：data/upload/{yyyy}/{mm}/{dd}/{session_id}/
              - 兜底：data/upload/{session_id}/
    """
    # 2026-06-30 新增：项目路由（优先于 session 路径）
    if project_id:
        from app.shared.utils.project.project_db import ProjectDB
        from app.shared.utils.files.project_path_manager import get_project_upload_dir
        # 同步查 DB 获取 uuid；同步 IO 在工具/上传场景足够
        # 若项目不存在则 fallback 到 session 路径
        try:
            project = ProjectDB._memory_cache.get(project_id)
            if not project and ProjectDB.is_enabled():
                # 同步路径不能 await，调用方应已通过 request.state 注入；
                # 这里走 DB 同步访问在异步上下文中不安全
                # 兜底：直接返回 session 路径
                logger.warning(
                    "get_session_upload_dir: project_id=%s 未在内存缓存中，fallback 到 session 路径",
                    project_id,
                )
            if project:
                return get_project_upload_dir(project['relative_path'], create=create)
        except Exception as e:
            logger.warning("get_session_upload_dir: project_id 路由失败，fallback 到 session 路径: %s", e)

    if not session_id:
        session_id = "default"

    date_path: Optional[str]
    if d is not None:
        date_path = _date_path(d)
    else:
        date_path = resolve_session_date_path(session_id)

    if date_path is None:
        if create:
            date_path = _date_path(date.today())
            register_session_upload_date(session_id, date.today())
        else:
            return _get_project_root() / _UPLOAD_ROOT / _to_filesystem_safe(session_id)

    # 2026-07-17 新增：读路径侧统一做 : → _ 转换，与飞书 WS 写路径
    # （_safe_session_marker）保持一致，避免 Windows 上 Path.iterdir()
    # 抛 WinError 123 引发文件树 500。
    fs_session_id = _to_filesystem_safe(session_id)
    session_dir = _get_project_root() / _UPLOAD_ROOT / date_path / fs_session_id
    if create:
        session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_session_tmp_upload_dir(
    session_id: str,
    create: bool = False,
    d: Optional[date] = None,
    project_id: Optional[int] = None,
) -> Path:
    """获取 session 解析后的 md 缓存目录（2026-06-30 扩展支持 project 路由）。

    Args:
        session_id: 会话 ID。
        create: 是否在目录不存在时自动创建，默认 False。
        d: 指定日期，默认为今天或索引中已记录的日期。
        project_id: 2026-06-30 新增；非空时走项目独立目录 data/tmp/project/yyyy/mm/dd/{project_uuid}/。

    Returns:
        Path: md 缓存目录路径。
              - 有 project_id：data/tmp/project/yyyy/mm/dd/{project_uuid}/
              - 无 project_id（默认）：data/tmp/upload/{yyyy}/{mm}/{dd}/{session_id}/
              - 兜底：data/tmp/upload/{session_id}/
    """
    # 2026-06-30 新增：项目路由
    if project_id:
        from app.shared.utils.project.project_db import ProjectDB
        from app.shared.utils.files.project_path_manager import get_project_tmp_upload_dir
        try:
            project = ProjectDB._memory_cache.get(project_id)
            if project:
                return get_project_tmp_upload_dir(project['relative_path'], create=create)
        except Exception as e:
            logger.warning("get_session_tmp_upload_dir: project_id 路由失败，fallback 到 session 路径: %s", e)

    if not session_id:
        session_id = "default"

    date_path: Optional[str]
    if d is not None:
        date_path = _date_path(d)
    else:
        date_path = resolve_session_date_path(session_id)

    if date_path is None:
        if create:
            date_path = _date_path(date.today())
            register_session_upload_date(session_id, date.today())
        else:
            return _get_project_root() / _TMP_UPLOAD_ROOT / _to_filesystem_safe(session_id)

    # 2026-07-17 新增：读路径侧统一做 : → _ 转换，与 get_session_upload_dir
    # 行为对齐，参见 _to_filesystem_safe 注释。
    fs_session_id = _to_filesystem_safe(session_id)
    tmp_dir = _get_project_root() / _TMP_UPLOAD_ROOT / date_path / fs_session_id
    if create:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir
