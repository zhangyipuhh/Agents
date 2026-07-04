# tech_third_party_ops.md · 第三方单位运维

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：实施部署方案 §3 部署环境 / 验收报告 §8 签字栏

## 询问时

先扫项目资料关键词：**运维 / 集成商 / 原厂 / 第三方 / 服务商 / 维保 / 驻场**

### 已有信息时

```markdown
**【已有信息】**

> 合同.pdf / §6.1 第 1 行
> "硬件由 XX 集成商提供 3 年驻场运维服务"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请选择：
- 全部由本项目组运维
- 部分由第三方运维（请说明哪些子系统/模块）
- 全部由第三方运维（如集成商 / 原厂）

如选了第三方，请补充：
- 第三方单位名称
- 运维范围（哪些模块/子系统）
- 运维方式（驻场 / 远程 / 定期巡检）
- 维保期
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为实施部署 §3 部署环境 / 验收报告 §8 签字栏。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_third_party_ops" \
    --question "第三方运维？" --answer "硬件由 XX 集成商运维" \
    --source "合同 §6.1 第 1 行" --asked-by "project-doc-outline"
```
