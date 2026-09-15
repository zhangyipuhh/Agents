# 知识库

知识库模块提供文档上传、检索与对话能力，支持个人知识库与团队共享知识库。

## 前置条件

- 已登录系统
- 浏览器已启用 Cookie
- 文档符合上传白名单（`.pdf / .doc / .docx / .txt / .md / .markdown / .csv / .json`）
- 单文件 ≤ 50 MB
- 单次批量 ≤ 20 个文件

## 功能概览

知识库支持以下核心能力：

1. **文档上传**：支持 PDF、Word、Excel、TXT、Markdown 等格式
2. **自动分块**：上传后自动按段落 / 章节切分，支持自定义分块大小
3. **对话检索**：智能体会自动从知识库中检索相关内容作为回答依据
4. **文件夹管理**：多级文件夹组织，支持按文件夹授权
5. **索引重建**：检索效果不佳时可触发索引重建

## 上传文档

点击「上传文件」按钮，选择本地文件即可。系统支持：

- 单文件最大 50 MB
- 批量上传（一次最多 20 个文件）
- 拖拽上传

#### 上传链路
1. 前端 `uploadFile()` 调用 `/api/core/upload*`（分片上传）或 `/api/files/upload`（单次上传）
2. `app/shared/utils/files/upload_validation.py` 白名单校验 + 魔数嗅探（`.pdf / .doc / .docx`）
3. 文件落地 `data/upload/{yyyy}/{mm}/{dd}/{session_id}/`
4. `attachment_db` 写库（`file_path` / `parsed_file_path` / `status`）
5. 异步任务推入解析队列

![上传文档](/help/screenshots/features-knowledge/upload-doc.png)

#### 上传后状态机

| 状态 | 含义 | 触发下一步 |
|---|---|---|
| `uploaded` | 文件已落地 | 触发解析 |
| `parsing` | OCR / 文本提取中 | 解析完成 |
| `parsed` | 文本已抽取 | 触发分块 + 向量化 |
| `indexed` | 向量索引已生成 | 可被检索 |
| `failed` | 解析失败 | 查看 `error_message` |

## 文档解析

上传的文档会进入解析队列，系统会：

1. **提取文本**：OCR 处理图片型 PDF（`.pdf` 魔数嗅探后走 OCR 路径）
2. **分块切分**：按段落 / 章节切分为 chunks（默认 chunk_size=500 tokens，overlap=50 tokens）
3. **向量索引**：生成向量索引用于语义检索（使用 embedding 模型，配置在「基本设置 → LLM 模型」）

#### 解析规则扩展
- 自定义解析规则可在「智能体管理 → 工具管理 → doc_parser」配置
- Excel 解析走 `XLSLoader.py` 多 sheet 处理
- Markdown 解析走 `MarkdownLoader.py` 标题分级处理

## 知识库对话

在主对话区，智能体会自动识别用户问题是否与知识库相关：

- 如相关：自动检索 top-k chunks 作为上下文注入提示词
- 如不相关：直接调用通用对话能力

#### 检索流程
1. 用户消息 → `query_transformer.py` 改写查询
2. 向量相似度检索 top-k（默认 k=5）
3. 注入到 system prompt 的 `<knowledge>` 节点
4. LLM 生成回答（基于检索内容 + 标注来源）

#### 提示词注入约定

```xml
<available_knowledge>
<chunks>
  <chunk id="chunk_001" source="运维手册.pdf" score="0.92">...</chunk>
  <chunk id="chunk_002" source="巡检脚本.md" score="0.85">...</chunk>
</chunks>
</available_knowledge>
```

LLM 回答时按 `<source>` 字段标注引用来源，前端可点击跳转到原文。

## 文件夹管理

支持多级文件夹组织文档：

- 创建 / 重命名 / 移动文件夹
- 按文件夹授权（仅管理员可配置 ACL）
- 批量操作（删除、移动、导出）

#### 文件夹 ACL
- admin 默认对全部文件夹有读写权限
- 普通用户需被授予文件夹级 ACL（`user_folder_acl` 表）
- `MemorySaver` 缓存按 user_id 隔离

## 索引重建

如检索效果不佳，管理员可在「知识库管理」中触发索引重建：

1. 删除现有索引（`drop_index` SQL）
2. 重新解析所有文档（异步任务）
3. 重新生成向量索引

> ⚠️ **索引重建期间知识库对话能力可能受影响**，建议在低峰期操作。

## 文件格式详解

### PDF
- 文本型 PDF：直接走文本提取
- 图片型 PDF（扫描件）：走 OCR（`pytesseract`）
- 加密 PDF：拒绝上传（不支持解密）

### Word（.doc / .docx）
- `.docx`：使用 `python-docx` 解析段落 + 表格
- `.doc`：旧格式，使用 `antiword` / `libreoffice` 转换

### Excel（.xlsx / .xls）
- 多 sheet 自动识别
- 每个 sheet 作为独立 chunk

### Markdown / TXT
- 按段落切分
- 保留标题层级

### CSV / JSON
- 结构化数据，按行/字段切分

## 常见问题

### 文档上传失败？
- 检查文件类型是否在白名单内
- 检查文件大小是否超 50 MB
- 检查网络连接（断点续传需后端支持）
- 查看浏览器 Console 是否报 CORS 错误

### 知识库检索不到相关内容？
- 检查文档是否完成解析（状态显示「已索引」）
- 提问时明确提及文档名或关键词
- 在问题中明确指示「请参考知识库」
- 如仍无效，触发「索引重建」

### 检索结果不准确？
- 调整 chunk_size（更大 chunk 包含更多上下文）
- 调整 embedding 模型（更先进的模型提升语义理解）
- 优化文档结构（清晰的标题层级）

## 相关章节

- [智能体对话](/help/features/chat) — 与智能体对话时引用知识库
- [权限管理](/help/features/permission-management) — 文件夹级 ACL
- [基本设置 → 文件解析](/help/features/basic-settings#文件解析) — 解析器配置