#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Anthropic模型创建模块

本模块提供Anthropic (Claude)大语言模型的创建接口。
使用langchain_anthropic库的ChatAnthropic类来创建模型实例。

支持的配置参数：
- model_name: 模型名称（如 "claude-3-5-sonnet-20241022"、"claude-3-opus-20240229"）
- api_key: Anthropic API密钥
- temperature: 温度参数，控制输出随机性（0-1）
- max_tokens: 最大生成令牌数
- timeout: 请求超时时间
- max_retries: 最大重试次数
"""
from langchain_anthropic import ChatAnthropic


def create_model(
    model_name: str, api_key: str, temperature: float = 0, base_url: str = None,
):
    """
    创建Anthropic大语言模型实例
    
    此函数根据提供的参数创建并返回一个ChatAnthropic实例，
    该实例可用于与Anthropic API进行交互。
    
    Args:
        model_name (str): Anthropic模型名称，如 "claude-3-5-sonnet-20241022"、"claude-3-opus-20240229"
        api_key (str): Anthropic API密钥，用于身份验证
        temperature (float, optional): 温度参数，控制输出的随机性和创造性
            - 0: 输出更加确定和一致
            - 1: 输出更加随机和多样化
            默认值为0
        max_tokens (int, optional): 模型生成的最大令牌数
            默认为None，由模型自动决定
        
    
    Returns:
        ChatAnthropic: Anthropic大语言模型实例，可用于后续的对话和推理任务
    """

    
    return ChatAnthropic(        
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        base_url=base_url
    )
