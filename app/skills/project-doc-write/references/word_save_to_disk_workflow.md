# write Step 7 Save-to-Disk Workflow (Word Document Generation)

> The .md file produced by the write workflow **must** be converted to .docx by the "Word-operating skill" before being saved to disk. This document describes the complete workflow.

## 0. Prerequisites

- Steps 1-6 have been completed to generate .md content
- .md already contains "cover info + TOC + body + tables + lists" and other complete structures (see `word_format_template_rule.md §8`)
- Content has been purified per `references/document_content_purification_rule.md` (removed Review Draft / "—" / empty talk)

## 1. Save-to-Disk Workflow

```
Step 7 Save to Disk
   │
   ├─ 7.1 Save .md to Project Directory
   │        <project_root>/03_技术文档及评审/<corresponding subdir>/<document_name>.md
   │
   ├─ 7.2 【Key】Check whether the "Word-operating skill" is in the current skill library
   │        │
   │        ├─ Model self-check: is any of the following available in the current skills:
   │        │     - docx-skill
   │        │     - word-skill
   │        │     - docx-generator
   │        │     - markdown-to-word
   │        │     - md2docx
   │        │     - pandoc-skill
   │        │     - or any other skill that can process .md → .docx conversion
   │        │
   │        ├─ Exists → 7.3
   │        │
   │        └─ Does not exist → 【Notify user】
   │              Stop the .docx saving process
   │              Output prompt: "⚠️ Generating project-level .docx documents requires a Word-operating skill,
   │                      which was not found in the current environment. This document will only be saved as an .md draft.
   │                      Please confirm:
   │                      1) Install docx-skill (or similar skill) and rerun Step 7
   │                      2) Or manually use Word/Pandoc to open .md for conversion"
   │              Jump to 7.4
   │
   ├─ 7.3 【Call Word skill to convert to .docx】
   │        │
   │        └─ Model action:
   │              - Call the "Word-operating skill" to convert <output.md> to <output.docx>
   │              - Apply the styles from `references/word_format_template_rule.md`:
   │                * Cover (Project Name/ID/Document Name/Version/Date)
   │                * TOC (Level 1-3 headings)
   │                * Font / Size / Line Spacing / Paragraph Spacing
   │                * Header / Footer (Project ID / Document Name / Page Number)
   │              - Output <project_root>/03_技术文档及评审/<corresponding subdir>/<document_name>.docx
   │
   ├─ 7.4 Save the intermediate draft to .aiassistive/output/
   │        <work_root>/.aiassistive/output/<project_id>/<document_name>_draft.md
   │
   └─ 7.5 Append the change log
            python ../project-doc-workflow/scripts/append_change_log.py
            --project-root <project_root> --doc-type <document type>
            --change-type 新增 (Add) --summary "Auto-generated V1.0 + called Word skill to convert to .docx"
```

## 2. Key Constraints

### 2.1 write Does Not Create docx-skill

write does **not** create or install docx-skill on its own. It is a third-party skill installed by the user.

### 2.2 write Does Not Hard-Code the Invocation Method

write does **not** hard-code in SKILL.md / references:
- ❌ `python ../docx-skill/scripts/md_to_docx.py ...`
- ❌ `from docx import Document` to write its own conversion logic

write **only tells the model** to "call the Word-operating skill", and the model selects based on the current skill library.

### 2.3 write Does Not Make Decisions for the Model

If the model determines that no Word skill is currently available, **notify the user**; do **not** auto-skip, and do **not** auto-fall back to the pandoc command line.

### 2.4 Saving Must Save Both .md and .docx

- .md is a **formal deliverable** (must exist in the project directory; can be cited in reviews)
- .docx is a **formal deliverable** (must exist in the project directory; can go through the project review process)
- Intermediate draft (AIAssistive\output\) only needs to keep .md

## 3. Anti-Patterns (Strictly Forbidden)

| Anti-Pattern | Consequence |
|---|---|
| write itself uses python-docx to generate .docx on the spot | Violates single responsibility + violates the anti-pattern red line (import in Python code) |
| write hard-codes `python ../docx-skill/scripts/...` | Violates high cohesion, low coupling |
| Skipping the docx-skill check and saving directly | User does not get .docx; violates workflow |
| Using pandoc command line as fallback | Cross-platform inconsistency + violates "call skill, not command" |
| Saving only .md, not .docx | User must convert manually; violates the V1.0 process goal |

## 4. Status Labels and Role Tables

| Field | Rule | Source |
|---|---|---|
| Document Status | Do not write by default; write according to user request when explicitly specified in Planning Sheet / requirements | `word_format_template_rule.md §11` |
| Role Sign-off Table | Do not write by default; fill in from Planning Sheet when it contains specific names | `word_format_template_rule.md §12` |
| Compile / Review / Approve | Role names are taken from the specific fields in the Planning Sheet | Same as above |

## 5. Error Handling

| Scenario | Handling |
|---|---|
| docx-skill call failure | Notify the user, but the .md already saved to the project directory is retained |
| docx-skill output .docx missing cover / TOC | Notify the user to check the docx-skill configuration; do not retry |
| Document content has no data (e.g., test report) | Step 4.2.5 proactively asks; after user confirms "no data", the chapter is retained but marked with "**Pending-fill (待补)**", no placeholders are written |

## 6. Collaboration with project-doc-workflow

workflow skill calls `append_change_log.py` to append the change log, and does **not** directly call the word skill. The word skill's save-to-disk is completed by write in Step 7.
