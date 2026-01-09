#!usr/bin/env python
# -*- coding: utf-8 -*-
import json
import asyncio
import threading

from langgraph.graph import StateGraph, START, END
from app.agents.llmcalls.model_factory import ModelFactory
from app.agents.config.config import LLM_CONFIG, PROMPT_TEMPLATE
from app.agents.states.mainstates import MessagesState
from app.agents.tools.maintools import MainTools
from app.agents.continues.maincontinues import should_continue
from langchain.messages import ToolMessage, AIMessage,HumanMessage,SystemMessage

# 全局流式输出队列
stream_queue = None
stream_lock = threading.Lock()


def get_stream_queue():
    """获取流式输出队列"""
    return stream_queue


def set_stream_queue(q):
    """设置流式输出队列"""
    global stream_queue
    with stream_lock:
        stream_queue = q
    with stream_lock:
        stream_queue = q



class MainAgent:
    def __init__(self):
        self.model_factory = ModelFactory()
        self.messages_state = MessagesState()
        #1.初始化模型
        self.model = self.model_factory.create_model(model_type=LLM_CONFIG["model_type"],model_name=LLM_CONFIG["model_name"], api_key=LLM_CONFIG["api_key"], temperature=0, base_url=LLM_CONFIG["base_url"])
        #2.绑定工具
        self.main_tools = MainTools()
        self.tools = self.main_tools.get_static_method_list()
        self.tool_dict = self.main_tools.get_static_methods()
        self.model_with_tools = self.model.bind_tools(self.tools)
    def CreateAgent(self, prompt: str=None):

       
        
        #3. 定义状态
        #response = model_with_tools.invoke(prompt)
        
        #4.连接状态图
        graph=(
            StateGraph[MessagesState, None, MessagesState, MessagesState](MessagesState)
            .add_node("llm_call", self.llm_call)
            .add_node("tool_node", self.tool_node)
            .add_edge(START, "llm_call")
            .add_conditional_edges(
                "llm_call",
                should_continue,
                ["tool_node", END]
            )
            .add_edge("tool_node", "llm_call")
        )
        
        return graph.compile()
    def tool_node(self, state: MessagesState):
        """工具节点：执行工具调用并返回结果"""
        # 从状态中获取 LLM 的响应
        llm_response = state["messages"][-1]
        
        # 检查是否有工具调用
        if not hasattr(llm_response, 'tool_calls') or not llm_response.tool_calls:
            print("⚠️ [警告] 没有检测到工具调用", flush=True)
            return state
        
        tool_messages = []
        
        # 执行所有工具调用
        for tool_call in llm_response.tool_calls:
            tool_name = tool_call.get("name")
            tool_args = tool_call.get("args", {})
            tool_id = tool_call.get("id")
            
            print(f"🔧 [执行工具] {tool_name}", flush=True)
            print(f"   参数: {tool_args}", flush=True)
            
            try:
                # 根据工具名称执行对应的工具
                result = self.tool_dict[tool_name].invoke(tool_args)
                # 创建 ToolMessage
                tool_msg = ToolMessage(
                    content=result,
                    tool_call_id=tool_id
                )
                tool_messages.append(tool_msg)
                print(f"✅ [工具执行完成]", flush=True)
                print(f"   结果: {result[:100]}{'...' if len(result) > 100 else ''}", flush=True)
                
            except Exception as e:
                print(f"❌ [工具执行错误] {e}", flush=True)
                # 创建错误消息
                error_msg = ToolMessage(
                    content=f"工具执行失败: {str(e)}",
                    tool_call_id=tool_id
                )
                tool_messages.append(error_msg)
        
        # 返回更新后的状态
        return {
            "messages": tool_messages
        }
    

    def llm_call(self, state: dict):
        """LLM 决定是否调用审批工具（真正的流式输出）
        
        Args:
            state: 当前状态
        """
        
        # 获取当前的消息列表
        existing_messages = state["messages"]
        
        # 检查是否需要添加系统提示词
        # 只有在消息列表中没有系统消息时才添加
        has_system_message = any(msg.type == "system" for msg in existing_messages)
        if not has_system_message:
            system_msg = SystemMessage(content=PROMPT_TEMPLATE["main"])
            # 将系统消息插入到最前面
            existing_messages = [system_msg] + existing_messages
        
        # 使用 stream 逐字输出，不使用 invoke
        print("🤖 [AI思考中]...", end="", flush=True)
        
        full_content = ""
        tool_calls_list = []
        args_list = "" #存储参数的，流式输出时参数要特殊处理
        
        # 获取当前线程的流式输出队列
        stream_q = get_stream_queue()
        
        try:
            for chunk in self.model_with_tools.stream(existing_messages):
                # 处理不同类型的 chunk
                if hasattr(chunk, 'content') and chunk.content:
                    # 真正的流式输出：逐字返回
                    print(chunk.content, end="", flush=True)
                    full_content += chunk.content
                    # 将流式内容放入队列
                    if stream_q:
                        try:
                            stream_q.put({"type": "content", "data": chunk.content}, block=False)
                        except queue.Full:
                            pass
                elif hasattr(chunk, 'tool_calls') and chunk.tool_calls:
                    # 如果有工具调用，收集工具调用信息
                    if not tool_calls_list:
                        print("\n🔧 [准备调用工具]", flush=True)
                    for tc in chunk.tool_calls:
                        if "name" not in tc or not tc["name"]:
                            continue
                        print(f"   工具: {tc['name']}", flush=True)
                        tool_calls_list.append(tc)
                        # 将工具调用信息放入队列
                        if stream_q:
                            try:
                                stream_q.put({"type": "tool_call", "data": {"name": tc["name"]}}, block=False)
                            except queue.Full:
                                pass
                elif hasattr(chunk, 'content_blocks') and chunk.content_blocks:
                    for block in chunk.content_blocks:
                        if "type" in block and block["type"] == "tool_call_chunk" and "args" in block and block["args"]:
                            print(f"  {block['args']}", end="", flush=True)
                            args_list += block["args"]
                            # 将工具参数放入队列
                            if stream_q:
                                try:
                                    stream_q.put({"type": "tool_args", "data": block["args"]}, block=False)
                                except queue.Full:
                                    pass
                            
                           # print( block["args"], end="", flush=True)
                        
        except Exception as e:
            print(f"\n[流式输出错误]: {e}", flush=True)
            # 将错误信息放入队列
            try:
                stream_q.put({"type": "error", "data": str(e)}, block=False)
            except queue.Full:
                pass
            # 如果流式输出失败，回退到 invoke
            response = model_with_tools.invoke(existing_messages)
            if hasattr(response, 'content') and response.content:
                print(response.content, flush=True)
                full_content = response.content
            if hasattr(response, 'tool_calls') and response.tool_calls:
                tool_calls_list = response.tool_calls
        
        print()  # 换行
        #用args_list替换tc的参数占位符
        for tc in tool_calls_list:
            tc["args"] = json.loads('{"'+args_list.replace(" ",""))
        # 过滤掉无效的工具调用
        valid_tool_calls = []
        for tc in tool_calls_list:
            # 检查工具调用是否有效
            if tc.get("name") and tc.get("id") and " " not in tc.get("name"):  # 确保 name 非空且不含空格，id 非空
                valid_tool_calls.append(tc)
        
        print(f"DEBUG: 有效工具调用数量: {len(valid_tool_calls)}")
        
        # 构造 AIMessage
        if valid_tool_calls:
            # 如果有有效的工具调用，创建包含 tool_calls 的消息
            response = AIMessage(
                content=full_content,
                tool_calls=valid_tool_calls
            )
        else:
            # 如果没有工具调用，创建普通消息
            response = AIMessage(content=full_content)
        
 
        return {
            "messages": [response],
            "checked_rules_count": state.get("checked_rules_count", 0) + 1
        }
    


if __name__ == "__main__":
    
    
    print("DEBUG: 开始执行代码")

    inputs = {
        "messages": [HumanMessage(content="合同条款是甲方应在收到发票后90天内付款。")]
        #"messages": [HumanMessage(content="查询客户数据库中所有状态为'已付款'的客户。")]
        # 测试工具调用
        #"messages": [HumanMessage(content="计算 5 乘以 3 等于多少？")]
    }
    print("DEBUG: inputs 已创建")
    print("=" * 50)
    print("🚀 开始流式审批")
    print("=" * 50)
    
    main_agent = MainAgent()
    # 使用 .stream() 替代 .invoke()
    # stream_mode="values" 表示获取完整的状态更新
     # 这一步很重要，让模型知道它手里有这个工具
    agent= main_agent.CreateAgent()
    for event in agent.stream(inputs, stream_mode="values"):
        # event 是完整的状态更新
        # 只在节点切换时打印分隔线，因为内容已经在节点内部逐字输出了
        if "messages" in event and len(event["messages"]) > 0:
            # 检查是否有新的消息
            last_msg = event["messages"][-1]
            print("\n" + "-" * 50)
            if isinstance(last_msg, AIMessage):
                if last_msg.tool_calls:
                    print(f"📍 节点: llm_call (准备调用工具)")
                else:
                    print(f"📍 节点: llm_call")
            elif isinstance(last_msg, ToolMessage):
                print(f"📍 节点: tool_node")
            print("-" * 50)

    print("\n" + "=" * 50)
    print("✅ 审批完成")
    print("=" * 50)
            
            
        
        