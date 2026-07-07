# tech_localization.md · 国产化适配

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：概要设计 §6.1 / 实施部署 §3 / 验收报告 §4.3 / 测试报告 §5.4 兼容性测试

## 询问时

先扫项目资料关键词：**国产化 / 信创 / 麒麟 / 统信 / UOS / 欧拉 / openEuler / 达梦 / 金仓 / 神通 / 人大金仓 / 高斯 / 海光 / 鲲鹏 / 飞腾 / 龙芯 / 兆芯 / 东方通 / 金蝶天燕 / 中创中间件**

### 已有信息时

```markdown
**【已有信息】**

> 合同.pdf / §3.4 第 3 行
> "系统应适配国产化操作系统（麒麟 V10）和数据库（达梦 8）"
```

请选择：
1) 按已有信息写
2) 我现在补充更详细的国产化清单
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请选择国产化范围：
- 不涉及国产化
- 涉及部分国产化（请说明范围：仅 OS / 仅 DB / OS+DB+中间件）
- 全面国产化（CPU/OS/DB/中间件 全部）

如选了部分/全面国产化，请补充：
- CPU：海光 / 鲲鹏 / 飞腾 / 龙芯 / 兆芯 / 国外（具体型号）
- 操作系统：麒麟 V10 / 统信 UOS / 欧拉 openEuler / RHEL / CentOS
- 数据库：达梦 DM8 / 人大金仓 KingbaseES / 神通 / 高斯 GaussDB / Oracle
- 中间件：东方通 TongWeb / 金蝶天燕 / 中创 / Tomcat / WebLogic
- 兼容性认证情况（如已取得）
```

## 用户回答"待定"时

```markdown
## ⚠️ 该项未确定，无法继续

**未确定项**：国产化范围

**该信息缺失将导致以下章节无法精确设计**：
- 概要设计 §6.1 安全设计
- 实施部署方案 §3 环境合规
- 验收报告 §4.3 验收环境
- 测试报告 §5.4 兼容性测试

请选择：
1) **停止大纲生成**（推荐）
2) **提供详细信息**
3) **强制继续**
```

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_localization" \
    --question "国产化范围？" --answer "OS=麒麟 V10 / DB=达梦 8" \
    --source "合同 §3.4 第 3 行 + 用户确认" --asked-by "project-doc-outline"
```
