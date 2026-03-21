#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
大语言模型工厂模块

本模块提供统一的模型创建工厂类，用于管理不同类型的大语言模型。
采用工厂模式设计，支持动态注册新的模型类型。

主要功能：
- 统一管理多种大语言模型的创建过程
- 支持动态注册新的模型类型
- 提供模型类型查询接口
- 封装模型创建的复杂性

支持的模型类型：
- deepseek: DeepSeek大语言模型
- ollama: Ollama本地大语言模型
- openai: OpenAI及其兼容API模型
- 其他自定义模型类型（根据需要动态注册）

Date: 2026/1/9 12:07
Author: 张镒谱
"""
from typing import Optional
from app.core.llmcalls.deepseek import create_model as create_deepseek_model
from app.core.llmcalls.ollama import create_model as create_ollama_model
from app.core.llmcalls.openai import create_model as create_openai_model


class ModelFactory:
    """
    模型工厂类，用于创建不同类型的LLM模型实例
    
    此类采用工厂模式设计，提供统一的模型创建接口。
    通过维护模型类型与创建函数的映射关系，实现模型的动态创建和管理。
    
    类属性：
        _model_creators: 类级别的模型创建器字典，存储模型类型与创建函数的映射
    
    设计模式：
        - 工厂模式：封装对象创建逻辑
        - 注册表模式：支持动态注册新的模型类型
    """
    
    # 类级别的模型创建器字典
    # 存储模型类型（字符串）与对应创建函数的映射关系
    # 使用类变量确保所有实例共享同一个注册表
    _model_creators = {
        'deepseek': create_deepseek_model,
        'ollama': create_ollama_model,
        'openai': create_openai_model,
    }
    
    def __init__(self):
        """
        初始化模型工厂实例
        
        创建实例时，初始化模型创建器字典。
        当前实现中，实例级别的创建器字典与类级别保持一致。
        
        注意：
            实例级别的_model_creators与类级别的_model_creators当前是相同的。
            如果需要实例级别的模型注册，可以在此处进行差异化配置。
        """
        # 初始化实例级别的模型创建器字典
        self._model_creators = {
            'deepseek': create_deepseek_model,
            'ollama': create_ollama_model,
        }
    
    @classmethod
    def create_model(
        cls,
        model_type: str,
        model_name: str,
        api_key: str,
        temperature: float = 0,
        base_url: Optional[str] = None
    ):
        """
        根据模型类型创建对应的LLM模型实例
        
        此类方法根据提供的模型类型，从注册表中查找对应的创建函数，
        并调用该函数创建模型实例。如果模型类型不支持，抛出ValueError异常。
        
        创建流程：
        1. 将模型类型转换为小写，确保大小写不敏感
        2. 检查模型类型是否在注册表中
        3. 如果不支持，抛出ValueError并提示支持的类型
        4. 如果支持，获取对应的创建函数
        5. 调用创建函数并返回模型实例
        
        Args:
            model_type (str): 模型类型，支持 'deepseek'、'ollama'、'openai'
                不区分大小写
            model_name (str): 模型名称，如 "gpt-4"、"deepseek-chat"等
            api_key (str): API密钥，用于身份验证
            temperature (float, optional): 温度参数，控制输出的随机性和创造性
                - 0: 输出更加确定和一致
                - 1: 输出更加随机和多样化
                默认值为0
            base_url (Optional[str], optional): API基础URL，用于自定义API端点
                默认为None，使用各模型的默认端点
        
        Returns:
            LLM模型实例：根据模型类型返回对应的大语言模型实例
        
        Raises:
            ValueError: 当传入不支持的模型类型时抛出，错误信息包含支持的类型列表
        
        Example:
            >>> model = ModelFactory.create_model(
            ...     model_type="openai",
            ...     model_name="gpt-4",
            ...     api_key="sk-xxx",
            ...     temperature=0.7
            ... )
        """
        # 将模型类型转换为小写，确保大小写不敏感
        model_type = model_type.lower()
        
        # 检查模型类型是否在注册表中
        if model_type not in cls._model_creators:
            # 获取支持的模型类型列表，用于错误提示
            supported_types = ', '.join(cls._model_creators.keys())
            # 抛出ValueError异常，提示用户支持的模型类型
            raise ValueError(
                f"不支持的模型类型: {model_type}. "
                f"支持的模型类型: {supported_types}"
            )
        
        # 从注册表中获取对应的模型创建函数
        creator = cls._model_creators[model_type]
        
        # 调用创建函数并返回模型实例
        # 将所有配置参数传递给创建函数
        return creator(
            model_name=model_name,
            api_key=api_key,
            temperature=temperature,
            base_url=base_url
        )
    
    @classmethod
    def register_model_creator(cls, model_type: str, creator_func):
        """
        注册新的模型创建函数
        
        此类方法允许动态注册新的模型类型及其创建函数，
        扩展工厂支持的模型范围，无需修改工厂类代码。
        
        注册流程：
        1. 将模型类型转换为小写，确保大小写不敏感
        2. 将创建函数添加到注册表中
        
        Args:
            model_type (str): 模型类型名称，用于标识新的模型类型
                注册后会转换为小写存储
            creator_func (callable): 模型创建函数，签名为
                create_model(model_name, api_key, temperature, base_url)
                该函数应返回对应的大语言模型实例
        
        Example:
            >>> def create_custom_model(model_name, api_key, temperature, base_url):
            ...     return CustomLLM(model_name=model_name, api_key=api_key)
            >>> ModelFactory.register_model_creator('custom', create_custom_model)
        """
        # 将模型类型转换为小写并注册创建函数
        cls._model_creators[model_type.lower()] = creator_func
    
    @classmethod
    def get_supported_models(cls) -> list:
        """
        获取支持的模型类型列表
        
        此类方法返回当前工厂支持的所有模型类型列表，
        可用于前端展示或用户提示。
        
        Returns:
            list: 支持的模型类型列表，如 ['deepseek', 'ollama', 'openai']
                返回的是列表的副本，避免外部修改内部数据
        
        Example:
            >>> models = ModelFactory.get_supported_models()
            >>> print(models)
            ['deepseek', 'ollama', 'openai']
        """
        # 返回支持的模型类型列表
        # 使用list()创建副本，避免外部修改内部字典
        return list(cls._model_creators.keys())
