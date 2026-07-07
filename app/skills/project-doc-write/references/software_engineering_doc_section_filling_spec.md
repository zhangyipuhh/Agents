# Software Engineering Document — Chapter Filling Specification

> This specification is the chapter filling standard for the `project-doc-write` stage.

## General Principles

1. **The first sentence of each chapter states the chapter's purpose** (1-2 sentences)
2. **At the end of each chapter, give a "summary" or "items to confirm"** (if any)
3. **Chapter titles are numbered with Arabic numerals** (1, 1.1, 1.1.1)
4. **Tables must have headers and units**
5. **Figures must have figure number and figure title**
6. **References must be annotated with the document source** (e.g., "Per Planning Sheet 'Review Plan' sub-tag")

## Filling Specifications for Each Chapter Type

### Introduction-Type Chapters (1.1/1.2/1.3)

- Write **project background, scope, readers, terminology**
- Background: can quote from the contract / project initiation document
- Scope: clearly state "what to do / not to do"
- Readers: list the main reader roles

### Overall / Overview-Type Chapters

- Include **one overall diagram** (architecture diagram / relationship diagram / flow chart)
- Write **3-5 core points**
- Use lists / tables; do not write at length

### Design / Solution-Type Chapters

- First explain "why choose this way" (solution comparison)
- Then explain "how to do it specifically" (steps / parameters / configuration)
- Finally explain "risks and alternatives" (Plan B)

### Plan / Schedule-Type Chapters

- Tables list: phase / start / end / deliverable / responsible person
- Must align with the "Milestone" and "WBS" sub-tags of the Planning Sheet
- Deviations must be annotated

### Test-Type Chapters

- Test cases: ID / module / input / step / expected / actual
- Defects: ID / severity / description / status / responsible person
- Coverage: clearly state the measurement method

### Risk-Type Chapters

- Risks: ID / description / probability / impact / response / responsible person
- Risk level: high / medium / low
- Must align with the "Risk Register" of the Planning Sheet

## Expression Specification

- Do not use "we / you"; use "project team / contractor / client"
- Time format: `YYYY-MM-DD`
- File path: `<project_root>/...` uses the path relative to the project root
- Currency unit: 10,000 yuan (with unit)

## Strictly Forbidden

- "etc." / "and so on" type unclear expressions
- "approximately" / "around" type vague quantities
- "should" / "might" / "perhaps" type unfounded expressions
- Fabricated contract amounts, dates, names
