# Skill Dependency Graph（套件内 skill 依赖关系）

```dot
digraph suite {
    rankdir=LR;
    node [shape=box, style=rounded];
    edge [label="调", fontsize=10];

    intent_clarification [label="intent-clarification\n(统一澄清协议)", color=red, style="rounded,filled", fillcolor="#fff5f5"];
    overview [label="project-doc-overview\n(本 skill · 元说明)", color=blue, style="rounded,filled", fillcolor="#f0f8ff"];
    hub [label="project-doc-hub\n(调度入口)"];
    query [label="project-doc-query"];
    outline [label="project-doc-outline"];
    write [label="project-doc-write"];
    workflow [label="project-doc-workflow"];
    data [label="data-skill\n(独立子套件)", color=gray, style="rounded,filled", fillcolor="#f5f5f5"];

    overview -> intent_clarification [label="强制调"];
    hub -> intent_clarification [label="强制调"];
    query -> intent_clarification [label="强制调"];
    outline -> intent_clarification [label="强制调"];
    write -> intent_clarification [label="强制调"];

    hub -> query [label="分派"];
    hub -> outline [label="分派"];
    hub -> write [label="分派"];
    hub -> data [label="分派"];

    workflow -> hub [label="编排"];
    workflow -> query [label="编排"];
    workflow -> outline [label="编排"];
    workflow -> write [label="编排"];
}
```

## 依赖规则

### 强依赖（必须调）
- **任何 skill** → `intent-clarification`（在需要问用户时）
- `project-doc-hub` → 各子 skill（按用户意图分派）

### 弱依赖（按需调）
- `project-doc-workflow` → `project-doc-hub`（编排时）
- 各 skill → `intent-clarification` 的具体 reference（按维度选）

### 不依赖
- `data-skill` 不依赖 `intent-clarification`（自行处理询问）
- 各子 skill 之间**不直接互调**（都通过 hub 编排）

## .project 目录写入规则

**任何** skill 流程结束后，**必须**调 `manage_project_log.py append-operation` 写一条到 `.project/<项目号>/project_log.md`。

**任何**澄清 Q/A 后，**必须**调 `manage_project_log.py append-clarification` 写一条到 `.project/<项目号>/clarification_log.md`。
