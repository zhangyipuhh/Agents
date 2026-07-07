# doc_status.md · 文档状态

> 配套 `intent-clarification/SKILL.md` 使用。
> owner skill：project-doc-write
> 场景分类：D. 文档属性

## 触发条件

write 准备在文档封面/头部添加"文档状态"字段时（"评审稿" / "草稿" / "正式版" / "V0.X" 等）。

## 询问话术

```markdown
## 关于文档《[文档名]》的文档状态

当前 write 默认不写状态字段（"评审稿" / "草稿" / "正式版" 等）。

请选择：
1. **保持沉默**（不写状态字段，文档默认是 V1.0 正式版）
2. **写状态**：请明确指定
   - "评审稿"
   - "草稿"
   - "正式版"
   - "V0.X 草稿"
   - "其他"（请说明）
```

## 推荐行为

| 用户选择 | 行为 |
|---|---|
| 没说 | **保持沉默**（不写状态字段） |
| "出 V1.0 初稿" | 写 `文档状态：初稿` |
| "出评审稿" | 写 `文档状态：评审稿` |
| "正式版" | 写 `文档状态：正式版` |
| "V0.X 草稿" | 写 `文档状态：V0.X 草稿` |

## 严禁行为

```markdown
❌ 文档状态：评审稿  ← 用户没说
❌ 文档状态：草稿    ← 用户没说
❌ 文档状态：V0.1 草稿 ← 用户没说
```

## 推荐格式

```markdown
| 项目编号 | XXX |
| --- | --- |
| 文档版本 | V1.0 |
| 编制日期 | YYYY-MM-DD |
| 文档状态 | [用户指定状态] |  ← 仅在用户指定时填
```

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "D.document_attr" --item "doc_status" \
    --question "文档状态？" --answer "保持沉默" \
    --source "用户口述" --asked-by "project-doc-write"
```
