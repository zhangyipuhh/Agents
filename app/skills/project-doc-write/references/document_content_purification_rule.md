# Document Content Purification Rule (must-read before writing deliverables)

> This rule is the hard constraint for write Step 4.1 when writing the body. Content violating this rule **must** be deleted or rewritten in the Step 4.8 self-check.

---

## 1. "Empty Talk" to Delete Unconditionally

### 1.1 Status Labels

```markdown
❌ Document Status: Review Draft
❌ Document Status: Draft
❌ Document Status: V0.X Draft
❌ Document Status: Pending Review
❌ Document Status: Final
❌ Document Version: V0.1
```

**Exception**: When the user **explicitly requests** to write a status in the Planning Sheet / requirements / task, use the user's wording.

### 1.2 Role Sign-off Table

```markdown
❌ | Role | Name |
❌ | Compile | Zhang San |
❌ | Review | Li Si |
❌ | Approve | Wang Wu |
```

**Exception**: When the Planning Sheet / requirements **explicitly specify** concrete names, fill in per the Planning Sheet (e.g., "Project Manager: Huang Min (黄敏)").

### 1.3 Meta-Placeholder Paragraphs

```markdown
❌ > Review draft stage: specific data not yet filled
❌ > To be supplemented in XX stage
❌ > This review draft is given as a placeholder
❌ > The actual case quantity is based on the test case library
```

**Replacement**: Use `**待补 (Pending-fill)**: [specific description]`, see §3.

### 1.4 "—" Placeholders

```markdown
❌ | Unit Test | — | — | — | — | — | — |
❌ | Critical | — | — | — | — |
❌ Performance Test: [ ] All pass / [ ] Basically pass
```

**Replacement**: See §3 "**待补 (Pending-fill)**" mode.

### 1.5 Empty References

```markdown
❌ 14.2 Test Report Template - Refer to the "Test Report" template in the project template library
❌ See appendix
❌ Refer to the "XX" template in the project template library
❌ Refer to project documents
```

**Replacement**: Provide the content directly, or write "**待补 (Pending-fill)**: [specific description]".

### 1.6 Project-Specific Tools

```markdown
❌ Use ZenTao / Jira for defect tracking
❌ Use Git / SVN for version management
❌ Notify via DingTalk / Feishu
```

**Exception**: When **explicitly mentioned** in project materials (Planning Sheet / requirements / contract / email), they may be written.

### 1.7 Fabricated Names / Dates / Numbers

```markdown
❌ Compiled by: Zhang San (the Planning Sheet has no "Zhang San")
❌ Acceptance time: 2025-12-31 (the Planning Sheet has no such date)
❌ Performance metric ≥ 500 TPS (the requirements have no such number)
```

**Strictly forbid fabrication**. All specific values must come from project materials. Not in materials → proactively ask the user.

---

## 2. Allowed Content

| Type | Example | Notes |
|---|---|---|
| Industry common terminology | "Unit test" "Regression test" "Gray-box test" | Industry common knowledge; allowed |
| National / industry standards | "GB/T 25000.51" "ISO/IEC/IEEE 29119" | Recognized standards; allowed |
| Tools explicitly mentioned in project materials | The Planning Sheet says "Use Postman for API testing" | Allowed |
| Names explicitly mentioned in project materials | The Planning Sheet says "Project Manager: Huang Min" | Allowed |
| Dates / numbers explicitly mentioned in project materials | The Planning Sheet says "K3 Planned Time: 2025-12-10" | Allowed |
| Data explicitly mentioned in project materials | The contract says "Duration 6 months" | Allowed |

---

## 3. Handling of Data-Less Chapters (Key)

For "data-driven" documents such as Test Report, Test Summary, Acceptance Report, the **chapter must be retained** (cannot be deleted), but **without any placeholders**:

### 3.1 Recommended Wording

```markdown
## 4.1 Test Case Execution Statistics

**待补 (Pending-fill)**: This chapter needs the project team to fill in the actual data after test execution.

Data Sources:
- Test case library (ZenTao / Jira / Excel form, decided by project reality)
- "K-Point Planned Cumulative Progress" column in the Planning Sheet
- Actual test execution records

Suggested fields (organized by "test stage × planned / executed / passed / failed / blocked / pass rate").

Current No Data Source: The Planning Sheet / requirements / contract provide no test execution data.
```

### 3.2 Not Allowed Wording

```markdown
## 4.1 Test Case Execution Statistics

| Test Stage | Planned Cases | Executed Cases | Passed | Failed | Blocked | Pass Rate |
| --- | --- | --- | --- | --- | --- | --- |
| Unit Test | — | — | — | — | — | — |
| Integration Test | — | — | — | — | — | — |
| System Test | — | — | — | — | — | — |
```

> ❌ Tables with all "—" placeholders are an anti-pattern.

### 3.3 Step 4.2.5 Data Integrity Inquiry

**Before** writing a data-driven chapter, write must proactively ask the user:

> "The following chapters require actual data, but there is no evidence in the current project materials:
>  - 4.1 Case statistics
>  - 5.2 Performance test results
>  - 7.1 Acceptance conclusion
>  Please choose:
>  1) Provide data (please give)
>  2) Keep 'Pending-fill' (待补) status (no placeholders; follow §3.1 wording)"

See `references/data_integrity_query_template.md` for detailed wording.

---

## 4. Chapter-Level Purification Checklist

After write Step 4.1 finishes a chapter, **self-check** the following:

- [ ] No status labels ("Review Draft" etc.)
- [ ] No fabricated role sign-off tables
- [ ] No meta-placeholder paragraphs ("> Review draft stage: not yet...")
- [ ] No "—" placeholders in tables (all replaced with "Pending-fill" paragraphs)
- [ ] No empty references ("see template" etc.)
- [ ] Tools / terms are all explicitly mentioned in project materials
- [ ] Data-driven chapters use the "**待补 (Pending-fill)**" mode or have asked the user

---

## 5. Linkage with docx Conversion

After purification, .md → docx-skill converts to .docx. docx-skill only does style application (cover / TOC / fonts), and does **not** do content purification. Therefore **purification must be completed at the .md stage**.
