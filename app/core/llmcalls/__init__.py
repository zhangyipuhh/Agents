#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
大语言模型调用模块

本模块提供统一的大语言模型创建和调用接口。
支持多种大模型提供商，包括：
- DeepSeek
- Ollama
- OpenAI
- Anthropic

通过工厂模式统一管理不同模型的创建过程，
提供灵活的模型类型扩展机制。
"""
