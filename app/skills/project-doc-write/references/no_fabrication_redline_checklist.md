# No-Fabrication Red Line Checklist

> Behaviors **strictly forbidden** for `project-doc-write` when writing the body and generating decisions.

## Red Line 1: Fabricating Numbers

- ❌ "The project is estimated to invest 5 million yuan" (no contract / Planning Sheet basis)
- ✅ "Per contract 0A_合同相关/合同.pdf clause 3, the contract amount is 5 million yuan"

## Red Line 2: Fabricating Dates

- ❌ "The project started on 2025-12-01"
- ✅ "Per Planning Sheet 'Overall Plan Overview' sub-tag, the start date is 2025-12-01"

## Red Line 3: Fabricating Names

- ❌ "The project manager is Zhang San"
- ✅ "Per Planning Sheet 'Cover' sub-tag, the project manager is Zhang Liupu (张镠谱)"

## Red Line 4: Fabricating Technical Details

- ❌ "This system uses the Spring Cloud microservice framework"
- ✅ "Per High-Level Design Specification §3.2, the technology stack is Spring Cloud Alibaba"

## Red Line 5: Fabricating Test Results

- ❌ "The test pass rate for this round is 100%"
- ✅ "Per Test Report §4.1, there are 120 test cases in this round, 115 passed, with a pass rate of 95.8%"

## Red Line 6: Fabricating Risks

- ❌ "This project has a requirement change risk"
- ✅ "Per Planning Sheet 'Risk Register' sub-tag row 5, 'Frequent client requirement changes' is a high risk"

## Red Line 7: Perfunctory "Suggestions"

- ❌ "Recommend strengthening communication"
- ✅ "Recommend adding 1 weekly progress sync meeting with the client (per Planning Sheet 'Communication Plan' sub-tag, current frequency is once every two weeks)"

## Red Line 8: Out-of-Scope Fabrication

- User says "write a Test Plan", but there is **no** requirements document in the project → **must** ask the user to upload a requirements document; not allowed to "make up one" on your own

## Red Line 9: Concealing the Unknown

- **Must** explicitly state when materials are insufficient
- ✅ "Requirements Specification §4.2 Performance Requirements chapter is missing; recommend supplementing before writing this section"

## Red Line 10: Misaligned References

- ❌ Calling the "Planning Sheet" a "Contract"
- ❌ Calling "High-Level Design" a "Detailed Design"
- References must be verifiable and traceable

## Self-Check List (check after each writing)

```
□ Are all numbers annotated with data sources (which document / which section / which line)?
□ Are all dates annotated with data sources?
□ Are all names annotated with data sources?
□ Are all technical solutions annotated with data sources?
□ Are all risks / suggestions annotated with data sources?
□ Are missing materials marked "Pending-fill" (待补) and the user queried?
□ Are all Decision and Opinion items annotated with 【Framework】+【Strength】+【Data Source】?
□ Are there any unfounded expressions like "should / might / perhaps"?
```

> Self-check **not passed** → **must** rewrite; cannot publish.
