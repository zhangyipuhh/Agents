# tech_network.md · 网络情况

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：实施部署方案 §3.3 / 概要设计 §7.3 / 验收报告 §4.3 / 测试方案 §6.3 网络环境

## 询问时

先扫项目资料关键词：**网络 / 政务外网 / 政务内网 / 互联网 / VPN / 专线 / 带宽 / 防火墙 / DMZ / 网段 / IP 地址规划**

### 已有信息时

```markdown
**【已有信息】**

> 策划表.xlsx / 02-总体计划 / 第 8 行
> "部署在政务外网，与省厅通过政务专网连接"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请提供：
- 部署网络（政务外网 / 政务内网 / 互联网 / 专网 / VPN / 专线）
- 带宽（如千兆 / 万兆 / 100Mbps）
- 与外部系统的连接（省厅 / 市局 / 第三方接口）
- 安全区域（DMZ / 内网 / 隔离区）
- IP 地址规划（如有）
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为实施部署 §3.3 / 概要设计 §7.3 / 验收 §4.3 / 测试 §6.1。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_network" \
    --question "网络情况？" --answer "政务外网 + 政务专网" \
    --source "策划表 §2 第 8 行" --asked-by "project-doc-outline"
```
