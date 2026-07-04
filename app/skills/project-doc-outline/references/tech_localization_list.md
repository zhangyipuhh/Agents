# tech_localization_list.md · 国产化清单

> 配套 `intent-clarification/SKILL.md` 使用。
> 与 `tech_localization.md` 配合使用：本文件是"清单"详细列举，`tech_localization.md` 是"范围"决定。
> 影响章节：概要设计 §6.1 / 实施部署 §3.2 硬件环境 / 验收报告 §4.3

## 询问时

先扫项目资料关键词：**国产化 / 信创 / 适配清单 / 兼容性证书 / 互认证书**

### 已有信息时

```markdown
**【已有信息】**

> 合同附件 B《国产化适配清单》
> "CPU：海光 7285；OS：麒麟 V10 SP3；DB：达梦 DM8；中间件：东方通 TongWeb 7.0"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写（仅写"详见附件 B"）

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请提供完整国产化清单（按需填写）：

| 类别 | 选型 | 版本 | 备注 |
|---|---|---|---|
| CPU | 海光/鲲鹏/飞腾/龙芯/兆芯/国外 |   |   |
| 操作系统 | 麒麟/统信 UOS/欧拉/RHEL/CentOS |   |   |
| 数据库 | 达梦/金仓/神通/高斯/Oracle |   |   |
| 中间件-应用 | 东方通/金蝶天燕/中创/Tomcat/WebLogic |   |   |
| 中间件-消息 | 东方通/金蝶/中创/Kafka/RabbitMQ |   |   |
| 中间件-缓存 | 东方通/Redis |   |   |
| 浏览器 | 360/红莲花/Chrome/Edge |   |   |
| 外设 | 国产打印机/扫描仪/... |   |   |

每项请补充：
- 选型
- 版本号
- 是否取得兼容性互认证书
- 备注（采购来源 / 替代方案）
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_localization_list" \
    --question "国产化清单？" --answer "CPU=海光7285; OS=麒麟V10; DB=达梦DM8" \
    --source "合同附件 B" --asked-by "project-doc-outline"
```
