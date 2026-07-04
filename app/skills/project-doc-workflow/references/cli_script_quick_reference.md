# project-doc-workflow · CLI Script Quick Reference

> This skill has 1 private CLI script. All actions go through the CLI.

## 0. Script List

| Script | Type | Purpose |
|---|---|---|
| `scripts/append_change_log.py` | CLI | **Append a row to the project's change log** |

> workflow does not bundle the DocumentLoader library or `read_doc.py` (it does not read project files itself).
> Actions that **read project files** in the workflow are delegated to the query / write skill CLIs (see §3 Cross-Skill References).

---

## 1. append_change_log.py — Full Reference

### 1.1 Purpose

Append a change record (Markdown table row) to `<project_root>/06_变更及暂停/变更记录.md`.

### 1.2 Parameters

| Parameter | Type | Default | Required | Description |
|---|---|---|---|---|
| `--project-root` | PATH | — | Yes | Absolute path to the project root directory |
| `--doc-type` | TEXT | — | Yes | Document type (e.g., "Test Plan" / "测试方案") |
| `--change-type` | TEXT | 新增 (Add) | No | Change type: Add / Update / Delete |
| `--summary` | TEXT | (auto) | No | Change summary (default auto-fills "Auto-added by project-doc-skill V1") |
| `--operator` | TEXT | project-doc-skill | No | Operator / system |

### 1.3 Automatic Behavior

- File does not exist → automatically create and write the header
- Project ID is auto-extracted from the project root directory name (e.g., `202410-C0008-...` → `202410-C0008`)
- Date is auto-filled with today (YYYY-MM-DD)

### 1.4 Exit Codes

| Exit Code | Meaning |
|---|---|
| 0 | Success |
| 1 | Project root directory does not exist |

### 1.5 Use Cases

#### 1.5.1 Append a Record After Adding a Document

```bash
python scripts/append_change_log.py \
    --project-root "D:\项目文档\202410-C0008-..." \
    --doc-type "测试方案" \
    --change-type "新增" \
    --summary "自动生成 V1.0 大纲与正文" \
    --operator "project-doc-skill"
```

#### 1.5.2 Update a Document

```bash
python scripts/append_change_log.py \
    --project-root "D:\项目文档\202410-C0008-..." \
    --doc-type "需求说明书" \
    --change-type "更新" \
    --summary "按客户反馈补充非功能需求章节"
```

#### 1.5.3 Only Required Parameters (Others Default)

```bash
python scripts/append_change_log.py \
    --project-root "D:\项目文档\202410-C0008-..." \
    --doc-type "验收报告"
```

---

## 2. Mapping Between workflow Steps and CLIs

In the workflow's 4-step pipeline, the CLIs corresponding to each "mechanical action":

| Step | CLI |
|---|---|
| Step 1 hub dispatch | (No CLI; dispatch is handled by hub) |
| Step 2 query material extraction | Delegated to query skill (using its `read_doc.py` / `find_planning_sheet.py`) |
| Step 3 outline generation | Delegated to outline skill (using its `extract_docx_outline.py`) |
| Step 4 write fill + decide + save | Delegated to write skill (using its `read_doc.py` / `extract_docx_outline.py`) |
| **Step 4 end — append change log** | **This skill's `append_change_log.py`** |

---

## 3. Cross-Skill References (when reading project files)

workflow itself does not bundle `read_doc.py`; **actions that read project files require cross-skill calls**:

```bash
# Read the Planning Sheet Review Plan
python ../project-doc-query/scripts/read_doc.py --file "D:\...\策划表V1.0.xlsm" --sheet 评审计划 --output table

# Find the latest version of the Planning Sheet
python ../project-doc-query/scripts/find_planning_sheet.py --project-root "D:\项目文档\202410-C0008-..." --output path
```

See `../project-doc-query/references/cli_script_quick_reference.md` for the full parameter table.

---

## 4. Anti-Pattern → Correct Usage Table

| Anti-Pattern | Correct Usage |
|---|---|
| Manually `open("变更记录.md", "a").write(...)` | `python scripts/append_change_log.py --project-root ... --doc-type ...` |
| `python -c "from openpyxl import load_workbook; ..."` | Delegate to query skill's `read_doc.py` |
| Skipping append of the change log | Forcefully call `append_change_log.py` (Step 4.6 rigid constraint) |

---

## 5. FAQ

**Q: What happens if `append_change_log.py` is run repeatedly?**
A: Each run appends a new table row; **no de-duplication** is performed. If you're worried about duplicates, you can Read the change log file first to see whether the same entry already exists.

**Q: Where is the change log file?**
A: `<project_root>/06_变更及暂停/变更记录.md` (fixed path, written as a constant in the script).

**Q: Can the workflow's 4 steps all be closed-loop using this skill's CLI?**
A: Not currently. The "read project files" actions in Steps 2/3/4 must cross-call the query/write/outline CLIs (the cost of high cohesion, low coupling). If you need a "one-stop" approach, you can add an aggregation script under workflow (future extension).
