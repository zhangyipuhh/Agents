# Framework Selection Decision Tree

> When the user's intent is "advisory", this decision tree determines which framework is used preferentially.

## Decision Tree

```
What type is the user's question?
├─ Review / delivery / milestone arrangement
│   └─ [PMP framework layer · Schedule Management] + [PRINCE2 landing layer · Managing Stage Boundaries]
├─ Scope / change / baseline
│   └─ [PRINCE2 landing layer · Change theme] + [PMP framework layer · Integration / Scope / Change]
├─ Quality / testing / defects
│   └─ [Systems Analyst practice layer · Testing and Maintenance] + [PMP framework layer · Quality Management] + [PRINCE2 landing layer · Quality theme]
├─ Risk
│   └─ [PMP framework layer · Risk Management] + [PRINCE2 landing layer · Risk theme]
├─ Resource / cost / procurement
│   └─ [PMP framework layer · Resource / Cost] + [PRINCE2 landing layer · Business Case theme]
├─ Requirements
│   └─ [Systems Analyst practice layer · Requirements Analysis] + [PMP framework layer · Scope]
├─ Architecture / design
│   └─ [Systems Analyst practice layer · System Design] + [PMP framework layer · Scope / Schedule]
├─ Implementation / deployment / O&M
│   └─ [Systems Analyst practice layer · System Implementation and O&M] + [PMP framework layer · Executing] + [PRINCE2 landing layer · Delivery theme]
├─ Closing / acceptance
│   └─ [PMP framework layer · Closing Process Group] + [PRINCE2 landing layer · Continued Business Justification]
└─ Communication / reporting / meetings
    └─ [PMP framework layer · Communication Management] + [PRINCE2 landing layer · Plans theme]
```

## Role Positioning of the Three-Layer Framework

| Framework | Layer | What It Solves |
|---|---|---|
| **PMP** | Framework layer | "What does the management system look like" (5 Process Groups / 10 Knowledge Areas) |
| **PRINCE2** | Landing layer | "How to do each step specifically" (7 Processes / 7 Themes) |
| **Systems Analyst** | Practice layer | "Practical engineering issues in software engineering" (5 modules: Planning / Requirements / Design / Testing-Maintenance / Informatization) |

> The three are **not alternatives** but **additive**.
> Example: A quality question should be viewed from PMP Quality Management, landed with PRINCE2 Quality theme, and examined for practice from the Systems Analyst's testing module.

## Output Format

The first line of each advisory item is mandatory:

```
【Framework: {PMP|PRINCE2|Systems Analyst} · {Framework Layer|Landing Layer|Practice Layer}】
```

When fully stacked, output in the order "framework layer → landing layer → practice layer".
