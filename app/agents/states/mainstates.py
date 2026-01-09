#!usr/bin/env python
# -*- coding: utf-8 -*-
from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator
# 主智能体的状态定义
class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    # 可以加一个字段来记录检查了多少条规则
    checked_rules_count: int 