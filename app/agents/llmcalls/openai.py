#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
OpenAI模型创建模块

本模块提供OpenAI大语言模型的创建接口。
使用langchain_openai库的ChatOpenAI类来创建模型实例。

支持OpenAI及其兼容的API服务（如Azure OpenAI、各种第三方API）。
支持的配置参数：
- model_name: 模型名称（如 "gpt-4"、"gpt-3.5-turbo"、"gpt-4-turbo"）
- api_key: OpenAI API密钥
- temperature: 温度参数，控制输出随机性（0-1）
- base_url: API基础URL（可选，用于兼容API或Azure OpenAI）
"""
from langchain_openai import ChatOpenAI


def create_model(model_name: str, api_key: str, temperature: float = 0, base_url: str = None):
    """
    创建OpenAI大语言模型实例
    
    此函数根据提供的参数创建并返回一个ChatOpenAI实例，
    该实例可用于与OpenAI API或兼容API进行交互。
    
    Args:
        model_name (str): OpenAI模型名称，如 "gpt-4"、"gpt-3.5-turbo"、"gpt-4-turbo"
        api_key (str): OpenAI API密钥，用于身份验证
        temperature (float, optional): 温度参数，控制输出的随机性和创造性
            - 0: 输出更加确定和一致
            - 1: 输出更加随机和多样化
            默认值为0
        base_url (str, optional): 自定义API基础URL，用于使用兼容API或Azure OpenAI
            默认为None，使用OpenAI官方API端点
    
    Returns:
        ChatOpenAI: OpenAI大语言模型实例，可用于后续的对话和推理任务
    """
    # 创建并返回ChatOpenAI实例
    # 将所有配置参数传递给ChatOpenAI构造函数
    return ChatOpenAI(
        model_name=model_name,
        api_key=api_key,
        temperature=temperature,
        base_url=base_url
    )
