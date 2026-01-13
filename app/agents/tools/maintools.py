#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
主智能体工具集模块

本模块定义了主智能体可用的工具集合，包括数据库搜索和合同条款审计等功能。
所有工具方法使用@tool装饰器进行注册，支持通过反射机制动态获取工具列表。
工具类提供静态方法和类方法，便于智能体在工作流中调用。

Date: 2026-01-13
Author: 张镒谱
"""

from langchain.tools import tool
from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class MainTools:
    """
    主智能体工具集类

    提供智能体工作流中使用的各种工具方法，包括数据库搜索、合同审计等功能。
    所有工具方法使用@tool装饰器注册为LangChain工具，支持动态获取和调用。

    Attributes:
        无实例属性，所有方法均为静态方法或类方法
    """

    def __init__(self):
        """
        初始化方法

        当前实现为空，保留用于未来可能的实例属性初始化。
        """
        pass

    @tool
    @staticmethod
    def search_database(query: str, limit: int = 10) -> str:
        """
        数据库搜索工具

        在客户数据库中搜索与查询条件匹配的记录，返回指定数量的结果。
        当前为模拟实现，实际使用时应连接真实数据库执行查询。

        Args:
            query: 搜索关键词，用于匹配数据库记录
            limit: 返回结果的最大数量，默认为10

        Returns:
            str: 搜索结果字符串，包含找到的记录数量和查询条件
        """
        # 模拟数据库查询，实际应替换为真实数据库操作
        return f"Found {limit} results for '{query}'"

    @tool
    @staticmethod
    def audit_contract_clause(clausetext: str) -> str:
        """
        合同条款审计工具

        根据知识库规则检查合同条款文本是否合规，执行规则匹配、文档检索和依据返回的完整流程。
        当前为模拟实现，实际应调用ContractCheckTool执行真实的合规性检查。

        Args:
            clausetext: 合同条款文本，需要进行合规性检查的内容

        Returns:
            str: 检查结果，包含发现的违规项、违规规则编号及参考依据文档
        """
        # 规则检查逻辑：遍历预设的合规性规则，匹配条款中的违规内容
        # 分支1：检查账期限制规则（R001）
        if "90天" in clausetext:
            # 发现账期违规，返回违规规则编号、违规描述及参考依据
            return "发现违规：【R001】账期限制。公司规定不得超过60天。参考依据：财务指引_v2.pdf"
        # 分支2：检查违约金上限规则（R002）
        elif "50%" in clausetext:
            # 发现违约金违规，返回违规规则编号、违规描述及参考依据
            return "发现违规：【R002】违约金上限。公司规定不得超过30%。参考依据：法务手册.pdf"
        # 分支3：未匹配到任何违规规则
        else:
            # 条款通过所有规则检查，返回合规结果
            return "未发现明显违规项。"

    @classmethod
    def get_static_methods(cls) -> dict[str, callable]:
        """
        获取所有工具方法的字典

        通过反射机制遍历类的所有属性，筛选出被@tool装饰的工具方法，
        返回方法名到方法对象的映射字典。用于动态工具注册和调用。

        Returns:
            dict[str, callable]: 工具方法字典，键为方法名，值为可调用的工具对象
        """
        # 初始化空字典，用于存储筛选出的工具方法
        static_methods = {}

        # 遍历类的所有属性名称
        for attr_name in dir(cls):
            # 跳过Python特殊方法（如__init__、__str__等）
            if attr_name.startswith('__') and attr_name.endswith('__'):
                continue

            # 跳过当前类的工具获取方法（get_static_*系列）
            if attr_name.startswith('get_static_'):
                continue

            # 通过反射获取属性对象
            attr = getattr(cls, attr_name, None)

            # 检查属性是否为LangChain工具对象（被@tool装饰）
            if isinstance(attr, BaseTool):
                # 将工具方法添加到结果字典中
                static_methods[attr_name] = attr

        # 返回筛选后的工具方法字典
        return static_methods

    @classmethod
    def get_static_method_names(cls) -> list[str]:
        """
        获取所有工具方法的名称列表

        返回当前类中所有被@tool装饰的工具方法的名称列表，
        便于工具注册和动态调用。

        Returns:
            list[str]: 工具方法名称列表
        """
        # 调用get_static_methods获取工具字典，提取所有键（方法名）并转换为列表
        return list(cls.get_static_methods().keys())

    @classmethod
    def get_static_method_list(cls) -> list[BaseTool]:
        """
        获取所有工具方法的对象列表

        返回当前类中所有被@tool装饰的工具方法的对象列表，
        便于直接传递给智能体工具集。

        Returns:
            list[BaseTool]: 工具方法对象列表
        """
        # 调用get_static_methods获取工具字典，提取所有值（方法对象）并转换为列表
        return list(cls.get_static_methods().values())
