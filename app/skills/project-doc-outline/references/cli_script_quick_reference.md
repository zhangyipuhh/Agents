# project-doc-outline · CLI Script Quick Reference

> This skill has 1 private CLI script + 1 environment self-check + 1 library suite. All project-file reading must go through the CLI; direct Python import is forbidden.

## 0. Script List

| Script | Type | Purpose |
|---|---|---|
| `scripts/check_env.py` | CLI | Environment self-check |
| `scripts/extract_docx_outline.py` | CLI | **Extract chapters from a project .docx as a format template for the outline** |
| `scripts/read_doc.py` | CLI | Read other project files (Excel/PDF/CSV, etc.) |
| `scripts/DocumentLoader.py` | Library | Generic file loading (used internally by the CLI) |
| `scripts/loader/*.py` | Library | 8 format loaders (used internally by the CLI) |

> **Important**: `extract_docx_outline.py` is the outline skill's **private script**; it is a **separate independent copy** with the same name as the write skill's `extract_docx_outline.py`. Do not cross-reference across skills.

---

## 1. extract_docx_outline.py — Full Reference

### 1.1 Purpose

Extract Heading 1/2/3/4 titles from a .docx file inside the project, and render them as a markdown format template.

Used by the outline output to reference "the chapter style of similar documents already in the project" at the chapter level.

### 1.2 Parameters

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `--docx` | PATH | — | Yes | Absolute path to the docx file |
| `--output` | PATH | — | Yes | Output markdown path |
| `--max-depth` | INT (1-4) | 4 | No | Heading truncation depth |

### 1.3 Output Format

```markdown
# Format Template: <filename>

# Level 1 Heading
## Level 2 Heading
### Level 3 Heading
#### Level 4 Heading
```

### 1.4 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success |
| 1 | File does not exist |
| 3 | Extraction failed (python-docx parsing exception) |

### 1.5 Examples

#### 1.5.1 Extract an Implementation Plan as a Format Template

```bash
python scripts/extract_docx_outline.py \
    --docx "D:\项目文档\202410-C0008-...\03_技术文档及评审\01_实施方案\实施方案V1.0.docx" \
    --output "D:\...\AIAssistive\output\202410-C0008\格式范本_实施方案.md"
```

#### 1.5.2 View only Levels 1 and 2

```bash
python scripts/extract_docx_outline.py --docx plan.docx --output out.md --max-depth 2
```

#### 1.5.3 Extract a Requirements Specification as Template (fallback)

```bash
python scripts/extract_docx_outline.py \
    --docx "D:\...\02_需求\需求说明书V1.0.docx" \
    --output "D:\...\AIAssistive\output\202410-C0008\格式范本_需求.md"
```

---

## 2. read_doc.py — Full Reference

> This skill bundles its own `read_doc.py`; it is a separate independent copy with the same name as the query skill.

| Parameter | Description |
|---|---|
| `--file` | Required; absolute path to the file |
| `--output` | text / json / table |
| `--max-rows` | Default 50 |
| `--keyword` | Substring filter |
| `--output-file` | Write to a file (to avoid console encoding issues) |
| `--sheet` | Excel sheet name (fuzzy match) |
| `--row-range` | e.g., `5-20` |
| `--jq-schema` | JSON path |
| `--encoding` / `--prefer-encoding` | Text/email encoding |

See the query quick reference for the full parameter table (**not duplicated here**; the command syntax is identical).

---

## 3. Anti-Pattern → Correct Usage Table

| Anti-Pattern | Correct Usage |
|---|---|
| `python -c "from docx import Document; ..."` to extract chapters | `python scripts/extract_docx_outline.py --docx ... --output ...` |
| `python -c "from DocumentLoader import DocumentLoader, ExcelLoader; ..."` | `python scripts/read_doc.py --file ...` |
| Referencing the write skill's `extract_docx_outline.py` | Use the outline's local copy (high cohesion, low coupling) |
| Copying the entire docx body directly into the outline | Use this CLI to extract heading titles; body content is handled in the write stage |
| Referencing query's `read_doc.py` | outline already has its own; no cross-skill reference needed |

---

## 4. FAQ

**Q: What is the relationship between the format template extracted by outline and the final outline?**
A: The template is for referencing "the chapter style of similar documents already in the project"; the outline itself is still generated per the `references/outline_*.md` templates.

**Q: Why doesn't outline directly call write's scripts?**
A: High cohesion, low coupling. Each skill owns a complete toolset and does not depend on other skills.

**Q: What is a good `--max-depth` value?**
A: Usually 2-3. `1` = outline only, `4` = full detail.

**Q: Chinese garbled characters after extraction?**
A: This CLI writes markdown in UTF-8 and will not produce garbled output. If you see garbled characters when using the Read tool to view raw bytes, that is a tool issue, not a script issue.
