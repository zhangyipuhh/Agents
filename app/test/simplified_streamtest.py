#!usr/bin/env python
# -*- coding: utf-8 -*-
# 简化版流式测试
from langchain_deepseek import ChatDeepSeek
from langgraph.graph import StateGraph, START, END
from langchain.messages import SystemMessage, AIMessage, HumanMessage
from typing_extensions import TypedDict, Annotated
import operator

# 1. 初始化模型
model = ChatDeepSeek(model_name="deepseek-chat", api_key="sk-d5652bb2e21c43debd1f22fbed6468cf", temperature=0)

# 2. 定义状态
class MessagesState(TypedDict):
    messages: Annotated[list, operator.add]

# 3. 定义模型节点
def llm_call(state: dict):
    print("🤖 [AI思考中]...", end="", flush=True)
    existing_messages = state["messages"]
    
    # 添加系统消息
    system_msg = SystemMessage(content="你是一个专业的合同审批员。")
    existing_messages = [system_msg] + existing_messages
    
    # 流式输出
    for chunk in model.stream(existing_messages):
        if hasattr(chunk, 'content') and chunk.content:
            print(chunk.content, end="", flush=True)
    
    print()
    
    # 获取完整响应
    response = model.invoke(existing_messages)
    return {"messages": [response]}

# 4. 构建图
graph_builder = StateGraph(MessagesState)
graph_builder.add_node("llm_call", llm_call)
graph_builder.add_edge(START, "llm_call")
graph_builder.add_edge("llm_call", END)

# 编译图
graph = graph_builder.compile()

# 5. 运行测试
print("=" * 50)
print("🚀 开始流式测试")
print("=" * 50)

inputs = {
    "messages": [HumanMessage(content="合同条款：甲方应在收到发票后90天内付款。")]
}

# 使用 stream
for event in graph.stream(inputs, stream_mode="updates"):
    for node_name, node_output in event.items():
        print(f"\n📍 节点: {node_name}")
        print("-" * 30)

print("\n" + "=" * 50)
print("✅ 测试完成")
print("=" * 50)