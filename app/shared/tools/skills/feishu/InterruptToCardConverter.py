#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
InterruptToCardConverter - LangGraph interrupt 请求 → 飞书带按钮的交互式卡片

职责：
    - 把 ``hitl_check_node`` 触发的 LangGraph interrupt 请求转为带按钮的飞书卡片
    - 用户点击按钮 → 飞书回调 ``card.action.trigger`` → 解析出 ``qid`` / ``oid`` →
      构造 ``Command(resume={"answers": [...]})`` 续跑 agent
    - 飞书单卡片按钮数有限（一般 ≤10），单题最多 5 个选项 + "其他"按钮

输入格式（来自 ``app/routers/_stream_helper.py::_extract_interrupt_requests``）::

    {
        "action": "ask_user_question",
        "questions": [
            {
                "question": "你想用哪种方案？",
                "options": [{"label": "A 方案"}, {"label": "B 方案"}],
                "multiSelect": false,
            }
        ],
    }

按钮 ``value`` 字段携带的契约（飞书回调时由 ``FeishuWebSocketService._on_card_action`` 解析）::

    {
        "action": "hitl_answer",
        "qid": <问题索引 int>,
        "oid": <选项索引 int>,
        "session_id": <LangGraph thread_id>,
        "chat_id": <飞书 chat_id>,
    }

依据：[飞书消息卡片文档](https://open.feishu.cn/document/develop-a-card-interactive-bot/card-building-steps)
"""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

# 单题最多按钮数（含"其他"按钮）；飞书单卡片按钮数有限（≤10）
_MAX_OPTIONS_PER_QUESTION = 5
# 按钮 value 固定 action 字段，便于回调路由
_ACTION_HITL_ANSWER = "hitl_answer"
# multiSelect 时按钮的 type（HITL 暂时只做单选，故 _LEGACY_MULTISELECT_TYPE 占位）
_BUTTON_TYPE_PRIMARY = "primary"
_BUTTON_TYPE_DEFAULT = "default"


class InterruptToCardConverter:
    """LangGraph interrupt → 飞书带按钮交互式卡片转换器。"""

    # ------------------------------------------------------------------ #
    # 公开 API                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def to_interactive_card(
        interrupt_request: Dict[str, Any],
        session_id: str,
        chat_id: str,
        header_title: str = "❓ 需要确认",
    ) -> Dict[str, Any]:
        """把 interrupt 请求转为飞书带按钮的交互式卡片 JSON。

        Args:
            interrupt_request: LangGraph interrupt 请求 dict，格式见模块 docstring
            session_id: LangGraph thread_id，用于 resume 时恢复 checkpoint
            chat_id: 飞书 chat_id，最终回复的目标 chat
            header_title: 卡片头部标题

        Returns:
            dict: 飞书卡片 JSON（schema 2.0），结构形如::

                {
                    "schema": "2.0",
                    "config": {"wide_screen_mode": True},
                    "header": {
                        "template": "orange",
                        "title": {"tag": "plain_text", "content": "❓ 需要确认"},
                    },
                    "body": {
                        "elements": [
                            {"tag": "markdown", "content": "**Q1:** 你想用哪种方案？\n> 单选"},
                            {"tag": "hr"},
                            {"tag": "action", "actions": [{"tag": "button", ...}, ...]},
                            ...
                        ],
                    },
                }
        """
        questions = InterruptToCardConverter._extract_questions(interrupt_request)
        if not questions:
            # 无 questions：退化为普通 markdown 提示卡片
            return {
                "schema": "2.0",
                "config": {"wide_screen_mode": True},
                "header": {
                    "template": "orange",
                    "title": {"tag": "plain_text", "content": header_title},
                },
                "body": {
                    "elements": [
                        {
                            "tag": "markdown",
                            "content": "（暂无可回答的问题）",
                        }
                    ],
                },
            }

        elements: List[Dict[str, Any]] = []
        for qid, q in enumerate(questions):
            question_text = str(q.get("question") or "")
            multi_select = bool(q.get("multiSelect"))
            options = q.get("options") or []
            select_label = "多选" if multi_select else "单选"

            # 题目块
            elements.append(
                {
                    "tag": "markdown",
                    "content": f"**Q{qid + 1}:** {question_text}\n> {select_label}",
                }
            )

            # 按钮组
            actions: List[Dict[str, Any]] = []
            truncated = False
            for oid, opt in enumerate(options):
                if oid >= _MAX_OPTIONS_PER_QUESTION:
                    truncated = True
                    break
                label = str(opt.get("label") or opt.get("text") or f"选项 {oid + 1}")
                btn_type = (
                    _BUTTON_TYPE_PRIMARY if oid == 0 else _BUTTON_TYPE_DEFAULT
                )
                actions.append(
                    {
                        "tag": "button",
                        "type": btn_type,
                        "text": {"tag": "plain_text", "content": label},
                        "value": {
                            "action": _ACTION_HITL_ANSWER,
                            "qid": qid,
                            "oid": oid,
                            "session_id": session_id,
                            "chat_id": chat_id,
                        },
                    }
                )
            # 补充"其他"按钮（点击后用户自由输入）
            actions.append(
                {
                    "tag": "button",
                    "type": _BUTTON_TYPE_DEFAULT,
                    "text": {"tag": "plain_text", "content": "其他（自由输入）"},
                    "value": {
                        "action": _ACTION_HITL_ANSWER,
                        "qid": qid,
                        "oid": -1,
                        "session_id": session_id,
                        "chat_id": chat_id,
                        "is_other": True,
                    },
                }
            )
            elements.append({"tag": "action", "actions": actions})

            if truncated:
                elements.append(
                    {
                        "tag": "markdown",
                        "content": "（选项较多，已省略；可回复文本自由输入）",
                    }
                )

            # 问题间分隔线（除最后一个）
            if qid < len(questions) - 1:
                elements.append({"tag": "hr"})

        return {
            "schema": "2.0",
            "config": {"wide_screen_mode": True},
            "header": {
                "template": "orange",
                "title": {"tag": "plain_text", "content": header_title},
            },
            "body": {"elements": elements},
        }

    # ------------------------------------------------------------------ #
    # 辅助方法                                                            #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _extract_questions(interrupt_request: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """从 interrupt_request 中提取 ``questions`` 列表。

        支持两种入参形态：
            1) ``{"action": "ask_user_question", "questions": [...]}``
            2) ``[{"question": ..., "options": [...]} ...]``（直接传入）

        Args:
            interrupt_request: 原始 interrupt 请求

        Returns:
            list[dict]: 问题列表
        """
        if not interrupt_request:
            return []
        if isinstance(interrupt_request, list):
            # 直接传入了 question 列表
            return [q for q in interrupt_request if isinstance(q, dict)]
        if isinstance(interrupt_request, dict):
            questions = interrupt_request.get("questions")
            if isinstance(questions, list):
                return [q for q in questions if isinstance(q, dict)]
        return []


def parse_card_action_value(raw_value: Any) -> Optional[Dict[str, Any]]:
    """把飞书卡片回调 ``action.value`` 解析为 dict。

    飞书 SDK 在回调时通常把 ``value`` 字段反序列化为 dict，但也可能仍以 JSON 字符串形式给出。

    Args:
        raw_value: 飞书回调的 value 字段

    Returns:
        dict: 解析后的 dict；解析失败返回 None
    """
    if raw_value is None:
        return None
    if isinstance(raw_value, dict):
        return raw_value
    if isinstance(raw_value, str):
        try:
            parsed = json.loads(raw_value)
            return parsed if isinstance(parsed, dict) else None
        except Exception:  # noqa: BLE001
            return None
    return None