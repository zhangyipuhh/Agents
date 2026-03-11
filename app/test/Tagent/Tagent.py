import asyncio


from app.agents.agent.agent import get_audit_document_agent, AuditDocumentAgent
from app.test.Tagent.TagentConfig import TAgentConfig,TAgentState,TAgentContext,TExecuteConfig,TConfigurableConfig
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.markdown import Markdown

if __name__ == "__main__":
    async def main():
        console = Console()
        print("=== 聊天助手初始化 ===")
        _checkpointer = MemorySaver()
        Aconfig = TAgentConfig(
            model_type="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
            max_tokens=4096,
            max_tokens_before_summary=1000,
            max_summary_tokens=2000,
            system_prompt="我是一个聊天助手，可以使用工具，可以解决问题",
            checkpointer=_checkpointer,
        )
        sid="user_chat_001"
        agent = await get_audit_document_agent(Aconfig)
        
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
                config = TExecuteConfig(
                    configurable=TConfigurableConfig(
                        thread_id=sid
                    )
                )
                state = TAgentState(
                    messages=[user_input],
                    error_limit=2,
                    limit=10
                )
                context=TAgentContext(
                    session_id=sid
                )

                result = await agent.invoke(
                    config=config,
                    input_state=state,
                    context=context
                )
                
                #result["messages"][-1].pretty_print()
                
                # 打印 Markdown
                md = Markdown(result["messages"][-1].content)
                console.print(md)
                print()
                
            except KeyboardInterrupt:
                print("\n\n对话已中断")
                break
            except Exception as e:
                print(f"发生错误: {e}")
                continue
        
        print(f"\n对话结束，共进行了 {round_num - 1} 轮")
        
        
        # 示例 2: 查看 checkpoint 内容
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
    asyncio.run(main())