---
name: project-doc-workflow
description: Use when generating a software-engineering project deliverable end-to-end (from initial user request to final document on disk) — orchestrates the 4-step pipeline (hub → query → outline → write) and provides the work-skill checklist
---

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
