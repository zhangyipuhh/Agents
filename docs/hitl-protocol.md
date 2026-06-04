# 人工回路（ask_user_question）返回值完整说明

> 状态：已上线
> 适用版本：2026-06-01 后的所有 Agent
> 作者：AI Assistant
> 日期：2026-06-01

## 一、协议总览

```
┌────────────┐                              ┌────────────┐
│   后端     │  ── SSE interrupt ──>        │   前端     │
│   Agent    │  <── Command(resume) ──      │   Vue      │
└────────────┘                              └────────────┘
```

人工回路分 3 个阶段：

| 阶段 | 方向 | 数据格式 | 触发 |
|---|---|---|---|
| **A. 中断** | 后端 → 前端 | SSE `data: {type:"interrupt",data:{requests:[...]}}` | LLM 调用 `ask_user_question` |
| **B. 展示** | 前端内部 | `aiMsg.interrupt = [{action, questions}]` | `extractApprovalData` 解包 |
| **C. 恢复** | 前端 → 后端 | `Command(resume={"answers": [[...], [...]]})` | 用户提交 HumanApprovalBox |

---

## 二、阶段 A：后端 → 前端（SSE 中断事件）

### 原始 SSE 事件

```json
data: {"type": "interrupt", "data": {"requests": [{"action": "ask_user_question", "questions": [...]}]}}
```

### `questions[i]` 字段约束（Pydantic 强制）

| 字段 | 类型 | 必填 | 约束 | 说明 |
|---|---|---|---|---|
| `question` | string | 是 | 1-500 字符 | 完整问题文本 |
| `header` | string | 是 | 1-30 字符 | Tab 标题（≤12 字符更佳） |
| `options` | array | 否 | 0-5 个 | 0=纯文本；2-4 业务+后端自动追加 Other |
| `multiple` | boolean | 否 | 默认 false | true=多选 |
| `text_only` | boolean | 否 | 默认 false | true=纯文本题，跳过 Other 注入 |

### `options[i]` 字段约束

| 字段 | 必填 | 约束 |
|---|---|---|
| `label` | 是 | 1-50 字符 |
| `description` | 是 | 1-200 字符 |

### 真实数据示例（用户提供的）

```json
{
  "type": "interrupt",
  "data": {
    "requests": [{
      "action": "ask_user_question",
      "questions": [
        {
          "question": "请选择项目类型（可多选）",
          "header": "项目类型",
          "options": [
            {"label": "工业用地", "description": "工业生产、制造加工类项目"},
            {"label": "住宅用地 (Recommended)", "description": "住宅小区、公寓等居住类项目"},
            {"label": "商业用地", "description": "商场、写字楼等商业经营类项目"},
            {"label": "公共服务用地", "description": "学校、医院等公共服务类项目"},
            {"label": "Other", "description": "输入自定义回答"}
          ],
          "multiple": true,
          "text_only": false
        },
        {
          "question": "请输入项目名称",
          "header": "项目名称",
          "options": [],
          "multiple": false,
          "text_only": true
        },
        {
          "question": "如有其他需求请简要说明",
          "header": "补充说明",
          "options": [],
          "multiple": false,
          "text_only": true
        }
      ]
    }]
  }
}
```

**注意**：
- Q1 LLM 传了 **5 个 options**（4 业务 + 1 Other），后端**不会重复追加**（去重）
- Q2/Q3 是 `text_only=true` + `options=[]` 模式，前端显示 textarea

---

## 三、阶段 B：前端解包

### 数据流

```
SSE 事件 (data: {...})
  ↓ processSSEEvent 解析
aiMsg.interrupt = [{action:"ask_user_question", questions:[...]}]
  ↓ extractApprovalData 解包
approvalData = { questions: [...] }
  ↓ 传给 HumanApprovalBox
<HumanApprovalBox :questions="approvalData.questions" />
```

### `extractApprovalData` 实现

**文件**：`web/Agent/src/App.vue`

```js
function extractApprovalData(interruptArray) {
  if (!Array.isArray(interruptArray) || interruptArray.length === 0) {
    return { questions: [] }
  }
  const req = interruptArray[0]
  const payload = req.value ?? req
  const questions = payload.questions ?? []
  return { questions }
}
```

`KnowledgeApp.vue` 同理。

### HumanApprovalBox 接收的最终数据

```js
props.questions = [
  { question, header, options: [...], multiple, text_only },
  ...
]
```

---

## 四、HumanApprovalBox 渲染规则

| 条件 | UI 行为 |
|---|---|
| `questions.length > 1` | 顶部显示 Tab 栏（header 文字 + 完成后打勾） |
| `options.length === 0` | 显示 textarea（freeform 模式） |
| `options.length >= 2` + `multiple=false` | 单选：圆形 radio + 描述 |
| `options.length >= 2` + `multiple=true` | 多选：方形 checkbox + 描述 |
| 点击 `label === "Other"` 的选项 | 弹出内联 textarea（其他场景下 hidden） |
| `confirm-btn` disabled 条件 | 任一题未答 |

---

## 五、阶段 C：前端 → 后端（恢复值）

### 提交时 emit

```js
// HumanApprovalBox 内部
emit('submit', { answers: finalAnswers })

// finalAnswers 结构：
// [
//   ['工业用地', '商业用地'],          // Q1 多选
//   ['阳光花园小区'],                  // Q2 纯文本
//   ['需要配套学校']                   // Q3 纯文本
// ]
```

### 父组件接收（App.vue / KnowledgeApp.vue）

```js
async function handleApprovalSubmit({ answers }) {
  const resumeData = { answers }
  // chatStream 第 3 个参数透传给后端
  await chatStream(sessionId, '', [], resumeData)
}
```

### 后端收到的 Command

```python
# 后端 (LangGraph) 收到
Command(resume={
    "answers": [
        ["工业用地", "商业用地"],
        ["阳光花园小区"],
        ["需要配套学校"]
    ]
})

# interrupt() 返回值（hitl_check_node 中）
response = interrupt(request)  # response = {"answers": [...]}
```

### hitl_check_node 构造的 HumanMessage

```
【用户对 3 个问题的回答】
问题「请选择项目类型（可多选）」：用户选择了 工业用地, 商业用地
问题「请输入项目名称」：用户选择了 阳光花园小区
问题「如有其他需求请简要说明」：用户选择了 需要配套学校

请基于以上回答继续。
```

---

## 六、完整 Vue 接入示例

### App.vue（主对话页）

```vue
<script setup>
import { ref } from 'vue'
import { chatStream } from '@/utils/api'
import HumanApprovalBox from '@/components/HumanApprovalBox.vue'

const approvalMode = ref(false)
const approvalData = ref({ questions: [] })

/**
 * 提取中断数据 → approvalData
 * 兼容多种 interrupt 数据格式
 */
function extractApprovalData(interruptArray) {
  if (!Array.isArray(interruptArray) || interruptArray.length === 0) {
    return { questions: [] }
  }
  const req = interruptArray[0]
  // 兼容：req.value（LangGraph 新格式） 或 req 直接（你的数据格式）
  const payload = req.value ?? req
  const questions = payload.questions ?? []
  return { questions }
}

/**
 * 提交时把 answers 包装为 { answers: [...] } 发回后端
 */
async function handleApprovalSubmit({ answers }) {
  approvalMode.value = false
  const aiMsg = messages[messages.length - 1]
  if (!aiMsg) return
  aiMsg.interrupt = null  // 清旧状态

  // resume 格式：{ answers: [[...], [...]] } —— 二维数组，每题一个 label 数组
  const resumeData = { answers }
  await chatStream(sessionId.value, '', [], resumeData)
}
</script>

<template>
  <HumanApprovalBox
    v-if="approvalMode"
    :questions="approvalData.questions"
    @submit="handleApprovalSubmit"
  />
</template>
```

### HumanApprovalBox.vue（已存在，无需改）

接收 `questions` prop，emit `submit({answers})` 事件。

### SSE 解析层（已存在）

`web/Agent/src/utils/sseParser.js:processSSEEvent` 在收到 `type: 'interrupt'` 事件时自动解包并设置 `aiMsg.interrupt`。

---

## 七、调试技巧

### 1. 打印实际收到的 interrupt

```js
// sseParser.js processSSEEvent case 'interrupt':
console.log('[HITL] interrupt received:', data.data)
// 应该是 { requests: [{action, questions}] }
```

### 2. 打印解包后的 approvalData

```js
// App.vue handleXxxStream
if (aiMsg.interrupt) {
  console.log('[HITL] extracted:', extractApprovalData(aiMsg.interrupt))
}
```

### 3. 验证后端 interrupt payload

```python
# tests/test_ask_user_question.py
from app.core.tools.HumanInTheLoopTools import AskUserQuestionInput

inp = AskUserQuestionInput(questions=[...])
import json
print(json.dumps([q.model_dump() for q in inp.questions], ensure_ascii=False, indent=2))
```

### 4. 常见错误

| 症状 | 原因 | 修复 |
|---|---|---|
| 前端不显示审批框 | `extractApprovalData` 返回空 | 检查 `aiMsg.interrupt` 是否被设置 |
| 提交后后端无反应 | `resumeData` 格式错 | 必须是 `{ answers: [[...]] }`，**不要** `{ args: { decision } }` |
| 选项超过 4 个被 Pydantic 拒绝 | max_length 太严 | 已修复为 5（4 业务 + 1 Other） |
| 纯文本题前端只显示空列表 | 用了 options 模式 | 传 `options=[]` + `text_only=true` |

---

## 八、测试覆盖

| 维度 | 文件 | 用例数 |
|---|---|---|
| 后端 Schema | `tests/test_ask_user_question.py::TestQuestion*` | 10 |
| 后端 auto-inject | `tests/test_ask_user_question.py::TestAutoInjectOther` | 5 |
| 后端 Tool | `tests/test_ask_user_question.py::TestAskUserQuestionTool` | 2 |
| 后端 HitlNode | `tests/test_ask_user_question.py::TestHitlCheckNode` | 5 |
| 前端组件 | `web/Agent/src/components/__tests__/HumanApprovalBox.spec.js` | 22 |
| **合计** | | **44** |

全量验证：后端 26/26 ✅ + 前端 82/82 ✅
