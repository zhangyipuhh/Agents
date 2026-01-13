#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
DeepSeek模型创建模块

本模块提供DeepSeek大语言模型的创建接口。
使用langchain_deepseek库的ChatDeepSeek类来创建模型实例。

支持的配置参数：
- model_name: 模型名称（如 "deepseek-chat"、"deepseek-coder"）
- api_key: DeepSeek API密钥
- temperature: 温度参数，控制输出随机性（0-1）
- base_url: API基础URL（可选，用于自定义API端点）
Date: 2026/1/9 12:07
Author: 张镒谱
"""
from langchain_deepseek import ChatDeepSeek


def create_model(model_name: str, api_key: str, temperature: float = 0, base_url: str = None):
    """
    创建DeepSeek大语言模型实例
    
    此函数根据提供的参数创建并返回一个ChatDeepSeek实例，
    该实例可用于与DeepSeek API进行交互。
    
    Args:
        model_name (str): DeepSeek模型名称，如 "deepseek-chat"、"deepseek-coder"
        api_key (str): DeepSeek API密钥，用于身份验证
        temperature (float, optional): 温度参数，控制输出的随机性和创造性
            - 0: 输出更加确定和一致
            - 1: 输出更加随机和多样化
            默认值为0
        base_url (str, optional): 自定义API基础URL，用于使用代理或私有部署
            默认为None，使用官方API端点
    
    Returns:
        ChatDeepSeek: DeepSeek大语言模型实例，可用于后续的对话和推理任务
    """
    # 创建并返回ChatDeepSeek实例
    # 将所有配置参数传递给ChatDeepSeek构造函数
    return ChatDeepSeek(
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        base_url=base_url
    )
