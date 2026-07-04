---
name: intent-clarification
description: "Use whenever any project-doc skill (query/outline/write/workflow/data-skill) needs to confirm something with the user — unified protocol: scan project artifacts first, show prior answers, cite source+line, handle 'TBD/待定' by re-asking. Re-entrant: can be invoked from any step, not just the start."
---

## Keywords (关键词)

- 意图澄清 (intent-clarification)
- 询问协议 (clarification-protocol)
- 多维度分流 (multi-dimension-dispatch)
- 强制澄清 (mandatory-clarification)
- 日志持久化 (log-persistence)
- 待定处理 (pending-handling)
- 项目级澄清 (project-level-clarification)
- 反模式红线 (anti-pattern-redline)

# Intent Clarification (Project-Level Clarification Protocol · For Model)

> **Target reader**: **The model** (not the user). After loading this skill, the model should be able to automatically:
> - Know that any "ask the user" action must first invoke this skill
> - Know where clarification logs are stored (`.project/<project_id>/`, **NOT inside the skill**)
> - Know the 4 major question scenarios (intent/data/environment/document_attr)
> - Know it is re-entrant (can be invoked at any time during the flow)

<HARD-GATE>
Do NOT write any outline / document / answer without first invoking this skill and completing clarification. Each clarification produces a row in `<用户工作根>/.project/<project_id>/clarification_log.md` (NOT inside the skill).
</HARD-GATE>

<HARD-GATE: NO FABRICATION>
Do NOT fabricate ANY content under ANY circumstance. When a fact is missing from project materials:
1. Mark as "**To Be Supplemented (待补)**：<specific field name>" (NEVER "—" / "TBD" / "待定" used alone)
2. Cite source field: "No project material supports this (无项目资料支撑)"
3. Append row to `<用户工作根>/.project/<project_id>/clarification_log.md` using file write tools
4. NEVER write a guess, even a plausible one

This applies to:
- People names (if 策划表 does not list "张三", do not write "张三")
- Dates (if 策划表 does not list "2025-12-31", do not write it)
- Numbers (test case count / duration / cost with no evidence → "**To Be Supplemented (待补)**")
- Tool names (if the project does not mention "ZenTao (禅道)" / "Git" / "DingTalk (钉钉)", do not write them)
- Role signoff (no specific name → stay silent, do not write)
- Doc status (user did not say → stay silent, do not write "Draft for Review (评审稿)")
- Framework tags (PMP/PRINCE2/Systems Analyst tags must be accurate)

When in doubt: ASK, don't WRITE.
</HARD-GATE: NO FABRICATION>

---

<HARD-GATE: Differentiated "To Be Supplemented (待补)" Handling by Document Type · 2026-06-XX Second Reinforcement>

> The semantics of "To Be Supplemented (待补)" placeholder are **classified by document type**. **Not** every document type can use the "To Be Supplemented (待补)" placeholder.

### A. Internal Process Documents (Allow "To Be Supplemented (待补)" Placeholder, but Must Ask User First)

**Applies to**: Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan

- When materials are missing → **Must first** invoke `intent-clarification` taking the B.data dimension (D4 decision) to ask the user
- User provides specific content → write it directly
- User answers "To Be Supplemented (待补)" / "Mark as To Be Supplemented for now" / "I will fill it in later" → allowed to use "**To Be Supplemented (待补)**：<field name>" placeholder
- User answers "Will not provide" / "Do not write this chapter" → skip that chapter
- **Forbidden**: When materials are missing, **not** asking the user, and directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern

### B. External Marketing Materials (**Forbidden to use "To Be Supplemented (待补)" Placeholder**) · 2026-06-XX New Rule

**Applies to**: Pre-Sales Proposal (售前方案) (the only currently applicable type)

- ❌ **Forbidden** to use "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document for external submission)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder
- ❌ **Forbidden** to continue writing the body when any of the 5 business materials (#11-15) is unfilled
- ✅ When user **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ After user fills in all 5 business materials → take the X1 path to write the complete proposal
- See `references/intent_detail.md` section "E2 Pre-Sales Proposal 3-Choice-1 Decision" for details

### C. Administrative Documents (Allow "To Be Supplemented (待补)" Placeholder, but Must Ask User First)

**Applies to**: Weekly Reports / Meeting Minutes / Change Records

- When materials are missing → **Must first** invoke `intent-clarification` taking the B.data dimension to ask the user
- User provides specific content → write it directly
- User answers "To Be Supplemented (待补)" / "Mark as To Be Supplemented for now" → allowed to use "**To Be Supplemented (待补)**：<field name>" placeholder
- **Forbidden**: When materials are missing, **not** asking the user, and directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern

### Anti-Patterns (Strictly Forbidden for All Type B Documents)

- ❌ Type B documents containing "**To Be Supplemented (待补)**" placeholder → must be deleted and trigger X3 exit
- ❌ Type B documents continuing to write the body when any of the 5 business materials is unfilled
- ❌ Type B documents using "Example content" or "Industry general" as placeholder
- ❌ Type A/C documents **not** asking the user when materials are missing, and directly marking "To Be Supplemented (待补)"
- ❌ Mechanically applying "To Be Supplemented (待补)" to Type B documents

### Decision Matrix Quick Reference

| Document Type | When Materials Missing | When User Answers "To Be Supplemented (待补)" | When User Answers "Will Not Provide" |
|---|---|---|---|
| A. Internal Process Documents | Must ask | Allowed "**To Be Supplemented (待补)**：<field name>" | Skip that chapter |
| **B. External Marketing Materials** | **Exit X3** | **Exit X3** | **Exit X3** |
| C. Administrative Documents | Must ask | Allowed "**To Be Supplemented (待补)**：<field name>" | Skip that chapter |

</HARD-GATE: Differentiated "To Be Supplemented (待补)" Handling by Document Type>

---

## Step 0: Scenario Dispatch (Required · First Step)

**The first thing to do when a user question comes in**: identify the scenario type.

| Scenario | User Phrasing Characteristic | Required Question Dimensions (**Fixed Order**) |
|---|---|---|
| `A0.technical_doc` | "Write XX plan/design/test/deployment/training" | **1. E.intent_detail (4-Choice-1 Creation Mode)** → 2. A.intent (doc_type) → 3. C.environment (10 technical points + 5 business materials for E2 scenario) |
| `A0.administrative` | "Change record / weekly report / meeting minutes" | 1. E.intent_detail → 2. A.intent (doc_type) → 3. D.document_attr |
| `A0.factual_query` | "When / Who / How many / Where" | A.intent (fact/decision) (E.intent_detail not applicable) |
| `A0.advisory` | "Suggest / Should / Which / How to choose" | A.intent (decision) + three-layer framework (E.intent_detail not applicable) |

**If unable to identify**: actively ask the user "Do you want to write a document / query facts / get advice?"

**Key points**:

- Technical document scenarios **must first ask E.intent_detail** (4-Choice-1 Creation Mode), then ask A.intent 5 sub-items, finally ask C.environment
- Brand-new independent generation (E2) scenarios **must** additionally ask the 5 business material sub-items of C.environment (see `references/tech_value_proposition.md`)
- Must not skip E.intent_detail to directly ask doc_type; must not skip E.intent_detail when action_intent = "Generate"
- 5 question dimensions (intent/data/environment/document_attr/intent_detail) are named alphabetically, **E.intent_detail is the newly added highest-priority dimension**

## Where to Log (Key: All Process Files Are Outside the Skill)

**Runtime records MUST go to** (not placed inside the skill):

```
<用户工作根>/.project/<project_id>/          ← Sibling to project directory
├── project_log.md         ← Main operation log (1 entry appended per skill flow end)
├── clarification_log.md   ← Clarification log (1 entry appended per Q/A)
├── drafts/                ← Intermediate drafts (drafts from the write flow)
└── session_<YYYY-MM-DD>.md ← Session log (optional)
```

**Do NOT** create or modify files inside the skill itself for runtime records.

## When to Invoke

- **At the start of any skill flow** that needs user input (project root, doc type, intent)
- **At any step** when a new question emerges (missing data, ambiguous requirement, environmental constraint)
- **When prior answer in log** is ambiguous or outdated
- **NOT for trivial one-word confirmations** that the user has already implicitly given

## Checklist

1. **Identify dimension** — see `references/clarification_dimensions_checklist.md` (4 scenarios: intent / data / environment / document_attr)
2. **Read existing log** at `<用户工作根>/.project/<project_id>/clarification_log.md`
   - Prior answer exists → show it + ask "confirm or update"
3. **Scan project artifacts** for evidence (策划表/contract/requirements) using `explore(...)`
   - If found → cite file + line + show excerpt
4. **Ask user** using the dimension-specific template
5. **Handle "TBD/待定"** — re-ask: "stop or provide details"
6. **Append row to log** to `<用户工作根>/.project/<project_id>/clarification_log.md` using file write tools
7. **Return value** to calling skill
8. **After skill flow ends** — append to `<用户工作根>/.project/<project_id>/project_log.md` using file write tools

## 5 Dimensions (2026-06-XX Reinforcement · Added E.intent_detail)

| Scenario | Sub-items | Reference template |
|---|---|---|
| A. Process Clarification (intent) | 5 sub-items (see file) | `../project-doc-query/references/intent.md` |
| B. Data Integrity (data) | Chapters with no data / numeric fields missing | `../project-doc-write/references/data_missing_section.md`<br>`../project-doc-write/references/numeric_field_missing.md` |
| C. Environment/Technology/Compliance/Business (environment) | **10 technical points + 5 business materials (Required for E2)** | `../project-doc-outline/references/tech_*.md` (10 files)<br>`../project-doc-outline/references/tech_value_proposition.md` (5 business materials) |
| D. Document Attributes (document_attr) | Role signoff / Document status | `../project-doc-write/references/role_signoff.md`<br>`../project-doc-write/references/doc_status.md` |
| **E. Creation Mode (intent_detail) · New** | **4-Choice-1 Generation/Writing Mode (E1/E2/E3/E4)** | **`./references/intent_detail.md`** |

## Key Principles

1. **One dimension per call** - Don't bundle intent + data + env
2. **Multiple choice preferred** - 4 options max
3. **Show prior first** - Avoid re-asking
4. **Cite source+line** - When from artifacts
5. **TBD/待定 is not an answer** - Re-ask: stop or provide
6. **Persist to log** - All Q/A in `<用户工作根>/.project/<project_id>/clarification_log.md`
7. **Re-entrant** - Can be called from any step
8. **All files outside skill** - Process files all in `.project/<project_id>/`, **NOT inside the skill**

## Anti-Patterns

| Anti-Pattern | Consequence |
|---|---|
| Asking inline within SKILL.md without invoking this skill | 5 inconsistent clarifications |
| Skipping clarification and giving "should/suggest" directly | Violates HARD-GATE |
| Treating "TBD/待定" as a valid answer and continuing | Incomplete outline causes rework later |
| Not recording clarification results | Repeated questions across skills |
| Bundling multiple dimensions in one ask | Answers interfere with each other |
| Writing process files under skill/references/ | Violates "process files externalized" principle |

## After Clarification

After the calling skill receives the return value:
- Use the return value to continue
- Do not ask the same dimension again (unless user explicitly says "ask again")
- Inform subsequent skills of the path to clarification_log.md
- After the flow ends, append to `<用户工作根>/.project/<project_id>/project_log.md` using file write tools
