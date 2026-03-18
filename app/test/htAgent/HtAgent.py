#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
HtAgent - 合同审批Agent测试脚本

用于测试和演示合同审批Agent的对话功能，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-17
Author: 张镒谱
"""

import asyncio
import uuid
from app.agents.agent.agent import get_agent
from app.test.htAgent.HtAgentConfig import HtAgentConfig, HtAgentState, HtAgentContext, HtExecuteConfig, HtConfigurableConfig
from langgraph.checkpoint.memory import MemorySaver
from langgraph.store.memory import InMemoryStore
from rich.console import Console
from rich.markdown import Markdown


def main():
    asyncio.run(_async_main())


async def _async_main():
    console = Console()
    print("=== 合同审批助手初始化 ===")
    
    _checkpointer = MemorySaver()
    store = InMemoryStore()
    
    prompt = """
        # 角色定义
        你是"合同审批AI助手"，专门负责自然资源业务相关的合同审批工作。你的核心职责是协助用户完成合同审批流程，确保合同内容符合审批要求。

        # 工具说明
        你拥有以下三个核心工具：

        1. validate_prerequisites - 验证前置条件
           - 用途：验证合同审批的前置条件是否满足
           - 调用时机：每次执行审批任务时必须首先调用此工具
           - 返回信息：前置条件验证结果

        2. warn_issue - 记录审批问题
           - 用途：将审批过程中发现的问题记录到 warn_message 字段
           - 调用时机：在分析合同内容后，如发现不符合审批要求的问题
           - 参数：问题描述内容

        3. check_approval - 设置审批状态
           - 用途：设置审批状态 is_check 字段
           - 调用时机：完成所有检查后，根据检查结果设置最终状态
           - 参数：true 表示审批通过，false 表示审批未通过

        # 工作流程
        1. 【前置验证】首先调用 validate_prerequisites 验证前置条件，确保审批流程可以正常进行
        2. 【内容分析】仔细分析用户提供的合同内容，检查是否符合审批要求
        3. 【问题记录】如发现问题，调用 warn_issue 工具将问题详细记录到 warn_message
        4. 【状态设置】根据检查结果调用 check_approval 工具设置审批状态：
           - 所有条件满足：设置 is_check = true
           - 存在问题未解决：设置 is_check = false

        # 范围限制
        - 你仅响应自然资源业务和合同审批相关问题
        - 对于与合同审批无关的问题（如天气、娱乐、编程等），请明确告知用户这超出了你的服务范围
        - 礼貌地引导用户回到合同审批相关话题

        # 回复风格
        - 专业、严谨、条理清晰
        - 使用标准化的审批术语
        - 对发现的问题给出具体的修改建议
        """

    Aconfig = HtAgentConfig(
        max_tokens=20000,
        max_tokens_before_summary=16000,
        max_summary_tokens=4000,
        system_prompt=prompt,
        checkpointer=_checkpointer,
        store=store
    )
    
    sid = "ht_agent_001"
    
    agent = await get_agent(Aconfig)
    
    max_rounds = 10
    
    print(f"\n开始对话（最多 {max_rounds} 轮，输入 'quit' 或 'exit' 退出）\n")
    
    for round_num in range(1, max_rounds + 1):
        try:
            user_input = input(f"[轮次 {round_num}] 请输入: ").strip()
            
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n退出对话")
                break
            
            if not user_input:
                print("输入不能为空，请重新输入")
                continue
            
            print("\n处理中...\n")
            
            config = HtExecuteConfig(
                configurable=HtConfigurableConfig(
                    thread_id=sid
                )
            )
            
            state = HtAgentState(
                messages=[user_input],
                error_limit=2,
                limit=10
            )
            
            context = HtAgentContext(
                session_id=sid
            )

            result = await agent.invoke(
                config=config,
                input_state=state,
                context=context
            )
            
            md = Markdown(result["messages"][-1].content)
            console.print(md)
            print()
            
        except KeyboardInterrupt:
            print("\n\n对话已中断")
            break
        except Exception as e:
            print(f"发生错误: {e}")
            import traceback
            traceback.print_exc()
            continue
    
    print(f"\n对话结束，共进行了 {round_num - 1} 轮")
    
    print("\n=== Checkpoint 信息 ===")
    checkpoint = await agent.inspect_checkpoint(session_id=sid)
    print(f"消息数: {checkpoint['messages_count']}")
    
    for msg in checkpoint['messages']:
        print(f"- {msg['type']}: {msg['content']}")
        if msg['tool_calls']:
            print(f"  工具调用: {msg['tool_calls']}")
    
    if checkpoint.get('context'):
        print("\n=== Context 信息 ===")
        for key, value in checkpoint['context'].items():
            print(f"{key}: {value['summary']} (长度: {value['summary_length']})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
