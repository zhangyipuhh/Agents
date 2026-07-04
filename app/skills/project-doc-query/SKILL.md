---
name: project-doc-query
description: Use when the user asks questions about a software-engineering project's documents, milestones, deliverables, review schedule, or wants PMO-level advisory — applies three-layer framework overlay (PMP framework layer + PRINCE2 implementation layer + Systems Analyst practice layer) and forces intent-clarification (fact vs decision) before answering
---

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
