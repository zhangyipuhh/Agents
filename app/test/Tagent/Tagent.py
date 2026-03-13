#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Tagent - 审计文档Agent测试脚本

用于测试和演示审计文档Agent的对话功能，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-11
Author: 张镒谱
"""

import asyncio
from app.agents.agent.agent import get_audit_document_agent
from app.test.Tagent.TagentConfig import TAgentConfig,TAgentState,TAgentContext,TExecuteConfig,TConfigurableConfig
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.markdown import Markdown


def main():
    """
    主函数 - 启动聊天助手并执行对话循环
    
    实现逻辑:
    1. 初始化检查点存储器用于保存对话状态
    2. 配置Agent参数（模型、API密钥、系统提示词等）
    3. 进入多轮对话循环，接受用户输入并调用Agent处理
    4. 对话结束后展示checkpoint中的历史消息和上下文摘要
    """
    asyncio.run(_async_main())


async def _async_main():
    """
    异步主函数 - 处理实际的对话逻辑
    
    变量说明:
        console: Rich控制台对象，用于美化输出
        _checkpointer: 内存检查点存储器，保存对话状态
        Aconfig: Agent配置对象，包含模型和API设置
        sid: 会话ID，用于标识不同的对话会话
        agent: 审计文档Agent实例
        max_rounds: 最大对话轮数限制
    """
    console = Console()
    print("=== 聊天助手初始化 ===")
    
    # 初始化内存检查点，用于保存和恢复对话状态
    # MemorySaver将状态存储在内存中，支持多轮对话的上下文保持
    _checkpointer = MemorySaver()
    
    # 配置Agent参数
    # model_type: 使用的模型类型
    # model_name: 具体模型名称
    # base_url: API服务端点
    # api_key: 认证密钥
    # max_tokens: 单次响应最大token数
    # max_tokens_before_summary: 触发摘要的token阈值
    # max_summary_tokens: 摘要的最大token数
    # system_prompt: 系统提示词，定义Agent角色
    # checkpointer: 状态持久化组件
    Aconfig = TAgentConfig(
        model_type="deepseek",
        model_name="deepseek-chat",
        base_url="https://api.deepseek.com",
        api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
        max_tokens=20000,
        max_tokens_before_summary=16000,
        max_summary_tokens=4000,
        system_prompt="我是一个聊天助手，可以使用工具，可以解决问题,当问时间时必须使用get_current_time工具，需要加法计算时必须使用add工具，看到工具结果后再回复用户",
        checkpointer=_checkpointer,
    )
    
    # 会话ID，用于关联同一对话的所有消息
    # 固定ID可实现多轮对话，注释掉则每次生成新ID（关闭多轮对话）
    sid="user_chat_001"
    
    # 初始化Agent实例
    # 根据配置创建审计文档Agent，准备处理用户请求
    agent = await get_audit_document_agent(Aconfig)
    
    # 设置最大对话轮数，防止无限循环
    max_rounds = 10
    
    print(f"\n开始对话（最多 {max_rounds} 轮，输入 'quit' 或 'exit' 退出）\n")
    
    # 对话主循环 - 持续接收用户输入直到达到最大轮次或用户退出
    # 循环逻辑: 获取输入 -> 验证输入 -> 调用Agent -> 展示结果 -> 检查退出条件
    for round_num in range(1, max_rounds + 1):
        # 测试关闭多轮对话，每次初始化新id
        # 当启用时，每轮对话使用新的session_id，Agent无法访问历史消息
        #sid=str(uuid.uuid4())
        try:
            # 获取用户输入并去除首尾空白
            user_input = input(f"[轮次 {round_num}] 请输入: ").strip()
            
            # 检查退出条件 - 用户输入quit/exit/q时结束对话
            # 使用lower()实现大小写不敏感匹配
            if user_input.lower() in ['quit', 'exit', 'q']:
                print("\n退出对话")
                break
            
            # 输入验证 - 空输入不处理，重新获取
            if not user_input:
                print("输入不能为空，请重新输入")
                continue
            
            print("\n处理中...\n")
            
            # 构建执行配置
            # TExecuteConfig包含可配置参数，如线程ID（会话标识）
            config = TExecuteConfig(
                configurable=TConfigurableConfig(
                    thread_id=sid
                )
            )
            
            # 构建Agent状态
            # messages: 用户消息列表
            # error_limit: 允许的最大错误次数
            # limit: 最大迭代次数，防止无限循环
            state = TAgentState(
                messages=[user_input],
                error_limit=2,
                limit=10
            )
            
            # 构建执行上下文
            # session_id: 会话唯一标识，用于状态追踪
            context=TAgentContext(
                session_id=sid
            )

            # 调用Agent处理用户输入
            # invoke方法接收配置、初始状态和上下文，返回包含AI响应的新状态
            result = await agent.invoke(
                config=config,
                input_state=state,
                context=context
            )
            
            #result["messages"][-1].pretty_print()
            
            # 使用Rich库渲染Markdown格式的响应
            # 将Agent返回的最后一条消息内容转换为Markdown并美化输出
            md = Markdown(result["messages"][-1].content)
            console.print(md)
            print()
            
        except KeyboardInterrupt:
            # 捕获Ctrl+C中断信号，优雅退出
            print("\n\n对话已中断")
            break
        except Exception as e:
            # 捕获其他异常，打印错误信息后继续对话
            # 使用continue确保单轮错误不影响后续对话
            print(f"发生错误: {e}")
            continue
    
    # 对话结束后展示统计信息
    # round_num - 1 是因为最后一轮可能未完成就退出了
    print(f"\n对话结束，共进行了 {round_num - 1} 轮")
    
    
    # 查看checkpoint内容 - 展示会话状态信息
    # 包括历史消息和上下文摘要，用于调试和验证状态管理
    print("\n=== Checkpoint 信息 ===")
    checkpoint = await agent.inspect_checkpoint(session_id=sid)
    print(f"消息数: {checkpoint['messages_count']}")
    
    # 遍历所有消息并打印详细信息
    # 区分不同类型的消息（用户/AI/系统），并显示工具调用信息
    for msg in checkpoint['messages']:
        print(f"- {msg['type']}: {msg['content']}")
        if msg['tool_calls']:
            print(f"  工具调用: {msg['tool_calls']}")
    
    # 如果存在上下文信息，打印摘要
    # 上下文包含会话的长期记忆摘要，用于理解会话主题
    if checkpoint.get('context'):
        print("\n=== Context 信息 ===")
        for key, value in checkpoint['context'].items():
            print(f"{key}: {value['summary']} (长度: {value['summary_length']})")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
