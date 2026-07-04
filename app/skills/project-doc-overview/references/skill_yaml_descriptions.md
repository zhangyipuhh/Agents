# 各 skill 的 YAML 描述（精炼版 · 给元说明引用）

## intent-clarification
```
name: intent-clarification
description: Use whenever any project-doc skill (query/outline/write/workflow/data-skill) needs to confirm something with the user — unified protocol: scan project artifacts first, show prior answers, cite source+line, handle "待定" by re-asking. Re-entrant.
```

## project-doc-hub
```
name: project-doc-hub
description: Use when the user wants to create, query, or update software-engineering project deliverables — entry point that dispatches to query/outline/write/workflow.
```

## project-doc-query
```
name: project-doc-query
description: Use when the user asks questions about a software-engineering project's documents, milestones, deliverables, review schedule, or wants PMO-level advisory — applies three-layer framework overlay (PMP framework layer + PRINCE2落地层 + 系统分析师实务层) and forces intent-clarification (fact vs decision) before answering.
```

## project-doc-outline
```
name: project-doc-outline
description: Use when the user wants a chapter outline (no body content) for any of the 10 supported software-engineering deliverable types — picks the corresponding reference template and applies software-engineering standard chapter structure. Forces environment/tech/compliance clarification before generating.
```

## project-doc-write
```
name: project-doc-write
description: Use when the user has an approved outline and wants the document body filled in based strictly on existing project artifacts — generates 决策与意见 from real project data deltas, never invents content, asks user when info is missing. Forces data-integrity clarification for data-driven sections.
```

## project-doc-workflow
```
name: project-doc-workflow
description: Use when generating a software-engineering project deliverable end-to-end (from initial user request to final document on disk) — orchestrates the 4-step pipeline (hub → query → outline → write) and provides the work-skill checklist.
```

## data-skill
```
name: data-skill
description: 把本地业务文件（PDF/DOCX/图片/Excel）通过 MinerU OCR 解析后, LLM 选表+抽字段, 脚本校验, SQLite 入库. 自动批处理 + 自愈核验 (verify+补跑).
```

> **注意**：data-skill 是独立的"数据入库"子套件，**不属于** project-doc 澄清协议范围。其配置询问（OCR/DB）自行处理。
