# tech_software.md · 软件配置

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：实施部署方案 §3.2 / 概要设计 §7.1 / 验收报告 §4.3 / 测试方案 §6.2

## 询问时

先扫项目资料关键词：**操作系统 / 中间件 / 版本 / JDK / .NET / Python / Tomcat / Nginx / Redis / 国产化软件**

### 已有信息时

```markdown
**【已有信息】**

> 需求说明书.docx / §5.2 第 8 行
> "操作系统：CentOS 7.9；中间件：Tomcat 9 + Redis 6.0"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请提供：
- 操作系统（Windows Server / Linux / 国产化如麒麟、统信）
- 应用服务器（Tomcat / Nginx / IIS / WebLogic）
- 缓存 / 消息中间件（Redis / Kafka / RabbitMQ / 国产化如东方通）
- 编程语言运行时（JDK / .NET / Python / 国产化如 JRE 国产版）
- 其他关键软件及版本
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为实施部署 §3.2 / 概要设计 §7.1 / 验收 §4.3 / 测试 §6.2。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_software" \
    --question "软件配置？" --answer "CentOS 7.9 + Tomcat 9" \
    --source "需求 §5.2 第 8 行" --asked-by "project-doc-outline"
```
