# -*- coding:utf-8 -*-
"""巡检分段 JSON 片段合并器(2026-09-16 新增)。

职责:把「一组有序小脚本」各自输出的顶层 JSON object 合并为单个 dict,
合并规则(D1):
    * dict + dict → 递归合并;
    * list + list → 按片段顺序拼接;
    * 其余冲突 → 后者覆盖,键点路径记入 conflicts。

纯函数模块:不连 SSH / 不读写 DB / 不写日志;调用方(server_ops)负责
分段执行、失败过滤与冲突日志。
"""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def merge_inspection_fragments(
    fragments: List[Dict[str, Any]],
) -> Tuple[Dict[str, Any], List[str]]:
    """按顺序深合并巡检 JSON 片段(语义见模块 docstring 与 D1)。

    参数:
        fragments: 各分段 stdout 解析结果,元素必须为顶层 dict。

    返回:
        Tuple[Dict[str, Any], List[str]]: (merged, conflicts)。

    异常:
        无。
    """
    merged: Dict[str, Any] = {}
    conflicts: List[str] = []
    for fragment in fragments:
        _merge_into(merged, fragment, "", conflicts)
    return merged, conflicts


def _merge_into(
    target: Dict[str, Any],
    source: Dict[str, Any],
    path: str,
    conflicts: List[str],
) -> None:
    """把 ``source`` 就地合并进 ``target``(递归辅助)。

    参数:
        target: 合并目标 dict(被原地修改)。
        source: 来源 dict(不修改;list 值拼接进 target 既有 list)。
        path: 当前层级的点路径前缀(供 conflicts 记录)。
        conflicts: 冲突键点路径收集列表(被原地追加)。

    返回:
        None

    异常:
        无。
    """
    for key, value in source.items():
        node_path = f"{path}.{key}" if path else str(key)
        if key not in target:
            target[key] = value
            continue
        existing = target[key]
        if isinstance(existing, dict) and isinstance(value, dict):
            _merge_into(existing, value, node_path, conflicts)
        elif isinstance(existing, list) and isinstance(value, list):
            existing.extend(value)
        else:
            target[key] = value
            conflicts.append(node_path)
