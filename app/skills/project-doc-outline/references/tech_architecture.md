# tech_architecture.md · 系统架构

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：概要设计 §2 系统总体架构 / 实施方案 §6.1 软件实施 / 验收报告 §4.3

## 询问时

先扫项目资料关键词：**架构 / 分层 / 微服务 / 单体 / MVC / SOA / 中台 / 前后端分离 / B/S / C/S / 部署架构 / 节点 / 集群**

### 已有信息时

```markdown
**【已有信息】**

> 概要设计说明书.docx / §2.2 第 1 行
> "采用前后端分离的 B/S 架构，前端 Vue，后端 Spring Boot 微服务"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请提供：
- 架构模式（单体 / 分层 / 微服务 / SOA / 中台）
- B/S 或 C/S
- 前后端是否分离
- 主要技术栈（前端框架 / 后端框架 / 数据库 / 中间件）
- 部署架构（单节点 / 主备 / 集群 / 分布式）
- 关键技术约束（如性能 / 容量 / 并发）
```

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为概要设计 §2 / 实施方案 §6.1 / 验收 §4.3。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_architecture" \
    --question "系统架构？" --answer "前后端分离 + 微服务" \
    --source "概要设计 §2.2 第 1 行" --asked-by "project-doc-outline"
```
