#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
项目路径常量模块

统一管理项目运行时所需的绝对路径常量，作为整个项目的"路径真相源"。
所有需要访问 data/、Knowledge/ 等数据目录的模块都应从这里导入，禁止自行
通过 os.path.dirname(__file__) 计算（避免不同文件深度导致 dirname 次数错乱）。

Date: 2026-06-29
Author: AI Assistant
"""

import os

# 项目根目录（app/core/config/paths.py，4 次 dirname 到项目根）
_PROJECT_ROOT = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.dirname(os.path.abspath(__file__))
        )
    )
)

# 知识库数据目录（地图 Agent 等子智能体的检索根目录）
KNOWLEDGE_DIR = os.path.join(_PROJECT_ROOT, "data", "Knowledge")

# 知识库元数据缓存文件（位于 data/tmp/Knowledge/，避免污染真实知识库目录）
METADATA_FILE = os.path.join(_PROJECT_ROOT, "data", "tmp", "Knowledge", "metadata.json")

# 知识库扫描根目录别名（与 KNOWLEDGE_DIR 保持一致，供 query_knowledge 等工具使用）
TMP_DIR = KNOWLEDGE_DIR

# 项目文件夹原文件根目录（2026-06-30 新增）
#   * 与会话上传目录完全隔离的物理路径
#   * 完整结构：<项目根>/data/project/{project_uuid}/
PROJECT_ROOT = os.path.join(_PROJECT_ROOT, "data", "project")

# 项目文件夹解析缓存根目录
#   * 完整结构：<项目根>/data/tmp/project/{project_uuid}/
PROJECT_TMP_ROOT = os.path.join(_PROJECT_ROOT, "data", "tmp", "project")

from pathlib import Path


def resolve_project_dir(relative_path: str) -> Path:
    """
    将相对路径解析为项目目录下的绝对路径。

    内部实现为 ``Path(_PROJECT_ROOT) / relative_path``，例如传入
    ``data/project/2026/07/01/uuid`` 会返回 ``<项目根>/data/project/2026/07/01/uuid``。

    :param relative_path: 相对于项目根的相对路径，使用正斜杠分隔。
    :type relative_path: str
    :return: 解析后的绝对路径。
    :rtype: Path
    :raises ValueError: 当 ``relative_path`` 为空字符串时抛出。
    """
    if not relative_path:
        raise ValueError("relative_path 不能为空字符串")
    return Path(_PROJECT_ROOT) / relative_path


def resolve_project_tmp_dir(relative_path: str) -> Path:
    """
    将项目原文件相对路径映射为项目临时缓存目录下的绝对路径。

    要求 ``relative_path`` 必须以 ``data/project`` 开头，映射规则为去掉前缀后追加到
    ``<项目根>/data/tmp/project``，例如 ``data/project/2026/07/01/uuid`` 会返回
    ``<项目根>/data/tmp/project/2026/07/01/uuid``。

    :param relative_path: 项目原文件相对路径，需以 ``data/project`` 开头。
    :type relative_path: str
    :return: 解析后的临时缓存绝对路径。
    :rtype: Path
    :raises ValueError: 当 ``relative_path`` 为空字符串时抛出。
    """
    if not relative_path:
        raise ValueError("relative_path 不能为空字符串")
    project_rel = Path(relative_path).relative_to("data/project")
    return Path(_PROJECT_ROOT) / "data" / "tmp" / "project" / project_rel
