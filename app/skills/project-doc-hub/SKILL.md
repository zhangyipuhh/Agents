---
name: project-doc-hub
description: Use when the user wants to create, query, or update software-engineering project deliverables (Implementation Plan / Requirements Specification / High-Level Design / Detailed Design / Test Plan / Test Report / Acceptance Report / Implementation & Deployment / Training Plan etc.) under a project root such as <项目根> — acts as the entry point that dispatches to project-doc-query/outline/write/workflow
---
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
