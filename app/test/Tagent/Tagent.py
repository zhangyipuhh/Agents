if __name__ == "__main__":
    async def main():
        """主函数，演示智能体的使用方法
        
        示例 1: 启用摘要功能
            - 创建智能体实例
            - 执行多次对话，测试摘要功能
            - 打印摘要信息
            
        示例 2: 查看 checkpoint 内容
            - 检查对话历史
            - 显示消息数量和内容
            - 显示摘要信息
        """
        # 示例 1: 启用摘要功能
        print("=== 启用摘要功能 ===")
        agent = await get_audit_document_agent(
            model_type="deepseek",
            model_name="deepseek-chat",
            base_url="https://api.deepseek.com",
            api_key="sk-d5652bb2e21c43debd1f22fbed6468cf",
            max_tokens=4096,
            max_tokens_before_summary=1000,
            max_summary_tokens=2000
        )
        checkpointer = get_global_checkpointer(db_path="./checkpoints.db")
        # 设置检查点
        #agent.graph.set_checkpointer(checkpointer)
        
        prompts = [
            "直接调用合同解析工具，合同内容：‘国有建设用地使用权出让合同’"
            #,
            #"你还能干什么",
            #"如何防止提示词注入",
            #"你是谁",
            #"总结我们的对话"
        ]

        for prompt in prompts:
            result = await agent.invoke(
                session_id="user_123",
                prompt=prompt,
                file_paths=["/path/to/file1.pdf", "/path/to/file2.docx"],
                file_ids=["file_001", "file_002"]
            )
            result["messages"][-1].pretty_print()
        
        # 显示摘要信息
        if "context" in result:
            print(f"\n=== 摘要信息 ===")
            for key, value in result["context"].items():
                if hasattr(value, 'summary'):
                    print(f"{key}: {value.summary}")
        
        # 示例 2: 查看 checkpoint 内容
        print("\n=== Checkpoint 信息 ===")
        checkpoint = await agent.inspect_checkpoint(session_id="user_123")
        print(f"消息数: {checkpoint['messages_count']}")
        for msg in checkpoint['messages']:
            print(f"- {msg['type']}: {msg['content']}")
            if msg['tool_calls']:
                print(f"  工具调用: {msg['tool_calls']}")
        
        if checkpoint.get('context'):
            print("\n=== Context 信息 ===")
            for key, value in checkpoint['context'].items():
                print(f"{key}: {value['summary'][:100]}... (长度: {value['summary_length']})")

    asyncio.run(main())