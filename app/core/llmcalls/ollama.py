#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Ollama模型创建模块

本模块提供Ollama大语言模型的创建接口。
使用langchain_ollama库的ChatOllama类来创建模型实例。

Ollama是一个本地运行大语言模型的工具，支持多种开源模型。
支持的配置参数：
- model_name: 模型名称（如 "llama2"、"mistral"、"codellama"）
- api_key: API密钥（可选，某些Ollama部署可能需要）
- temperature: 温度参数，控制输出随机性（0-1）
- base_url: Ollama服务基础URL（默认为 "http://localhost:11434"）
Date: 2026/1/9 12:07
Author: 张镒谱
"""
from langchain_ollama import ChatOllama


def create_model(model_name: str, api_key: str, temperature: float = 0, base_url: str = None, reasoning: bool = True, timeout: int = 120):
    """
    创建Ollama大语言模型实例
    
    此函数根据提供的参数创建并返回一个ChatOllama实例，
    该实例可用于与本地运行的Ollama服务进行交互。
    
    Args:
        model_name (str): Ollama模型名称，如 "llama2"、"mistral"、"codellama"
        api_key (str): API密钥，某些Ollama部署可能需要认证
            默认为None
        temperature (float, optional): 温度参数，控制输出的随机性和创造性
            - 0: 输出更加确定和一致
            - 1: 输出更加随机和多样化
            默认值为0
        base_url (str, optional): Ollama服务的基础URL
            默认为None，使用Ollama默认地址 "http://localhost:11434"
        reasoning (bool, optional): 是否启用推理功能
            默认值为True
        timeout (int, optional): 请求超时时间（秒）
            默认值为120
    
    Returns:
        ChatOllama: Ollama大语言模型实例，可用于后续的对话和推理任务
    """
    return ChatOllama(
        model=model_name,
        api_key=api_key,
        temperature=temperature,
        base_url=base_url,
        reasoning=reasoning,
        timeout=timeout,
        num_ctx=20000
    )
