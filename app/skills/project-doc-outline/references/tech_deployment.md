# tech_deployment.md · 部署方式

> 配套 `intent-clarification/SKILL.md` 使用。
> 影响章节：实施部署方案 §4 / 概要设计 §2.4 / 验收报告 §4.3

## 询问时

先扫项目资料关键词：**部署 / 云 / 物理机 / 虚拟化 / 容器 / K8s / Docker / 阿里云 / 华为云 / 政务云 / 私有云 / 混合**

### 已有信息时

```markdown
**【已有信息】**

> 合同.pdf / §3.3 第 2 行
> "采用政务云部署，应用容器化"
```

请选择：
1) 按已有信息写
2) 我现在补充
3) 大纲阶段先不写

### 无信息时

```markdown
**【未找到】** 项目资料中无相关描述。

请选择：
- 物理机部署
- 虚拟化部署（VMware / Hyper-V / KVM）
- 容器化部署（Docker + Kubernetes）
- 云部署（阿里云 / 华为云 / 腾讯云 / 政务云）
- 混合部署（多种方式组合）
```

如选了具体类型，请补充：
- 云服务商 / 私有云厂商
- 节点规模
- 是否高可用 / 容灾

## 用户回答"待定"时

同 `tech_hardware.md` 模板，影响章节为实施部署 §4 / 概要设计 §2.4 / 验收 §4.3。

## 记录到日志

```bash
python manage_project_log.py append-clarification \
    --project-id <ID> --work-root <ROOT> \
    --dimension "C.environment" --item "tech_deployment" \
    --question "部署方式？" --answer "政务云 + 容器化" \
    --source "合同 §3.3 第 2 行" --asked-by "project-doc-outline"
```
