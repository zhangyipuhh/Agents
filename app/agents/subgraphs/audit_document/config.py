#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
配置模块

本模块定义了合同审批智能体的配置信息，包括子图类型枚举等。

Date: 2026/3/4
Author: 张镒谱
"""
from enum import Enum


class DocumentType(Enum):
    """
    文档类型枚举
    """
    CONTRACT = "contract"  # 合同
    TRANSACTION = "transaction"  # 成交确认书
    MEETING = "meeting"  # 会议纪要


class Config:
    """
    智能体配置类
    """
    # Ollama 模型配置
    OLLAMA_MODEL = "qwen3-vl:30b"  # 用于图片识别的模型
    OLLAMA_BASE_URL = "http://192.168.1.107:11434"  # Ollama 服务地址
    OLLAMA_TEMPERATURE = 0.1  # 生成温度
    
    # 文档解析配置
    PDF_TO_IMAGE_DPI = 300  # PDF 转图片的 DPI
    PDF_TO_IMAGE_FORMAT = "jpg"  # PDF 转图片的格式
    
    # 滚动窗口配置
    SLIDING_WINDOW_SIZE = 2  # 滚动窗口大小
    SLIDING_WINDOW_STEP = 1  # 滚动窗口步长
