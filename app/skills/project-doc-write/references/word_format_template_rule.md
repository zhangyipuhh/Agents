# Word Format Template Rule (Hard-coded · Distilled from Project Implementation Plan.docx)

> This rule is the style baseline extracted from `<project_root>/03_技术文档及评审/01_实施方案/实施方案V1.0.docx`, frozen into the following hard rules.
> Reason for hard-coding: to maintain write skill's "high cohesion, low coupling" — no dependency on third-party skills such as docx-skill / word-skill.
> Re-extraction / Rewrite: you can modify this file manually, or delete this file and re-run `scripts/extract_word_style.py` + manual proofreading.

---

## 1. Cover Page (Mandatory · Page 1)

| Element | Rule |
|---|---|
| Project Name | Centered, **Heiti (黑体) size 2** (22pt), 6cm space before, 1cm space after |
| Project ID | Centered, **Heiti (黑体) size 3** (16pt), 1cm space before, 0.5cm space after |
| Document Name | Centered, **Heiti (黑体) size 2** (22pt), 1.5cm space before, 0.5cm space after |
| Version + Date | Centered, **Songti (宋体) small 4** (12pt), 0.5cm space before, 0.5cm space after |

> **Do not write status labels like "Review Draft" / "Draft" / "Official Version"** (unless the user explicitly requests in the Planning Sheet / requirements)
> **Do not write "Compile / Review / Approve" role table** (unless the user explicitly specifies a concrete name in the Planning Sheet)
> Cover page **is not counted in page numbers**

---

## 2. Table of Contents Page (Mandatory · Page 2)

- Auto-generated from Level 1-3 headings
- Occupies 1 page
- **Two-layer table of contents**:
  - **markdown static layer** (exists in .md as `## Table of Contents` + link list, directly clickable for models / readers)
  - **docx auto layer** (when converting to .docx, docx-skill uses Word's automatic TOC to overlay and update page numbers)
- Table of contents page **is not counted in page numbers**

---

## 3. Body Style

| Element | Rule |
|---|---|
| Level 1 Heading (H1 / `## 1 Introduction`) | **Heiti (黑体) small 3** (15pt), 24pt space before, 18pt space after, single line spacing |
| Level 2 Heading (H2 / `### 1.1 Scope`) | **Heiti (黑体) size 4** (14pt), 18pt space before, 12pt space after, single line spacing |
| Level 3 Heading (H3 / `#### 1.1.1`) | **Heiti (黑体) small 4** (12pt), 12pt space before, 6pt space after, 1.5x line spacing |
| Body | **Songti (宋体) small 4** (12pt), 1.5x line spacing, 2-character first-line indent |
| Table Text | **Songti (宋体) small 4** (12pt), 1.25x line spacing |
| Code / Path | Consolas size 5 (10.5pt) |
| Quote / Note | Kaiti (楷体) small 4 (12pt), 2-character left indent |
| List | Body style + bullet / number |

---

## 4. Table Style

| Element | Rule |
|---|---|
| Header | Bold + centered, **Heiti (黑体) small 4** (12pt) |
| Cell Border | 0.5pt black solid line |
| Column Width | Auto-fit (based on longest cell content) |
| Header Shading | Light gray (e.g., #D9D9D9) |

---

## 5. Header and Footer

| Element | Rule |
|---|---|
| Header Left | Project ID + Project Name (Songti small 5 9pt) |
| Header Right | Document Name (Songti small 5 9pt) |
| Footer Centered | Page X / Y (Songti small 5 9pt) |
| Page Number Start | First body page after the TOC page (cover + TOC not counted) |
| Header Line | 0.5pt black solid line |

---

## 6. Page Setup

| Element | Rule |
|---|---|
| Paper | A4 Portrait (21cm × 29.7cm) |
| Top Margin | 2.54cm |
| Bottom Margin | 2.54cm |
| Left Margin | 3.18cm (binding position) |
| Right Margin | 2.54cm |

---

## 7. Forbidden Content (Hard Constraints)

> These are **NOT allowed in generated documents** unless the user explicitly requests:

- ❌ Status labels: `Review Draft` / `Draft` / `Official Version` / `Pending Review` / `Final` / `V0.X`
- ❌ Role sign-off table: `Compile` / `Review` / `Approve` (unless the Planning Sheet has concrete names)
- ❌ Meta-placeholder paragraphs: `> Review draft stage: specific data not yet filled` / `> To be supplemented in XX stage`
- ❌ "—" placeholders (replace with `**Pending-fill (待补)**: [field name]`)
- ❌ Empty references: `Refer to the "XX" template in the project template library` / `See appendix`
- ❌ Project-specific tools: ZenTao / Jira / Git / DingTalk / Feishu (unless the project materials explicitly mention them)
- ❌ Specific names / dates / numbers that do not appear in the project materials (**Strictly forbid fabrication**)

---

## 8. Required Markdown Structure

Each .md document **must** contain the following structure (enforced by write Step 4.1):

```markdown
# <Document Name>

<Cover info: Project Name/ID/Version/Date>

---

## Table of Contents

- [1 Introduction](#1-introduction)
  - [1.1 Purpose](#11-purpose)
  - [1.2 Scope](#12-scope)
- [2 <Chapter Name>](#2-chapter-name)
- [...]

---

## 1 Introduction

### 1.1 Purpose
...
```

> The TOC must be written manually (markdown does not support automatic TOC), but the anchor of each link must be correct.

---

## 9. Chapter Numbering Convention

- Level 1: `## 1 Introduction` (Arabic numerals)
- Level 2: `### 1.1 Purpose`
- Level 3: `#### 1.1.1 Subsection`
- Do not use Chinese numerals like "Chapter One"
- Do not use numbering with a pause like "One,"

---

## 10. Markdown Syntax Mapping (for docx-skill reference)

| Markdown Element | docx Element | Style |
|---|---|---|
| `# H1` | Title Style | Heiti size 2 centered (for cover) |
| `## H2` | Heading 1 | Heiti small 3 + space before/after |
| `### H3` | Heading 2 | Heiti size 4 + space before/after |
| `#### H4` | Heading 3 | Heiti small 4 + space before/after |
| `\| table \|` | Table | Header bold + 0.5pt border + light gray shading |
| `> quote` | Quote | Kaiti small 4 + left indent |
| ` ```code``` ` | Code | Consolas size 5 |
| `- list` | List Paragraph | Bullet |
| `1. list` | List Paragraph | Number |
| `**bold**` | Run(bold=True) | — |
| `*italic*` | Run(italic=True) | — |
| `[text](URL)` | Hyperlink | Blue underline |

---

## 11. Document Status Convention

write does not write "Review Draft / Draft" etc. status by default. If the user explicitly requests a status in the Planning Sheet / requirements, use the following wording:

| User's Original Words | What to Write in the Document |
|---|---|
| "Generate V1.0 initial draft" | `Document Status: Initial Draft` |
| "Generate review draft" | `Document Status: Review Draft` |
| "Official version" | `Document Status: Official Version` |
| Not stated | **Do not write status field** (keep silent) |

---

## 12. Role Sign-off Table Convention

write does not write "Compile / Review / Approve" role tables by default. If the Planning Sheet / requirements explicitly specify concrete names, fill in from the Planning Sheet:

| Role | Source |
|---|---|
| Compile (编制) | "Project Manager" or "Compiler" field in the Planning Sheet |
| Review (审核) | "Reviewer" or "Project Manager" field in the Planning Sheet |
| Approve (批准) | "Approver" or "Project Sponsor" field in the Planning Sheet |

Planning Sheet has **no** field → document **does not** write the role.
Planning Sheet **has** field → document fills in from the Planning Sheet.

---

## 13. Maintenance Notes

- This rule is maintained internally by the write skill
- To re-extract style: `python scripts/extract_word_style.py --docx <path> --output raw.json`; manually proofread, then modify this file
- Do not introduce a new "format template" mechanism (avoid over-governance)
