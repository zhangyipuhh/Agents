# Planning Sheet Field Quick Reference

> Used together with `references/planning_sheet_subtag_template.md`. This table is a **field-level** quick reference for reverse lookup by "field name" to its location.

## Field Name → Sub-tag Location

| Field Name | Sub-tag | Column Name | Row / Cell |
|---|---|---|---|
| Project ID (项目编号) | Cover (封面) | — | — |
| Project Name (项目名称) | Cover (封面) | — | — |
| Phase Name (阶段名) | Overall Plan Overview (总体计划概述) / WBS | Phase (阶段) | Row N |
| Phase Start Date (阶段起始日) | Overall Plan Overview (总体计划概述) / WBS | Start (起始) | Row N |
| Phase End Date (阶段结束日) | Overall Plan Overview (总体计划概述) / WBS | End (结束) | Row N |
| Phase Deliverable (阶段交付物) | Overall Plan Overview (总体计划概述) / WBS | Deliverable (交付物) | Row N |
| Milestone Name (里程碑名) | Milestone (里程碑) | Milestone (里程碑) | Row N |
| Milestone Date (里程碑日期) | Milestone (里程碑) | Planned Date (计划日期) | Row N |
| Document Name (文档名) | Review Plan (评审计划) | Deliverable (交付物) | Row N |
| Document Submission Date (文档提交日期) | Review Plan (评审计划) | Submission Date (提交日期) | Row N |
| Document Review Date (文档评审日期) | Review Plan (评审计划) | Review Date (评审日期) | Row N |
| Reviewer (评审人) | Review Plan (评审计划) | Reviewer (评审人) | Row N |
| Risk Description (风险描述) | Risk Register (风险登记册) | Risk (风险) | Row N |
| Risk Response (风险应对) | Risk Register (风险登记册) | Response (应对) | Row N |
| Person-Month (人月) | Summary Cost-Benefit Analysis (汇总损益分析) | Person-Month (人月) | Row N |
| Cost (成本) | Summary Cost-Benefit Analysis (汇总损益分析) | Cost (成本) | Row N |

## Fuzzy-Match Keywords

> Sub-tag names may vary by project; **fuzzy-match** the following keywords is recommended:

| Standard Sub-tag | Alternative Names |
|---|---|
| 总体计划概述 (Overall Plan Overview) | 项目概述 (Project Overview) / Overview / 项目概况 (Project Summary) |
| 里程碑 (Milestone) | Milestone / 关键节点 (Key Node) / 节点计划 (Node Plan) |
| 评审计划 (Review Plan) | 评审安排 (Review Arrangement) / Review Plan / 评审 (Review) |
| 风险登记册 (Risk Register) | 风险 (Risk) / Risk Register / 风险清单 (Risk List) |
| 汇总损益分析 (Summary Cost-Benefit Analysis) | 损益 (Cost-Benefit) / Cost Summary / 成本汇总 (Cost Summary) |
| WBS | 工作分解 (Work Breakdown) / 任务分解 (Task Breakdown) / 任务清单 (Task List) |
| RACI | 责任矩阵 (Responsibility Matrix) / 责任分配 (Responsibility Assignment) / 责任人 (Responsible Person) |

## Extraction Recommendations

- Use openpyxl to read the entire sheet content, separating columns by `\t`
- Scan "column headers" of each row to locate key columns
- Field not found → ask the user to upload the Planning Sheet or confirm the Planning Sheet version
- Field found → output "row number + column name" as evidence for traceability
