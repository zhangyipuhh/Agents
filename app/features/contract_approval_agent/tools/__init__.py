#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
ApprovalAgent工具模块初始化

导出ApprovalAgent可用的工具函数。

Date: 2026-03-19
Author: 张镒谱
"""

from .ApprovalAgentTools import (
    get_reference_files,
    write_approval_result,
    get_clause_approval_rules,
    extract_all_reference_content,
)

__all__ = [
    "get_reference_files",
    "write_approval_result",
    "get_clause_approval_rules",
    "extract_all_reference_content",
]
