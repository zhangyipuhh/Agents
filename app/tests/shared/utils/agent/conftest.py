# -*- coding:utf-8 -*-
"""
agent 测试目录的本地 conftest

为 langgraph.graph.MessagesState 提供真实的 TypedDict 基类，
避免根 conftest 中 Mock() 导致 AgentState 继承 Mock 而非真实类。

根 conftest（app/tests/conftest.py:393）将 MessagesState 设为 Mock()，
导致 AgentConfig.py 中 `class AgentState(MessagesState):` 生成的 AgentState
成为 Mock 对象而非 TypedDict 子类。本 conftest 在测试收集前覆盖该 Mock，
确保 AgentState / AgentContext 动态子类构建逻辑可正确运行。
"""
import sys
import types
from typing import Any

from typing_extensions import TypedDict


class _MessagesState(TypedDict):
    """模拟 langgraph.graph.MessagesState 的 TypedDict 基类。

    Attributes:
        messages: 消息列表，与 LangGraph MessagesState 保持一致
    """
    messages: list[Any]


# 覆盖根 conftest 中的 Mock，确保 AgentState 能正确继承 TypedDict
_lg_graph = sys.modules.get("langgraph.graph")
if _lg_graph is not None:
    _lg_graph.MessagesState = _MessagesState
else:
    _lg_graph = types.ModuleType("langgraph.graph")
    _lg_graph.MessagesState = _MessagesState
    sys.modules["langgraph.graph"] = _lg_graph

# 清除可能已缓存的模块，确保用真实 MessagesState 重新导入
for _mod in [
    "app.core.agent.AgentConfig",
    "app.core.agent.AgentContext",
    "app.shared.utils.agent.dynamic_schema",
]:
    sys.modules.pop(_mod, None)
