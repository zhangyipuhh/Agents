#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
app.core.tools.base - 工具基类包

提供可被各业务工具复用的基础执行器，当前包含：
    - BaseFilesystemTool: 文件系统子智能体通用封装

Date: 2026-06-18
Author: AI Assistant
"""

from app.core.tools.base.BaseFilesystemTool import BaseFilesystemTool

__all__ = ["BaseFilesystemTool"]
