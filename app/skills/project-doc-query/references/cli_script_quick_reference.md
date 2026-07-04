# project-doc-query · CLI Script Quick Reference

> This skill has 3 CLI scripts + 1 environment self-check script. All project-file reading must go through the CLI; direct Python import is forbidden.

## 0. Script List

| Script | Type | Purpose |
|---|---|---|
| `scripts/check_env.py` | CLI | Environment self-check (whether dependencies are complete) |
| `scripts/read_doc.py` | CLI | **Universal file reader** (auto-dispatches to 8 Loaders by extension) |
| `scripts/find_planning_sheet.py` | CLI | Locate the latest version of the Planning Sheet xlsm under the project root |
| `scripts/scan_project_root.py` | CLI | Scan the project root directory and list files |
| `scripts/DocumentLoader.py` | Library | Generic file loading (used internally by the CLI) |
| `scripts/loader/*.py` | Library | 8 format loaders (used internally by the CLI) |

> **Important**: `DocumentLoader` and the 8 Loaders are **libraries**; **forbidden** to import them in Python code. File reading must go through `read_doc.py`.

---

## 1. read_doc.py — Full Reference

### 1.1 Purpose

Auto-dispatches to one of the 8 Loaders under DocumentLoader by file extension. Supported:

- `.xlsx` / `.xlsm` → ExcelLoader
- `.docx` / `.doc` → WordLoader
- `.pdf` → PDFLoader
- `.txt` → TextLoader
- `.md` / `.markdown` → MarkdownLoader
- `.csv` → CSVLoader
- `.json` → JSONLoader
- `.eml` → EmlLoader

### 1.2 Common Parameters (apply to all formats)

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--file` | PATH | Required | Absolute path to the file |
| `--output` | text/json/table | text | Output format |
| `--output-file` | PATH | None | Write to a file (bypass Windows console GBK encoding) |
| `--max-rows` | INT | 50 | Maximum number of output fragments (0 = unlimited) |
| `--keyword` | TEXT | None | Filter by page_content substring (case-insensitive) |

### 1.3 Pass-through Parameters Dispatched by Extension

| Extension | Parameter | Passed to |
|---|---|---|
| `.xlsx` `.xlsm` | `--sheet` (sheet name, fuzzy match) | `ExcelLoader(sheet_name=)` |
| `.xlsx` `.xlsm` | `--row-range` (e.g., `5-20`) | `ExcelLoader(row_range=)` |
| `.xlsx` `.xlsm` | `--include-hidden` (flag) | `ExcelLoader(include_hidden=True)` |
| `.json` | `--jq-schema` (e.g., `.data.items`) | `JSONLoader(jq_schema=)` |
| `.json` | `--text-content` (flag) | `JSONLoader(text_content=True)` |
| `.txt` `.csv` | `--encoding` | `TextLoader/CSVLoader(encoding=)` |
| `.eml` | `--prefer-encoding` | `EmlLoader(prefer_encoding=)` |

### 1.4 Output Format

| `--output` | Description |
|---|---|
| `text` | Default; output each fragment as `--- Fragment N --- [metadata] + page_content` |
| `json` | Structured JSON, including index / page_content / metadata |
| `table` | markdown table (only friendly to Excel/CSV-style data; text lines are auto-parsed into tables when separated by `\t`) |

### 1.5 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success |
| 1 | File does not exist |
| 2 | Unsupported extension |
| 3 | Loading exception (file locked / corrupted) |
| 4 | No matching results (empty after filtering by sheet/keyword) |

---

## 2. find_planning_sheet.py — Full Reference

### 2.1 Purpose

Find Planning Sheet xlsm files in `<project_root>/01_项目策划/` matching a glob pattern, **sorted by version number in descending order**.

### 2.2 Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--project-root` | PATH | Required | Absolute path to the project root directory |
| `--pattern` | GLOB | `*策划表V*.xlsm` | Matching pattern |
| `--output` | path/info/json | path | path = output absolute path (easy for piping); info = human-readable; json = structured |

### 2.3 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Project root directory does not exist |
| 4 | No matching items found |

---

## 3. scan_project_root.py — Full Reference

### 3.1 Purpose

Scan the project root (or a specified subdirectory) and list files filtered by extension.

### 3.2 Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--project-root` | PATH | Required | Project root directory |
| `--subdir` | NAME | None | Subdirectory name (multi-level supported, e.g., `03_技术文档及评审/01_实施方案`) |
| `--ext` | LIST | None | Extension filter, comma-separated (e.g., `.docx,.pdf`) |
| `--output` | list/json/table | list | Output format |
| `--output-file` | PATH | None | Write to file |

> Automatically skips Excel temporary lock files starting with `~$`.

---

## 4. Typical Use Cases

### 4.1 Review Plan Extraction (most common)

```bash
# One step: locate + read
python scripts/find_planning_sheet.py --project-root "D:\项目文档\202410-C0008-..." --output path
# → D:\...\策划表V1.0.xlsm

python scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --output table
```

### 4.2 Excel Row-Level Keyword Filtering

```bash
# Find all rows involving "Zhang San"
python scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --keyword 张三 --output table
```

### 4.3 Excel Row Range

```bash
# View only rows 5-20
python scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --row-range 5-20
```

### 4.4 PDF Text Extraction (Scanned Document Detection)

```bash
python scripts/read_doc.py --file "D:\...\需求.pdf" --output json
# Output metadata with is_scanned=true indicates a scanned document
```

### 4.5 DOCX Paragraph Extraction

```bash
python scripts/read_doc.py --file "D:\...\实施方案.docx" --max-rows 30
```

### 4.6 CSV to Markdown Table

```bash
python scripts/read_doc.py --file "D:\...\成本.csv" --output table
```

### 4.7 JSON Field Extraction by jq Schema

```bash
python scripts/read_doc.py --file "D:\...\接口.json" --jq-schema ".data.items" --output json
```

### 4.8 EML Read Mail Headers

```bash
python scripts/read_doc.py --file "D:\...\会议通知.eml" --output text
# 5 sections: subject / sender / recipient / date / body
```

### 4.9 Scan the Project Root for Implementation Plans

```bash
python scripts/scan_project_root.py --project-root "D:\项目文档\202410-C0008-..." --subdir 03_技术文档及评审/01_实施方案 --ext .docx --output table
```

### 4.10 Output to File to Bypass Console Encoding Issues

```bash
python scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --output table --output-file D:\review_plan.md
```

### 4.11 Chained Pipeline (find → read)

```powershell
$plan = python scripts/find_planning_sheet.py --project-root "D:\项目文档\202410-C0008-..." --output path
python scripts/read_doc.py --file $plan.Trim() --sheet 评审计划 --output table
```

### 4.12 Complete Workflow (recommended path)

```powershell
# 1. Generate project path variables
python scripts/dump_paths.py --project-root "D:\项目文档\202410-C0008-..." --format ps1 --output-file D:\paths.ps1

# 2. Load into PowerShell
. D:\paths.ps1

# 3. Use variables to call read_doc.py directly
python scripts/read_doc.py --file $PLANNING_SHEET_LATEST --sheet 评审计划 --output json --output-file D:\review.json
```

---

## 5. dump_paths.py — Full Reference

### 5.1 Purpose

One-click output of common paths for the project root (Planning Sheet / project directory / emails / output / change log, etc.),
output as PowerShell variable assignments that can be loaded directly into the current shell with `. (path.ps1)`.

**Pain point addressed**: PowerShell long paths / Chinese paths / paths with spaces → quoting and escaping is painful.

### 5.2 Parameters

| Parameter | Type | Default | Description |
|---|---|---|---|
| `--project-root` | PATH | Required | Project root directory |
| `--format` | ps1 | ps1 | Output format (currently only ps1) |
| `--output-file` | PATH | None | Write to file (recommended to avoid console encoding issues) |

### 5.3 Use Cases

```bash
# Load into PowerShell and use variables
. (python scripts/dump_paths.py --project-root "D:\项目文档\202410-C0008-..." --format ps1)
python scripts/read_doc.py --file $PLANNING_SHEET_LATEST --output json

# Or write to a file first, then dot-source
python scripts/dump_paths.py --project-root "D:\项目文档\..." --format ps1 --output-file D:\paths.ps1
. D:\paths.ps1
python scripts/read_doc.py --file $PLANNING_SHEET_LATEST --output json
```

### 5.4 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success (Planning Sheet included) |
| 1 | Project root does not exist |
| 2 | Planning Sheet not found (other variables still output, warning to stderr) |

### 5.5 Output Variables

| Variable | Description |
|---|---|
| `$PROJECT_ROOT` | Project root directory |
| `$PROJECT_ID` | Project ID (e.g., 202410-C0008) |
| `$PLANNING_DIR` | 01_项目策划 directory |
| `$PLANNING_SHEET_LATEST` | Absolute path to the latest version Planning Sheet xlsm |
| `$PLANNING_SHEET_OLD` | Absolute path to the second-latest Planning Sheet xlsm (when multiple exist) |
| `$REVIEW_DIR` | 03_技术文档及评审 directory |
| `$EMAIL_DIR` | Email storage directory (usually = PLANNING_DIR) |
| `$OUTPUT_DIR` | AIAssistive\output\<project_id>\ draft directory |
| `$CHANGE_LOG` | 06_变更及暂停\变更记录.md path |

---

## 6. Anti-Pattern → Correct Usage Table

| Anti-Pattern | Correct Usage |
|---|---|
| `python -c "from DocumentLoader import DocumentLoader, ExcelLoader; ..."` | `python scripts/read_doc.py --file ...` |
| `python -c "from openpyxl import load_workbook; ..."` | `python scripts/read_doc.py --file ... --sheet ...` |
| `python -c "from docx import Document; ..."` | `python scripts/read_doc.py --file ...` |
| `python -c "from pypdf import PdfReader; ..."` | `python scripts/read_doc.py --file ...` |
| Writing a one-off script in `tmp/` or `D:\` root to read files | Use this skill's `scripts/` CLI |

---

## 7. FAQ

**Q: Windows PowerShell output garbled?**
A: Use `--output-file PATH` to write to a file, bypassing console encoding; or upgrade to PowerShell 7.

**Q: `--sheet 评审计划` not found?**
A: read_doc.py auto-fuzzy-matches; keywords like "评审" / "Review" / "Plan" are enough. If no match, exit code 4 and print all available sheet names.

**Q: Want to read multiple sheets in batch?**
A: read_doc.py only supports a single sheet per call. Just call multiple times (change `--sheet` each time).

**Q: Can the 3 new parameters of ExcelLoader (sheet_name/keyword/row_range) be used directly via the library?**
A: Yes, but it's "internal use"; CLI is preferred. The library API is only for internal import by the CLI.
