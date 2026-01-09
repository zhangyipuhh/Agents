#!usr/bin/env python
# -*- coding: utf-8 -*-
from typing import Literal
from langgraph.graph import END
from app.agents.states.mainstates import MessagesState

def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """决定是否继续：如果模型调用了工具就去 tool_node，否则结束"""
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"
    return END