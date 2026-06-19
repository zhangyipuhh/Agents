#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Session 上传路径管理器

统一管理 session 上传目录的日期化路径解析，并提供 session_id 到日期目录的索引维护。

目录结构：
    data/upload/{yyyy}/{mm}/{dd}/{session_id}/          # 原文件
    data/tmp/upload/{yyyy}/{mm}/{dd}/{session_id}/      # 解析后的 md 缓存
    data/upload/session_index.json                      # session_id -> "yyyy/mm/dd"

使用方式：
    from app.shared.utils.files.session_path_manager import (
        get_session_upload_dir,
        get_session_tmp_upload_dir,
        register_session_upload_date,
    )
    upload_dir = get_session_upload_dir(session_id, create=True)
    tmp_dir = get_session_tmp_upload_dir(session_id, create=True)

Date: 2026-06-19
"""

import json
import logging
from datetime import date
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)

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
) -> Path:
    """获取 session 原文件上传目录。

    Args:
        session_id: 会话 ID。
        create: 是否在目录不存在时自动创建并注册索引，默认 False。
        d: 指定日期，默认为今天或索引中已记录的日期。

    Returns:
        Path: session 原文件目录路径。
              若 create=False 且无法解析日期，则兜底返回 data/upload/{session_id}。
    """
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
            return _get_project_root() / _UPLOAD_ROOT / session_id

    session_dir = _get_project_root() / _UPLOAD_ROOT / date_path / session_id
    if create:
        session_dir.mkdir(parents=True, exist_ok=True)
    return session_dir


def get_session_tmp_upload_dir(
    session_id: str,
    create: bool = False,
    d: Optional[date] = None,
) -> Path:
    """获取 session 解析后的 md 缓存目录。

    Args:
        session_id: 会话 ID。
        create: 是否在目录不存在时自动创建，默认 False。
        d: 指定日期，默认为今天或索引中已记录的日期。

    Returns:
        Path: session md 缓存目录路径。
              若 create=False 且无法解析日期，则兜底返回 data/tmp/upload/{session_id}。
    """
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
            return _get_project_root() / _TMP_UPLOAD_ROOT / session_id

    tmp_dir = _get_project_root() / _TMP_UPLOAD_ROOT / date_path / session_id
    if create:
        tmp_dir.mkdir(parents=True, exist_ok=True)
    return tmp_dir
