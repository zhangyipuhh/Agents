# Document Type → Directory Quick Reference

> The 10 types of project deliverables supported by the suite and their locations under the project root.

| # | Document Type | Project Root Location | Review Requirements |
|---|---|---|---|
| 1 | Pre-Sales Proposal | `03_技术文档及评审/00_售前方案/` | — |
| 2 | Requirements Specification | `03_技术文档及评审/02_需求分析/` | Internal + external review |
| 3 | High-Level Design Specification | `03_技术文档及评审/03_概要设计/` | Internal + external review |
| 4 | Detailed Design Specification | `03_技术文档及评审/03_概要设计/` (some projects) or separate directory | Internal review |
| 5 | Implementation Plan | `03_技术文档及评审/01_实施方案/` | Archived after passing review |
| 6 | Test Plan | `03_技术文档及评审/05_测试、验收/` | Internal + external review |
| 7 | Test Report | `03_技术文档及评审/05_测试、验收/` | Internal + external review |
| 8 | Acceptance Report | `03_技术文档及评审/05_测试、验收/` or `07_验收结题/` | External review + client signature |
| 9 | Implementation & Deployment Plan | `03_技术文档及评审/06_实施部署及培训/` | Pre-implementation review |
| 10 | Training Plan | `03_技术文档及评审/06_实施部署及培训/` | Pre-implementation review |

## Document Type Identification Keywords (user expressions → standard types)

| User may say | Suite mapping |
|---|---|
| 售前 (pre-sales), 立项 (initiation), 可行性 (feasibility) | Pre-Sales Proposal |
| 需求 (requirements), 规格 (specification), SRS | Requirements Specification |
| 概要 (high-level), HLD, 总体设计 (overall design) | High-Level Design Specification |
| 详细 (detailed), LLD, 模块设计 (module design) | Detailed Design Specification |
| 实施 (implementation), 落地 (landing), 上线 (go-live) | Implementation Plan |
| 测试方案 (test plan), 测试计划 (test plan) | Test Plan |
| 测试报告 (test report), 测试总结 (test summary) | Test Report |
| 验收 (acceptance), 签收 (sign-off), 终验 (final acceptance) | Acceptance Report |
| 部署 (deployment), 运维 (O&M), 迁移 (migration) | Implementation & Deployment Plan |
| 培训 (training), 演练 (drill) | Training Plan |

## Dynamic Document Location Identification Rules

- Standard-numbered subdirectories → follow the table above
- Numbering does not exactly match the project → ask the user to confirm the location
- Document does not exist → ask the user:
  - "Generate a new document" or "modify based on an existing draft"?
  - Provide a format template?
