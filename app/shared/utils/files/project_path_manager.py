#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目文件夹路径管理器

负责解析项目文件夹的物理路径（原文件目录 + 解析缓存目录）。
与 session_path_manager 完全独立的物理路径体系，遵循「项目文件不与会话文件混目录」的隔离原则。

目录结构：
    data/project/{project_uuid}/                  # 原文件
    data/tmp/project/{project_uuid}/              # 解析后的 md 缓存

使用方式：
    from app.shared.utils.files.project_path_manager import (
        get_project_upload_dir,
        get_project_tmp_upload_dir,
    )
    upload_dir = get_project_upload_dir(project_uuid, create=True)
    tmp_dir = get_project_tmp_upload_dir(project_uuid, create=True)

Date: 2026-06-30
Author: AI Assistant
"""
from pathlib import Path


def _get_project_root() -> Path:
    """获取项目根目录。

    Returns:
        Path: 本文件向上回溯五级到达项目根目录（app/shared/utils/files/ -> 项目根）。
    """
    return Path(__file__).parent.parent.parent.parent.parent


def get_project_upload_dir(project_uuid: str, create: bool = False) -> Path:
    """获取项目原文件目录。

    Args:
        project_uuid: 项目 UUID（= 创建时的 session_id）。
        create: 是否在目录不存在时自动创建，默认 False。

    Returns:
        Path: 项目原文件目录绝对路径，格式为 <项目根>/data/project/{project_uuid}/。
    """
    if not project_uuid:
        project_uuid = "default"
    project_dir = _get_project_root() / "data" / "project" / project_uuid
    if create:
        project_dir.mkdir(parents=True, exist_ok=True)
    return project_dir


def get_project_tmp_upload_dir(project_uuid: str, create: bool = False) -> Path:
    """获取项目解析缓存目录（.md 文件）。

    Args:
        project_uuid: 项目 UUID（= 创建时的 session_id）。
        create: 是否在目录不存在时自动创建，默认 False。

    Returns:
        Path: 项目解析缓存目录绝对路径，格式为 <项目根>/data/tmp/project/{project_uuid}/。
    """
    if not project_uuid:
        project_uuid = "default"
    project_tmp_dir = _get_project_root() / "data" / "tmp" / "project" / project_uuid
    if create:
        project_tmp_dir.mkdir(parents=True, exist_ok=True)
    return project_tmp_dir
