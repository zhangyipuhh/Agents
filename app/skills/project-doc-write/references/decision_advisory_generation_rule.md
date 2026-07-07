# Decision Advisory Generation Rule

> Used when `project-doc-write` generates the "Decision and Opinion" (决策与意见) section.

## Input

- Project Planning Sheet (xlsm)
- Contract / requirements / proposal
- Weekly reports / milestone reports
- The current document's writing context

## Output

A "Decision and Opinion" (决策与意见) section in the format of `references/decision_advisory_template.md`.

## Decision Categories (per PMP Knowledge Areas)

| Category | Trigger Conditions | Data Source |
|---|---|---|
| Scope Decision | Contract scope vs. actual delivery | Contract + requirements + weekly report |
| Schedule Decision | Planned vs. actual deviation > 5% | Planning Sheet "Milestone" + weekly report |
| Cost Decision | Planned cost vs. actual cost | Planning Sheet "Cost-Benefit Analysis" + weekly report |
| Quality Decision | Failed test / defect density exceeds threshold | Test report + Planning Sheet "Quality Objectives" |
| Risk Decision | Risk register vs. actual triggers | Planning Sheet "Risk Register" + weekly report |
| Resource Decision | Person-month input inconsistent with plan | Planning Sheet "Cost-Benefit Analysis" + weekly report |
| Communication Decision | Important stakeholders absent | Communication plan + meeting minutes |
| Procurement Decision | Procurement delivery delay | Procurement contract + implementation report |
| Change Decision | Client raised new requirement | Client email + change control record |
| Stakeholder Decision | Stakeholder conflict / low satisfaction | Stakeholder register + communication records |

## Decision Strength

| Strength | Meaning | Trigger |
|---|---|---|
| Strong Recommendation (强建议) | Should be executed | Multi-source data consistently supports |
| Weak Recommendation (弱建议) | Worth considering | Single data source supports |
| Notice (提示) | Needs attention | Data trend shows anomaly |
| Warning (警告) | Must respond | Deviation exceeds tolerance |

## Mandatory Output Format

The first line of each Decision and Opinion (决策与意见):

```
【Framework: {PMP|PRINCE2|Systems Analyst} · {Framework Layer|Landing Layer|Practice Layer}】
【Category: {Scope|Schedule|Cost|Quality|Risk|Resource|Communication|Procurement|Change|Stakeholder}】
【Strength: {Strong Recommendation|Weak Recommendation|Notice|Warning}】
【Data Source: Planning Sheet "X" sub-tag + document path N】
【Decision Point】: <specific question>
【Basis】: <specific data>
【Suggestion】: <specific action>
【Risk】: <consequence of not executing>
```

## Strictly Forbidden

- Baseless assumptions
- No data source
- No framework label
- Perfunctory one-liners
- Using "industry best practice" to substitute this project's data
