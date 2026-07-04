# tech_database.md · 数据库

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：实施部署方案 §3.2 / 概要设计 §4.2 / 验收报告 §4.3 / 测试方案 §6.2 软件环境（含数据库配置子项）

## 询问时

先扫项目资料关键词：**数据库 / Oracle / PostgreSQL / MySQL / 达梦 / 金仓 / 神通 / 人大金仓 / 高斯 / TiDB / 部署模式 / 主备 / 集群**

### 已有信息时

```markdown
**【已有信息】**

> 合同.pdf / §3.1 第 5 行
> "数据库采用达梦 DM8 国产化数据库，主备模式"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请提供：
- 数据库选型（Oracle / PostgreSQL / MySQL / 达梦 / 金仓 / 神通 / 人大金仓 / 高斯 / TiDB / OceanBase）
- 版本号
- 部署模式（单机 / 主备 / RAC / 集群 / 分布式）
- 字符集与排序规则
- 容量规划（如有）
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为实施部署 §3.2 / 概要设计 §4.2 / 验收 §4.3 / 测试 §6.2。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_database" \
    --question "数据库？" --answer "达梦 DM8 主备" \
    --source "合同 §3.1 第 5 行" --asked-by "project-doc-outline"
```
