# project-doc-write · CLI Script Quick Reference

> This skill has 1 private CLI + 1 library suite. Use this skill's built-in `read_doc.py` to read any project file; use `extract_docx_outline.py` to extract docx chapters.

## 0. Script List

| Script | Type | Purpose |
|---|---|---|
| `scripts/check_env.py` | CLI | Environment self-check |
| `scripts/extract_docx_outline.py` | CLI | **Extract docx chapters as a format template** (write's private copy) |
| `scripts/read_doc.py` | CLI | Read other project files (Excel/PDF/CSV/email, etc.) |
| `scripts/DocumentLoader.py` | Library | Generic file loading |
| `scripts/loader/*.py` | Library | 8 format loaders |

> `extract_docx_outline.py` has **one independent copy in each of the write and outline skills**.

---

## 1. extract_docx_outline.py (write's private copy)

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `--docx` | PATH | — | Yes | Absolute path to the docx file |
| `--output` | PATH | — | Yes | Output markdown path |
| `--max-depth` | INT (1-4) | 4 | No | Heading truncation depth |

### Exit Codes: 0 success / 1 file does not exist / 3 extraction failed

### Use Cases

```bash
# Extract an Implementation Plan as a format template
python scripts/extract_docx_outline.py \
    --docx "D:\项目文档\202410-C0008-...\03_技术文档及评审\01_实施方案\实施方案V1.0.docx" \
    --output "D:\...\AIAssistive\output\202410-C0008\格式范本.md"

# Only levels 1-2
python scripts/extract_docx_outline.py --docx plan.docx --output out.md --max-depth 2
```

---

## 2. read_doc.py (write's built-in copy)

Parameters are identical to the query skill:

| Parameter | Description |
|---|---|
| `--file` | Required |
| `--output` | text / json / table |
| `--max-rows` | Default 50 |
| `--keyword` | Substring filter |
| `--output-file` | Write to a file |
| `--sheet` / `--row-range` / `--include-hidden` | Excel-specific |
| `--jq-schema` / `--text-content` | JSON-specific |
| `--encoding` / `--prefer-encoding` | Text / email |

### Common Usage in write Scenarios

#### 2.1 Read the Planning Sheet to Extract the Review Plan

```bash
python scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --output table
```

#### 2.2 Read the Requirements docx to Get Evidence

```bash
python scripts/read_doc.py --file "D:\...\需求说明书V1.0.docx" --max-rows 100 --output text
```

#### 2.3 Read a PDF (note scanned documents)

```bash
python scripts/read_doc.py --file "D:\...\需求.pdf" --output json
# is_scanned=true in the metadata indicates a scanned document; ask the user to provide a readable version
```

#### 2.4 Read Email

```bash
python scripts/read_doc.py --file "D:\...\客户反馈.eml" --output text
```

---

## 3. Anti-Pattern → Correct Usage Table

| Anti-Pattern | Correct Usage |
|---|---|
| `python -c "from docx import Document; for p in doc.paragraphs: ..."` to extract chapters | `python scripts/extract_docx_outline.py --docx ... --output ...` |
| `python -c "from DocumentLoader import DocumentLoader; docs = loader.load()"` | `python scripts/read_doc.py --file ...` |
| Referencing the outline skill's `extract_docx_outline.py` | Use write's local copy (high cohesion) |
| Referencing query's `read_doc.py` | write already has its own |
| `open(file, encoding='utf-8').read()` in Python | `python scripts/read_doc.py --file ...` |

---

## 4. FAQ

**Q: When does the write workflow use `read_doc.py`?**
A: When loading project materials in Step 2 (Planning Sheet / requirements / design / contract / email), use `read_doc.py` to replace Python import.

**Q: What is the difference between write's `extract_docx_outline.py` and outline's?**
A: They are currently **functionally identical** (two independent copies). write's extracted output is used as the "format template" for Step 3, while outline's is used as "project-internal similar document style reference" for Step 3.

**Q: What to do when PDFLoader extracts < 100 characters of text?**
A: Treat as a scanned document; ask the user to provide a readable version (docx/md/txt). **Forbidden** to use out-of-scope workarounds like OCR / PDF image recognition.
