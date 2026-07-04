# 典型流程（给元说明引用）

## Flow A: 纯查询
**触发**：用户问"项目里有什么/什么时候评审"

```
1. project-doc-overview（当前 skill · 加载即可）
2. → intent-clarification（取项目根 + intent + 范围）
3. → project-doc-query
4. → 调 read_doc.py 读项目资料
5. → 输出答案
6. → manage_project_log.py append-operation 写主日志
```

## Flow B: 仅大纲
**触发**：用户说"写个测试方案大纲"

```
1. project-doc-overview
2. → intent-clarification（项目根 + 文档类型 + 意图）
3. → project-doc-outline
4. → intent-clarification（环境/技术/合规 10 个技术点）
5. → 输出大纲 .md（含"环境技术声明"附录）
6. → manage_project_log.py append-operation
```

## Flow C: 完整文档生成
**触发**：用户说"按项目资料写完整测试方案"

```
1. project-doc-overview
2. → intent-clarification（项目根 + 文档类型 + 意图）
3. → project-doc-workflow（编排）
4. → Step 2: project-doc-query（抽章节 + 提取证据）
5. → Step 3: project-doc-outline（生成大纲）
6. → Step 4: project-doc-write
7.   → intent-clarification（数据完整性，无数据章节主动问）
8.   → 调 read_doc.py 取证据
9.   → 填充正文 + 生成"决策与意见"
10.  → 调"操作 word 的 skill"转 .docx
11.  → 追加变更记录
12. → manage_project_log.py append-operation（多次）
```

## Flow D: 流程中再问（澄清可重入）
**触发**：任何子 skill 任何步骤遇到新问题

```
当前 skill 调 intent-clarification
  ↓
按维度指向具体 reference
  ↓
按规范询问 + 记录
  ↓
继续原 skill 流程
```

**关键**：必须**先读** `.project/<项目号>/clarification_log.md` 避免重复问。

## Flow E: 数据入库（独立子套件）
**触发**：用户说"把这个 PDF 入库"

```
1. project-doc-overview（可选）
2. → data-skill（不通过 intent-clarification）
3. → 自处理配置询问
4. → 调 parse_file.py OCR
5. → 自愈核验
6. → 完结
```

## Flow F: .project 目录初始化（首次执行任何 skill）
**触发**：用户首次对某项目调用任何 project-doc skill

```
1. 调 manage_project_log.py init --project-id X --work-root Y
2. 自动创建 Y/.project/X/ + project_log.md + clarification_log.md
3. → 写入初始化行
4. → 后续所有操作追加到 project_log.md
```

## Flow G: 跨会话恢复
**触发**：用户跨天/跨会话继续

```
1. 调 manage_project_log.py read --project-id X --work-root Y
2. 读 project_log.md 看到上次进度
3. 读 clarification_log.md 看到已有澄清
4. 继续上次流程
```
