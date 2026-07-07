# Planning Sheet Sub-tag Description Template

> The Planning Sheet (策划表, V1.0.xlsm) is the project's **guiding document**. All submission timing, review timing, responsible persons, and cost-benefit estimates for deliverables are recorded here.
> This template defines the sub-tag structure and field extraction rules used by the suite when reading the Planning Sheet.

## Typical Sub-tags (per industry practice / GB/T 8564 / ISO 21500)

| Sub-tag | Purpose | Key Fields |
|---|---|---|
| **Cover** (封面) | Project ID, name, version, classification, responsible person | Project ID, Project Name, V1.0, Responsible Person, Date |
| **Overall Plan Overview** (总体计划概述) | Phase division, key milestones | Phase, Start Date, End Date, Deliverables |
| **Project Milestones** (项目里程碑) | Milestone nodes | Milestone Name, Planned Date, Status, Linked Deliverable |
| **WBS / Work Breakdown** (WBS / 工作分解) | Task list | WBS ID, Task Name, Responsible Person, Start/End Date, Duration |
| **Code Estimation** (编码估算) | Line count / function point estimation | Module, Estimated Lines of Code, Reuse Rate |
| **Summary Cost-Benefit Analysis** (汇总损益分析) | Person-month / cost estimation | Phase, Person-Month, Cost, Revenue |
| **Risk Register** (风险登记册) | Risk items | Risk Description, Probability, Impact, Response Strategy, Owner |
| **Assumptions & Constraints** (假设与约束) | Project assumptions | Assumption Description, Impact Scope |
| **Quality Objectives** (质量目标) | Quality metrics | Metric Name, Target Value, Measurement Method |
| **Communication Plan** (沟通计划) | Communication mechanism | Audience, Frequency, Method |
| **Change Control** (变更控制) | Change process | Change Level, Approval Authority |
| **Review Plan** (评审计划) | Review arrangement | Document Name, Submission Date, Review Date, Review Method, Reviewer |
| **Gantt Chart / Timeline** (甘特图 / 时间线) | Visual timeline | Task bars, milestones |
| **Responsibility Matrix (RACI)** (责任人矩阵 RACI) | Responsibility assignment | Task, Responsible, Accountable, Consulted, Informed |
| **Configuration Management Plan** (配置管理计划) | Baseline / version rules | Baseline Name, Version Number, Baseline Inclusion Date |

## Review Plan Sub-tag (most frequently used)

> When the user asks "when to submit / when to review", **read this table directly**.

| Field | Meaning |
|---|---|
| Deliverable Name (交付物名称) | Test Plan / Implementation Plan / Requirements Specification / ... |
| Submission Date (提交日期) | Internal completion date |
| Review Date (评审日期) | Review meeting date |
| Review Method (评审方式) | Meeting review / Email review / Peer review |
| Reviewer (评审人) | List of reviewers (may be multiple) |
| Review Conclusion (评审结论) | Pass / Conditional Pass / Fail (filled in after review) |

## Cost-Benefit Analysis Sub-tag (used for advisory)

- Planned person-month per phase vs. actual person-month → schedule variance
- Planned cost vs. actual cost → cost variance
- Risk Register vs. actual risk triggers → risk hit rate

> When the suite generates "Decision and Opinion" (决策与意见), it **must** derive the conclusions from the difference between these sub-tags' actual values and baseline values; no fabrication is allowed.

## Field Extraction Notes

1. The xlsm may contain VBA macro formulas; the suite uses openpyxl's `data_only=True` to read **calculated** values
2. Hidden sheets are **not** included by default (`include_hidden=False`), unless the user explicitly requests
3. Tables are rendered as plain text (separated by `\t`) for easy slicing and searching later
4. Sub-tag names may vary by project; the suite **fuzzy-matches** the keywords above (e.g., "Milestone" / "里程碑")
