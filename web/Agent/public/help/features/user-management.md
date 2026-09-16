# 用户管理

用户管理模块负责**用户账号状态**、**注册审批**、**密码重置**、**MFA 管理**与**会话查询**。

![用户管理](/help/screenshots/features-user-management/01-user-management.png)

## 前置条件

- **admin 角色**（路由 `require_admin`）
- 浏览器已登录
- 数据库 `users` / `user_login_sessions` / `registration_approval_logs` 表已初始化

## 用户列表

### 入口
「用户管理 → 用户列表」，即 admin 点击左下角头像 → 「管理后台」后默认打开的页面。

#### 操作说明
- 「新增用户」：创建账号并指定角色（user / admin）
- 「编辑」：修改昵称 / 邮箱 / 手机号 / 部门 / 职位（**不含密码**，密码修改走「个人设置」或管理员重置）
- 「强制下线」：吊销该用户全部 refresh token 与登录会话，立即生效
- 「删除」：删除账号（不可逆，删除前请确认）

### 字段

| 字段 | 来源 | 说明 |
|---|---|---|
| `id` | users.id | 用户 ID |
| `username` | users.username | 登录名 |
| `display_name` | users.display_name | 昵称 |
| `email` | users.email | 邮箱 |
| `status` | users.status | 账号状态（详见下文） |
| `is_admin` | users.is_admin | 是否 admin |
| `failed_login_count` | users.failed_login_count | 累计登录失败次数 |
| `locked_until` | users.locked_until | 锁定到期时间 |
| `created_at` | users.created_at | 创建时间 |
| `last_login_at` | users.last_login_at | 最近登录时间 |

## 账号状态

`users.status` 字段，枚举值 4 种：

| 状态 | 含义 | 登录拦截 |
|---|---|---|
| `active` | 正常 | ✅ 允许 |
| `pending_approval` | 注册待审批 | ❌ 403 拦截（登录 / login-api / refresh 三处统一） |
| `rejected` | 注册被拒 | ❌ 403 拦截 |
| `disabled` | 账号被禁用 | ❌ 403 拦截 |

#### 状态拦截文案

| 状态 | 拦截文案 |
|---|---|
| `pending_approval` | 「账号待管理员审批,请耐心等待审批结果」 |
| `rejected` | 「账号审批未通过」 |
| `disabled` | 「账号已禁用,请联系管理员」 |

> 拦截仅在 `user is not None` 时生效，反枚举特性不变（user is None 时不暴露具体原因）。

#### DB 约束
- `users_status_chk` CHECK 约束
- `idx_users_status` 索引
- 迁移文件：`2026_08_30_add_user_registration_approval.sql`

## 注册审批（闸门 2）

### 启用流程

1. `.env` 设 `REGISTRATION_SECURITY_ENABLED=true`
2. 填 `REGISTRATION_SECURITY_IP_WHITELIST`（CIDR + 精确 IP）
3. 重启服务（lifespan 加载）

### 三个 admin 端点

| 端点 | 说明 |
|---|---|
| `GET /api/users/pending` | admin 查待审批列表 |
| `POST /api/users/{id}/approve` | admin 批准（status → active） |
| `POST /api/users/{id}/reject` | admin 拒绝（body `reason` 必填，status → rejected + reason 落库） |

### 设置后效果
- 注册请求落库 `users.status='pending_approval'`
- 异步通知 admin（邮件 + 飞书开关）
- admin 在「用户管理 → 待审批列表」审批
- `registration_approval_logs` 表记录操作（target_user_id / target_register_ip / action / operator_user_id 等）

### 并发安全

`UserDB.update_user_status` 含并发守卫：
- 检查当前 status 必须为 `pending_approval`
- race condition 防护

## IP 白名单（闸门 1）

详见「[IP 白名单配置](/help/features/ip-whitelist)」章节。

### 双闸门访问控制

| 闸门 | 控制 | 配置位置 |
|---|---|---|
| 闸门 1 | IP 白名单（挡外网） | `REGISTRATION_SECURITY_IP_WHITELIST` |
| 闸门 2 | admin 审批（挡内网非目标用户） | `RegistrationApprovalService` |

### 审计日志

每次拦截事件通过 `LogService.emit` 写入统一审计日志：
- `action`: `register_ip_blocked`
- `log_type`: `AUTH`
- `result`: `FAILURE`
- `ip_address`: 被拦截的客户端 IP（从 `X-Real-IP` 透传）

## 密码重置

### API
- `POST /api/users/{user_id}/password`
- body：`{"old_password": "...", "new_password": "..."}`
- 仅本人可调用（admin 不能改他人密码）

### 复杂度校验

`password_policy.validate_password` 强制调用：
- 长度 ≥ 8
- 必须大写字母
- 必须小写字母
- 必须数字
- 必须特殊字符（白名单 `!@#$%^&*`）

## MFA 重置

### API
- admin 在「用户管理 → MFA 管理」
- 调 `mfa_service.reset_user_mfa(user_id)`

### 效果
- 清空 `user_mfa_totp.enabled` / `secret_encrypted`
- 删除 `mfa_recovery_codes` 全部记录

> ⚠️ **admin 无法查看用户恢复码**（出于安全考虑），仅清空绑定记录。

## 会话查询

### 入口
「用户管理 → 会话查询」

### 字段

| 字段 | 来源 | 说明 |
|---|---|---|
| `session_uuid` | user_login_sessions.session_uuid | 会话 UUID |
| `user_id` | user_login_sessions.user_id | 用户 ID |
| `last_active_at` | user_login_sessions.last_active_at | 最后活跃时间 |
| `revoked_at` | user_login_sessions.revoked_at | 撤销时间 |
| `revoke_reason` | user_login_sessions.revoke_reason | 撤销原因（logout / idle / admin_force） |
| `ip_address` | request.client.host | 客户端 IP |

### 强制下线

- admin 点击「强制下线」→ 调 `revoke_session(session_uuid)`
- refresh_token_revoke 触发，access_token 立即失效
- 用户下次操作收到 401

## 并发会话限制

- `settings.auth.max_concurrent_sessions` 默认 5
- `RefreshTokenDB.count_active_tokens` + `delete_oldest_tokens` 实现踢出最旧
- `refresh_tokens.username` 列（2026-08-11 新增）

## 锁定窗口

- 5 次连续登录失败锁定 30 分钟（`login_lockout.py`）
- 双重保险：路由层 + `UserDB.update_password` 持久化层
- **固定锁定窗口**：活动锁定期间 `locked_until` 不被顺延（PG CASE + 内存 mode 同步）

## 常见问题

### 注册后无法登录？
**排查**：
1. 检查 `users.status` 字段（应为 `active`）
2. 检查是否被 admin 拒绝
3. 检查 IP 白名单是否配置

### 忘记密码？
- 普通用户：联系 admin 重置
- admin 重置：`POST /api/users/{user_id}/password`（需本人旧密码）

### 登录失败计数不重置？
**排查**：
- 检查 `login_lockout.check_login_lock` 是否正确调用
- 检查 `failed_login_count` 字段是否累加

### 强制下线后用户仍能访问？
**排查**：
1. 检查 `revoked_at` 是否设置
3. 浏览器是否使用缓存的 access_token（30 分钟有效期内仍可用）
4. 30 分钟后自动失效

## 相关章节

- [权限管理](/help/features/permission-management) — ACL 配置
- [IP 白名单配置](/help/features/ip-whitelist) — 注册 IP 闸门
- [快速入门 → 启用 MFA](/help/getting-started#启用-mfa双因素认证) — MFA 启用步骤
- [常见问题 → 登录问题](/help/faq#登录问题) — 登录故障