# Implementation Plan Format Template — Extraction Specification

> During the `project-doc-write` stage, the suite needs to extract the chapter structure from the project's existing "Implementation Plan.docx" as a format template.
> This specification defines the extraction path, fallback order, and output format.

## Extraction Path

```
<project_root>/03_技术文档及评审/01_实施方案/*.docx
```

## Fallback Order

```
01_实施方案/*.docx
  └─ Does not exist → 02_需求分析/*.docx
              └─ Does not exist → 03_概要设计/*.docx
                          └─ Does not exist → Ask the user to upload a format template
```

## Extraction Script

```bash
python scripts/extract_docx_outline.py \
  --docx "<docx_path>" \
  --output "<output_md_path>"
```

> The script uses this skill's **own** `scripts/DocumentLoader.py` (path: `../project-doc-write/scripts/DocumentLoader.py`), and processes docx through `scripts/loader/WordLoader.py`;
> heading extraction uses `python-docx` directly (to preserve hierarchy information, since DocumentLoader's WordLoader does not preserve heading hierarchy).

## Output Format

```markdown
# Format Template: Implementation Plan

## Level 1 Chapter 1
### 1.1 Level 2 Chapter
### 1.2 Level 2 Chapter
## Level 1 Chapter 2
### 2.1 Level 2 Chapter
...
```

> Only extract chapter titles (Heading 1/2/3), not body content.

## Use

- As a fine-tuning reference for `project-doc-outline` chapter titles
- As a style reference for `project-doc-write` body layout (title hierarchy / numbering style)

## Exception Handling

| Exception | Handling |
|---|---|
| docx file is locked by Word | Ask the user to close Word and retry |
| No headings in docx | Ask the user to manually confirm the chapter structure |
| Multiple docx with the same name | Take the one with the latest modification date |
