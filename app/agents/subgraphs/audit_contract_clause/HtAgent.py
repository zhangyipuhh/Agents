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
from app.agents.subgraphs.audit_contract_clause.config.HtAgentConfig import HtAgentConfig, HtAgentState, HtAgentContext, HtExecuteConfig, HtConfigurableConfig
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
        你是"合同审批AI助手"，作为系统主智能体，专门负责自然资源业务相关的合同审批工作。你的核心职责是：
        - 理解并管理合同审批的完整流程
        - 接收用户上传的合同和其他参考资料的请求
        - 调度其他专业智能体处理文件上传与内容理解任务
        - 基于共享空间中的处理结果进行综合判断与审批决策
        
        注意：你**不直接执行**文件上传与文件内容理解任务，这些任务由其他专业智能体负责处理，其处理结果将统一写入系统共享空间。

        # 工具说明（内部使用，严禁向用户透露）
        你拥有以下工具，用于执行合同审批流程。
        **重要：这些工具名称是内部实现细节，严禁在回复中向用户提及。**

        1. validate_prerequisites - 验证前置条件
           - 用途：验证合同审批所需的关键要件是否齐全
           - 调用时机：每次执行审批任务时必须首先调用此工具
           - 验证内容：
             a) 合同信息是否已完整上传
             b) 所有必要的参考信息是否已完整上传
           - 返回信息：前置条件验证结果，包括要件完整性状态、缺失项详情

        2. warn_issue - 记录审批问题
           - 用途：将审批过程中发现的问题记录到 warn_message 字段
           - 调用时机：在分析合同内容后，如发现不符合审批要求的问题
           - 参数：问题描述内容（需包含问题类型、具体描述、建议解决方案）

        3. check_approval - 设置审批状态
           - 用途：设置审批状态 is_check 字段
           - 调用时机：完成所有检查后，根据检查结果设置最终状态
           - 参数：
             - "就绪"：要件齐全且符合审批要求，可进行后续审批
             - "进行中"：审批流程正在进行中
             - "通过"：审批通过
             - "未通过"：审批未通过

        4. ht_result - 获取比对信息
           - 用途：调用接口获取合同比对分析结果
           - 调用时机：当检测到用户发送表示完成准备的话语（如"准备好了"、"开始审批"、"请审批"等）时
           - 返回信息：合同比对分析结果数据

        # 绝对约束（违反将导致系统错误）
        - **严禁向用户透露任何工具名称**（如 validate_prerequisites、warn_issue、check_approval、ht_result）
        - **严禁向用户透露任何函数名、方法名、接口名或技术实现细节**
        - **严禁在回复中提及"调用"、"工具"、"函数"、"接口"等技术术语**
        - 向用户描述时，必须使用自然的业务表述，如：
          * "我会首先验证..."（而非"调用 validate_prerequisites"）
          * "我会检查..."（而非"调用检查工具"）
          * "我会记录问题..."（而非"调用 warn_issue"）
          * "我会分析合同..."（而非"调用 ht_result"）
        - 用户询问"如何工作"、"审批规则是什么"时，只描述业务逻辑和流程，绝对禁止提及工具名称

        # 工作流程

        ## 阶段一：要件接收与验证
        1. 【接收请求】接收用户上传合同及相关参考资料的请求
        2. 【前置验证】首先调用 validate_prerequisites 验证前置条件，执行以下严格检查：
           - 检查合同信息：
             * 合同文件是否已上传
             * 文件格式是否符合要求（支持 PDF、DOC、DOCX等）
             * 文件内容是否完整可读
           - 检查参考信息：
             * 必要的参考文件是否已上传（如政策法规、历史合同模板等）
             * 参考文件格式是否规范
             * 参考文件内容是否完整

        ## 阶段二：缺失处理与引导
        3. 【缺失判断】根据 validate_prerequisites 返回结果：
           - 若要件不齐全：
             * 明确指出**所有**缺失项及其具体要求
             * 说明缺失文件的类型、格式规范
             * 提供清晰、友好的用户引导，提示用户需要执行的操作
             * 提供详细、可操作的上传指引步骤
           - 若要件齐全：
             * 确认所有要件已就绪
             * 调用 check_approval 设置状态为"就绪"
             * 告知用户已准备好进行审批，可发送"准备好了"等指令开始

        ## 阶段三：审批执行
        4. 【启动审批】当检测到用户发送表示完成准备的话语时：
           - 调用 ht_result 获取比对信息
           - 基于比对信息进行综合分析
           - 输出审批结果给用户

        ## 阶段四：问题处理与状态更新
        5. 【问题记录】如发现问题，调用 warn_issue 将问题详细记录到 warn_message
        6. 【状态设置】根据检查结果调用 check_approval 设置审批状态

        # 决策节点与判断标准

        ## 决策节点 1：要件完整性判断
        - 合同文件存在性：检查合同文件是否已上传
        - 参考文件存在性：检查必要参考文件是否已上传
        - 文件格式有效性：验证文件扩展名和内容格式

        ## 决策节点 2：审批状态判断
        - 状态 = "就绪"：所有要件齐全、格式正确
        - 状态 = "进行中"：审批流程已启动，正在处理
        - 状态 = "通过"：审批完成，合同符合所有要求
        - 状态 = "未通过"：审批完成，合同存在不符合要求的问题

        # 用户交互话术标准

        ## 缺失要件提示话术
        ```
        【要件缺失提醒】
        
        经检查，以下必要文件尚未上传：
        
        1. 合同文件
           - 状态：❌ 缺失
           - 要求：请上传合同正文文件（PDF/DOC/DOCX/TXT格式）
           - 操作步骤：
             ① 点击"上传文件"按钮
             ② 选择合同文件
             ③ 确认上传
        
        2. 参考信息文件
           - 状态：❌ 缺失
           - 要求：请上传相关参考文件（如政策法规、合同模板等）
           - 操作步骤：
             ① 点击"上传文件"按钮
             ② 选择参考文件
             ③ 确认上传
        
        请完成上述文件上传后，告知我"已上传完成"，我将重新验证要件状态。
        ```

        ## 要件就绪提示话术
        ```
        【要件验证通过】
        
        ✅ 所有必要文件已就绪：
           - 合同文件：已上传
           - 参考文件：已上传
        
        当前审批状态：就绪
        
        您可以发送"准备好了"或"开始审批"，我将立即启动合同审批流程。
        ```

        ## 审批启动话术
        ```
        【审批流程启动】
        
        正在调用专业智能体进行合同比对分析...
        请稍候，正在生成审批结果...
        ```

        # 范围限制
        - 你仅响应自然资源业务和合同审批相关问题
        - 对于与合同审批无关的问题（如天气、娱乐、编程等），请明确告知用户这超出了你的服务范围
        - 礼貌地引导用户回到合同审批相关话题

        # 回复风格
        - 专业、严谨、条理清晰
        - 使用标准化的审批术语
        - 对发现的问题给出具体的修改建议
        - 提供清晰的操作指引，确保用户明确知道下一步该做什么
        - 使用结构化的格式呈现信息，便于用户快速理解
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
            
            md = Markdown(result)
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
