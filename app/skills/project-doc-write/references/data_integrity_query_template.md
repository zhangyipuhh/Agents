# write Step 4.2.5 Data Integrity Query Template

> When the target document is "data-driven" (Test Report / Test Summary / Acceptance Report / Implementation Summary, etc.),
> write must use the wording from this template to proactively ask the user.

---

## Trigger Conditions

Trigger if any of the following is met:

1. The target document is one of the following:
   - Test Report
   - Test Summary
   - Acceptance Report
   - Implementation Summary
   - Trial Run Report
   - Any document whose chapters contain data fields such as "case count / defect count / performance metrics / coverage / pass rate"
2. These data fields have **no evidence** in the project materials (Planning Sheet / requirements / contract / email / weekly reports)

---

## Inquiry Wording (copy directly to use)

### Template A: First Inquiry (chapter-level)

> **Inquiry on data integrity for document "[Document Name]"**
>
> The following chapters require actual data, but there is no evidence in the current project materials:
>
> | Chapter | Required Data | Available in Current Project Materials? |
> |---|---|---|
> | [Chapter No.] [Chapter Name] | [Field 1] / [Field 2] / ... | ❌ No |
> | [Chapter No.] [Chapter Name] | [Field 1] / [Field 2] / ... | ❌ No |
>
> **Please choose**:
> 1. **Provide data** (please tell me the specific value of each field directly)
> 2. **Keep "Pending-fill" (待补) status** (follow the wording from `references/document_content_purification_rule.md §3.1`; no "—" placeholder)
> 3. **Do not generate** this document (wait until data is ready)

### Template B: Chapter-by-Chapter Inquiry (fine-grained)

> Document "[Document Name]" Chapter [X] "[Chapter Name]" requires the following data:
>
> - [Field 1]:
> - [Field 2]:
> - [Field 3]:
>
> How would you like to handle this?
> 1. Provide item by item (please answer in the order listed above)
> 2. All "Pending-fill"
> 3. Skip this chapter

### Template C: Re-confirmation (user has chosen "Keep Pending-fill")

> You have chosen "Keep 'Pending-fill' (待补) status". This chapter will be written in the following format:
>
> ```markdown
> ## [X.Y] [Chapter Name]
>
> **待补** (Pending-fill): This chapter needs the project team to fill in the actual data after [expected completion time].
>
> Suggested data sources:
> - [Source 1]
> - [Source 2]
>
> Suggested fields: [field list]
> ```
>
> Confirm? Or revise the wording?

---

## Inquiry Timing

| Scenario | Timing |
|---|---|
| Document is data-driven | In Step 4.1, ask for the data needed for each chapter before writing it |
| Document is process-type (Implementation Plan / Solution Design) | Do not ask (no data chapters) |
| User says midway "first give me a V1.0" | Ask once: "Which chapters should be 'Pending-fill' and which can be filled?" |

---

## Inquiry Principles

1. **Do not fabricate on your own**: All data must be given by the user or exist in project materials
2. **Do not write "—" placeholders**: Empty table rows are worse than a "**待补** (Pending-fill)" paragraph
3. **Do not repeat inquiries**: For the same set of data in the same document, ask once
4. **Interruptible**: The user can say "all Pending-fill", and write will immediately continue in "Pending-fill" mode

---

## The Fundamental Difference from "Review Draft" (评审稿)

| Old Practice (Review Draft) | New Practice (Pending-fill) |
|---|---|
| Document status: Review Draft | Do not write status (silence if user doesn't say) |
| > Review draft stage: specific data not yet filled | **待补** (Pending-fill): This chapter needs the project team to fill in actual data after [time] |
| \| Unit Test \| — \| — \| — \| | **Do not write empty tables**; use a "**待补** (Pending-fill)" paragraph instead |
| Compiled by: Zhang San (Planning Sheet has no Zhang San) | **Do not write role table** (silence if Planning Sheet has none) |

> See `references/document_content_purification_rule.md` for detailed purification rules.
