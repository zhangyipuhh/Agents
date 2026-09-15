# 常见问题

本章节汇总了用户使用过程中的高频问题与解决方案。

![常见问题](/help/screenshots/faq/01-faq.png)

## 登录问题

### 忘记密码怎么办？

联系系统管理员重置密码。如系统启用了自助密码重置，可在登录页面点击「忘记密码」按邮件验证码重置。

### 登录失败次数过多被锁定怎么办？

系统默认 5 次连续登录失败后会锁定账户 30 分钟（`login_lockout`）。请等待锁定窗口结束后再试，或联系管理员手动解锁。

#### 锁定计数位置
- `users.failed_login_count` + `users.locked_until`
- 路由双重保险：`app/shared/utils/auth/login_lockout.py`
- **固定锁定窗口**：活动锁定期间 `locked_until` 不被顺延（PG CASE + 内存 mode 同步）

### 启用了 MFA 但丢失了恢复码？

请联系管理员重置 MFA 绑定。出于安全考虑，管理员无法查看您的恢复码，但可以在验证身份后为您清空绑定记录。

```sql
-- admin 重置 MFA 绑定（仅清空，不查恢复码）
UPDATE user_mfa_totp SET enabled=false, secret_encrypted=NULL WHERE user_id=<id>;
DELETE FROM mfa_recovery_codes WHERE user_id=<id>;
```

### 启用了 MFA 但丢失了手机？

用 **10 个恢复码之一** 登录（每个一次性，使用后失效）。若恢复码也全部丢失，请联系 admin 调 `mfa_service.reset_user_mfa()`。

## 权限问题

### 为什么我看不到某些菜单？

菜单的可见性由系统管理员配置的 ACL 决定。普通用户只能看到管理员授权的菜单项。

如需申请菜单权限，请联系系统管理员在「权限管理 → 菜单管理」中为您授权。

#### 可见性规则
- admin：返全量 `enabled=True` 项（按 sort_order 排序）
- 普通用户：`user_menu_acl.menu_id` 集合 ∩ enabled，末尾强制追加 `profile`

### 为什么我能进智能运维中心但看不到某些服务器？

服务器级别的可见性受「用户服务器配置」控制。即使有 `task-scheduler.server-management` 菜单权限，仍需管理员将具体服务器授权给您。

#### 数据层隔离
- `devops_servers` 表（含 `created_by_user_id` + ACL 关联）
- `OwnershipScope` 过滤：`admin` 透传全量，普通用户按 `user_server_nodes` 可见集去重
- POST `/collect` 额外逐 `server_id` 校验归属，越权 403 / 不存在 404

### 看不到某些智能体？

普通用户只能看到 `users.allowed_agents` JSONB 字段中授权的智能体。admin 在「权限管理 → 智能体访问」授权。

## 性能问题

![常见问题滚动视图](/help/screenshots/faq/01-faq.png)

### 对话响应慢怎么办？

可能的原因：

1. **网络问题**：检查本地网络与服务器网络连通性
2. **模型繁忙**：当前 LLM 提供商可能负载较高，可稍后重试
3. **上下文过长**：开启新会话以重置上下文
4. **token 流式断流**：检查 nginx `proxy_read_timeout 300s;` 配置

### 知识库检索慢怎么办？

- 知识库文档较多时，检索可能需要 1~3 秒
- 如检索明显变慢，管理员可触发「索引重建」
- 调整 `chunk_size` 与 `embedding` 模型（详见「[知识库](/help/features/knowledge)」）

### 并发达到上限怎么办？

`agent_chat_max_concurrency` 默认 5（可在「基本设置 → 沙箱与任务」调整）。超出后前端展示「排队中」横幅，等待前面的会话完成。

## 错误处理

### 遇到「鉴权失败 / 401」怎么办？

刷新页面重新登录即可。如频繁出现：

1. 检查浏览器 Cookie 是否被禁用
2. 检查是否达到 `AUTH_MAX_CONCURRENT_SESSIONS`（默认 5）
3. 检查是否达到 `AUTH_IDLE_TIMEOUT_SECONDS`（默认 30 分钟无操作自动登出）
4. 检查 access_token 是否被 `refresh_token_revoke`（登出 / 改密）

### 遇到「网络错误 / 5xx」怎么办？

1. 刷新页面重试
2. 查看浏览器 Console 是否有 CORS / CSP / Mixed Content 错误
3. 如频繁出现，联系管理员查看后端日志
4. 查看 nginx `error.log` 是否记录反向代理错误

### 工具调用失败（如 SSH 执行失败）

检查：

1. 服务器是否在线（ping 测试）
2. SSH 凭据是否正确
3. 防火墙是否放行 SSH 端口
4. `ssh_timeout` 配置（默认 30 秒，范围 [1, 120]）
5. `CommandInterceptor` 黑白名单（详见 `app/shared/tools/skills/devops/CommandInterceptor.py`）

## 数据问题

### 误删了会话能恢复吗？

会话删除为**不可逆**操作，删除前请确认。如重要会话被误删，请联系管理员查看审计日志（仅记录操作记录，不保留会话内容）。

#### 审计日志查询
- admin 在「用户管理 → 会话查询」按 user_id / 时间范围查询
- 审计字段：`user_id` / `username` / `time` / `ip` / `action` / `target` / `result`

### 文档上传后智能体没引用怎么办？

1. 确认文档已成功上传并完成解析（解析完成后状态显示「已索引」）
2. 提问时明确提及文档名或关键词
3. 在问题中明确指示「请参考知识库」

## 注册审批问题

### 状态：`pending_approval`
**含义**：注册成功但等待 admin 审批。

**修复**：
1. admin 在「用户管理 → 待审批列表」批准
2. 或联系 admin 调 `POST /api/users/{id}/approve`

### 状态：`rejected`
**含义**：注册被 admin 拒绝（带 `reason`）。

**修复**：联系 admin 重新注册，或 admin 调 `POST /api/users/{id}/approve` 重激活。

### 状态：`disabled`
**含义**：账号被禁用（admin 操作）。

**修复**：联系 admin 调 `UserDB.update_user_status(user_id, 'active')`。

#### 三态拦截
- `pending_approval` / `rejected` / `disabled` 三态在 `auth_router.login` / `login-api` / `refresh` 三处统一拦截
- 反枚举特性不变（user is None 时不暴露具体原因）

## 沙箱问题

### Docker 不可用，sandbox 工具报错？

**错误文案**：`沙箱执行失败：Docker daemon 未运行或未安装。`

**修复**：
1. 启动 Docker daemon（Linux: `sudo systemctl start docker`）
2. 或设置 `SANDBOX_FALLBACK_TO_LOCAL=true`（仅开发环境，失去隔离）

### 沙箱启动容器后立即退出？

**排查**：
1. 检查 `SANDBOX_IMAGE` 是否存在（`docker pull python:3.12-alpine`）
2. 检查 `SANDBOX_MAX_MEMORY_Mb` 是否小于镜像要求（alpine 默认 64 MB 即可）
3. 检查 `SANDBOX_CONTAINER_WORKSPACE` 路径权限

### 沙箱工具超时？

**原因**：`SANDBOX_DEFAULT_TIMEOUT` 默认 60 秒，超出后会被中止。

**修复**：在「基本设置 → 沙箱与任务」调大超时（重启后生效）。

## 飞书问题

### 凭证无效？

**错误文案**：`飞书发送配置缺失` 或 `invalid app_secret`

**修复**：
1. 在「消息设置 → 飞书设置」检查 `app_id` / `app_secret` 是否正确
2. 检查 Fernet 加密的 `DEVOPS_CREDENTIAL_KEY` 是否与 `email_*` 共用
3. 重新保存 channel 配置

### WS 连接断开？

**现象**：「飞书通知 → 通道状态：离线」

**修复**：
1. 检查飞书 channel 是否 `enabled=true`
2. 查看后端日志是否有 `lark SDK ClientException`
3. 重启服务或重新保存 channel 配置触发热加载

### 发送失败？

**排查**：
1. 检查 target `chat_id` / `chat_type` 是否正确
2. 检查 channel ` `agent_name` 是否绑定到正确的智能体
3. 检查 LLM 工具 `send_feishu_message` 是否能 resolve 到 endpoint

## 相关章节

- [快速入门](/help/getting-started) — 登录与 MFA
- [基本设置](/help/features/basic-settings) — 配置项
- [权限管理](/help/features/permission-management) — 菜单 / 智能体 ACL
- [用户管理](/help/features/user-management) — 账号状态与审批
- [智能运维中心](/help/features/ops-console) — 沙箱 / SSH
- [飞书通知](/help/features/feishu-notification) — 飞书配置
