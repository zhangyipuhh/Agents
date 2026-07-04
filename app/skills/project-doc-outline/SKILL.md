---
name: project-doc-outline
description: Use when the user wants a chapter outline (no body content) for any of the 10 supported software-engineering deliverable types (Pre-Sales Proposal / Requirements Specification / High-Level Design / Detailed Design / Implementation Plan / Test Plan / Test Report / Acceptance Report / Implementation & Deployment Plan / Training Plan) — picks the corresponding reference template and applies software-engineering standard chapter structure
---

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
