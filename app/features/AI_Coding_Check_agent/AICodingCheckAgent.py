#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
AICodingCheckAgent - AI辅助编程效果评审Agent类

提供可复用的AI辅助编程效果评审Agent类，支持非流式评审调用。
通过调用大模型对开发者数据进行评审，生成包含5个维度的评估结果。

Date: 2026-04-21
Author: 张镒谱
"""

import json
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from app.core.agent.agent import get_agent
from app.features.AI_Coding_Check_agent.config.AICodingCheckConfig import (
    AICodingCheckConfig,
    AICodingCheckState,
    AICodingCheckContext,
    AICodingCheckExecuteConfig,
    AICodingCheckConfigurableConfig,
)
from app.features.AI_Coding_Check_agent.config.prompts import REVIEW_SYSTEM_PROMPT
from app.features.AI_Coding_Check_agent.config.config import ai_coding_check_settings
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.store.base import BaseStore

# 模块级日志记录器
logger = logging.getLogger(__name__)


def _to_str(value) -> str:
    """
    将任意类型的值转换为字符串

    处理字符串、字符串列表、字典列表等多种输入格式。
    字典会被序列化为JSON格式的字符串。

    Args:
        value: 待转换的值，可以是字符串、列表或字典

    Returns:
        str: 转换后的字符串
    """
    if isinstance(value, list):
        return "\n".join(
            json.dumps(item, ensure_ascii=False) if isinstance(item, dict) else str(item)
            for item in value
        )
    return str(value) if value else ""


class AICodingCheckAgent:
    """
    AI辅助编程效果评审Agent类

    提供可复用的AI辅助编程效果评审功能，支持非流式评审调用。
    通过调用大模型对开发者数据进行评审，生成包含5个维度的评估结果。

    Attributes:
        checkpointer: LangGraph 检查点保存器
        store: LangGraph 内存存储器
        store_id: 存储 ID
        system_prompt: 系统提示词
        max_tokens: 最大 token 数
        max_tokens_before_summary: 触发摘要的 token 阈值
        max_summary_tokens: 摘要最大 token 数
        _agent: 底层 agent 实例
    """

    def __init__(
        self,
        checkpointer: BaseCheckpointSaver = None,
        store: BaseStore = None,
        store_id: Optional[str] = None,
        system_prompt: Optional[str] = None,
        max_tokens: int = 160000,
        max_tokens_before_summary: int = 120000,
        max_summary_tokens: int = 8000,
    ):
        """
        初始化 AICodingCheckAgent 实例

        Args:
            checkpointer: LangGraph 检查点保存器，用于持久化会话状态
            store: LangGraph 内存存储器，用于存储上下文信息
            store_id: 存储 ID，用于区分不同用户的存储空间
            system_prompt: 自定义系统提示词，默认使用评审专用提示词
            max_tokens: 最大 token 数，默认 160000
            max_tokens_before_summary: 触发摘要的 token 阈值，默认 120000
            max_summary_tokens: 摘要最大 token 数，默认 8000
        """
        self.checkpointer = checkpointer
        self.store = store
        self.store_id = store_id
        # 若未指定系统提示词，则使用评审专用的默认提示词
        self.system_prompt = system_prompt or REVIEW_SYSTEM_PROMPT
        # 若未指定最大token数，则从配置中读取
        self.max_tokens = max_tokens or ai_coding_check_settings.model_max_tokens
        self.max_tokens_before_summary = max_tokens_before_summary
        self.max_summary_tokens = max_summary_tokens
        # 延迟初始化标记，首次调用时才创建agent实例
        self._agent = None

    async def _ensure_agent(self):
        """
        确保 agent 已初始化

        采用延迟初始化模式，在第一次调用时创建 agent 实例。
        创建 AICodingCheckConfig 配置实例，并调用 get_agent() 获取 agent 实例。

        Returns:
            Agent: 初始化完成的智能体实例
        """
        # 仅在agent未初始化时执行创建逻辑，避免重复创建
        if self._agent is None:
            # 根据配置参数构建Agent配置实例
            config = AICodingCheckConfig(
                model_type=ai_coding_check_settings.model_type,
                model_name=ai_coding_check_settings.model_name,
                api_key=ai_coding_check_settings.deepseek_api_key,
                base_url=ai_coding_check_settings.model_base_url or None,
                temperature=ai_coding_check_settings.model_temperature,
                max_tokens=self.max_tokens,
                max_tokens_before_summary=self.max_tokens_before_summary,
                max_summary_tokens=self.max_summary_tokens,
                system_prompt=self.system_prompt,
                checkpointer=self.checkpointer,
                store=self.store,
                state_class=AICodingCheckState,
                context_class=AICodingCheckContext,
            )
            # 通过工厂方法获取agent实例并缓存
            self._agent = await get_agent(config)
        return self._agent

    async def review(self, developer_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        评审开发者数据（非流式）

        接收开发者数据，调用 Agent 进行评审，返回完整的评审结果。

        Args:
            developer_data: 开发者数据字典，包含 name、content、code、task 等字段

        Returns:
            Dict[str, Any]: 评审结果字典，包含 dimensions、overall_score、summary 等字段
        """
        # 确保agent已初始化
        agent = await self._ensure_agent()

        # 从开发者数据中提取各字段，缺失字段使用空值兜底
        name = developer_data.get("name", "")
        content = developer_data.get("content", [])
        code = developer_data.get("code", [])
        task = developer_data.get("task", [])

        # 将列表类型的字段拼接为字符串，兼容字符串、字符串列表和字典列表三种输入格式
        content_str = _to_str(content)
        code_str = _to_str(code)
        task_str = _to_str(task)

        # 延迟导入评审提示词模板，避免循环依赖
        from app.features.AI_Coding_Check_agent.config.prompts import REVIEW_PROMPT_TEMPLATE
        # 使用模板格式化用户输入，将开发者数据填入提示词
        user_input = REVIEW_PROMPT_TEMPLATE.format(
            name=name,
            content=content_str,
            code=code_str,
            task_list=task_str,
        )

        # 生成唯一的会话ID，由开发者姓名和时间戳组成，确保每次评审独立
        session_id = f"review_{name}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

        # 构建执行配置，设置会话线程ID和递归限制
        config = AICodingCheckExecuteConfig(
            configurable=AICodingCheckConfigurableConfig(thread_id=session_id),
            recursion_limit=25,
        )

        # 构建输入状态，包含用户消息、开发者数据和评审结果初始值
        state = AICodingCheckState(
            messages=[user_input],
            developer_data=developer_data,
            review_result={},
            error_limit=5,
            limit=25,
        )

        # 构建上下文，关联会话ID和存储ID
        context = AICodingCheckContext(
            session_id=session_id,
            store_id=self.store_id or session_id,
        )

        try:
            # 调用agent执行评审，传入状态、上下文和配置
            result = await agent.invoke(
                input_state=state,
                context=context,
                config=config,
            )

            # 从执行结果中提取消息列表
            messages = result.get("messages", [])
            if messages:
                # 取最后一条消息作为评审响应
                last_message = messages[-1]
                response_text = getattr(last_message, "content", "")
                try:
                    # 清理响应文本，去除 markdown 代码块标记
                    cleaned_text = self._extract_json_from_markdown(response_text)
                    # 尝试将清理后的文本解析为JSON格式的评审结果
                    review_result = json.loads(cleaned_text)
                    # 确保返回结果中包含 name 字段，保持数据结构一致性
                    review_result["name"] = name
                    return review_result
                except (json.JSONDecodeError, TypeError) as e:
                    logger.warning(f"JSON解析失败: {e}, 原始内容: {response_text[:200]}...")
                    # JSON解析失败时，尝试从状态中获取评审结果
                    review_result = result.get("review_result", {})
                    if review_result:
                        # 状态中存在评审结果则直接返回
                        return review_result
                    # 状态中也无评审结果，返回默认结果
                    return self._get_default_review_result(name)

            # 消息列表为空时，返回默认评审结果
            return self._get_default_review_result(name)

        except Exception as e:
            # 捕获agent执行过程中的所有异常，记录日志并返回默认结果
            logger.error(f"评审失败: {e}")
            return self._get_default_review_result(name)

    def _extract_json_from_markdown(self, text) -> str:
        """
        从 markdown 代码块中提取 JSON 内容

        模型返回的内容可能包含 ```json ... ``` 或 ``` ... ``` 的 markdown 标记，
        需要先去除这些标记才能正确解析 JSON。

        Args:
            text: 包含 markdown 代码块的文本，可能是字符串或列表

        Returns:
            str: 清理后的 JSON 字符串
        """
        import re

        # 处理列表类型的情况（某些消息模型的 content 可能是列表）
        if isinstance(text, list):
            # 将列表中的文本内容拼接起来
            text_parts = []
            for item in text:
                if isinstance(item, str):
                    text_parts.append(item)
                elif isinstance(item, dict) and "text" in item:
                    text_parts.append(item["text"])
                elif hasattr(item, "text"):
                    text_parts.append(item.text)
            text = "".join(text_parts)

        # 确保 text 是字符串类型
        if not isinstance(text, str):
            text = str(text) if text else ""

        # 匹配 ```json ... ``` 或 ``` ... ``` 格式的代码块
        pattern = r'```(?:json)?\s*\n?(.*?)\n?```'
        match = re.search(pattern, text, re.DOTALL)

        if match:
            # 提取代码块内的内容
            return match.group(1).strip()

        # 如果没有匹配到代码块，直接返回原文本
        return text.strip()

    def _get_default_review_result(self, name: str = "") -> Dict[str, Any]:
        """
        获取默认评审结果

        当评审过程出现异常或解析失败时，返回此默认结果作为兜底。

        Args:
            name: 开发者姓名

        Returns:
            Dict[str, Any]: 默认评审结果
        """
        return {
            "name": name,
            "review_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "document_quality": {
                "overall_score": 0,
                "completeness": {
                    "score": 0,
                    "has_requirement": False,
                    "has_design": False,
                    "has_implementation": False,
                    "has_problem_solution": False,
                    "has_summary": False,
                    "analysis": "评审失败，无法评估完整性"
                },
                "clarity": {
                    "score": 0,
                    "structure_quality": "",
                    "readability": "",
                    "logic_flow": "",
                    "analysis": "评审失败，无法评估清晰度"
                },
                "technical_accuracy": {
                    "score": 0,
                    "concept_accuracy": "",
                    "scheme_rationality": "",
                    "analysis": "评审失败，无法评估技术正确性"
                },
                "ai_assistance_traces": {
                    "estimated_ai_ratio": 0.0,
                    "typical_traces": [],
                    "integration_quality": "",
                    "analysis": "评审失败，无法评估AI辅助痕迹"
                }
            },
            "ai_adoption_rate": {
                "adoption_rate": 0.0,
                "data_combination_type": "insufficient_data",
                "doc_code_consistency": {
                    "consistency_score": 0.0,
                    "has_document": False,
                    "has_code": False,
                    "function_match": "",
                    "logic_match": "",
                    "interface_match": ""
                },
                "ai_assistance_quality": {
                    "doc_ai_ratio": 0.0,
                    "code_ai_ratio": 0.0,
                    "integration_quality": "",
                    "effectiveness": ""
                },
                "workflow_compliance": {
                    "doc_first": False,
                    "sync_development": False,
                    "authentic_reflection": ""
                },
                "analysis": "评审失败，无法评估AI编程采纳率"
            },
            "doc_task_consistency": {
                "score": 0,
                "has_task_list": False,
                "goal_alignment": "",
                "coverage_completeness": "",
                "scope_control": "",
                "analysis": "评审失败，无法评估文档任务一致性"
            },
            "anti_patterns": {
                "has_issues": False,
                "single_function_repeated_commits": {
                    "detected": False,
                    "function_name": "",
                    "commit_count": 0,
                    "has_substantial_improvement": False,
                    "issue_type": "",
                    "analysis": ""
                },
                "unrelated_to_ai_coding": {
                    "detected": False,
                    "indicators": [],
                    "analysis": ""
                },
                "other_patterns": [],
                "overall_assessment": "评审失败，无法评估反模式"
            },
            "improvement_suggestions": {
                "document_structure": [],
                "content_completeness": [],
                "anti_pattern_correction": [],
                "ai_adoption_optimization": [],
                "ai_usage_optimization": [],
                "priority": "high"
            },
            "overall_score": 0.0,
            "summary": "评审失败，返回默认结果",
            "coach_notes": "评审过程出现异常，请检查输入数据或稍后重试"
        }

    async def get_agent(self):
        """
        获取底层 agent 实例

        Returns:
            Agent: 底层 agent 实例
        """
        return await self._ensure_agent()
