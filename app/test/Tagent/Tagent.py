#!/usr/bin/python
# -*- coding:utf-8 -*-
"""
Tagent - 审计文档Agent测试脚本

用于测试和演示审计文档Agent的对话功能，支持多轮对话、工具调用和会话状态管理。

Date: 2026-03-11
Author: 张镒谱
"""

import asyncio
import uuid
import base64
from pathlib import Path
from app.agents.agent.agent import get_agent
from app.test.Tagent.TagentConfig import TAgentConfig, TAgentState, TAgentContext, TExecuteConfig, TConfigurableConfig
from app.utils.files.fileTransfer import FileTransfer
from langgraph.checkpoint.memory import MemorySaver
from rich.console import Console
from rich.markdown import Markdown
from langgraph.store.memory import InMemoryStore


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
        file_transfer: 文件传输工具实例
    """
    console = Console()
    print("=== 聊天助手初始化 ===")
    
    # 初始化内存检查点，用于保存和恢复对话状态
    # MemorySaver将状态存储在内存中，支持多轮对话的上下文保持
    _checkpointer = MemorySaver()
    
    # 初始化文件传输工具
    file_transfer = FileTransfer(upload_dir="app/data/upload")
    
    prompt = """
        # 角色定义
        你是"对话式AI助手"，核心定位是"有工具能力的思考伙伴"，而非"工具触发器"。

        # 双模式工作流
        【探索模式】发散：理解意图 → 关联知识 → 提供视角 → 激发思考
        【执行模式】收敛：验证事实 → 精准计算 → 调用工具 → 确保准确

        # 决策原则
        1. 先问"为什么"，再问"怎么做"
        2. 工具是增强可信度的手段，不是回复的全部
        3. 每个回复都应包含"引导层"，主动推进对话

        #回复风格：
        - 直接给核心信息，不要"我注意到/根据系统"等元话语
        - 用1-2句话自然过渡，把事实和追问连起来
        - 追问要具体猜场景，不要罗列功能选项
        - 允许省略【观察】层，如果意图显而易见

        # 禁止事项
        - 禁止只给工具结果，零上下文
        - 禁止被动等待指令，不主动引导
        - 禁止过度发散，忘记用户原始问题
        """
   
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
    store = InMemoryStore()
    Aconfig = TAgentConfig(
        max_tokens=20000,
        max_tokens_before_summary=16000,
        max_summary_tokens=4000,
        system_prompt=prompt,
        checkpointer=_checkpointer,
        store=store
    )
    store_id = uuid.uuid4()  # 公用内存id
    # 会话ID，用于关联同一对话的所有消息
    # 固定ID可实现多轮对话，注释掉则每次生成新ID（关闭多轮对话）
    sid = "user_chat_001"
    
    # 初始化Agent实例
    # 根据配置创建Agent，准备处理用户请求
    agent = await get_agent(Aconfig)
    
    # 设置最大对话轮数，防止无限循环
    max_rounds = 10
    
    print(f"\n开始对话（最多 {max_rounds} 轮，输入 'quit' 或 'exit' 退出）")
    print("提示：每轮对话可以输入 'upload' 来上传文件或图片\n")
    
    # 对话主循环 - 持续接收用户输入直到达到最大轮次或用户退出
    # 循环逻辑: 获取输入 -> 验证输入 -> 调用Agent -> 展示结果 -> 检查退出条件
    for round_num in range(1, max_rounds + 1):
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
            
            # 初始化图片路径列表
            image_paths_id = []
            
            # 检查是否需要上传文件
            if user_input.lower() == 'upload':
                # 询问用户要上传什么类型的文件
                print("\n请选择上传类型:")
                print("1. 普通文件（文档、PDF等）")
                print("2. 图片文件（用于多模态分析）")
                upload_choice = input("请输入选项 (1/2): ").strip()
                
                if upload_choice == '1':
                    # 上传普通文件
                    file_paths = input("请输入文件路径（多个文件用逗号分隔）: ").strip()
                    if file_paths:
                        uploaded_files = await _upload_files(file_paths, sid, file_transfer)
                        if uploaded_files:
                            print(f"成功上传 {len(uploaded_files)} 个文件:")
                            for f in uploaded_files:
                                print(f"  - {f['filename']} (ID: {f['id']})")
                        # 上传后继续下一轮，不调用Agent
                        continue
                    else:
                        print("未提供文件路径，取消上传")
                        continue
                        
                elif upload_choice == '2':
                    # 上传图片
                    image_paths = input("请输入图片路径（多个图片用逗号分隔）: ").strip()
                    if image_paths:
                        uploaded_images = await _upload_images(image_paths, sid, file_transfer, store)
                        if uploaded_images:
                            image_paths_id = [img['id'] for img in uploaded_images]
                            print(f"成功上传 {len(uploaded_images)} 张图片:")
                            for img in uploaded_images:
                                print(f"  - {img['filename']} (ID: {img['id']})")
                        # 上传图片后询问用户输入问题
                        user_input = input("\n图片已上传，请输入您的问题: ").strip()
                        if not user_input:
                            print("未输入问题，取消本次对话")
                            continue
                    else:
                        print("未提供图片路径，取消上传")
                        continue
                else:
                    print("无效选项，取消上传")
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
            # image_paths_id: 图片ID列表，用于多模态模型
            state = TAgentState(
                messages=[user_input],
                error_limit=2,
                limit=10,
                file_chunk_read_progress=1,
                image_paths_id=image_paths_id,
                IS_MULTIMODAL=len(image_paths_id) > 0  # 如果有图片则启用多模态
            )
            
            # 构建执行上下文
            # session_id: 会话唯一标识，用于状态追踪
            context = TAgentContext(
                session_id=sid
            )

            # 调用Agent处理用户输入
            # invoke方法接收配置、初始状态和上下文，返回包含AI响应的新状态
            result = await agent.invoke(
                config=config,
                input_state=state,
                context=context
            )
            
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
            import traceback
            traceback.print_exc()
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


async def _upload_files(file_paths_str: str, session_id: str, file_transfer: FileTransfer) -> list:
    """
    上传普通文件
    
    Args:
        file_paths_str: 文件路径字符串，多个路径用逗号分隔
        session_id: 会话ID
        file_transfer: 文件传输工具实例
        
    Returns:
        list: 上传成功的文件信息列表
    """
    from fastapi import UploadFile
    import io
    
    uploaded_files = []
    paths = [p.strip() for p in file_paths_str.split(',') if p.strip()]
    
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            print(f"警告: 文件不存在 - {path_str}")
            continue
        
        try:
            # 读取文件内容
            with open(path, 'rb') as f:
                content = f.read()
            
            # 创建UploadFile对象
            upload_file = UploadFile(
                filename=path.name,
                file=io.BytesIO(content)
            )
            
            # 使用fileTransfer上传
            result = await file_transfer.upload_files([upload_file], session_id)
            uploaded_files.extend(result)
            
        except Exception as e:
            print(f"上传文件失败 {path_str}: {e}")
    
    return uploaded_files


async def _upload_images(image_paths_str: str, session_id: str, file_transfer: FileTransfer, store) -> list:
    """
    上传图片文件并将base64编码存入store
    
    Args:
        image_paths_str: 图片路径字符串，多个路径用逗号分隔
        session_id: 会话ID
        file_transfer: 文件传输工具实例
        store: LangGraph存储实例
        
    Returns:
        list: 上传成功的图片信息列表
    """
    from fastapi import UploadFile
    import io
    
    uploaded_images = []
    paths = [p.strip() for p in image_paths_str.split(',') if p.strip()]
    
    for path_str in paths:
        path = Path(path_str)
        if not path.exists():
            print(f"警告: 图片不存在 - {path_str}")
            continue
        
        # 检查文件类型
        valid_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.webp'}
        if path.suffix.lower() not in valid_extensions:
            print(f"警告: 不支持的图片格式 - {path_str}")
            continue
        
        try:
            # 读取图片并转换为base64
            with open(path, 'rb') as f:
                image_content = f.read()
            
            base64_data = base64.b64encode(image_content).decode('utf-8')
            # 添加data URI前缀
            mime_type = f"image/{path.suffix.lower().replace('.', '')}"
            if mime_type == "image/jpg":
                mime_type = "image/jpeg"
            base64_url = f"data:{mime_type};base64,{base64_data}"
            
            # 创建UploadFile对象用于获取UUID
            upload_file = UploadFile(
                filename=path.name,
                file=io.BytesIO(image_content)
            )
            
            # 使用fileTransfer上传获取ID
            result = await file_transfer.upload_files([upload_file], session_id)
            
            if result:
                image_id = result[0]['id']
                # 将base64数据存入store，使用image_前缀
                # 命名空间使用session_id，key使用image_前缀加图片ID
                store.put(
                    (session_id,),           # namespace
                    f"image_{image_id}",     # key
                    base64_url               # value
                )
                uploaded_images.extend(result)
                
        except Exception as e:
            print(f"上传图片失败 {path_str}: {e}")
            import traceback
            traceback.print_exc()
    
    return uploaded_images


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n程序被用户中断")
