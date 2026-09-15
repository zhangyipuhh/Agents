# 基本设置

基本设置是 `.env` 配置迁入 DB 后的统一管理入口（2026-09-14 落地）。所有 22 组配置通过 `system_settings_groups` 表 + `SystemConfigRegistry` 注册。

## 前置条件

- **admin 角色**（路由 `require_admin_or_menu_acl('system.basic-settings')`）
- 浏览器已登录
- ⚠️ **重启后生效**：本页面修改的配置写入 DB，**重启 uvicorn / docker compose 后**才会加载到内存（lifespan 启动期 `seed_from_settings` 一次性加载到 `settings` 实例）

## 6 个孙 Tab 概览

| Tab | 包含 group_key 数 | 说明 |
|---|---|---|
| LLM 模型 | 5 | 主模型 + 各子智能体 LLM |
| 文件解析 | 3 | PDF / Word / 文档解析器 |
| 安全认证 | 4 | 密码策略 / MFA / CORS / Cookie |
| 网络与集成 | 3 | 飞书 / 邮件 / 第三方端点 |
| 沙箱与任务 | 4 | SANDBOX_* 11 字段 / 巡检 / 定时任务 |
| 其他 | 3 | 日志 / 缓存 / 实验性 |

## 沙箱与任务（重点详解）

### sandbox 组（SANDBOX_* 11 字段）

#### 前置依赖
1. **Docker daemon** 必须运行（Linux: `systemctl start docker`；Windows/Mac: Docker Desktop）
2. **`.env` 文件可访问**（首次 seed 时读取 fallback）
3. **admin 登录态**

#### 字段详解

| 字段 | 默认值 | 取值范围 | 设置效果 | 语法说明 |
|---|---|---|---|---|
| `SANDBOX_DOCKER_MODE` | `local` | `local` / `socket` / `dind` / `k8s` | 决定 sandbox 如何连 Docker daemon | `local` = 同进程；`socket` = 挂 docker.sock；`dind` = 容器内嵌 daemon |
| `SANDBOX_DOCKER_HOST` | `""` | URL 字符串 | socket 模式用 `unix:///var/run/docker.sock` | 仅 socket 模式必填 |
| `SANDBOX_IMAGE` | `python:3.12-alpine` | 任意已存在的镜像名 | 容器内 Python 运行时 | 镜像必须已 `docker pull` |
| `SANDBOX_MAX_MEMORY_MB` | `512` | ≥ 64 | 容器内存限制（MB） | 超出后容器 OOM kill |
| `SANDBOX_MAX_CPU_PERCENT` | `100` | 10~100 | 容器 CPU 限制（百分比） | 100 = 1 个 CPU 核心 |
| `SANDBOX_NETWORK_ENABLED` | `false` | bool | **默认禁用外网**（隔离） | 启用后容器可访问公网 |
| `SANDBOX_DEFAULT_TIMEOUT` | `60` | ≥ 1 | 命令默认超时（秒） | 超时后工具被中止 |
| `SANDBOX_CONTAINER_WORKSPACE` | `/workspace` | 容器内绝对路径 | bind mount target | 容器内工作目录 |
| `SANDBOX_HOST_WORKSPACE_PREFIX` | `""` | 宿主机绝对路径前缀 | socket 模式专用 | 例：`/host/app/data` |
| `SANDBOX_K8S_NAMESPACE` | `default` | K8s 命名空间 | **占位，未实现** | K8s 模式下生效 |
| `SANDBOX_FALLBACK_TO_LOCAL` | `true` | bool | Docker 不可用时降级到本地 | false 时只抛 `DockerException` |

#### 设置流程
1. 进入「基本设置 → 沙箱与任务」Tab
2. 找到 sandbox 组（11 字段）
3. 修改字段 → 点击「保存」
4. **重启 uvicorn / docker compose**

#### 重启后效果
- lifespan 启动期 `seed_from_settings` 写入 DB（运行期不重读）
- 容器内 sandbox 工具调用使用新配置
- 沙箱启动失败时不再降级（若 `fallback_to_local=false`）

### 其他组（简要列出）

| group_key | 所属 Tab | 说明 |
|---|---|---|
| `llm` | LLM 模型 | 主模型配置（model_type / model_name / api_key / base_url / temperature / max_tokens） |
| `llm.contract` | LLM 模型 | 合同三智能体专属 LLM（CONTRACT_LLM_* 前缀） |
| `file_parser` | 文件解析 | PDF / Word / Excel 解析器配置 |
| `auth.password_policy` | 安全认证 | 口令复杂度（长度 ≥ 8 + 大小写 + 数字 + 特殊字符） |
| `auth.mfa` | 安全认证 | MFA issuer / 强制启用策略 |
| `cors` | 安全认证 | CORS_ALLOWED_ORIGINS（**默认空 List**，禁止恢复 `*`） |
| `auth.cookie` | 安全认证 | HttpOnly Cookie 配置（AUTH_COOKIE_*） |
| `feishu` | 网络与集成 | 飞书基础配置（已迁移到 DB；.env 字段保留兼容） |
| `email` | 网络与集成 | 邮件 SMTP 配置 |
| `third_party_executor` | 网络与集成 | 第三方 SSH 执行器 |
| `inspection` | 沙箱与任务 | 巡检字段规则（inspection_scripts） |
| `task_scheduler` | 沙箱与任务 | cron 调度 / 并发数 |
| `log` | 其他 | 日志级别 / 保留时间 |
| `cache` | 其他 | Redis / 内存缓存 |
| `experimental` | 其他 | 实验性开关 |

## 安全认证（重点详解）

### cors 组

#### 设置 → 效果
- 修改 `CORS_ALLOWED_ORIGINS` → 重启后生效
- 新跨域请求只允许通过环境变量加白
- 第三方 server-to-server 接入（login-api / portal token / X-Refresh-Token）**不受 CORS 约束**

#### 语法

```env
# .env（启动期 fallback）
CORS_ALLOWED_ORIGINS='["https://app1.example.com", "https://app2.example.com"]'

# DB（admin 在「基本设置」修改）
group_key=cors → config={"allowed_origins": ":.."}
```

### auth.password_policy 组

#### 设置 → 效果
- 立即生效（**无需重启**，被 `UserDB.create_user` / `update_password` 持久化层强制调用）
- 路由层 + service 层双重校验

#### 语法

| 字段 | 默认值 | 说明 |
|---|---|---|
| `min_length` | 8 | 最小长度 |
| `require_uppercase` | true | 必须大写 |
| `require_lowercase` | true | 必须小写 |
| `require_digit` | true | 必须数字 |
| `require_special` | true | 必须特殊字符 |
| `special_char_whitelist` | `!@#$%^&*` | 允许的特殊字符集 |

## 文件解析（重点详解）

### file_parser 组

#### 设置 → 效果
- **重启后生效**（lifespan 一次性加载）
- 修改后下次上传文件时按新解析器处理

#### 字段详解

| 字段 | 默认值 | 说明 |
|---|---|---|
| `pdf_extractor` | `pdfplumber` | PDF 文本提取（可选 pypdf / pdfplumber / pymupdf） |
| `pdf_ocr_engine` | `tesseract` | 图片型 PDF OCR（可选 tesseract / paddleocr） |
| `word_extractor` | `python-docx` | Word 文档解析 |
| `excel_extractor` | `openpyxl` | Excel 解析 |
| `chunk_size` | `500` | 分块大小（tokens） |
| `chunk_overlap` | `50` | 分块重叠（tokens） |
| `embedding_model` | `text-embedding-3-small` | 向量化模型 |

## 敏感字段加密

`SETTINGS_SECRET_KEY`（Fernet 密钥）用于加密以下敏感字段：

- LLM API key
- 飞书 App Secret
- 邮件 SMTP 密码
- 第三方 SSH private key
- 任何 `sensitive_fields` 注册的字段

#### 加密标识
- DB 存储密文以 `fernet:` 前缀标记
- 服务端读时自动解密（`_ensure_fernet()` 懒加载）
- 写时 `fernet.encrypt(value.encode()).decode('ascii')`

#### Fernet 密钥生成命令

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

## 22 组完整清单

```
llm, llm.contract, file_parser, auth.password_policy, auth.mfa,
cors, auth.cookie, feishu, email, third_party_executor,
inspection, task_scheduler, sandbox,
log, cache, experimental, ...
```

每个组通过 `SystemConfigRegistry.register(group_key, tab, label, settings_cls, sensitive_fields, description)` 自注册。

## 常见问题

### 修改后为何不生效？
- **重启后生效**：本页面修改的配置写入 DB，lifespan 启动期 `seed_from_settings` 加载到内存
- 运行期不重读（性能考虑）

### 敏感字段忘记保存原值怎么办？
- 字段以 `fernet:` 前缀标记密文，无法反向解密
- 必须**重新设置原值**，否则下次解密失败

### 配置被误改如何回滚？
- admin 在「基本设置」编辑表单手动改回
- 或 PG 直接 UPDATE `system_settings_groups.config` JSONB 字段
- 重启服务生效

## 相关章节

- [权限管理](/help/features/permission-management) — ACL 控制谁能访问此菜单
- [智能运维中心 → 沙箱](/help/features/ops-console#前置条件必须先确认否则功能不可用) — 沙箱使用指南
- [飞书通知](/help/features/feishu-notification) — 飞书凭证管理