# End-to-End Workflow — Detailed Description

> Companion to SKILL.md; provides "what to do / what not to do / exception handling" for each step.

## Step 1: hub (Acceptance + Clarification)

### Must Do

1. List all subdirectories under `<work_root>/` (including hidden ones)
2. If there are multiple projects → list them and let the user select
3. Have the user confirm the target document type (one of the 10)
4. Have the user state the intent (generate / update / query)

### Do Not

- Do not pre-assume a project
- Do not pre-assume a document type
- Do not start working without user clarification

### Exceptions

- Root directory is not `<work_root>/` → ask the user to confirm
- Root directory has no projects → ask the user to provide a project root directory

## Step 2: query (Material Extraction)

### Must Do

1. Use `DocumentLoader` to load the Planning Sheet (V1.0.xlsm) and extract:
   - Milestone dates
   - Review Plan
   - Cost-Benefit Analysis
   - Risk Register
2. Use `glob` to list existing similar docx files in the project
3. Use `project-doc-write/scripts/extract_docx_outline.py` to extract docx chapter structure as a format template

### Do Not

- Do not open files outside the project root on your own
- Do not write ad-hoc scripts to read files (DocumentLoader must be used)
- Do not fabricate content for missing materials

### Exceptions

- xlsm loading failure (locked) → ask the user to close Excel
- xlsm has no "Review Plan" sub-tag → fuzzy-match
- Project root has no target-type docx → ask the user to upload a template
- PDF text < 100 characters → treat as scanned; tell the user

## Step 3: outline (Generate Outline)

### Must Do

1. Load `references/outline_<type>.md`
2. Output chapters in order (Level 1 / Level 2 headings)
3. Annotate the "Purpose" and "Required Subsections" at the end of each chapter
4. Have the user confirm the outline

### Do Not

- Do not write the body
- Do not adjust chapter order on your own
- Do not add or remove chapters on your own

### Exceptions

- Reference template missing → use `outline_other_process_documents.md`
- User requests chapter changes → regenerate the outline after the change and re-confirm

## Step 4: write (Fill + Decide)

### Must Do

1. Fill chapter by chapter in order
2. Annotate the data source for each chapter (which document / which section / which line)
3. Proactively ask the user when materials are missing (provide options)
4. Generate the "Decision and Opinion" (决策与意见) section (with 【Framework】+【Strength】+【Data Source】)
5. Self-check against the no-fabrication red line checklist
6. Append the change log
7. Output the final document to the project directory
8. Output the intermediate draft to `<work_root>/.aiassistive/output/<project_id>/`

### Do Not

- Do not fabricate any numbers / dates / names
- Do not write unfounded expressions like "should / might / perhaps"
- Do not skip the change log

### Exceptions

- User refuses to provide missing materials → mark the corresponding chapter as "Pending-fill" (待补)
- Self-check fails → must rewrite the corresponding chapter

## Deliverables List

| Deliverable | Location |
|---|---|
| Final official document | `<project_root>/03_技术文档及评审/<subdir>/<type_name>.md` |
| Change log (appended) | `<project_root>/06_变更及暂停/变更记录.md` |
| Intermediate draft | `<work_root>/.aiassistive/output/<project_id>/<type_name>_draft.md` |
| Console report | `<project_id> · <type> · Generated` + 3 paths |
