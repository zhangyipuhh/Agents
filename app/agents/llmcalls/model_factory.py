#!usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Optional
from app.agents.llmcalls.deepseek import create_model as create_deepseek_model
from app.agents.llmcalls.ollama import create_model as create_ollama_model 

class ModelFactory:
    """模型工厂类，用于创建不同类型的LLM模型实例"""
    
    _model_creators = {
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
        
        参数:
            model_type: 模型类型，支持 'deepseek' 或 'ollama'
            model_name: 模型名称
            api_key: API密钥
            temperature: 温度参数，控制输出的随机性，默认为0
            base_url: 基础URL，可选
            
        返回:
            LLM模型实例
            
        异常:
            ValueError: 当传入不支持的模型类型时抛出
        """
        model_type = model_type.lower()
        
        if model_type not in cls._model_creators:
            supported_types = ', '.join(cls._model_creators.keys())
            raise ValueError(
                f"不支持的模型类型: {model_type}. "
                f"支持的模型类型: {supported_types}"
            )
        
        creator = cls._model_creators[model_type]
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
        
        参数:
            model_type: 模型类型名称
            creator_func: 模型创建函数，签名为 create_model(model_name, api_key, temperature, base_url)
        """
        cls._model_creators[model_type.lower()] = creator_func
    
    @classmethod
    def get_supported_models(cls) -> list:
        """
        获取支持的模型类型列表
        
        返回:
            支持的模型类型列表
        """
        return list(cls._model_creators.keys())
