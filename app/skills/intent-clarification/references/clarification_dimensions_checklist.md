# Clarification Dimensions Checklist (pointing to independent references within each skill)

> Companion to `intent-clarification/SKILL.md`.
> One reference file per technical point (under the owner skill's references/).
> **A0 Scenario Routing (场景分流)** — see SKILL.md §Step 0.

## A0. Scenario Routing (场景分流) (Required · First Step)

| Scenario | Required Inquiry Dimensions |
|---|---|
| `A0.technical_doc` Write a technical document | A.intent (doc_type) + C.environment (10 technical points) |
| `A0.administrative` Write a management document | A.intent (doc_type) + D.document_attr |
| `A0.factual_query` Factual query | A.intent (fact/decision) |
| `A0.advisory` Advisory consultation | A.intent (decision) + three-layer framework |

## A. Workflow Clarification (intent)

| Sub-item | Reference |
|---|---|
| Fact/decision + scope (project/industry) + project root + document type + intent | `../project-doc-query/references/intent.md` |

## B. Data Integrity (data)

| Sub-item | Reference |
|---|---|
| Section without data | `../project-doc-write/references/data_missing_section.md` |
| Numeric field missing | `../project-doc-write/references/numeric_field_missing.md` |

## C. Environment/Technology/Compliance (environment) — 10 technical points

| Technical Point | Reference |
|---|---|
| Hardware configuration | `../project-doc-outline/references/tech_hardware.md` |
| Software configuration | `../project-doc-outline/references/tech_software.md` |
| Database | `../project-doc-outline/references/tech_database.md` |
| Network | `../project-doc-outline/references/tech_network.md` |
| Deployment mode | `../project-doc-outline/references/tech_deployment.md` |
| Third-party O&M | `../project-doc-outline/references/tech_third_party_ops.md` |
| Classified Protection Level 3 (等保三级) | `../project-doc-outline/references/tech_security_level.md` |
| Localization (国产化) | `../project-doc-outline/references/tech_localization.md` |
| System architecture | `../project-doc-outline/references/tech_architecture.md` |
| Localization list (国产化清单) | `../project-doc-outline/references/tech_localization_list.md` |

## D. Document Attributes (document_attr)

| Sub-item | Reference |
|---|---|
| Role sign-off table (compile/review/approve) | `../project-doc-write/references/role_signoff.md` |
| Document status (review draft/draft/official version) | `../project-doc-write/references/doc_status.md` |

## E. Tool Configuration (data-skill, **not** within the project-doc suite)

Configuration inquiries for data-skill (OCR URL / DB path, etc.) are **not** handled through intent-clarification; they are processed independently.
