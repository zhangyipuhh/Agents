
-- ============================================================
-- 2026-07-02 新增：project 智能体依赖的 skills 种子数据
-- 来源：app/skills/project-doc-*/SKILL.md 与 app/skills/intent-clarification/SKILL.md
-- 幂等：ON CONFLICT (name) DO UPDATE 可重复执行
-- ============================================================

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-overview',
    '',
    '',
    'Use when any conversation involves software-engineering project documents (策划表/requirements/design/plans/test/acceptance/deployment) — this skill is the model''s entry point to the project-doc suite, listing all 7 child skills and how to dispatch them. Auto-loaded by models at conversation start when project-doc context detected.',
    'app/skills/project-doc-overview/SKILL.md',
    'app/skills/project-doc-overview',
    $SKILL_PROJECT_PROJECT_DOC_OVERVIEW_BODY$
## Keywords (关键词)

- 套件总览 (suite-overview)
- 元说明 (meta-description)
- 7个skill (seven-skills)
- 调度决策树 (dispatch-decision-tree)
- 场景分流 (scenario-dispatch)
- 流程规范 (workflow-standard)
- 入口文档 (entry-document)
- 不瞎编 (no-fabrication)

# Project Doc Overview (Suite Meta Description · For Model)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

All skills in this suite strictly forbid fabrication during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

See `../intent-clarification/references/no_fabrication.md` and the `<HARD-GATE: NO FABRICATION>` section in `../intent-clarification/SKILL.md` for details.

---

## Scenario Dispatch (Required · First Step)

```dot
digraph dispatch {
    "User question" [shape=box];
    "Question type?" [shape=diamond];
    "Technical document" [shape=box, color=red, style="rounded,filled", fillcolor="#fff5f5"];
    "Management document" [shape=box, color=blue, style="rounded,filled", fillcolor="#f0f8ff"];
    "Factual query" [shape=box, color=green, style="rounded,filled", fillcolor="#f0fff0"];
    "Advisory" [shape=box, color=purple, style="rounded,filled", fillcolor="#f8f0ff"];

    "User question" -> "Question type?";
    "Question type?" -> "Technical document\n→ A0.technical_doc\n→ Must ask doc_type + C.environment" [label="Write technical document"];
    "Question type?" -> "Management document\n→ A0.administrative\n→ D.document_attr" [label="Write management document"];
    "Question type?" -> "Factual query\n→ A0.factual_query\n→ A.intent (fact)" [label="Query facts"];
    "Question type?" -> "Advisory\n→ A0.advisory\n→ A.intent (decision) + three-layer framework" [label="Get advice"];
}
```

> **Target reader**: **The model**. After loading this skill, the model should be able to automatically:
> - Know what each of the 7 skills in the suite does and when to invoke them
> - Know that **all "ask the user" actions must first invoke `intent-clarification`**
> - Know the `.project` directory structure and log conventions
> - Know how to orchestrate typical flows

## Purpose

This suite is used to manage **software-engineering project documents** (策划表, requirements, design, plans, test, acceptance, deployment, training, etc.).
This skill is the **model-read** entry document, not a user document.

Core principle: **Deterministic things are done by scripts; things requiring judgment/confirmation are done by the LLM**.

## Suite Roster (7 skills)

| Skill | YAML Description (Concise) | When to Invoke |
|---|---|---|
| `intent-clarification` | Unified clarification protocol: scan project materials → show existing info → ask user → log | **Any** scenario needing user confirmation (re-entrant during flow) |
| `project-doc-hub` | Dispatch entry: accept "project + document" requests → clarify → dispatch to query/outline/write/data | The first step of any "project + document" request |
| `project-doc-query` | Answer project facts/consultation: facts from 策划表/requirements/plans/contracts/emails + decision advisory | User asks "what's in the project", "when is the review" |
| `project-doc-outline` | Generate chapter outlines for 10 document types (no body) | User wants "see outline first" or during hub orchestration |
| `project-doc-write` | Fill body based on existing materials + generate decision advisory (no draft/— placeholder) | User wants "write complete document" |
| `project-doc-workflow` | 4-step pipeline checklist (query→outline→write→save-to-disk) | End-to-end automation scenarios |
| `data-skill` | Business file OCR → SQLite ingestion + self-healing verification (**Independent sub-suite**) | User wants to "ingest" data |

Full YAML descriptions see `references/skill_yaml_descriptions.md`.

## Hard Rule: Every User-Facing Question Goes Through `intent-clarification`

When the model needs to ask the user at any time:
- Project root, target document type, intent (query/generate/update)
- Fact vs decision, project-related vs industry-general
- Hardware/software/network/deployment/security level/localization/system architecture/localization list
- Document status / role signoff table
- Proactively ask when data is missing

**Must** first invoke `intent-clarification`, **forbidden** to ask inline within SKILL.md / reference.

## Process Files Location (Key: All Process Files Under .project/)

```
<用户工作根>/.project/<项目号>/          ← Sibling to project directory (e.g., <工作根>/.project/202410-C0008/)
├── project_log.md                     ← Main operation log (1 entry appended per skill flow end)
├── clarification_log.md               ← Clarification log (1 entry appended per Q/A)
├── drafts/                            ← Intermediate drafts
└── session_<YYYY-MM-DD>.md            ← Session log (optional)
```

**Do NOT** create or modify files inside any skill for runtime records.

## Dispatch Decision Tree

```
User says something related to "project + document"
  │
  ├─ Involves "ingest/OCR/SQLite" → data-skill (Independent sub-suite)
  │
  ├─ Involves "generate/update/write document"
  │   ├─ hub path
  │   │   ├─ Pure query → hub → project-doc-query
  │   │   ├─ Outline only → hub → project-doc-outline
  │   │   └─ Complete document → hub → project-doc-workflow → query→outline→write
  │   └─ Direct to a specific sub-skill (user has specified)
  │
  └─ Involves "ask the user" → Any skill first invokes intent-clarification
```

## Anti-Patterns (Strictly Forbidden for the Model)

| Anti-Pattern | Consequence |
|---|---|
| Directly invoking query/outline/write/data without calling intent-clarification | 5 inconsistent clarifications, repeated questions |
| Asking "what is the project root" inline within SKILL.md | Violates unified protocol |
| Skipping clarification and giving "should/suggest" directly | Violates HARD-GATE |
| Model inventing its own "question phrasing" to bypass intent-clarification | Protocol failure |
| Repeatedly asking the same question across skills | Should read `.project/<项目号>/clarification_log.md` |
| Writing process files under skill/references/ | Violates "process files externalized" principle |
| Skipping append to `.project/<项目号>/project_log.md` | Main log missing |

## Typical Flows

See `references/typical_flows.md` for details.

### Flow A: User Asks "What's in the Project"
1. project-doc-overview (current skill)
2. → intent-clarification (get project root + intent + scope)
3. → project-doc-query → use `explore(...)` to read project files → answer
4. → append operation record to `.project/<项目号>/project_log.md`

### Flow B: User Says "Write a Test Plan"
1. project-doc-overview
2. → intent-clarification (project root + document type + intent)
3. → project-doc-outline
4. → intent-clarification (environment/technology/compliance 10 technical points)
5. → project-doc-write
6. → intent-clarification (data integrity)
7. → Invoke "the skill that operates Word" to convert to .docx
8. → Append change record to `.project/<项目号>/06_变更及暂停/变更记录.md`
9. → append operation record to `.project/<项目号>/project_log.md`

### Flow C: Re-asking During Flow (Clarification is Re-entrant)
Any sub-skill encountering a new question at any step → invoke intent-clarification → log → continue.

    $SKILL_PROJECT_PROJECT_DOC_OVERVIEW_BODY$,
    TRUE,
    0
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-hub',
    '',
    '',
    'Use when the user wants to create, query, or update software-engineering project deliverables (Implementation Plan / Requirements Specification / High-Level Design / Detailed Design / Test Plan / Test Report / Acceptance Report / Implementation & Deployment / Training Plan etc.) under a project root such as <项目根> — acts as the entry point that dispatches to project-doc-query/outline/write/workflow',
    'app/skills/project-doc-hub/SKILL.md',
    'app/skills/project-doc-hub',
    $SKILL_PROJECT_PROJECT_DOC_HUB_BODY$
## Keywords (关键词)

- 项目文档 (project-document)
- 调度入口 (dispatch-entry)
- 软件工程 (software-engineering)
- 项目管理 (project-management)
- 分流调度 (dispatch-routing)
- 多框架 (multi-framework)
- 4步流水线 (four-step-pipeline)
- 售前方案 (pre-sales-proposal)

# Project Doc Hub (Project Management Skill V1 · Main Entry Point)

> **Stage Positioning**: The current suite is at **V1 Basic Capability Version**, and will continue to expand in the future (PMP/PRINCE2/Systems Analyst multi-framework overlay, see "Future Extensions" in each sub-skill).

## Overview

Accepts user requests related to "software-engineering project documents" and serves as the main entry dispatching to:

1. `project-doc-query` — Answers "what's in the project / when to deliver / review milestones" questions
2. `project-doc-outline` — Generates chapter outlines conforming to software-engineering standards based on the target document type
3. `project-doc-write` — Strictly fills the outline based on project materials + generates decision advisory
4. `project-doc-workflow` — Orchestrates the 4-step pipeline checklist

> **Note**: This skill is the **dispatch layer**, it does not directly write documents; document writing is completed in `project-doc-write`.

---

## Trigger Conditions (When to use)

- User mentions "project" + "document" + "generate/query/update" intent (e.g., "write a test plan", "implementation plan outline", "when is the review")
- User provides a project root path (e.g., `<项目根>`)
- User uses this suite's terminology ("project process documents", "策划表", "implementation plan", "high-level design", etc.)

---

## Core Flow (Dispatch · 2026-06-XX Reinforcement)

```
Step 1  Accept request
   ↓
Step 2  Clarification (Dispatch first, then ask · 5 dimensions · Fixed order)
   ↓ (If no project specified, list all projects under root directory and let user choose)
Step 2-a  [New · Required] intent-clarification · E.intent_detail (4-Choice-1 Creation Mode)
   ├─ E1 Generate based on existing materials → proceed to query to load materials
   ├─ E2 Brand-new independent generation  → skip query; must go through C.environment including 5 business materials
   ├─ E3 Incremental update of existing document → proceed to query to load existing docx
   └─ E4 Mimic writing from other project → let user specify reference project, load that docx
   ↓
Step 2-b  intent-clarification · A.intent 5 sub-items (doc_type/project_root/action_intent etc.)
   ↓
Step 2-c  Branch on E dispatch result: C.environment / D.document_attr
   ├─ E1/E3/E4 → C.environment 10 technical points (fill as needed)
   ├─ E2      → C.environment 10 technical points + 5 business materials (**All 5 business materials required**)
   └─ Writing administrative document → D.document_attr
   ↓
Step 2-d  [2026-06-XX New] Pre-Sales Proposal 5-item all-required validation (Required when E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 3
   ├─ Any item unfilled → [X3 Exit] return 5-item required checklist + (a) supplement / (b) hold
   └─ After X3 exit **do not** enter Step 3, **do not** load outline, **do not** write body
   ↓
Step 3  Load and activate corresponding sub-skill
   ├─ Query/consultation only → project-doc-query
   ├─ Outline only     → project-doc-outline
   │   ├─ E1/E3/E4 → outline version A (implementation-detail oriented)
   │   └─ E2      → outline version B (value-proposition oriented, see outline_pre_sales_proposal.md)
   ├─ Generate document   → project-doc-workflow (auto-chain query→outline→write)
   │   ├─ E1/E3/E4 → query → outline A → write regular
   │   └─ E2      → skip query → outline B → write Step 3.B new branch
   └─ Update document   → project-doc-write (incremental mode)
   ↓
Step 4  Collect output location confirmation (project directory vs intermediate draft)
   ↓
Step 5  Report output paths
```

### Future Extension: X2 Company Sales Archive Library (To Be Implemented · 2026-06-XX Reserved Interface)

**Goal**: When the company sales archive library is available, the X2 path can be taken under E2 Pre-Sales Proposal (auto-extract needed materials).

**Interface Reserved**:
- Library path: `<TBD · to be specified by company>` (Recommended: `<company archive root>/sales_archive/<industry>/<client>/<project>/`)
- Library-invoking method: `<TBD>` (Recommended: use `explore(...)` for unified file loading)
- Extraction field mapping: #11-15 business materials ↔ corresponding fields in sales archive
- Status: **Not implemented** in this round; if library is available in the future, `project-doc-hub` in Step 2-c will auto-detect library existence and dispatch to X2

**Current Default Behavior**: Library does not exist → auto-degrade to X1 or X3
```

---

## Key File Loading Method (Rigid Constraint)

- **All file-reading actions MUST use** `explore(...)` to read project files/attachments
- Forbidden to write one-off scripts in `tmp/` or absolute path root directories to read files
- Forbidden to bypass `explore(...)` by directly using "open() by extension"

---

## Mandatory Clarification Items (Call intent-clarification Before Talking to User)

**Forbidden** to ask inline within hub SKILL.md. **Must** invoke `intent-clarification` skill (see `../intent-clarification/SKILL.md` + `../project-doc-query/references/intent.md` for details).

### Step 0: Scenario Dispatch (Required · First Step)

**The first thing to do when a user question comes in**: identify the scenario type.

| Scenario | User Phrasing Characteristic | Required Question Dimensions (**Fixed Order**) |
|---|---|---|
| `A0.technical_doc` | "Write XX plan/design/test/deployment/training" | **1. E.intent_detail (4-Choice-1 Creation Mode)** → 2. A.intent (doc_type) → 3. C.environment (10 technical points + 5 business materials for E2 scenario) |
| `A0.administrative` | "Change record / weekly report / meeting minutes" | 1. E.intent_detail → 2. A.intent (doc_type) → 3. D.document_attr |
| `A0.factual_query` | "When / Who / How many / Where" | A.intent (fact/decision) |
| `A0.advisory` | "Suggest / Should / Which / How to choose" | A.intent (decision) + three-layer framework |

**Key points**:

- Technical document scenarios **must first ask E.intent_detail** (4-Choice-1 Creation Mode), then ask A.intent 5 sub-items
- E2 brand-new independent generation scenarios **must** additionally ask the 5 business material sub-items of C.environment
- Must not skip E.intent_detail to directly ask doc_type

### Step 1: 5 intent Dimension Sub-items + E.intent_detail (New)

Clarification items total 6 sub-items (including newly added E):

**A.intent (5 sub-items, in order)**:
1. Fact/Decision (intent_fact_or_decision)
2. Scope (scope_project_or_industry)
3. Project root directory (project_root)
4. Target document type (doc_type)
5. Action (action_intent: query / generate / update / delete)

**E.intent_detail (New · Required when action_intent = generate/update)**:
- 4-Choice-1 Creation Mode: E1 Based on existing materials / **E2 Brand-new independent** / E3 Incremental update / E4 Mimic other
- See `../intent-clarification/references/intent_detail.md` for details

---

## Output Location Convention

| Output         | Location                                                         |
| ------------ | ------------------------------------------------------------ |
| Final formal document | `<项目根>/03_技术文档及评审/<corresponding subdirectory>/<document name>.md`      |
| Change record     | `<项目根>/06_变更及暂停/变更记录.md` (append)               |
| Intermediate draft  | `<工作根>/.aiassistive/output/<项目号>/<document name>_草稿.md` |

---

## ⚠️ Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Writing Code)

**Forbidden** to skip clarification or violate the clarification order in the following scenarios:

- ❌ action_intent = "generate" but E.intent_detail not asked (don't know if it's "based on materials" or "brand-new") → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 5 business materials not asked → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 10 technical points not asked → considered an anti-pattern
- ❌ Pre-Sales Proposal / external material scenario but still writing "specific fields/interfaces/table structure" → considered an anti-pattern
- ❌ Only when user asks "why didn't you ask" do you go back and ask clarification → considered an anti-pattern (should be asked in the first clarification)
- ❌ Skipping E.intent_detail to directly ask doc_type → considered an anti-pattern (order reversed)

### ⚠️ Differentiated Anti-Pattern Redline by Document Type (2026-06-XX Second Reinforcement · Read Before Writing Code)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to have "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder (Q3 decision)
- ❌ **Forbidden** to use "**To Be Supplemented (待补)**：<field name>" as placeholder
- ❌ **Forbidden** to continue writing when any of the 5 business materials is unfilled (All 5 required, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any of 5 items unfilled → still taking X1 path to write outline → considered an anti-pattern
- ✅ User **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ User fills in all 5 business materials → take the X1 path to write the complete proposal

#### C. Administrative Documents (Weekly Reports / Meeting Minutes / Change Records)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal with any of 5 items unfilled and **continuing** to take X1 path to write outline → considered an anti-pattern
- ❌ Pre-Sales Proposal with a chapter outline full of "To Be Supplemented (待补)" → considered an anti-pattern
- ❌ Pre-Sales Proposal using "Example content" or "Industry general" as placeholder → considered an anti-pattern
- ❌ Mechanically applying "To Be Supplemented (待补)" to Pre-Sales Proposal → considered an anti-pattern

---

## Future Extensions (Reserved, Not Implemented)

- Program/Portfolio Management (PgMP/MSP)
- Agile Dual-Track (Scrum/SAFe)
- Quantitative Project Management (QPM/CMMI)
- AI-Assisted Decision Making (based on historical project databases)

---

## Resource References

- Project root directory and subdirectory mapping table: `references/project_root_index.md`
- 策划表 subtag description template: `references/planning_sheet_subtag_template.md`
- Decision advisory template: `references/decision_advisory_template.md`
- **Meta description skill (each skill in the suite introduction)**: `../project-doc-overview/SKILL.md`
- **Unified clarification protocol**: `../intent-clarification/SKILL.md`
  - intent 5 sub-items: `../project-doc-query/references/intent.md`
  - environment 10 technical points: `../project-doc-outline/references/tech_*.md`
- .project log management: append operation records to `.project/<项目号>/project_log.md` and clarification rows to `.project/<项目号>/clarification_log.md`

    $SKILL_PROJECT_PROJECT_DOC_HUB_BODY$,
    TRUE,
    1
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-query',
    '',
    '',
    'Use when the user asks questions about a software-engineering project''s documents, milestones, deliverables, review schedule, or wants PMO-level advisory — applies three-layer framework overlay (PMP framework layer + PRINCE2 implementation layer + Systems Analyst practice layer) and forces intent-clarification (fact vs decision) before answering',
    'app/skills/project-doc-query/SKILL.md',
    'app/skills/project-doc-query',
    $SKILL_PROJECT_PROJECT_DOC_QUERY_BODY$
## Keywords (关键词)

- 事实查询 (factual-query)
- 决策建议 (decision-advisory)
- PMP框架 (pmp-framework)
- PRINCE2 (prince2)
- 系统分析师 (systems-analyst)
- 三层框架 (three-layer-framework)
- 评审计划 (review-plan)
- 框架叠加 (framework-overlay)

# Project Doc Query (Query / Consultation)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: This skill is currently at **V1 Basic Capability Version**, will be extended to Program/Agile/Quantitative Management in the future.

---

## ⚠️ Anti-Pattern Redline (Read Before Writing Code · 2026-06-11 Reinforcement)

**Forbidden** to use in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly reading xlsm/xlsx
- ❌ `from docx import Document` directly reading docx
- ❌ `from pypdf import PdfReader` directly reading pdf
- ❌ `import csv` / `import json` / `import email` directly reading csv/json/eml

**Must** be changed to invoke `explore(...)` for reading project files/attachments.

### Quick Entry (To Avoid Writing One-Off Scripts)

| Pain Point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need to search within file content | Use `explore(file_path="<path>", keyword="<keyword>")` |
| Need structured output | `explore(...)` returns readable text; process it directly |

**Code violating this constraint is considered an anti-pattern** and should be rewritten to call `explore(...)`.

---

## Overview

Provides answers for two types of questions about software-engineering projects: **facts/data** and **decision advisory**, applying the **PMP + PRINCE2 + Systems Analyst three-layer framework overlay**.

Before answering, **must** first do "intent clarification" (fact vs decision); the answer **must** explicitly mark the framework used.

---

## Trigger Conditions

- User asks "what's in the project / when to deliver / who's responsible / how are reviews arranged"
- User asks "what should this document contain / how to determine test coverage / how to handle risks"
- User wants PMO-level advisory

---

## Rigid Constraints

1. **Clarification must go through intent-clarification**: When this skill starts, **must** invoke `intent-clarification` skill (see references/intent.md for details). **Forbidden** to ask "fact/decision" or "project root" inline within SKILL.md.
2. **Mandatory framework tag**: First line of each answer outputs `【Framework: {PMP|PRINCE2|Systems Analyst} · {Framework Layer|Implementation Layer|Practice Layer}】`.
3. **Traceable evidence**: All fact-type answers must attach "project evidence" — 策划表 subtag name + document path + row/cell.
4. **Three-layer framework overlay** (mutually non-conflicting):
   - **PMP Framework Layer**: 5 Process Groups / 10 Knowledge Areas (provides "management system panorama")
   - **PRINCE2 Implementation Layer**: 7 Principles / 7 Themes / 7 Processes (provides "how to do it specifically")
   - **Systems Analyst Practice Layer**: 5 Major Modules (System Planning/Requirements Analysis/System Design/Test & Maintenance/Informatization) (provides "software engineering practice")
5. **Strictly forbid fabrication**: All numbers, dates, people names in answers must come from project materials; invoke `intent-clarification` for the data dimension when materials are missing.

---

## Core Flow

```
Step 1  Invoke intent-clarification skill (clarify intent + project root + scope)
   ├─ 5 sub-items see references/intent.md
   └─ Re-ask when necessary during flow (clarification is re-entrant)
   ↓
Step 2  Load project materials per directory conventions (use `explore(...)` to read files)
   ↓
Step 3  If fact/data: directly give data + evidence
         If decision: select framework → reference framework cheat sheet → give advice (with project evidence)
   ↓
Step 4  Mark framework tag + data source
   ↓
Step 5  Append operation record to `.project/<项目号>/project_log.md`
```

---

## Framework Selection Decision Tree

| Scenario | Priority Framework | Layers |
|---|---|---|
| Review/deliverable arrangement | PMP · Framework Layer (Schedule Management) | + PRINCE2 Implementation Layer (Management Stage Boundaries) |
| Scope/change control | PRINCE2 · Implementation Layer (Change Theme) | + PMP (Scope/Change/Integration) |
| Quality/test | Systems Analyst · Practice Layer (Test & Maintenance) | + PMP (Quality Management) + PRINCE2 (Quality Theme) |
| Risk | PMP · Framework Layer (Risk Management) | + PRINCE2 (Risk Theme) |
| Resource/cost | PMP · Framework Layer (Resource/Cost) | + PRINCE2 (Business Case Theme) |
| Requirements analysis | Systems Analyst · Practice Layer (Requirements Analysis) | + PMP (Scope) |
| Architecture/design | Systems Analyst · Practice Layer (System Design) | + PMP (Scope/Schedule) |
| Implementation/deployment | Systems Analyst · Practice Layer (Implementation O&M) | + PMP (Executing) + PRINCE2 (Delivery Theme) |
| Closing/acceptance | PMP · Framework Layer (Closing Process Group) | + PRINCE2 (Continued Business Validation) |

---

## Key File Loading Method

- **All file-reading actions MUST use** `explore(...)` to read project files/attachments
- PDF / eml extracted text < 100 characters is considered a scanned document → prompt user to provide a readable version

---

## Resource References

- Process clarification (intent 5 sub-items, scheduled by intent-clarification): `references/intent.md`
- Framework cheat sheets: `references/framework_pmp_quick_reference.md`, `references/framework_prince2_quick_reference.md`, `references/framework_systems_analyst_quick_reference.md`
- Framework selection decision tree: `references/framework_selection_decision_tree.md`
- 策划表 field cheat sheet: `references/planning_sheet_field_quick_reference.md`
- Document type directory cheat sheet: `references/document_type_directory_quick_reference.md`
- Review plan extraction method: `references/review_plan_extraction_method.md`
- Meta description (each skill in the suite introduction): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Future Extensions (Reserved)

- Program/Portfolio (PgMP/MSP)
- Agile Dual-Track (Scrum/SAFe)
- Quantitative Management (QPM/CMMI)
- AI-Assisted Decision Making (based on historical project databases)

    $SKILL_PROJECT_PROJECT_DOC_QUERY_BODY$,
    TRUE,
    2
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-outline',
    '',
    '',
    'Use when the user wants a chapter outline (no body content) for any of the 10 supported software-engineering deliverable types (Pre-Sales Proposal / Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan) — picks the corresponding reference template and applies software-engineering standard chapter structure',
    'app/skills/project-doc-outline/SKILL.md',
    'app/skills/project-doc-outline',
    $SKILL_PROJECT_PROJECT_DOC_OUTLINE_BODY$
## Keywords (关键词)

- 文档大纲 (document-outline)
- 章节结构 (chapter-structure)
- 10种文档 (ten-document-types)
- 售前方案 (pre-sales-proposal)
- 实施细节 (implementation-detail)
- 价值主张 (value-proposition)
- 软件工程规范 (software-engineering-standard)
- 创作模式 (creation-mode)

# Project Doc Outline (Document Outline)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: V1 Basic Capability Version.

## Overview

Selects the corresponding reference template by target document type, outputs **chapter-level outline** (without body content).

The outline must conform to software-engineering standards (GB/T 8564, ISO/IEC/IEEE 42010, ISO 21500), and **must not contain any fabricated body content**.

---

## Trigger Conditions

- User says "write a test plan outline"
- User says "what chapters should an implementation plan have"
- User provides target document type + needs "see outline first"

## Not Applicable

- User wants "complete document" (switch to `project-doc-write`)
- User only asks "what documents does the project have" (switch to `project-doc-query`)

---

## Rigid Constraints

1. **Outline ≠ Body**: Only output chapter titles (level 1/2), do not write body
2. **Chapter numbering convention**: Level 1: 1, 2, 3; Level 2: 1.1, 1.2; Level 3: 1.1.1 (when necessary)
3. **Each chapter must explain**: purpose (what problem this chapter solves) + required sub-sections (if any spec)
4. **Reference template source**: Default extracts chapters from `<项目根>/03_技术文档及评审/01_实施方案/*.docx`; if empty, fall back to 02 Requirements → 03 High-Level
5. **Extraction method**: Use `explore(...)` to read existing docx files and extract chapter structure
6. **Environment/Technology/Compliance clarification required**: Before writing the outline, **must** invoke `intent-clarification` (C.environment dimension, 10 technical point references: tech_hardware.md / tech_software.md / tech_database.md / tech_network.md / tech_deployment.md / tech_third_party_ops.md / tech_security_level.md / tech_localization.md / tech_architecture.md / tech_localization_list.md)
   - Even if user has uploaded materials, **still must ask** and completely cite the original + mark source file + line number, let user confirm "whether to write based on existing info"
   - User answers "TBD/待定" → re-ask "whether to stop outline generation / provide detailed information"
   - Asking result is recorded to `.project/<项目号>/clarification_log.md`
   - Skipping this step and directly writing the outline is considered an anti-pattern

---

## Supported 10 Document Types

| # | Type | Reference Template |
|---|---|---|
| 1 | Pre-Sales Proposal | `references/outline_pre_sales_proposal.md` |
| 2 | Requirements Specification | `references/outline_requirements_specification.md` |
| 3 | High-Level Design Specification | `references/outline_high_level_design_specification.md` |
| 4 | Detailed Design Specification | `references/outline_detailed_design_specification.md` |
| 5 | Implementation Plan | `references/outline_implementation_plan.md` |
| 6 | Test Plan | `references/outline_test_plan.md` |
| 7 | Test Report | `references/outline_test_report.md` |
| 8 | Acceptance Report | `references/outline_acceptance_report.md` |
| 9 | Implementation & Deployment Plan | `references/outline_implementation_deployment_plan.md` |
| 10 | Training Plan | `references/outline_training_plan.md` |
| — | Other Process Documents | `references/outline_other_process_documents.md` |

---

## Core Flow (2026-06-XX Second Reinforcement · Dispatch by E.intent_detail · With X3 Exit)

```
Step 0  [Required · Fixed order] Invoke intent-clarification
   ├─ Step 0-a  E.intent_detail (4-Choice-1 Creation Mode) —— Required
   ├─ Step 0-b  A.intent (doc_type) —— Required
   └─ Step 0-c  C.environment
       ├─ E1/E3/E4 → 10 technical points (fill as needed)
       └─ E2      → 10 technical points + **5 business materials required** (see tech_value_proposition.md)
   ↓
Step 0-d  [2026-06-XX New · Pre-Sales Proposal 5-item all-required validation] (Required when E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 0-e
   ├─ Any item unfilled → [X3 Exit] return 5-item required checklist + (a) supplement / (b) hold
   │   └─ After X3 exit **do not** enter subsequent Step 1-6, **do not** load outline, **do not** write body
   └─ E2 + other doc_type → take original "all 5 items required" constraint (**do not** force X3 exit, **do not** forbid "To Be Supplemented (待补)" placeholder)
   ↓
Step 0-e  [Select version by E]
   ├─ E1/E3/E4 → take corresponding reference template's "Version A"
   └─ E2      → 走对应 reference 模板的"版本 B"（如 outline_pre_sales_proposal.md 版本 B）
   ↓
Step 1  Receive target document type + Creation Mode (E)
   ↓
Step 2  Load corresponding reference template (select version by E)
   ↓
Step 3  (Optional) Extract format template from existing similar docx in project (use `explore(...)`)
   ├─ E1/E3/E4 → read docx in project and extract chapter structure
   └─ E2      → skip (no project materials); optional "reference industry-general docx"
   ↓
Step 4  Output "chapter-level" outline (no body)
   ├─ E1/E3/E4 → implementation-detail oriented
   ├─ E2 + Pre-Sales Proposal → value-proposition oriented (embed "Customer Value" + "Relative Advantage" at end of each chapter); **"To Be Supplemented (待补)" placeholder not allowed**
   └─ E2 + other doc_type → value-proposition oriented; "To Be Supplemented (待补)" placeholder **only** used when user has explicitly agreed
   ↓
Step 5  Mark "Purpose" and "Required sub-section" hints at end of each chapter
   ├─ E1/E3/E4 → data source marking
   ├─ E2 + Pre-Sales Proposal → data source marking (**not** using "**To Be Supplemented (待补)**" placeholder)
   └─ E2 + other doc_type → data source marking / "**To Be Supplemented (待补)**" placeholder (when user has explicitly agreed)
   ↓
Step 6  Append operation record to `.project/<项目号>/project_log.md`
```

### Future Extension: X2 Company Sales Archive Library (To Be Implemented · 2026-06-XX Reserved Interface)

**Goal**: When the company sales archive library is available, the X2 path can be taken under E2 Pre-Sales Proposal (auto-extract needed materials → take X1 path to write complete proposal, **do not** trigger X3 exit).

**Interface Reserved**:
- Library path: `<TBD · to be specified by company>` (Recommended: `<company archive root>/sales_archive/<industry>/<client>/<project>/`)
- Library-invoking method: `<TBD>` (Recommended: use `explore(...)` for unified file loading)
- Extraction field mapping: #11-15 business materials ↔ corresponding fields in sales archive
- Status: **Not implemented** in this round; if library is available in the future, this skill in Step 0-d will auto-detect library existence and dispatch

**Current Default Behavior**: Library does not exist → auto-degrade to X1 (user provides) or X3 (exit)

---

## Resource References

- 10 outline references: `references/outline_*.md`
- 10 technical point references (scheduled by intent-clarification): `references/tech_*.md`
- Meta description (each skill in the suite introduction): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Anti-Pattern Redline (Rigid Constraint · 2026-06-11 Reinforcement · Read Before Writing Code)

**Forbidden** to use in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly reading xlsm/xlsx
- ❌ `from docx import Document` directly reading docx (for chapter extraction)
- ❌ `import csv` / `import json` directly reading csv/json

**Must** be changed to invoke `explore(...)` for reading project files/attachments:

| Scenario | Tool |
|---|---|
| Extract chapters from in-project docx as format template | `explore(file_path="<path>")` |
| Read other project files | `explore(file_path="<path>")` |

### Quick Entry (To Avoid Writing One-Off Scripts)

| Pain Point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need structured output | Process `explore(...)` result directly |

**Code violating this constraint is considered an anti-pattern** and should be rewritten to call `explore(...)`.

---

## ⚠️ Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Writing Code)

**Forbidden** to skip clarification or violate the clarification order in the following scenarios:

- ❌ action_intent = "generate" but E.intent_detail not asked (don't know if it's "based on materials" or "brand-new") → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 5 business materials not asked → considered an anti-pattern
- ❌ E2 brand-new scenario but C.environment 10 technical points not asked → considered an anti-pattern
- ❌ E2 Pre-Sales Proposal scenario not selecting outline Version B (mistakenly using Version A) → considered an anti-pattern
- ❌ Pre-Sales Proposal / external material scenario but still writing "specific fields/interfaces/table structure" → considered an anti-pattern
- ❌ Only when user asks "why didn't you ask" do you go back and ask clarification → considered an anti-pattern (should be asked in the first clarification)
- ❌ Skipping E.intent_detail to directly ask doc_type → considered an anti-pattern (order reversed)
- ❌ All 5 business materials as "To Be Supplemented (待补)" and still writing body → considered an anti-pattern (violates `<HARD-GATE: NO FABRICATION>`)

### ⚠️ Differentiated Anti-Pattern Redline by Document Type (2026-06-XX Second Reinforcement · Read Before Writing Code)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to have "**To Be Supplemented (待补)**" placeholder (Pre-Sales Proposal is a finished document)
- ❌ **Forbidden** to use "Example content / Industry general template / Company's typical scale" as placeholder
- ❌ **Forbidden** to use "**To Be Supplemented (待补)**：<field name>" as placeholder
- ❌ **Forbidden** to continue writing when any of the 5 business materials is unfilled (All 5 required, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any of 5 items unfilled → still taking X1 path to write outline → considered an anti-pattern
- ✅ User **cannot provide materials** → **Exit X3 directly**: return the X3 refuse-to-write template + 5 required materials checklist
- ✅ User fills in all 5 business materials → take the X1 path to write the complete proposal

#### C. Administrative Documents (Weekly Reports / Meeting Minutes / Change Records)
- ✅ Missing materials → **Must** invoke intent-clarification to continue asking the user (D4 decision)
- ❌ Missing materials → **Not** asking, directly marking "To Be Supplemented (待补)" placeholder → considered an anti-pattern
- ✅ User **explicitly says "mark as To Be Supplemented for now"** → allowed "**To Be Supplemented (待补)**：<field name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal with any of 5 items unfilled and **continuing** to take X1 path to write outline → considered an anti-pattern
- ❌ Pre-Sales Proposal with a chapter outline full of "To Be Supplemented (待补)" → considered an anti-pattern
- ❌ Pre-Sales Proposal using "Example content" or "Industry general" as placeholder → considered an anti-pattern
- ❌ Mechanically applying "To Be Supplemented (待补)" to Pre-Sales Proposal → considered an anti-pattern

---

## Future Extensions

- Industry-specific (Government/Finance/Healthcare) outline versions
- Auto-derive project phase document structure from 策划表 WBS

    $SKILL_PROJECT_PROJECT_DOC_OUTLINE_BODY$,
    TRUE,
    3
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-write',
    '',
    '',
    'Use when the user has an approved outline and wants the document body filled in based strictly on existing project artifacts (planning sheet / requirements / contract / plan / weekly report etc.) — generates decision-and-opinion from real project data deltas, never invents content, asks user when info is missing',
    'app/skills/project-doc-write/SKILL.md',
    'app/skills/project-doc-write',
    $SKILL_PROJECT_PROJECT_DOC_WRITE_BODY$
## Keywords (关键词)

- 填充正文 (body-filling)
- 决策与意见 (decision-advisory)
- 严禁虚构 (no-fabrication)
- 数据完整性 (data-integrity)
- 净化规则 (purification-rule)
- word落盘 (word-save)
- 变更记录 (change-log)
- 售前方案 (pre-sales-proposal)

# Project Doc Write (Body Filling + Decision Advisory)

## Hard Rule: No Fabrication

**This skill must NEVER fabricate** any of the following at any stage of execution:
- Person names / dates / numbers / tool names / role signoff table / document status / framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` on the relevant dimension
2. User answers "TBD" / "待定" → re-ask "stop or provide detailed info"
3. User did not specify → **do not write**, **do not auto-fill defaults**

**Strictly forbidden "placeholder for later"**:
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **Pending-fill**: <field-name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md`.

> **Stage**: V1 base capability.

## Overview

On the chapter outline output by `project-doc-outline`, **strictly based on existing project artifacts** fill in the body, and generate "Decision and Opinion" based on the delta between actual values and baseline values from planning sheet / contract / weekly report.

> **Core principle: mechanical work is done by tools; judgments are made by the LLM.**
> Reading planning sheet subtags, extracting docx chapters — all "mechanical work" goes through `explore(...)`; body writing and decision advisory are done by the model.

---

## Trigger Conditions

- User already has an outline (generated by hub or provided by outline)
- User requires "write a complete document based on existing project artifacts"
- User requires "complete/update a document"

---

## Rigid Constraints

1. **Strictly no fabrication**: every body section must have project evidence. Missing evidence → **actively ask** the user.
2. **Format template**: by default extract chapters from `<项目根>/03_技术文档及评审/01_实施方案/*.docx` as the format template.
3. **Decision and Opinion source**: `references/decision_advisory_generation_rule.md` + `references/no_fabrication_redline_checklist.md`.
4. **Multi-framework overlay**: every decision-and-opinion entry must be tagged `【Framework: {PMP|PRINCE2|Systems Analyst} · {layer}】`.
5. **Change log mandatory**: after each document write, **must** append a record to `<项目根>/06_变更及暂停/变更记录.md` (in the canonical planning sheet subtag format).
6. **Read files via `explore(...)`**: forbidden to write one-off scripts in `tmp/` or `D:\` root. Use `explore(file_path="<path>")` to read project files/attachments.
7. **Scanned document detection**: PDFLoader extracts < 100 characters → treat as scanned → ask user to provide a readable version.
8. **TOC mandatory**: every generated .md document **must** contain a `## Table of Contents` section listing 1-3 level heading links (markdown static layer).
9. **Content purification**: when writing body, follow `references/document_content_purification_rule.md` — do not write "Draft for review", do not write "Prepared by/Reviewed by/Approved by" (when planning sheet has not specified), do not write "—" placeholders, do not write empty quotes, do not write tools not mentioned in project artifacts.
10. **Sections without data**: use `**Pending-fill**: [specific explanation]` pattern, do not write "—" placeholders; before writing, use `references/data_integrity_query_template.md` to actively ask the user.
11. **word save-to-disk**: after writing .md **must** convert to .docx via "word operation skill" (e.g. docx-skill) and save to project directory. write **does not** implement markdown → docx itself, **does not** hard-code third-party skill paths. See `references/word_save_to_disk_workflow.md`.

---

## Core Workflow (2026-06-XX Second Reinforcement — By E.intent_detail Branching — With X3 Exit)

```
Step 1  Receive outline (from outline) + E.intent_detail branch identifier
   ↓
Step 1.0  [2026-06-XX New · Pre-Sales Proposal 5-Item All-Required Check] (E2 + doc_type = Pre-Sales Proposal)
   ├─ All 5 items filled → enter Step 2
   ├─ Any one not filled → [X3 Exit] return 5-item checklist + (a) supplement / (b) suspend
   │   └─ After X3 exit, **do not** enter Step 2-7, **do not** write body
   └─ Other doc_type → original flow
   ↓
Step 2  Load project artifacts (DocumentLoader)
   ├─ E1/E3/E4 → load project artifacts (planning sheet / requirements / contract etc.)
   └─ E2      → skip project artifact loading (none available); directly load value_proposition_template.md
   ↓
Step 3  [Key · By E branching] Fill in order of chapters
   ↓
Step 3.0  Judge E.intent_detail branch
   ├─ E1/E3/E4 → Step 3.A Regular Branch
   └─ E2      → Step 3.B New Branch
   ↓
Step 3.A Regular Branch (E1/E3/E4 · Based on artifacts)
   ├─ Content has evidence → write directly
   ├─ Content no evidence → invoke intent-clarification (B.data dimension) **continue to ask user** (D4 decision)
   ├─ User answers concrete content → write on the spot
   ├─ User answers "mark pending first" / "fill in later" → mark "**Pending-fill**: <field-name>" placeholder
   ├─ User answers "not providing for now" → skip that section
   ├─ Data-driven section without data → same as above via B.data
   ├─ Role signoff table / document status → invoke intent-clarification (D.document_attr dimension)
   └─ Content exceeds spec → notify out-of-scope, ask whether to keep
   ↓
Step 3.B New Branch (E2 · 2026-06-XX Second Reinforcement)
   ├─ 3.B.0 [2026-06-XX New] Pre-check: all 5 business materials filled
   │    ├─ Any one not filled → [X3 Exit] **do not** enter 3.B.1-3.B.7
   │    └─ All filled → enter 3.B.1
   ├─ 3.B.1 Load value proposition template (references/value_proposition_template.md)
   ├─ 3.B.2 Fill by outline Version B (value-proposition-oriented, **no implementation details**)
   ├─ 3.B.3 Each chapter structure = Solution Points + **Customer Value** + **Relative Advantage** + **Data Source** (**no** "Pending-fill" section)
   ├─ 3.B.4 [2026-06-XX Modified] **Forbidden** "**Pending-fill**: <field-name>" placeholders (pre-sales proposal is a finished document)
   ├─ 3.B.5 Do not write "how exactly" — only write "why this is the best approach"
   ├─ 3.B.6 Strictly forbidden: "specific fields / interfaces / table structures / duration numbers / team member names / empty quotes"
   └─ 3.B.7 Industry-specific fields (4.1-4.4 chapter names) dynamically replaced by E2 clarification item 12
   ↓
Step 4  Generate "Decision and Opinion" chapter (references/decision_advisory_template.md)
   ├─ E1/E3/E4 → regular decision advisory
   └─ E2 + Pre-Sales Proposal → **do not** generate "Decision and Opinion" chapter (pre-sales proposal has no such chapter)
   ↓
Step 5  Scanned document detection (references/scanned_doc_handling_rule.md)
   ↓
Step 6  Content purification self-check (references/document_content_purification_rule.md)
   ├─ Remove "Draft for review / Draft" status tags
   ├─ Remove "Prepared by / Reviewed by / Approved by" role table (when planning sheet has not specified)
   ├─ Remove "—" placeholder → change to "**Pending-fill**" section (A/C type) / delete entire section (B type, trigger X3 re-review)
   ├─ Remove empty quotes ("advanced/reliable/easy-to-use/secure/scalable" stacked without evidence)
   ├─ [2026-06-XX New] Differentiated purification by document type:
   │    ├─ A type (internal process): "**Pending-fill**: <field-name>" section **retained** (user has explicitly agreed)
   │    ├─ **B type (pre-sales proposal): "**Pending-fill**" section must be deleted** + trigger X3 re-review (violates "pre-sales proposal is a finished document" principle)
   │    └─ C type (administrative): "**Pending-fill**: <field-name>" section **retained** (user has explicitly agreed)
   ├─ E2 extra: remove "specific fields / interfaces / table structures / duration numbers / team member names"
   └─ Remove tools / terms not mentioned in project artifacts
   ↓
Step 7  Output (project directory final save + AIAssistive\output\ draft)
   ├─ 7.1 Save .md to project directory
   ├─ 7.2 [Key] Check whether "word operation skill" is in the current skill library
   │       ├─ Exists → 7.3
   │       └─ Not exists → notify user to install docx-skill, skip 7.3
   ├─ 7.3 Invoke word skill to convert to .docx (apply styles from references/word_format_template_rule.md)
   ├─ 7.4 Save draft to AIAssistive\output\
   └─ 7.5 Append change record (references/change_record_append_format.md)
```

---

## Resource References

- Format template extraction method: `references/implementation_plan_format_template_extraction.md`
- Software engineering document chapter filling spec: `references/software_engineering_doc_section_filling_spec.md`
- Decision advisory generation rule: `references/decision_advisory_generation_rule.md`
- No-fabrication redline checklist: `references/no_fabrication_redline_checklist.md`
- **Word format template rules** (hard-coded, cover / font / line spacing / header-footer / TOC): `references/word_format_template_rule.md`
- **Word save-to-disk workflow** (Step 7 detailed, with docx-skill self-check): `references/word_save_to_disk_workflow.md`
- **Document content purification rules** (do not write "Draft/— placeholder/Prepared by" etc. useless content): `references/document_content_purification_rule.md`
- **Data integrity reference** (Step 4.2.5 active asking, dispatched by intent-clarification):
  - `references/data_missing_section.md`
  - `references/numeric_field_missing.md`
- **Document attribute reference** (role signoff table / document status):
  - `references/role_signoff.md`
  - `references/doc_status.md`
- Meta description (each skill intro): `../project-doc-overview/SKILL.md`
- Unified clarification protocol: `../intent-clarification/SKILL.md`

---

## Clarification Anti-Pattern Redline (2026-06-XX Reinforcement · Read Before Coding)

**Forbidden** in the following scenarios to skip clarification or violate clarification order:

- ❌ action_intent = "Generate" but no E.intent_detail asked (do not know "based on artifacts" or "new") → anti-pattern
- ❌ E2 new scenario but did not go through C.environment 5 business materials → anti-pattern
- ❌ E2 new scenario but did not go through C.environment 10 technical points → anti-pattern
- ❌ E2 pre-sales proposal scenario did not go through Step 3.B new branch (mistakenly went Step 3.A regular) → anti-pattern
- ❌ Pre-sales proposal / external material scenario but still writing "specific fields/interfaces/table structures" → anti-pattern
- ❌ User asks "why didn't you ask" then going back to supplement clarification → anti-pattern (should have asked during first clarification)
- ❌ Skipping E.intent_detail to ask doc_type directly → anti-pattern (order reversed)
- ❌ 5 business materials all "Pending-fill" still writing body → anti-pattern (violates `<HARD-GATE: NO FABRICATION>`)

### Anti-Pattern Redline Differentiated by Document Type (2026-06-XX Second Reinforcement · Read Before Coding)

Differentiate "missing materials" behavior by document type:

#### A. Internal Process Documents
(Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan)
- ✅ Missing materials → **must** invoke intent-clarification to continue asking user (D4 decision)
- ❌ Missing materials → **do not** ask, directly mark "Pending-fill" placeholder → anti-pattern
- ✅ User **explicitly says "mark pending first"** → allow "**Pending-fill**: <field-name>" placeholder
- ❌ Using "—/TBD/待定" alone

#### B. External Marketing Materials (Pre-Sales Proposal) · 2026-06-XX New Rule
- ❌ **Forbidden** to use "**Pending-fill**" placeholder (pre-sales proposal is a finished document)
- ❌ **Forbidden** to use "example content / industry generic template / company typical scale" placeholder
- ❌ **Forbidden** to use "**Pending-fill**: <field-name>" as placeholder
- ❌ **Forbidden** to continue writing when any of 5 business materials is not filled (all 5 mandatory, D3 decision)
- ❌ E2 + doc_type = Pre-Sales Proposal + any 5-item not filled → still going Step 3.B to write body → anti-pattern
- ❌ E2 + Pre-Sales Proposal Step 6 purification self-check when "**Pending-fill**" section not deleted → anti-pattern
- ✅ User **cannot provide materials** → **direct X3 exit**: return X3 refuse-write template + 5-item mandatory checklist
- ✅ User completes 5 business materials → go Step 3.B to write complete proposal

#### C. Administrative Documents (Weekly Report / Minutes / Change Record)
- ✅ Missing materials → **must** invoke intent-clarification to continue asking user (D4 decision)
- ❌ Missing materials → **do not** ask, directly mark "Pending-fill" placeholder → anti-pattern
- ✅ User **explicitly says "mark pending first"** → allow "**Pending-fill**: <field-name>" placeholder

#### X3 Exit Anti-Patterns
- ❌ Pre-Sales Proposal any 5-item not filled yet **continues** to go Step 3.B to write body → anti-pattern
- ❌ Pre-Sales Proposal written with a body full of "Pending-fill" → anti-pattern
- ❌ Pre-Sales Proposal uses "example content" or "industry generic" placeholder → anti-pattern
- ❌ Mechanically applying "Pending-fill" to pre-sales proposal → anti-pattern

#### Step 6 Purification Self-Check Anti-Patterns
- ❌ A type document "**Pending-fill**: <field-name>" section **mistakenly deleted** (user has explicitly agreed to retain) → anti-pattern
- ❌ B type document "**Pending-fill**" section **not deleted** (pre-sales proposal is a finished document) → anti-pattern
- ❌ Purification self-check list does not distinguish A/B/C 3 types → anti-pattern

---

## Anti-Pattern Redline (Rigid Constraint · 2026-06-11 Reinforcement · Read Before Coding)

**Forbidden** in `python -c "..."` or any Python code:

- ❌ `from DocumentLoader import DocumentLoader, ExcelLoader, ...`
- ❌ `from loader.ExcelLoader import ExcelLoader` / `from loader.WordLoader import WordLoader` etc.
- ❌ `import openpyxl` / `from openpyxl import load_workbook` directly read xlsm/xlsx
- ❌ `from docx import Document` directly read docx
- ❌ `from pypdf import PdfReader` directly read pdf
- ❌ `import csv` / `import json` / `import email` directly read csv/json/eml

**Must** be changed to call `explore(...)` for reading project files/attachments:

| Scenario | Tool |
|---|---|
| Read any file | `explore(file_path="<path>")` |
| Extract docx chapters as format template | `explore(file_path="<path>")` |
| Extract word style baseline | `explore(file_path="<path>")` |

### Quick Entry (Avoid Writing One-Off Scripts)

| Pain point | Solution |
|---|---|
| Need to read project files or attachments | Use `explore(file_path="<path>")` |
| Need structured output | Process `explore(...)` result directly |

**Violations of this constraint are anti-patterns** and should be rewritten as `explore(...)` calls.

---

## Future Extensions

- Auto-derive templates from historical same-type documents
- AI decision advisory scoring (linked with program/PMO database)
- Multi-language version generation

    $SKILL_PROJECT_PROJECT_DOC_WRITE_BODY$,
    TRUE,
    4
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'project-doc-workflow',
    '',
    '',
    'Use when generating a software-engineering project deliverable end-to-end (from initial user request to final document on disk) — orchestrates the 4-step pipeline (hub → query → outline → write) and provides the work-skill checklist',
    'app/skills/project-doc-workflow/SKILL.md',
    'app/skills/project-doc-workflow',
    $SKILL_PROJECT_PROJECT_DOC_WORKFLOW_BODY$
## Keywords (关键词)

- 端到端工作流 (end-to-end-workflow)
- 4步流水线 (four-step-pipeline)
- hub-query-outline-write (hub-query-outline-write)
- 检查清单 (checklist)
- 落盘规范 (save-to-disk-spec)
- 变更记录 (change-log)
- work-skill (work-skill)
- 不瞎编 (no-fabrication)

# Project Doc Workflow (End-to-End Workflow)

## ⚠️ Hard Constraint: No Fabrication (NO FABRICATION)

**This skill strictly forbids** fabrication at **any** step during execution:
- People names / Dates / Numbers / Tool names / Role signoff tables / Document status / Framework tags

**When evidence is missing**:
1. Immediately invoke `../intent-clarification/` with the corresponding dimension
2. User answers "TBD/待定" → re-ask "stop / provide detailed information"
3. User has not specified → **do not write**, **do not fill in default values without permission**

**Strictly forbidden** "write placeholder, fill later":
- ❌ `| XX | — |` / `| XX | TBD |` / `| XX | 待定 |` used alone
- ✅ `| XX | **To Be Supplemented (待补)**：<field name> |` must include explanation

See `../intent-clarification/references/no_fabrication.md` for details.

> **Stage Positioning**: V1 Basic Capability Version.

## Overview

Orchestrates the requests accepted by `project-doc-hub` into an executable checklist following the 4-step pipeline (query → outline → write → save-to-disk + change record), **guiding the work skill (executing agent) to execute in order**.

> **Core principle: Deterministic things are done by scripts; things requiring judgment are done by the LLM.**

---

## Trigger Conditions

- User wants to "generate a complete project document from 0"
- User wants to "write a complete document based on existing project materials"
- Not applicable: query only / outline only / update only (these go to a single sub-skill)

---

## 4-Step Pipeline

```
┌────────────────────────────────────────┐
│  Step 1  project-doc-hub (Accept + Clarify)   │
│  - Invoke intent-clarification for intent dimension │
│  - Get project root + document type + intent        │
│  - Let user choose when there are multiple projects │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 2  project-doc-query (Material Extraction)    │
│  - Load 策划表 xlsm → extract milestones/review plan  │
│  - Load project root → list existing similar docx   │
│  - Extract docx chapters as format template          │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 3  project-doc-outline (Generate Outline)  │
│  - Invoke intent-clarification for environment dimension │
│  - Pick reference template by document type           │
│  - Output "chapter-level" outline (no body)          │
└────────────────────────────────────────┘
                  ↓
┌────────────────────────────────────────┐
│  Step 4  project-doc-write (Fill + Decisions)  │
│  - Invoke intent-clarification for data/document_attr dimension │
│  - Strictly fill body based on existing project materials          │
│  - Actively ask user when materials are missing                  │
│  - Generate "Decision & Advisory" (with [Framework] tags)     │
│  - Append change record                          │
│  - Append operation record to `.project/<项目号>/project_log.md` │
│  - Output to project directory + intermediate draft               │
└────────────────────────────────────────┘
```

---

## Work Skill Execution Checklist

The executing agent must complete each item in order, after each item change `□` to `☑`:

```
□ Step 1 hub
   □ 1.1 List all projects under root directory
   □ 1.2 User selects project (or already provided)
   □ 1.3 User selects target document type
   □ 1.4 User states intent (generate/update/query)
   □ 1.5 User confirms output location

□ Step 2 query
   □ 2.1 Load 策划表 xlsm (via `explore(...)`)
   □ 2.2 Extract milestones/review plan/P&L analysis/risk register
   □ 2.3 List existing similar docx in project (if any)
   □ 2.4 Extract docx chapters as format template (if any, via `explore(...)`)
   □ 2.5 Scan detection (PDF)

□ Step 3 outline
   □ 3.1 Load outline_*.md reference template
   □ 3.2 Output chapter-level outline
   □ 3.3 User confirms outline

□ Step 4 write
   □ 4.1 Fill chapters in order
   □ 4.2 Mark data source for each chapter
   □ 4.3 Actively ask user when materials are missing (do not fabricate)
   □ 4.4 Generate "Decision & Advisory" chapter (with [Framework] + [Strength] + [Data Source])
   □ 4.5 Self-check no-fabrication redline
   □ 4.6 Content purification self-check (remove "draft/— placeholder/compile-review" boilerplate, see write/references/document_content_purification_rule.md)
   □ 4.7 Append change record to <项目根>/06_变更及暂停/变更记录.md
   □ 4.8 Output final document to project directory (.md + .docx)
        ├─ 4.8.1 Save .md to project directory
        ├─ 4.8.2 [Invoke word skill to convert to .docx] — Model self-checks whether current skill library has "a skill that operates Word" (docx-skill / word-skill / docx-generator etc.)
        │        ├─ Exists → Invoke that skill to convert to .docx
        │        └─ Not exists → Prompt user to install docx-skill, only save .md
        ├─ 4.8.3 Save intermediate draft to AIAssistive\output\
   □ 4.9 Report output paths
```

---

## Key Execution Constraints

1. **Must follow Step order**: Cannot skip Step 1 clarification
2. **Each Step must complete before moving to next**: Especially Step 2's material extraction
3. **Step 4.3 is the core constraint**: Must ask when materials are missing, cannot make own decisions
4. **Step 4.6 is mandatory output**: Change record must be written
5. **Dual output**: Project directory (formal) + .aiassistive/output/ (intermediate draft)

---

## Resource References

- End-to-end workflow detailed description: `references/end_to_end_workflow.md`
- Output file naming convention: `references/output_file_naming_convention.md`

---

## Future Extensions

- Multi-document concurrent generation (parallel via subagent)
- Integration with PMO database (auto-fill historical project data)
- Automatic review email generation

    $SKILL_PROJECT_PROJECT_DOC_WORKFLOW_BODY$,
    TRUE,
    5
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;

INSERT INTO skills (name, display_name, category, description, location, base_dir, content, enabled, sort_order)
VALUES (
    'intent-clarification',
    '',
    '',
    'Use whenever any project-doc skill (query/outline/write/workflow/data-skill) needs to confirm something with the user — unified protocol: scan project artifacts first, show prior answers, cite source+line, handle ''TBD/待定'' by re-asking. Re-entrant: can be invoked from any step, not just the start.',
    'app/skills/intent-clarification/SKILL.md',
    'app/skills/intent-clarification',
    $SKILL_PROJECT_INTENT_CLARIFICATION_BODY$
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

    $SKILL_PROJECT_INTENT_CLARIFICATION_BODY$,
    TRUE,
    6
)
ON CONFLICT (name) DO UPDATE
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description,
    location = EXCLUDED.location,
    base_dir = EXCLUDED.base_dir,
    content = EXCLUDED.content,
    enabled = EXCLUDED.enabled,
    sort_order = EXCLUDED.sort_order,
    updated_at = CURRENT_TIMESTAMP;
