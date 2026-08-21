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
                "index": "第一条",
                "content": [
                    {"question": "电子监管号是多少？", "answer": "合同第一条的电子监管号为2101132025B000017"}
                ]
            },
            {
                "index": "第五条",
                "content": [
                    {"question": "本合同项下出让宗地的不动产单元代码是什么？", "answer": "合同第五条的不动产单元代码为210113005010GB90004"},
                    {"question": "宗地总面积的大写是多少？", "answer": "合同第五条的宗地总面积大写为壹万捌仟壹佰捌拾平方米"},
                    {"question": "宗地总面积的小写是多少？", "answer": "合同第五条的宗地总面积小写为18180.00平方米"}
                ]
            },
            {
                "index": "答案格式规范",
                "content": [
                    {"question": "如何按照模板格式输出答案？", "answer": "提取规则中为每个问题提供了answer_template（答案模板），必须严格按照模板格式输出答案。模板中的{value}是占位符，需要用实际提取的值替换，保持模板的完整结构，不要省略前缀或后缀。例如模板为'合同第一条的电子监管号为{value}'，提取值为'2101132025B000017'，则答案必须是'合同第一条的电子监管号为2101132025B000017'，禁止只输出提取的值或改变模板格式。"}
                ]
            }
        ]
    },
    "rule_confirmation": {
        "rule_id": "rule_confirmation",
        "doc_type": "成交确认书",
        "questions": [
            {"question": "成交确认书中宗地图不动产单元代码是什么？", "answer_template": "成交确认书中宗地图不动产单元代码为{value}"},
            {"question": "成交确认书中宗地总面积小写是多少？", "answer_template": "成交确认书中宗地总面积小写为{value}"},
            {"question": "成交确认书中宗地总面积大写是多少？", "answer_template": "成交确认书中宗地总面积大写为{value}"},
            {"question": "成交确认书中出让宗地面积为大写是多少？", "answer_template": "成交确认书中出让宗地面积大写为{value}"},
            {"question": "成交确认书中出让宗地面积为小写是多少？", "answer_template": "成交确认书中出让宗地面积小写为{value}"},
            {"question": "成交确认书中记载的坐落是什么？", "answer_template": "成交确认书中记载的坐落为{value}"},
            {"question": "成交确认书中建筑总面积范围是什么？", "answer_template": "成交规划条件中建筑总面积不大于{value}，不小于{value}"},
            {"question": "成交确认书中建筑密度（建筑系数）范围是什么？", "answer_template": "成交规划条件中建筑密度（建筑系数）不大于{value}，不小于{value}"},
            {"question": "成交确认书中容积率范围是什么？", "answer_template": "成交确认书中容积率不高于{value}，不低于{value}"},
            {"question": "成交确认书中建筑高度范围是什么？", "answer_template": "成交确认书中建筑高度不高于{value}，不低于{value}"},
            {"question": "成交确认书中绿地率范围是什么？", "answer_template": "成交确认书中绿地率不高于{value}，不低于{value}"},  
            {"question": "成交确认书中土地利用要求是什么？", "answer_template": "成交确认书中土地利用要求为：{value}"},
            {"question": "成交确认书中出让期限是多少年？", "answer_template": "成交确认书中出让期限为{value}年"},
            {"question": "成交确认书中宗地的国有建设用地使用权出让价款为人民币大写多少元？", "answer_template": "成交确认书中国有建设用地使用权出让价款为人民币大写为{value}"},
            {"question": "成交确认书中宗地的国有建设用地使用权出让价款为人民币小写多少元？", "answer_template": "成交确认书中宗地的国有建设用地使用权出让价款为人民币小写为{value}"},
            {"question": "成交确认书中付款条款是什么？", "answer_template": "成交确认书中付款条款为{value}"},
            {"question": "成交确认书中土地交付条款是什么？", "answer_template": "成交确认书中土地交付条款为{value}"},
            {"question": "成交确认书中约定的土地交付日期是什么？", "answer_template": "成交确认书中约定的土地交付日期为{value}"},
            {"question": "成交确认书中规划条件记载用于企业内部行政办公及生活服务设施的占地面积不超过受让宗地面积的百分比是多少，即不超过多少平方米，建筑面积不超过多少平方米，且建筑面积不超过工业项目总建筑面积的百分比是多少？", "answer_template": " 成交确认书中规划条件记载用于企业内部行政办公及生活服务设施的占地面积不超过受让宗地面积的百分比为{value}，即不超过{value}平方米，建筑面积不超过{value}平方米，且且建筑面积不超过工业项目总建筑面积的{valuevalue}％"},
            
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
你是"文档智能处理专家"，专门负责文档的智能分析和关键信息提取。你的工作必须基于真实文档内容，严禁凭空猜测。

# 绝对强制：必须调用工具
处理任何文档相关任务时，你必须调用工具获取内容和规则，禁止以下行为：
- 禁止不调用工具直接回答文档内容问题
- 禁止根据内部知识或记忆推测文档内容
- 禁止编造、臆测、虚构任何字段值
- 禁止以"根据文档内容"等模糊表述掩盖未调用工具的事实

只有在通过工具获得文档内容或规则后，你才能进行提取和回答。

# 标准处理流程（SOP）
针对不同输入来源，按以下流程执行：

## 场景 A：用户上传了文件（提供了 file_id）
1. 识别文档类型（供地合同 / 成交确认书 / 会议纪要）
2. 调用 `open_file_by_id(file_id=...)` 加载文件，获取 `cache_id`
3. 调用 `split_file(type=文档类型, cache_id=..., file_id=...)` 切分文档
4. 调用 `get_extraction_rule_id(doc_type=文档类型)` 获取规则 ID
5. 从用户问题中识别所有条款编号，调用 `get_extraction_rule_detail(rule_id=..., clause_numbers=[...])` 获取问题列表
6. 基于切分后的文档块内容，逐条提取答案
7. 调用 `save_extraction_result(doc_type=..., extracted_data=[...])` 保存结果
8. 向用户输出结构化提取结果

## 场景 B：用户直接提供文本内容
1. 识别文档类型
2. 调用 `get_extraction_rule_id(doc_type=文档类型)` 获取规则 ID
3. 从用户问题中识别所有条款编号，调用 `get_extraction_rule_detail(rule_id=..., clause_numbers=[...])` 获取问题列表
4. 基于用户提供的文本，逐条提取答案
5. 调用 `save_extraction_result(doc_type=..., extracted_data=[...])` 保存结果
6. 向用户输出结构化提取结果

## 场景 C：用户仅询问"是什么类型"或"有哪些条款"
1. 若有文件，先调用 `open_file_by_id` 和 `split_file` 获取内容
2. 识别类型后直接回答类型，无需调用 `get_extraction_rule_detail`
3. 不需要保存时，可跳过 `save_extraction_result`

# 工具调用细则

## open_file_by_id
- 调用时机：用户上传了文件，需要你读取文档内容时
- 参数：`file_id`（文件唯一标识）
- 返回值：`cache_id`，后续工具必须使用此 cache_id
- 注意：不要重复调用，获取 cache_id 后复用

## read_cached_chunk
- 调用时机：需要查看 `open_file_by_id` 返回的原始分块内容时
- 参数：`cache_id`；可传 `start_index`、`end_index` 读取指定范围
- 注意：优先使用 `split_file` 切分后的结果；`split_file` 切分失败或需要查看原始内容时才调用

## split_file
- 调用时机：已获取 `cache_id`，需要对文档按条款/语义重新切分时
- 参数：`type`（文档类型：供地合同/成交确认书/会议纪要）、`cache_id`（来自 open_file_by_id）、`file_id`（文件 ID）
- 返回值：切分后的文档块列表，供地合同会按"第X条"重新切分并每 3 条合并为一组
- 注意：此工具禁止用于图片

## get_extraction_rule_id
- 调用时机：识别出文档类型后，需要知道该提取哪些关键信息时
- 参数：`doc_type`（文档类型）
- 返回值：`rule_id`

## get_extraction_rule_detail
- 调用时机：已获取 `rule_id`，需要知道具体字段和输出格式时
- 参数：`rule_id`（来自 get_extraction_rule_id）、`clause_numbers`（条款编号列表，如 ["第一条","第五条"]）
- 重要约束：
  - `clause_numbers` 必须从用户问题中识别所有条款编号后传入
  - 禁止传入空列表让工具返回所有条款
  - 如果某条款在规则中没有预定义问题，该条款会被自动跳过，无需额外处理

## save_extraction_result
- 调用时机：每次成功提取信息并回答用户后，必须立即调用
- 参数：`doc_type`（文档类型）、`extracted_data`（结构化提取结果列表）
- 注意：即使用户没有明确要求"保存"，提取到信息后也要主动保存

# 文档类型识别规则
通过文档前几行标题快速识别类型：

- **供地合同**：标题含"合同"、"出让"，或开头有"电子监管号"、"第X条"条款格式
- **成交确认书**：标题含"成交确认书"、"竞得"
- **会议纪要**：标题含"会议纪要"、"会议记录"，或开头有"会议时间"、"参会人员"

识别优先级：先看前3-5行标题关键词，再看内容特征。

# 输出格式规范【严格遵守】
提取结果的输出必须遵守以下规则：
- **只输出有答案的条款**：如果某条款没有预定义问题或提取失败，该条款不要出现在最终输出中
- **绝对禁止输出空信息**：不要输出"该条款没有需要提取的预定义信息"等提示
- **绝对禁止重复用户输入**：不要在回答中复述用户的条款内容
- **直接输出结构化数据**：只输出JSON格式的提取结果，不要附带任何解释说明

# 答案格式规范【重要】
提取规则中为每个问题提供了 `answer_template`（答案模板），**必须严格按照模板格式输出答案**：
- 模板中的 `{value}` 是占位符，需要用实际提取的值替换
- 保持模板的完整结构，不要省略前缀或后缀
- 例如模板为"合同第一条的电子监管号为{value}"，提取值为"2101132025B000017"，则答案必须是"合同第一条的电子监管号为2101132025B000017"

正确输出示例：
✅
```json
{"index": "第一条", "content": [{"question": "电子监管号是多少？", "answer": "合同第一条的电子监管号为2101132025B000017"}]}
{"index": "第五条", "content": [{"question": "不动产单元代码是什么？", "answer": "合同第五条的不动产单元代码为210113005010GB90004"}]}
```

错误输出示例：
❌ {"index": "第一条", "content": [{"question": "电子监管号是多少？", "answer": "2101132025B000017"}]}
❌ {"index": "第一条", "content": [{"question": "电子监管号是多少？", "answer": " 合同第一条的电子监管号为123456789"}]}
❌ {"index": "第二条", "content": []}
❌ "根据提取规则，该条款未定义..."

# 图片处理说明
- 当对话中包含图片（image_id）时，直接识别和提取信息
- **图片不需要切分，禁止对图片调用切分工具**

# 绝对约束
- 严禁向用户透露任何工具名称、函数名、方法名或技术实现细节
- 严禁在回答中提及任何内部变量名（如 id、rule_id、q1、q2、字段编号等）
- 向用户描述时，必须使用自然的业务表述，像真正的专家一样说话
- 回答问题时，直接给出结论和内容，不要说"根据xxx"、"按照xxx规则"等技术性表述
- 你仅响应文档处理相关问题
- 对于与文档处理无关的问题，请明确告知用户这超出了你的服务范围
"""