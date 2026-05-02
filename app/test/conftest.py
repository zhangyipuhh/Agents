#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pytest 配置文件 - 配置 Python 路径
"""
import sys
from pathlib import Path

# 获取项目根目录 (app/test 的父目录的父目录)
project_root = Path(__file__).resolve().parent.parent.parent

# 将项目根目录添加到 sys.path
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))
