#!usr/bin/env python
# -*- coding: utf-8 -*-

# --- Step 1: 定义工具和模型 ---
from langchain.tools import tool
from langchain.chat_models import init_chat_model
# 注意：这里我用 Ollama 接入，替换掉你的 Claude 代码
from langchain_deepseek import ChatDeepSeek
from typing import Literal
from langgraph.graph import StateGraph, START, END
import time

# 1. 初始化模型 (使用 DeepSeek)
# 如果你有 DeepSeek Key，当然可以继续用 init_chat_model("deepseek-chat", temperature=0)
# model = init_chat_model("deepseek-chat", temperature=0)
model = ChatDeepSeek(model_name="deepseek-chat", api_key="sk-d5652bb2e21c43debd1f22fbed6468cf", temperature=0)

# 2. 定义你的那个“通用 MCP 工具” (简化版代码模拟)
@tool
def audit_contract_clause(clause_text: str) -> str:
    """
    审计合同条款。输入合同条款文本，根据知识库规则检查是否合规。
    这里模拟了之前讨论的：匹配规则 -> 检索文档 -> 返回依据的过程。
    """
    # 模拟逻辑：实际这里你会调用之前的 ContractCheckTool
    if "90天" in clause_text:
        return "发现违规：【R001】账期限制。公司规定不得超过60天。参考依据：财务指引_v2.pdf"
    elif "50%" in clause_text:
        return "发现违规：【R002】违约金上限。公司规定不得超过30%。参考依据：法务手册.pdf"
    else:
        return "未发现明显违规项。"

# 3. 将工具绑定到模型
tools = [audit_contract_clause]
# 这一步很重要，让模型知道它手里有这个工具
model_with_tools = model.bind_tools(tools)

# --- Step 2: 定义状态 (保持不变) ---
from langchain.messages import AnyMessage
from typing_extensions import TypedDict, Annotated
import operator

class MessagesState(TypedDict):
    messages: Annotated[list[AnyMessage], operator.add]
    # 可以加一个字段来记录检查了多少条规则
    checked_rules_count: int 

# --- Step 3: 定义模型节点 (逐字流式输出) ---
from langchain.messages import SystemMessage, AIMessage

def llm_call(state: dict):
    """LLM 决定是否调用审批工具（一次性输出）"""
    
    # 获取当前的消息列表
    existing_messages = state["messages"]
    
    # 检查是否需要添加系统提示词
    # 只有在消息列表中没有系统消息时才添加
    has_system_message = any(msg.type == "system" for msg in existing_messages)
    if not has_system_message:
        system_msg = SystemMessage(content="你是一个专业的合同审批员。对于用户输入的每一条合同条款，你都必须使用 audit_contract_clause 工具进行核查，不能凭空回答。")
        # 将系统消息插入到最前面
        existing_messages = [system_msg] + existing_messages
    
    # 使用 invoke 一次性输出
    print("🤖 [AI思考中]...", flush=True)
    
    response = model_with_tools.invoke(existing_messages)
    
    if hasattr(response, 'content') and response.content:
        print(response.content, flush=True)
    
    if hasattr(response, 'tool_calls') and response.tool_calls:
        print("\n🔧 [准备调用工具]", flush=True)
        for tc in response.tool_calls:
            print(f"   工具: {tc['name']}, 参数: {tc['args']}", flush=True)
    
    print()  # 换行
    
    # 过滤掉无效的工具调用
    valid_tool_calls = []
    if hasattr(response, 'tool_calls') and response.tool_calls:
        for tc in response.tool_calls:
            # 检查工具调用是否有效
            if tc.get("name") and tc.get("id"):  # 确保有 name 和 id
                valid_tool_calls.append(tc)
    
    print(f"DEBUG: 有效工具调用数量: {len(valid_tool_calls)}")
    
    # 构造 AIMessage
    if valid_tool_calls:
        # 如果有有效的工具调用，创建包含 tool_calls 的消息
        response = AIMessage(
            content=response.content if hasattr(response, 'content') else "",
            tool_calls=valid_tool_calls
        )
    else:
        # 如果没有工具调用，创建普通消息
        response = AIMessage(content=response.content if hasattr(response, 'content') else "")
    
    return {
        "messages": [response],
        "checked_rules_count": state.get("checked_rules_count", 0) + 1
    }

# --- Step 4: 定义工具节点为子流程 (子图) ---
from langchain.messages import ToolMessage, AIMessage
from typing import Annotated, List
from typing_extensions import TypedDict
import operator

# 定义子图的状态
class ToolSubgraphState(TypedDict):
    messages: Annotated[List[AnyMessage], operator.add]
    current_rule_index: int
    total_rules: int
    tool_call_id: str
    clause_text: str
    audit_results: List[str]

# 子图的节点1：检查单个规则
def check_single_rule(state: ToolSubgraphState):
    """检查单个规则"""
    rules = [
        ("R001", "账期限制", "90天", "公司规定不得超过60天", "财务指引_v2.pdf"),
        ("R002", "违约金上限", "50%", "公司规定不得超过30%", "法务手册.pdf"),
        ("R003", "付款方式", "现金", "必须通过银行转账", "财务指引_v2.pdf"),
    ]
    
    current_index = state["current_rule_index"]
    rule_code, rule_name, keyword, violation_desc, reference = rules[current_index]
    
    clause_text = state["clause_text"]
    
    if keyword in clause_text:
        result = f"发现违规：【{rule_code}】{rule_name}。{violation_desc}。参考依据：{reference}"
    else:
        result = f"通过：【{rule_code}】{rule_name}检查通过。"
    
    # 输出检查结果（真正的流式输出）
    print(f"  ✅ 正在检查规则 {rule_code}: {rule_name}...", flush=True)
    print(f"  ✅ {result}", flush=True)
    
    return {
        "current_rule_index": current_index + 1,
        "audit_results": state["audit_results"] + [result],
        "tool_call_id": state["tool_call_id"],
        "clause_text": state["clause_text"],
        "total_rules": state["total_rules"],
        "messages": []  # 不在这里添加消息，只在 subgraph_end 添加
    }

# 子图的节点2：判断是否继续检查
def should_continue_check(state: ToolSubgraphState) -> Literal["check_single_rule", "subgraph_end"]:
    """判断是否继续检查下一个规则"""
    if state["current_rule_index"] < state["total_rules"]:
        return "check_single_rule"
    return "subgraph_end"

# 子图的节点3：汇总结果
def subgraph_end(state: ToolSubgraphState):
    """汇总所有检查结果"""
    combined_result = "\n".join(state["audit_results"])
    
    # 输出汇总结果
    print(f"\n  📊 [汇总结果]: {combined_result}", flush=True)
    
    return {
        "messages": [ToolMessage(content=combined_result, tool_call_id=state["tool_call_id"])],
        "audit_results": state["audit_results"],
        "current_rule_index": state["current_rule_index"],
        "tool_call_id": state["tool_call_id"],
        "clause_text": state["clause_text"],
        "total_rules": state["total_rules"]
    }

# 构建子图
tool_subgraph = StateGraph[ToolSubgraphState, None, ToolSubgraphState, ToolSubgraphState](ToolSubgraphState)
tool_subgraph.add_node("check_single_rule", check_single_rule)
tool_subgraph.add_node("subgraph_end", subgraph_end)

tool_subgraph.add_edge(START, "check_single_rule")
tool_subgraph.add_conditional_edges(
    "check_single_rule",
    should_continue_check,
    ["check_single_rule", "subgraph_end"]
)
tool_subgraph.add_edge("subgraph_end", END)

# 编译子图
tool_subgraph_compiled = tool_subgraph.compile()

# 定义主图的 tool_node，它调用子图
def tool_node(state: dict):
    """执行工具调用（调用子图）"""
    result = []
    last_message = state["messages"][-1]
    
    # 过滤掉无效的工具调用
    valid_tool_calls = []
    for tc in last_message.tool_calls:
        # 检查工具调用是否有效
        if tc["id"] and tc["name"]:  # 确保有 id 和 name
            valid_tool_calls.append(tc)
    
    print(f"DEBUG: 有效工具调用数量: {len(valid_tool_calls)}")
    
    for tool_call in valid_tool_calls:
        print(f"DEBUG: 处理工具调用: {tool_call['name']}, id: {tool_call['id']}")
        
        # 初始化子图状态
        subgraph_inputs = {
            "messages": [],
            "current_rule_index": 0,
            "total_rules": 3,
            "tool_call_id": tool_call["id"],
            "clause_text": tool_call["args"].get("clause_text", ""),
            "audit_results": []
        }
        
        print("\n🔧 [工具执行中]...", flush=True)
        
        # 运行子图并获取最终结果
        final_state = tool_subgraph_compiled.invoke(subgraph_inputs)
        
        # 获取子图返回的 ToolMessage
        if "messages" in final_state and final_state["messages"]:
            # 将子图返回的消息添加到结果中
            result.extend(final_state["messages"])
    
    return {"messages": result}

# --- Step 5: 定义路由逻辑 (保持不变) ---


def should_continue(state: MessagesState) -> Literal["tool_node", END]:
    """决定是否继续：如果模型调用了工具就去 tool_node，否则结束"""
    messages = state["messages"]
    last_message = messages[-1]

    if last_message.tool_calls:
        return "tool_node"
    return END

# --- Step 6: 构建并运行 Agent ---
agent_builder = StateGraph[MessagesState, None, MessagesState, MessagesState](MessagesState)

agent_builder.add_node("llm_call", llm_call)
agent_builder.add_node("tool_node", tool_node)

agent_builder.add_edge(START, "llm_call")
agent_builder.add_conditional_edges(
    "llm_call",
    should_continue,
    ["tool_node", END]
)
# 工具执行完后，必须回到 LLM，让它根据工具结果生成最终回答
agent_builder.add_edge("tool_node", "llm_call")

agent = agent_builder.compile()

# --- 运行测试 ---
from langchain.messages import HumanMessage

print("DEBUG: 开始执行代码")

inputs = {
    "messages": [HumanMessage(content="合同条款为甲方应在收到发票后90天内付款。")]

}

print("DEBUG: inputs 已创建")
print("=" * 50)
print("🚀 开始审批")
print("=" * 50)

# 使用 .invoke() 执行
result = agent.invoke(inputs)

print("\n" + "=" * 50)
print("✅ 审批完成")
print("=" * 50)
