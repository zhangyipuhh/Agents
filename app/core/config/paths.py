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

# 定时任务运行日志根目录（2026-07-15 新增）
#   * 完整结构：<项目根>/data/logs/Task/{任务名 slug}/{YYYYMMDD_HHMMSS}_{run_id}.log
#   * 文件扩展名仍为 .log，但内容为 Markdown
TASK_LOG_DIR = os.path.join(_PROJECT_ROOT, "data", "logs", "Task")

# 定时任务附件存储根目录（用于定时脚本生成的邮件附件）
#   * 完整结构：<项目根>/data/attachments/Task/{任务名 slug}/{YYYYMMDD_HHMMSS}_{run_id}.docx
#   * 仅记录路径约定，物理写入由调用方负责创建目录（mkdir(parents=True, exist_ok=True)）
TASK_ATTACHMENT_DIR = os.path.join(_PROJECT_ROOT, "data", "attachments", "Task")

# 定时任务附件默认文件扩展名（2026-07-22 新增）
#   * 与 TASK_ATTACHMENT_DIR 配合使用，由 resolve_task_attachment_path 默认拼接 .docx
#   * 历史报告均以 docx 生成；保留常量以便未来扩展（如 pdf）一处改全局生效
TASK_ATTACHMENT_SUFFIX = "docx"

# 脚本扫描根目录（2026-07-16 新增）
#   * ScriptDiscoveryService 扫描此目录下所有 .py 文件
#   * 通过 @register_script 装饰器注册到全局 registry
#   * 完整结构：<项目根>/app/scripts/
SCRIPTS_DIR = os.path.join(_PROJECT_ROOT, "app", "scripts")

# DevOps 服务器配置目录（2026-07-15 新增）
#   * SSH 远程服务器配置（业务名/IP/端口/用户名/密码/类型/黑白名单）的 YAML 文件目录
#   * 完整结构：<项目根>/data/devops/servers.yaml（默认文件名）
DEVOPS_SERVER_CONFIG_PATH = os.path.join(_PROJECT_ROOT, "data", "devops", "servers.yaml")
# DevOps 服务器配置目录（用于存放扫描时找不到 config.yaml 的默认目录）
DEVOPS_SERVER_CONFIG_DIR = os.path.join(_PROJECT_ROOT, "data", "devops")

from pathlib import Path
import re as _re


# 用于把任务名安全化到目录名的正则：非字母数字下划线连字符全部替换为 _
_TASK_NAME_SLUG_RE = _re.compile(r"[^\w\-]+", flags=_re.UNICODE)


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


def slugify_task_name(name: str) -> str:
    """
    把定时任务名安全化到文件系统目录名片段。

    规则：
      - 非字母数字、下划线、连字符的字符替换为 ``_``；
      - 连续下划线折叠为单个；
      - 去掉首尾下划线；
      - 空字符串或纯非法字符时返回 ``"task"``，避免生成隐藏目录或写穿路径。

    :param name: 原始任务名。
    :type name: str
    :return: 安全化后的目录名片段。
    :rtype: str
    """
    if not name:
        return "task"
    cleaned = _TASK_NAME_SLUG_RE.sub("_", name.strip())
    cleaned = _re.sub(r"_+", "_", cleaned).strip("_")
    return cleaned or "task"


def resolve_task_log_path(
    name: str,
    run_id: int,
    when: "datetime",
) -> Path:
    """
    生成定时任务运行日志文件路径（不创建文件，仅返回路径对象）。

    完整结构：``<项目根>/data/logs/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.log``。

    :param name: 任务名，会经过 :func:`slugify_task_name` 安全化。
    :type name: str
    :param run_id: 执行记录 ID（来自 ``agent_task_runs.id``）。
    :type run_id: int
    :param when: 执行开始时间，用于文件名时间戳。
    :type when: datetime
    :return: 日志文件的绝对路径（父目录可能尚未创建，调用方负责 ``mkdir(parents=True, exist_ok=True)``）。
    :rtype: Path
    :raises ValueError: 当 ``run_id`` 非正整数或 ``when`` 为 ``None`` 时抛出。
    """
    if run_id is None or int(run_id) <= 0:
        raise ValueError("run_id must be a positive integer")
    if when is None:
        raise ValueError("when must be a datetime instance")
    slug = slugify_task_name(name)
    timestamp = when.strftime("%Y%m%d_%H%M%S")
    file_name = f"{timestamp}_{int(run_id)}.log"
    return Path(TASK_LOG_DIR) / slug / file_name


def resolve_task_attachment_path(
    name: str,
    run_id: int,
    when: "datetime",
    *,
    suffix: str = TASK_ATTACHMENT_SUFFIX,
) -> Path:
    """
    生成定时任务附件文件路径（不创建文件，仅返回路径对象）。

    完整结构：``<项目根>/data/attachments/Task/{slug}/{YYYYMMDD_HHMMSS}_{run_id}.{suffix}``。
    与 :func:`resolve_task_log_path` 路径模板一致，便于日志与附件归档对齐。

    :param name: 任务名，会经过 :func:`slugify_task_name` 安全化。
    :type name: str
    :param run_id: 执行记录 ID（来自 ``agent_task_runs.id``）。
    :type run_id: int
    :param when: 执行开始时间，用于文件名时间戳。
    :type when: datetime
    :param suffix: 文件扩展名（不含 ``.``），默认 ``"docx"``。
    :type suffix: str
    :return: 附件文件的绝对路径（父目录可能尚未创建）。
    :rtype: Path
    :raises ValueError: 当 ``run_id`` 非正整数、``when`` 为 ``None`` 或 ``suffix`` 为空时抛出。
    """
    if run_id is None or int(run_id) <= 0:
        raise ValueError("run_id must be a positive integer")
    if when is None:
        raise ValueError("when must be a datetime instance")
    if not suffix:
        raise ValueError("suffix must be non-empty")
    slug = slugify_task_name(name)
    timestamp = when.strftime("%Y%m%d_%H%M%S")
    file_name = f"{timestamp}_{int(run_id)}.{suffix}"
    return Path(TASK_ATTACHMENT_DIR) / slug / file_name


def resolve_tmp_mirror_path(original_path: str | Path) -> Path | None:
    """
    将 data/ 下的原文件路径映射为 data/tmp/... 下的 .md 镜像路径。

    用于支持子智能体（explore / query_knowledge / sandbox）读取文档类文件的 .md 缓存。
    原路径必须位于 ``<项目根>/data/`` 下；否则返回 ``None``。
    返回路径的扩展名统一替换为 ``.md``。

    例如：
        - ``data/upload/2026/07/07/session-abc/report.docx``
          → ``data/tmp/upload/2026/07/07/session-abc/report.md``
        - ``data/project/2026/07/07/uuid/readme.md``
          → ``data/tmp/project/2026/07/07/uuid/readme.md``

    :param original_path: 原文件路径（字符串或 Path）。
    :type original_path: str | Path
    :return: 对应的 .md 镜像路径；若原路径不在 data/ 下则返回 None。
    :rtype: Path | None
    """
    original_path = Path(original_path)
    data_root = Path(_PROJECT_ROOT) / "data"
    try:
        rel = original_path.resolve().relative_to(data_root.resolve())
    except ValueError:
        return None
    return (Path(_PROJECT_ROOT) / "data" / "tmp" / rel).with_suffix(".md")


def resolve_devops_server_config_path(path: str | Path) -> Path:
    """
    将 DevOps servers.yaml 路径解析为绝对路径。

    规则：
        - 已经是绝对路径（任意平台）→ 原样返回；
        - 相对路径（包含 ``data/devops/...`` 形式）→ 相对项目根解析；
        - 空字符串抛 ``ValueError``。

    :param path: 配置路径（绝对 / 相对项目根）。
    :type path: str | Path
    :return: 解析后的绝对路径。
    :rtype: Path
    :raises ValueError: 当 ``path`` 为空字符串时抛出。
    """
    if path is None or str(path) == "":
        raise ValueError("path 不能为空字符串")
    p = Path(str(path))
    if p.is_absolute():
        return p
    return Path(_PROJECT_ROOT) / p
