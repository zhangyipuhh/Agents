# Clarification Log Unified Template

> Companion to `intent-clarification/SKILL.md`.

## File Location

**Main log (主日志)**: `<user_work_root>/.project/<project_id>/project_log.md`
**Clarification log (澄清记录)**: `<user_work_root>/.project/<project_id>/clarification_log.md`

## Templates (used on first creation)

### project_log.md

```markdown
# Project Log · 202410-C0008

<!-- Note: Meta information such as project root / initialization time / initializing skill is recorded uniformly on the first line (row #0) of clarification_log.md, and is NOT duplicated in the header of project_log.md. -->

## Operation Records

| Timestamp | Skill | Operation Type | Modified Content | Evidence/Path |
|---|---|---|---|---|
| 2026-06-11 12:00 | project-doc-overview | Initialize | Create .project directory and this file | .project/202410-C0008/ |
```

### clarification_log.md

```markdown
# Clarification Log · 202410-C0008

> Companion to project_log.md.
> Append one row each time the model asks the user and receives an answer.

| # | Timestamp | Dimension | Sub-item | Question Summary | User Answer | Source | Invoking Skill |
|---|---|---|---|---|---|---|---|
| 0 | 2026-06-11 12:00 | (init) | (init) | Initialize empty log | (init) | (init) | project-doc-overview |
```

## Source Field Convention

| Source Identifier | Meaning |
|---|---|
| `用户口述` (User direct input) | User answered directly (no project material basis) |
| `用户确认` (User confirmed) | Project material already exists, user confirmed adoption |
| `策划表 §X 第 Y 行` (Planning Sheet §X line Y) | Cited from a specific location in the Planning Sheet |
| `合同 §X 第 Y 条` (Contract §X clause Y) | Cited from a specific location in the contract |
| `需求 §X 第 Y 行` (Requirements §X line Y) | Cited from a specific location in the Requirements Specification |
| `澄清日志 #N` (Clarification Log #N) | Reference to a prior clarification record |

## Append Operations

Via `manage_project_log.py`:

```bash
# Append a clarification record
python scripts/manage_project_log.py append-clarification \
    --project-id 202410-C0008 \
    --work-root "D:\项目文档" \
    --dimension "C.environment" \
    --item "tech_hardware" \
    --question "是否按已有信息写？" \
    --answer "是" \
    --source "策划表 §2 第 3 行 + 用户确认" \
    --asked-by "project-doc-outline"

# Append main log (after skill workflow ends)
python scripts/manage_project_log.py append-operation \
    --project-id 202410-C0008 \
    --work-root "D:\项目文档" \
    --skill "project-doc-write" \
    --op-type "新增" \
    --content "测试方案.md" \
    --evidence "项目根/03_技术文档及评审/05_.../测试方案.md"
```

## Path Exogeneity Principle

**Key**: All `.md` files are **not** stored inside the skill. Reasons:
- Skills are read-only assets and should not be modified at runtime
- Cross-project isolation (different projects have different logs)
- User's working directory can be backed up/versioned (optional)
