# Review Plan Extraction Method

> The standard extraction workflow when the user asks "when to submit / when to review".

## Step 1: Locate the Planning Sheet

```python
from pathlib import Path
import glob

project_root = Path(r"<project_root>")
candidate = sorted(
    glob.glob(str(project_root / "01_项目策划" / "*策划表*V*.xlsm")),
    key=lambda p: [int(s) for s in Path(p).stem.split("V")[-1].split(".") if s.isdigit()],
    reverse=True,
)
plan_file = candidate[0]  # Take the latest version
```

## Step 2: Read the "Review Plan" Sheet (use the CLI script; Python import is forbidden)

```bash
# Option A: Use find_planning_sheet.py to complete "locate + read review plan" in one command
# First locate the Planning Sheet
python scripts/find_planning_sheet.py --project-root "<project_root>" --output path
# → Output: <planning_sheet.xlsx> (e.g., <project_root>/01_项目策划/策划表V1.0.xlsm)

# Then read the "Review Plan" sheet (auto fuzzy-match: 评审 / Review / Plan)
python scripts/read_doc.py --file "<output from the previous step>" --sheet 评审计划 --output table
```

See `references/cli_script_quick_reference.md` for full parameter descriptions.

## Step 3: Parse Rows

- Columns: `Deliverable | Submission Date | Review Date | Review Method | Reviewer | Review Conclusion`
- Separate each row by `\t`
- Render as a table for output

## Output Format

| Deliverable | Submission Date | Review Date | Review Method | Reviewer | Review Conclusion |
|---|---|---|---|---|---|
| Requirements Specification | 2025-12-10 | 2025-12-15 | Meeting Review | Zhang San, Li Si | Pass |
| ... | ... | ... | ... | ... | ... |

## Exception Handling

| Exception | Handling |
|---|---|
| Planning Sheet not found | Ask the user to provide the Planning Sheet location |
| xlsm read failure (file locked) | Ask the user to close Excel and retry |
| "Review Plan" sub-tag not found | Fuzzy-match the "Review" keyword |
| Review Plan is empty | Ask the user whether a Review Plan exists |
| Field misalignment | Ask the user to upload a preview screenshot or manually confirm |
