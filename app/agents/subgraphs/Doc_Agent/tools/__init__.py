#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Doc_Agent工具模块初始化

导出DocAgent可用的工具函数。

Date: 2026-03-19
Author: 张镒谱
"""

from .DocTools import (
    get_reference_files,
    get_contract_content,
    write_approval_result,
)

__all__ = [
    "get_reference_files",
    "get_contract_content",
    "write_approval_result",
]
