# -*- coding:utf-8 -*-
"""
DocAgent 提示词模块

该模块定义了 DocAgent 的系统提示词和提取规则配置。

Date: 2026-03-19
Author: 张镒谱
"""

EXTRACTION_CONFIG = {
    "rule_contract_供地合同_all": {
        "rule_id": "rule_contract_供地合同_all",
        "doc_type": "供地合同",
        "questions": [
            {"id": "q1", "question": "合同的编号是多少？", "answer_template": "合同编号为{value}"},
            {"id": "q2", "question": "出让方是谁？", "answer_template": "出让方为{value}"},
            {"id": "q3", "question": "受让方是谁？", "answer_template": "受让方为{value}"},
            {"id": "q4", "question": "地块位置在哪里？", "answer_template": "地块位置为{value}"},
            {"id": "q5", "question": "土地面积是多少？", "answer_template": "土地面积为{value}平方米"},
            {"id": "q6", "question": "土地用途是什么？", "answer_template": "土地用途为{value}"},
            {"id": "q7", "question": "出让年限是多少？", "answer_template": "出让年限为{value}"},
            {"id": "q8", "question": "成交价格是多少？", "answer_template": "成交价格为{value}"},
            {"id": "q9", "question": "付款方式是什么？", "answer_template": "付款方式为{value}"},
            {"id": "q10", "question": "违约责任条款是什么？", "answer_template": "违约责任条款为{value}"},
        ],
        "clause_questions": {
            "第一条": [
                {"id": "c1_1", "question": "合同第一条的电子监管号是多少？", "answer_template": "合同第一条的电子监管号为{value}"},
            ],
            "第二条": [
                {"id": "c2_1", "question": "合同第二条的宗地编号是多少？", "answer_template": "合同第二条的宗地编号为{value}"},
                {"id": "c2_2", "question": "合同第二条的不动产单元号是多少？", "answer_template": "合同第二条的不动产单元号为{value}"},
            ],
            "第三条": [
                {"id": "c3_1", "question": "合同第三条的出让面积是多少？", "answer_template": "合同第三条的出让面积为{value}平方米"},
            ],
            "第四条": [
                {"id": "c4_1", "question": "合同第四条的出让年限是多少？", "answer_template": "合同第四条的出让年限为{value}"},
            ],
            "第五条": [
                {"id": "c5_1", "question": "合同第五条的不动产单元号是多少？", "answer_template": "合同第五条的不动产单元号为{value}"},
            ],
        },
        "output_example": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "合同编号是多少？", "answer": "合同编号为HT2024001"},
                    {"question": "出让方是谁？", "answer": "出让方为XX市自然资源局"}
                ]
            },
            {
                "index": "第五条",
                "content": [
                    {"question": "合同第五条的不动产单元号是多少？", "answer": "合同第五条的不动产单元号为234455666666"}
                ]
            }
        ]
    },
    "rule_contract_供地合同_clauses": {
        "rule_id": "rule_contract_供地合同_clauses",
        "doc_type": "供地合同",
        "questions": [],
        "clause_questions": {
            "第一条": [
                {"id": "c1_1", "question": "合同第一条的电子监管号是多少？", "answer_template": "合同第一条的电子监管号为{value}"},
            ],
            "第二条": [
                {"id": "c2_1", "question": "合同第二条的宗地编号是多少？", "answer_template": "合同第二条的宗地编号为{value}"},
                {"id": "c2_2", "question": "合同第二条的不动产单元号是多少？", "answer_template": "合同第二条的不动产单元号为{value}"},
            ],
            "第三条": [
                {"id": "c3_1", "question": "合同第三条的出让面积是多少？", "answer_template": "合同第三条的出让面积为{value}平方米"},
            ],
            "第四条": [
                {"id": "c4_1", "question": "合同第四条的出让年限是多少？", "answer_template": "合同第四条的出让年限为{value}"},
            ],
            "第五条": [
                {"id": "c5_1", "question": "合同第五条的不动产单元号是多少？", "answer_template": "合同第五条的不动产单元号为{value}"},
            ],
        },
        "output_example": [
            {
                "index": "第五条",
                "content": [
                    {"question": "合同第五条的不动产单元号是多少？", "answer": "合同第五条的不动产单元号为234455666666"}
                ]
            }
        ]
    },
    "rule_confirmation": {
        "rule_id": "rule_confirmation",
        "doc_type": "成交确认书",
        "questions": [
            {"id": "q1", "question": "确认书编号是多少？", "answer_template": "确认书编号为{value}"},
            {"id": "q2", "question": "成交标的是什么？", "answer_template": "成交标的为{value}"},
            {"id": "q3", "question": "成交价格是多少？", "answer_template": "成交价格为{value}"},
            {"id": "q4", "question": "竞得人是谁？", "answer_template": "竞得人为{value}"},
            {"id": "q5", "question": "成交时间是什么时候？", "answer_template": "成交时间为{value}"},
            {"id": "q6", "question": "签约时限是什么时候？", "answer_template": "签约时限为{value}"},
        ],
        "output_example": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "确认书编号是多少？", "answer": "确认书编号为QR2024001"},
                    {"question": "成交价格是多少？", "answer": "成交价格为5000万元"}
                ]
            }
        ]
    },
    "rule_meeting_minutes": {
        "rule_id": "rule_meeting_minutes",
        "doc_type": "会议纪要",
        "questions": [
            {"id": "q1", "question": "会议时间是什么时候？", "answer_template": "会议时间为{value}"},
            {"id": "q2", "question": "会议地点在哪里？", "answer_template": "会议地点为{value}"},
            {"id": "q3", "question": "主持人是谁？", "answer_template": "主持人为{value}"},
            {"id": "q4", "question": "参会人员有哪些？", "answer_template": "参会人员为{value}"},
            {"id": "q5", "question": "会议议题是什么？", "answer_template": "会议议题为{value}"},
            {"id": "q6", "question": "决议事项是什么？", "answer_template": "决议事项为{value}"},
            {"id": "q7", "question": "行动计划是什么？", "answer_template": "行动计划为{value}"},
        ],
        "output_example": [
            {
                "index": "基础信息",
                "content": [
                    {"question": "会议时间是什么时候？", "answer": "会议时间为2024年3月15日"},
                    {"question": "会议议题是什么？", "answer": "会议议题为土地出让方案审批"}
                ]
            }
        ]
    }
}

DOC_TYPE_RULE_MAPPING = {
    "供地合同": {
        "all": "rule_contract_供地合同_all",
        "clauses": "rule_contract_供地合同_clauses"
    },
    "成交确认书": {
        "default": "rule_confirmation"
    },
    "会议纪要": {
        "default": "rule_meeting_minutes"
    }
}

DEFAULT_SYSTEM_PROMPT = """
# 角色定义
你是"文档智能处理专家"，专门负责文档的智能分析和关键信息提取。

# 你的核心职责
- 根据文档类型智能拆分文档
- 识别文档类型（供地合同、成交确认书、会议纪要）
- 针对不同文档类型提取关键信息

# 你的工作方式：目标导向推理
理解用户的任务目标后，自主规划调用步骤。

**核心推理原则：**
1. **信息充足性判断**：先判断你是否已经拥有完成任务所需的所有信息
   - 如果用户已提供文档内容，直接处理，无需调用文件读取工具
   - 如果缺少信息，再调用相应工具获取
   
2. **工具使用必要性**：只在真正需要时才调用工具
   - 文件读取工具：当你需要文档内容但用户未提供时使用
   - 提取规则工具：当你需要知道提取哪些字段时使用
   - 保存工具：当你完成提取需要保存结果时使用

3. **最小化工具调用**：避免不必要的工具调用，提高效率

**推理示例（仅供参考，请根据实际情况灵活调整）：**

用户说："这个文档是什么类型？"
→ 推理：需要文档内容 → 用户未提供 → 调用文件读取工具
→ 返回类型

用户说："提取这份合同的关键信息"
→ 推理：需要文档内容和提取规则 → 用户未提供内容 → 调用文件读取工具 + 提取规则工具
→ 返回提取结果

用户说："从以下内容中提取合同信息：'电子监管号：xxx...'"
→ 推理：用户已提供内容 → 无需文件读取工具 → 只需提取规则工具
→ 返回提取结果

# 文档类型识别规则
通过文档前几行标题快速识别类型：

- **供地合同**：标题含"合同"、"出让"，或开头有"电子监管号"、"第X条"条款格式
- **成交确认书**：标题含"成交确认书"、"竞得"
- **会议纪要**：标题含"会议纪要"、"会议记录"，或开头有"会议时间"、"参会人员"

识别优先级：先看前3-5行标题关键词，再看内容特征。

# 工具使用原则
- 根据用户需求，按需调用工具
- 每个工具的 description 中已说明使用场景，请仔细阅读后决定是否调用
- 完成用户要求的任务后立即停止，不要执行用户未要求的操作

# 输出格式规范
提取结果的输出格式由提取规则工具动态提供，你需要：
- 严格按照规则定义的字段提取
- 使用规则提供的JSON模板格式输出
- 确保必填字段不为空

# 绝对约束
- 严禁向用户透露任何工具名称、函数名、方法名或技术实现细节
- 严禁在回答中提及任何内部变量名（如 id、rule_id、q1、q2、字段编号等）
- 向用户描述时，必须使用自然的业务表述，像真正的专家一样说话
- 回答问题时，直接给出结论和内容，不要说"根据xxx"、"按照xxx规则"等技术性表述
- 你仅响应文档处理相关问题
- 对于与文档处理无关的问题，请明确告知用户这超出了你的服务范围
"""
