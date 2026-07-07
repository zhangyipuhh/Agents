#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目文件夹路径管理器

负责解析项目文件夹的物理路径（原文件目录 + 解析缓存目录）。
与 session_path_manager 完全独立的物理路径体系，遵循「项目文件不与会话文件混目录」的隔离原则。

目录结构示例：
    data/project/2026/07/01/{project_uuid}/       # 原文件
    data/tmp/project/2026/07/01/{project_uuid}/   # 解析后的 md 缓存

使用方式：
    from app.shared.utils.files.project_path_manager import (
        get_project_upload_dir,
        get_project_tmp_upload_dir,
    )
    upload_dir = get_project_upload_dir("data/project/2026/07/01/uuid", create=True)
    tmp_dir = get_project_tmp_upload_dir("data/project/2026/07/01/uuid", create=True)

Date: 2026-07-01
Author: AI Assistant
"""
from pathlib import Path

from app.core.config.paths import resolve_project_dir, resolve_project_tmp_dir


def get_project_upload_dir(relative_path: str, create: bool = False) -> Path:
    """获取项目原文件目录。

    Args:
        relative_path: 相对于项目根的相对路径，使用正斜杠分隔，
            例如 ``data/project/2026/07/01/uuid``。
        create: 是否在目录不存在时自动创建，默认 False。

    Returns:
        Path: 项目原文件目录绝对路径。
    """
    project_dir = resolve_project_dir(relative_path)
    if create:
        project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def get_project_tmp_upload_dir(relative_path: str, create: bool = False) -> Path:
    """获取项目解析缓存目录（.md 文件）。

    Args:
        relative_path: 项目原文件相对路径，需以 ``data/project`` 开头，
            例如 ``data/project/2026/07/01/uuid``。
        create: 是否在目录不存在时自动创建，默认 False。

    Returns:
        Path: 项目解析缓存目录绝对路径。
    """
    project_tmp_dir = resolve_project_tmp_dir(relative_path)
    if create:
        project_tmp_dir.mkdir(parents=True, exist_ok=True)
    return project_tmp_dir
