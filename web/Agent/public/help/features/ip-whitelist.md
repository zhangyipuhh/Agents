# IP 白名单配置

本章节面向系统管理员,介绍如何启用与配置注册接口 IP 白名单闸门,以及常见错误排查与审计日志查看方式。

> ⚠️ **本章是「闸门 1」IP 白名单的详细文档**。闸门 2（admin 审批）详见「[用户管理 → 注册审批](/help/features/user-management#注册审批)」。

## 1. 前置条件

- 已部署系统，能通过 nginx 反向代理访问（**禁止绕过 nginx 直连 uvicorn**，否则白名单 fail-closed）
- nginx 已配置 `proxy_set_header X-Real-IP $remote_addr;`
- admin 角色（用于审批闸门 2 的 pending_approval 用户）

## 2. 启用后的效果

- `/api/auth/register` 仅接受白名单内 IP 的请求
- 白名单外的 IP 立即返回 403 + 写审计日志 `register_ip_blocked`
- 用户提交注册后，状态转 `pending_approval`，需 admin 调 `/api/users/{id}/approve` 才能登录
- **空白名单 fail-closed**：未启用任何 IP 也拒绝所有注册请求（防止误配置导致外网可注册）

## 3. 快速截图参考

![IP 白名单配置文档](/help/screenshots/features-ip-whitelist/01-ip-whitelist.png)

### 界面配置入口

注册安全配置已迁入「基本设置 → 安全认证」Tab（2026-09-14 起），无需再改 `.env`。找到「注册安全」配置组中的 **IP 白名单** 字段（`ip_whitelist`，JSON 数组格式）：

配置示例（CIDR 或精确 IP 混合）：

```json
["10.0.0.0/8", "192.168.1.100"]
```

留空表示不限制。修改后**重启服务生效**（lifespan 启动期加载到内存）。同组还可配置「Admin 通知邮箱」与「同步发送飞书通知」。

## 概述

注册安全采用「双闸门」访问控制,符合等保三级 §7.1.3 a/e 项要求:

- **闸门 1(IP 白名单)**:挡住外网或非授权网段对 `/api/auth/register` 的访问,基于 nginx 写入的 `X-Real-IP` + CIDR 匹配。
- **闸门 2(管理员审批)**:挡内网非目标用户,通过 `users.status='pending_approval'` 落库 + admin 调 `/api/users/{id}/approve` 激活。

本章仅覆盖闸门 1 的配置细节,闸门 2 详见「[常见问题 → 注册问题](/help/faq)」。

## 环境变量

注册安全配置类 `RegistrationSecuritySettings` 统一使用 `REGISTRATION_SECURITY_` 前缀,以下表格列出全部 4 个环境变量。

| 名称 | 类型 | 默认值 | 含义 |
|------|------|--------|------|
| `REGISTRATION_SECURITY_ENABLED` | bool | `false` | 总开关。`true` 同时启用 IP 白名单 + 注册审批;`false` 退化为无审批/无白名单(保留原行为,向后兼容) |
| `REGISTRATION_SECURITY_IP_WHITELIST` | JSON list | `[]` | IP 白名单(CIDR 或精确 IP)。启用时注册请求源 IP 必须命中其中任一条;空白名单 fail-closed 拒绝所有 IP |
| `REGISTRATION_SECURITY_ADMIN_NOTIFICATION_EMAILS` | JSON list | `[]` | 注册待审批时抄送这些邮箱;为空则跳过邮件通知(飞书通知不受此影响) |
| `REGISTRATION_SECURITY_FEISHU_NOTIFY_ENABLED` | bool | `false` | 是否同步发送飞书审批通知;依赖飞书渠道已配置 webhook / 飞书 channel |

完整字段定义见 `app/core/config/settings.py::RegistrationSecuritySettings`,`.env.example` 行 333~358 含详细注释。

## nginx 前置配置

IP 白名单依赖 nginx 写入的 `X-Real-IP` 请求头,**绝不读取** `X-Forwarded-For`(可被任意客户端伪造)。

请在 nginx 反代配置的 `/api/auth/register` 路径上加入:

```nginx
location /api/ {
    proxy_set_header X-Real-IP $remote_addr;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header Host $host;
    proxy_pass http://127.0.0.1:8000;
}
```

如果绕过 nginx 直接访问 uvicorn(开发调试场景),请求将不含 `X-Real-IP`,中间件**fail-closed** 直接返回 403「无法识别客户端来源 IP,请通过反向代理访问」,不允许绕过。

## 白名单写法

白名单支持两种写法,**混用**也可以:

- **CIDR 网段**:`192.168.1.0/24`(覆盖 `192.168.1.0`~`192.168.1.255`)、`10.0.0.0/8`(覆盖 `10.0.0.0`~`10.255.255.255`)。
- **精确 IP**:`10.0.0.5`、`172.26.160.50`、`127.0.0.1`。

匹配逻辑使用 Python 标准库 `ipaddress.ip_network(..., strict=False)`,非法 CIDR 条目会被跳过并写 `WARNING` 日志,不阻断其他条目匹配。

### 推荐配置示例

内网办公网段 + 堡垒机出口 + 本地回环:

```env
REGISTRATION_SECURITY_IP_WHITELIST='["192.168.1.0/24", "10.0.0.5", "127.0.0.1"]'
```

仅单 IP 开放:

```env
REGISTRATION_SECURITY_IP_WHITELIST='["172.26.160.50"]'
```

> ⚠️ **空白名单 fail-closed**:`REGISTRATION_SECURITY_IP_WHITELIST='[]'` 时,**所有注册请求一律拒绝**(包括合法内网)。生产环境务必确认至少有一条白名单条目后再启用。

## 启用流程

按以下步骤启用 IP 白名单 + 注册审批双闸门:

1. **修改 `.env`**:设置 `REGISTRATION_SECURITY_ENABLED=true`,填好 `REGISTRATION_SECURITY_IP_WHITELIST` 列表。
2. **重启服务**:`uvicorn --port 8000 ...` 或 docker compose 重启,确保新配置被加载(`lifespan` 启动期间配置即生效)。
3. **验证 nginx**:`curl -I https://your-domain/api/auth/register -X POST` 应看到响应头含 `X-Real-IP` 透传(从 nginx 日志核实 `$remote_addr`)。
4. **测试注册**:从白名单内的 IP 提交注册请求,DB 中 `users.status='pending_approval'`,admin 收到邮件 / 飞书通知。
5. **激活账号**:admin 调 `POST /api/users/{user_id}/approve`,`status` 转 `active` 后用户可正常登录。

闸门 2 的 `pending_approval` 拦截由 `auth_router.login` / `login-api` / `refresh` 三处 `status` 检查统一处理,无需额外配置。

## 错误排查

IP 白名单拦截统一返回 HTTP 403,文案区分以下三类,可通过文案精准定位原因:

| 场景 | 403 文案 | 根因 | 修复方向 |
|------|---------|------|---------|
| 反向代理未注入 `X-Real-IP` | `无法识别客户端来源 IP,请通过反向代理访问` | nginx 缺少 `proxy_set_header X-Real-IP $remote_addr;` 或绕过 nginx 直连 uvicorn | nginx 配置补齐,或改走反向代理访问 |
| `X-Real-IP` 格式非法 | `客户端 IP 格式非法` | 反代写入的 IP 字符串含非法字符(如 `unknown` / `127.0.0.1, 10.0.0.1` 拼接错) | 检查 nginx `set_header` 顺序,优先 `$remote_addr` 而非 `$proxy_add_x_forwarded_for` |
| 不在白名单 | `当前网络不允许注册,如有疑问请联系管理员` | 客户端 IP 未命中 `REGISTRATION_SECURITY_IP_WHITELIST` 任一 CIDR / 精确 IP | 确认客户端出口 IP,加入白名单后重启服务 |

### 审计日志位置

每次拦截事件都会通过 `LogService.emit` 写入统一审计日志:

- **action**:`register_ip_blocked`
- **log_type**:`AUTH`
- **result**:`FAILURE`
- **ip_address**:被拦截的客户端 IP(从 `X-Real-IP` 透传)

审计日志写入失败时 fail-soft 仅写 WARNING,**不阻断**拦截响应。查询方式见「[常见问题 → 数据问题 → 误删了会话能恢复吗?](/help/faq)」中的审计日志说明。

## 相关章节

- 「[常见问题 → 注册问题](/help/faq)」:闸门 2(注册审批 + status 拦截)详解
- 「[快速入门](/help/getting-started)」:登录与会话基础
