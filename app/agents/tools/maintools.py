#!usr/bin/env python
# -*- coding: utf-8 -*-
from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field



class MainTools:
    def __init__(self):
        pass
    @tool
    @staticmethod    
    def search_database(query: str, limit: int = 10) -> str:
        """Search the customer database for records matching the query.

        Args:
            query: Search terms to look for
            limit: Maximum number of results to return
        """
        return f"Found {limit} results for '{query}'"
    # 定义工具为独立函数，而不是类方法
    @tool
    @staticmethod
    def audit_contract_clause( clausetext: str) -> str:
        """
        审计合同条款。输入合同条款文本，根据知识库规则检查是否合规。
        这里模拟了之前讨论的：匹配规则 -> 检索文档 -> 返回依据的过程。
        args:
            clausetext (str): 合同条款文本 必填
        return:
            str: 检查结果，包含违规项和参考依据
        """
        # 模拟逻辑：实际这里你会调用之前的 ContractCheckTool
        if "90天" in clausetext:
            return "发现违规：【R001】账期限制。公司规定不得超过60天。参考依据：财务指引_v2.pdf"
        elif "50%" in clausetext:
            return "发现违规：【R002】违约金上限。公司规定不得超过30%。参考依据：法务手册.pdf"
        else:
            return "未发现明显违规项。"
    
    @classmethod
    def get_static_methods(cls) -> dict[str, callable]:
        """
           获取类中所有静态方法的字典，键为方法名，值为可调用的方法对象
        """
        static_methods = {}
        # 遍历类的所有属性
        for attr_name in dir(cls):
            # 跳过特殊方法（如__init__、__str__等）
            if attr_name.startswith('__') and attr_name.endswith('__'):
                continue
            
            # 跳过当前类的类方法（get_static_*系列）
            if attr_name.startswith('get_static_'):
                continue
            
            # 获取属性
            attr = getattr(cls, attr_name, None)
            
            # 检查是否是langchain工具（被@tool装饰）
            if isinstance(attr, BaseTool):
                # 对于被@tool装饰的方法，直接添加到结果中
                static_methods[attr_name] = attr
        
        return static_methods
        
    @classmethod
    def get_static_method_names(cls) -> list[str]:
        """获取类中所有静态方法的名称列表"""
        return list(cls.get_static_methods().keys())

    @classmethod
    def get_static_method_list(cls) -> list[BaseTool]:
        """获取类中所有静态方法的列表"""
        return list(cls.get_static_methods().values())


