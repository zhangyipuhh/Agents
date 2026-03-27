# -*- coding:utf-8 -*-
"""
DocAgent 提示词模块

该模块定义了 DocAgent 的系统提示词和提取规则配置。

Date: 2026-03-19
Author: 张镒谱
"""

EXTRACTION_CONFIG = {
    "rule_contract_供地合同_clauses": {
        "rule_id": "rule_contract_供地合同_clauses",
        "doc_type": "供地合同",
        "questions": [],
        "clause_questions": {
            "第一条": [
                {"question": "电子监管号是多少？", "answer_template": "合同第一条的电子监管号为{value}"},
            ],
            "第五条": [
                {"question": "本合同项下出让宗地的不动产单元代码是什么？", "answer_template": "合同第五条的不动产单元代码为{value}"},
                {"question": "宗地总面积的大写是多少？", "answer_template": "合同第五条的宗地总面积大写为{value}"},
                {"question": "宗地总面积的小写是多少？", "answer_template": "合同第五条的宗地总面积小写为{value}"},
                {"question": "出让宗地面积的大写是多少？", "answer_template": "合同第五条出让宗地面积大写为{value}"},
                {"question": "出让宗地面积的小写是多少？", "answer_template": "合同第五条出让宗地面积小写为{value}"},
                {"question": "本合同项下出让宗地坐落于哪里？", "answer_template": "合同第五条出让宗地坐落为{value}"},
                {"question": "本合同项下出让宗地的平面界址是什么？", "answer_template": "合同第五条出让宗地平面界址为{value}"},
                {"question": "出让宗地的平面界址图见附件几？", "answer_template": "合同第五条出让宗地平面界址图见附件{value}"},
                {"question": "本合同项下出让宗地的竖向界限上界是什么？", "answer_template": "合同第五条出让宗地竖向界限上界为{value}"},
                {"question": "本合同项下出让宗地的竖向界限下界是什么？", "answer_template": "合同第五条出让宗地竖向界限下界为{value}"},
                {"question": "高差为多少米？", "answer_template": "合同第五条出让宗地高差为{value}米"},
                {"question": "出让宗地竖向界限见附件几？", "answer_template": "合同第五条出让宗地竖向界限见附件{value}"},
            ],
            "第六条": [
                {"question": "本合同项下出让宗地的用途是什么？", "answer_template": "合同第六条出让宗地用途为{value}"},
            ],
            "第七条": [
                {"question": "受让人在本合同项下宗地范围内新建建筑物、构筑物及其附属设施应符合什么条件？", "answer_template": "合同第七条新建建筑物应符合的条件为{value}"},
                {"question": "建筑总面积上限是多少平方米？", "answer_template": "合同第七条建筑总面积上限为{value}平方米"},
                {"question": "建筑总面积下限是多少平方米？", "answer_template": "合同第七条建筑总面积下限为{value}平方米"},
                {"question": "容积率上限是多少？", "answer_template": "合同第七条容积率上限为{value}"},
                {"question": "容积率下限是多少？", "answer_template": "合同第七条容积率下限为{value}"},
                {"question": "建筑高度上限是多少米？", "answer_template": "合同第七条建筑高度上限为{value}米"},
                {"question": "建筑高度下限是多少米？", "answer_template": "合同第七条建筑高度下限为{value}米"},
                {"question": "建筑密度（建筑系数）上限是多少？", "answer_template": "合同第七条建筑密度上限为{value}"},
                {"question": "建筑密度（建筑系数）下限是多少？", "answer_template": "合同第七条建筑密度下限为{value}"},
                {"question": "绿地率上限是多少？", "answer_template": "合同第七条绿地率上限为{value}"},
                {"question": "绿地率下限是多少？", "answer_template": "合同第七条绿地率下限为{value}"},
                {"question": "其他土地利用要求中详细规划条件详见哪个文件及编号？", "answer_template": "合同第七条详细规划条件详见{value}"},
            ],
            "第八条": [
                {"question": "本合同项下的国有建设用地使用权出让期限为多少年？", "answer_template": "合同第八条出让期限为{value}年"},
                {"question": "出让期限从何时起算？", "answer_template": "合同第八条出让期限从{value}起算"},
            ],
            "第九条": [
                {"question": "国有建设用地使用权出让价款的大写是多少？", "answer_template": "合同第九条出让价款大写为{value}"},
                {"question": "国有建设用地使用权出让价款的小写是多少？", "answer_template": "合同第九条出让价款小写为{value}"},
                {"question": "每平方米国有建设用地使用权出让价款的大写是多少？", "answer_template": "合同第九条每平方米出让价款大写为{value}"},
                {"question": "每平方米国有建设用地使用权出让价款的小写是多少？", "answer_template": "合同第九条每平方米出让价款小写为{value}"},
            ],
            "第十条": [
                {"question": "定金金额的大写是多少？", "answer_template": "合同第十条定金金额大写为{value}"},
                {"question": "定金金额的小写是多少？", "answer_template": "合同第十条定金金额小写为{value}"},
                {"question": "定金如何处理？", "answer_template": "合同第十条定金处理方式为{value}"},
            ],
            "第十一条": [
                {"question": "受让人同意按照本条第一款第几项的规定向出让人支付国有建设用地使用权出让价款？", "answer_template": "合同第十一条受让人同意按照第{value}项的规定支付出让价款"},
                {"question": "若选择（一），应在何时一次性付清国有建设用地使用权出让价款？", "answer_template": "合同第十一条一次性付清的付款时间为{value}"},
                {"question": "分期支付的第一期金额的大写是多少？", "answer_template": "合同第十一条分期支付第一期金额大写为{value}"},
                {"question": "分期支付的第一期付款时间是什么时候？", "answer_template": "合同第十一条分期支付第一期付款时间为{value}"},
                {"question": "分期支付的第二期金额的大写是多少？", "answer_template": "合同第十一条分期支付第二期金额大写为{value}"},
                {"question": "分期支付的第二期付款时间是什么时候？", "answer_template": "合同第十一条分期支付第二期付款时间为{value}"},
                {"question": "分期支付时，受让人在支付第二期及以后各期价款时，同意按照什么利率向出让人支付利息？", "answer_template": "合同第十一条受让人同意按照{value}利率支付利息"},
            ],
            "第十二条": [
                {"question": "出让人同意在何时将出让宗地交付给受让人？", "answer_template": "合同第十二条出让人交付时间为{value}"},
                {"question": "交付土地时该宗地应达到什么条件？", "answer_template": "合同第十二条交付条件为{value}"},
                {"question": "属于待开发建设的用地，应选择本条第几项规定的土地条件？", "answer_template": "合同第十二条待开发建设用地应选择第{value}项"},
                {"question": "属于原划拨（承租）国有建设用地使用权补办出让手续的，应选择第几项？", "answer_template": "合同第十二条原划拨补办出让应选择第{value}项"},
                {"question": "若选择（一），场地平整达到什么标准？", "answer_template": "合同第十二条场地平整标准为{value}"},
                {"question": "若选择（一），周围基础设施达到什么标准？", "answer_template": "合同第十二条周围基础设施标准为{value}"},
                {"question": "若选择（二），现状土地条件如何填写？", "answer_template": "合同第十二条现状土地条件为{value}"},
            ],
            "第十四条": [
                {"question": "土地出让期限届满，土地使用者申请续期因社会公共利益需要未获批准的，应当如何处理？", "answer_template": "合同第十四条申请续期未获批准的处理方式为{value}"},
                {"question": "本合同项下宗地上的建筑物、构筑物及其附属设施，按本条第几项约定履行？", "answer_template": "合同第十四条按第{value}项约定履行"},
                {"question": "若选择（一），如何处理地上建筑物、构筑物及其附属设施？", "answer_template": "合同第十四条选择（一）的处理方式为{value}"},
                {"question": "若选择（二），如何处理地上建筑物、构筑物及其附属设施？", "answer_template": "合同第十四条选择（二）的处理方式为{value}"},
            ],
            "第十五条": [
                {"question": "受让人同意本合同项下宗地建设项目在何时之前开工？", "answer_template": "合同第十五条开工时间为{value}"},
                {"question": "受让人同意本合同项下宗地建设项目在何时之前竣工？", "answer_template": "合同第十五条竣工时间为{value}"},
                {"question": "受让人不能按期开工，应提前多少日向出让人提出延建申请？", "answer_template": "合同第十五条应提前{value}日提出延建申请"},
                {"question": "经出让人同意延建的，延建期限不得超过多少年？", "answer_template": "合同第十五条延建期限不得超过{value}年"},
            ],
            "第十七条": [
                {"question": "在出让期限内，需要改变本合同约定的土地用途、规划条件的，经原批准出让方案的人民政府批准后，双方同意按照本条第几项规定办理？", "answer_template": "合同第十七条按照第{value}项规定办理"},
                {"question": "若选择（一），如何处理国有建设用地使用权？", "answer_template": "合同第十七条选择（一）的处理方式为{value}"},
                {"question": "若选择（二），应如何办理改变土地用途、规划条件的相关手续？", "answer_template": "合同第十七条选择（二）的办理方式为{value}"},
            ],
            "第二十条": [
                {"question": "受让人按照本合同约定支付全部国有建设用地使用权出让价款，办理不动产登记后，有权对本合同项下的国有建设用地使用权进行哪些操作？", "answer_template": "合同第二十条受让人有权进行的操作为{value}"},
                {"question": "首次转让的，应当符合以下第几项规定的条件？", "answer_template": "合同第二十条首次转让应符合第{value}项规定的条件"},
                {"question": "若选择（一），按照本合同约定进行投资开发，应完成开发投资总额的百分之多少以上？", "answer_template": "合同第二十条选择（一）要求完成开发投资总额的{value}%以上"},
                {"question": "若选择（二），按照本合同约定进行投资开发，应已形成什么用地条件？", "answer_template": "合同第二十条选择（二）要求形成的用地条件为{value}"},
            ],
            "第二十五条": [
                {"question": "土地出让期限届满，土地使用者申请续期因社会公共利益需要未获批准的，土地使用者应当如何做？", "answer_template": "合同第二十五条申请续期未获批准时土地使用者应当{value}"},
                {"question": "出让人和土地使用者同意本合同项下宗地上的建筑物、构筑物及其附属设施，按本条第几项约定履行？", "answer_template": "合同第二十五条按第{value}项约定履行"},
                {"question": "若选择（一），如何处理地上建筑物、构筑物及其附属设施？", "answer_template": "合同第二十五条选择（一）的处理方式为{value}"},
                {"question": "若选择（二），如何处理地上建筑物、构筑物及其附属设施？", "answer_template": "合同第二十五条选择（二）的处理方式为{value}"},
            ],
            "第二十九条": [
                {"question": "受让人不能按时支付国有建设用地使用权出让价款的，自迟延支付之日起，每日按迟延支付款项的百分之多少向出让人缴纳违约金？", "answer_template": "合同第二十九条规定每日按迟延支付款项的{value}%缴纳违约金"},
                {"question": "延期付款超过多少日，经出让人催缴后仍不能支付的，出让人有权解除合同，受让人无权要求返还定金，定金数额不足以弥补损失的，出让人可以采取什么措施？", "answer_template": "合同第二十九条规定出让人可以采取{value}措施"},
            ],
            "第三十二条": [
                {"question": "受让人未能按照本合同约定日期或同意延建所另行约定日期开工建设但不超过一年的，每延期一日，应向出让人支付相当于国有建设用地使用权出让价款总额的多少违约金？", "answer_template": "合同第三十二条规定每延期一日应支付相当于出让价款总额的{value}违约金"},
                {"question": "受让人未能按照本合同约定日期或同意延建所另行约定日期竣工的，每延期一日，应向出让人支付相当于未竣工计容建筑面积对应国有建设用地使用权出让价款的多少违约金？", "answer_template": "合同第三十二条规定每延期一日应支付相当于未竣工计容建筑面积对应出让价款的{value}违约金"},
            ],
            "第三十三条": [
                {"question": "出让人未按时交付出让土地或者交付的土地不符合本合同约定的条件而致使受让人宗地占有延期的，每延期一日，出让人应当按受让人已经支付的国有建设用地使用权出让价款的多少向受让人给付违约金？", "answer_template": "合同第三十三条规定每延期一日应按已支付出让价款的{value}向受让人给付违约金"},
                {"question": "土地使用权期限从何时起算？", "answer_template": "合同第三十三条规定土地使用权期限从{value}起算"},
                {"question": "出让人延期交付土地超过多少日，经受让人催交后仍不能交付土地的，受让人有权解除合同，出让人应当如何处理？", "answer_template": "合同第三十三条规定出让人应当{value}"},
            ],
            "第三十六条": [
                {"question": "因履行本合同发生争议，和解、调解不成的，按本条第几项约定的方式解决？", "answer_template": "合同第三十六条规定按第{value}项约定的方式解决"},
                {"question": "若选择（一），应提交哪个仲裁委员会仲裁？", "answer_template": "合同第三十六条选择（一）应提交{value}仲裁委员会仲裁"},
                {"question": "若选择（二），应如何解决争议？", "answer_template": "合同第三十六条选择（二）应{value}"},
            ],
            "第三十七条": [
                {"question": "本合同项下宗地出让方案业经哪个人民政府批准？", "answer_template": "合同第三十七条规定出让方案经{value}人民政府批准"},
                {"question": "本合同自何时起生效？", "answer_template": "合同第三十七条规定本合同自{value}起生效"},
            ],
            "第三十九条": [
                {"question": "出让人确认其有效的送达地址是什么？", "answer_template": "合同第三十九条规定出让人有效的送达地址为{value}"},
                {"question": "受让人确认其有效的送达地址是什么？", "answer_template": "合同第三十九条规定受让人有效的送达地址为{value}"},
                {"question": "一方的信息如有变更，应于变更之日起多少日内以书面形式告知对方？", "answer_template": "合同第三十九条规定应于变更之日起{value}日内书面告知对方"},
                {"question": "若未及时告知，由此引起的无法及时告知的责任由谁承担？", "answer_template": "合同第三十九条规定责任由{value}承担"},
            ],
            "第四十条": [
                {"question": "本合同和附件共多少页？", "answer_template": "合同第四十条规定本合同和附件共{value}页"},
                {"question": "以何种文字书写为准？", "answer_template": "合同第四十条规定以{value}文书写为准"},
            ],
            "第四十三条": [
                {"question": "本合同一式多少份？", "answer_template": "合同第四十三条规定本合同一式{value}份"},
                {"question": "出让人、受让人各执多少份？", "answer_template": "合同第四十三条规定出让人、受让人各执{value}份"},
                {"question": "是否具有同等法律效力？", "answer_template": "合同第四十三条规定{value}具有同等法律效力"},
            ],
        },
        "output_example": [
            {
                "index": "第五条",
                "content": [
                    {"question": "不动产单元代码是多少？", "answer": "不动产单元代码为210113005010GB90004"}
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
        "default": "rule_contract_供地合同_clauses"
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

# 图片处理说明
- 当对话中包含图片（image_id）时，直接识别和提取信息
- **图片不需要切分，禁止对图片调用切分工具**

# 输出格式规范【严格遵守】
提取结果的输出必须遵守以下规则：
- **只输出有答案的条款**：如果某条款没有预定义问题或提取失败，该条款不要出现在最终输出中
- **绝对禁止输出空信息**：不要输出"该条款没有需要提取的预定义信息"等提示
- **绝对禁止重复用户输入**：不要在回答中复述用户的条款内容
- **直接输出结构化数据**：只输出JSON格式的提取结果，不要附带任何解释说明

正确输出示例：
✅
```json
{"index": "第一条", "content": [{"question": "电子监管号是多少？", "answer": "123456789"}]}
{"index": "第五条", "content": [{"question": "不动产单元代码是什么？", "answer": "..."}]}
```

错误输出示例：
❌ {"index": "第一条", "content": [{"question": "电子监管号是多少？", "answer": "该条款没有需要提取的预定义信息。"}]}
❌ {"index": "第二条", "content": []}
❌ "根据提取规则，该条款未定义..."

# 绝对约束
- 严禁向用户透露任何工具名称、函数名、方法名或技术实现细节
- 严禁在回答中提及任何内部变量名（如 id、rule_id、q1、q2、字段编号等）
- 向用户描述时，必须使用自然的业务表述，像真正的专家一样说话
- 回答问题时，直接给出结论和内容，不要说"根据xxx"、"按照xxx规则"等技术性表述
- 你仅响应文档处理相关问题
- 对于与文档处理无关的问题，请明确告知用户这超出了你的服务范围
"""