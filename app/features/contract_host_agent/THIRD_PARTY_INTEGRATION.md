# 第三方接入合同审批智能体指南（Portal Refresh Token 模式）

> 本文档说明第三方系统如何以最小改造接入 `/api/contract/chat`。
>
> **方案**：复用现有 Portal Refresh Token 通道 —— 零新增表、零中间件改动、零应用代码变更，全部走现有鉴权链路。
>
> **适用版本**：与 `app/features/contract_host_agent` 同仓库版本同步。

---

## 0. 适用场景

第三方业务系统（无浏览器、无用户交互、无法走登录流程）需要调用合同审批智能体的 `/api/contract/chat` 接口，且：

- 不允许（或无法）使用 `POST /api/auth/login-api`（程序化登录）作为长期接入方式
- 需要可吊销、可审计、可设置 TTL 的机器凭据
- 不得新增数据表 / 改动鉴权中间件 / 改动业务路由

满足以上约束时，按本文档实施。

---

## 1. 鉴权要素清单

| 环节 | 端点 | 鉴权要求 | 说明 |
|---|---|---|---|
| 1.1 凭据签发（运维） | `POST /api/auth/login-api` | 服务账号 username + password | 一次性获取短期 access_token |
| 1.2 Portal Token 签发（运维） | `POST /api/auth/issue-portal-refresh-token` | Bearer access_token | 签发 portal_refresh_token（长期），交付第三方 |
| 2.1 换 access_token（第三方） | `POST /api/auth/refresh` | `X-Refresh-Token: <portal>` 头 | 第三方每次调用业务前执行 |
| 2.2 创建会话（第三方） | `POST /api/session/create` | Bearer access_token | 第三方首次调用业务前执行 |
| 2.3 业务调用（第三方） | `POST /api/contract/chat` | Bearer + `X-Session-ID` | 第三方核心调用 |

---

## 2. 阶段 A：一次性准备（运维在服务端执行，仅一次）

> 服务账号由管理员在管理后台创建（强口令满足 `password_policy.validate_password`：≥8 位 + 大小写 + 数字 + 特殊字符）。本文档不包含建账号步骤。

### 2.1 登录取 access_token

```
POST http://192.168.1.125:8001/api/auth/login-api
Content-Type: application/json
```

**请求体（ApiLoginRequest）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `username` | string | 是 | 服务账号用户名 |
| `password` | string | 是 | 服务账号口令 |

**响应（LoginResponse）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `access_token` | string | **取出缓存，JWT，30 分钟有效** |
| `token_type` | string | `"Bearer"`，本流程忽略 |
| `expires_in` | int | 30（分钟） |
| `role` | string | 本流程忽略 |
| `username` | string | 本流程忽略 |
| `user_id` | int | 本流程忽略 |
| `visible_menus` | array | 本流程忽略 |
| `allowed_agents` | array | 本流程忽略 |

### 2.2 签发 portal_refresh_token

```
POST http://192.168.1.125:8001/api/auth/issue-portal-refresh-token
Authorization: Bearer <2.1 拿到的 access_token>
Content-Type: application/json
```

**请求体**：`{}`（空对象；该端点仅靠 `Authorization` 头鉴权）

**响应（IssuePortalRefreshTokenResponse）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `portal_refresh_token` | string | **明文仅此一次返回**，安全交付第三方 |
| `expires_in` | int | 有效期秒数，默认 86400（24h），env `PORTAL_REFRESH_TOKEN_TTL_SECONDS` 可调 |
| `expires_at` | string | ISO8601 格式过期时间 |

阶段 A 结束。

---

## 3. 阶段 B：第三方运行时调用（每次使用）

### 3.1 第 1 步 — 换 access_token

```
POST http://192.168.1.125:8001/api/auth/refresh
X-Refresh-Token: <portal_refresh_token>
```

**请求体**：无
**请求头**：`X-Refresh-Token`（读取优先级：此头 → body.refresh_token → HttpOnly Cookie，第三方用头即可）

**响应**

| 字段 | 类型 | 说明 |
|---|---|---|
| `access_token` | string | **取出缓存，后续所有请求用** |
| `token_type` | string | `"Bearer"`，忽略 |
| `expires_in` | int | 30（分钟），用于本地计时提前刷新 |

**失败处理**

| 状态码 | 含义 | 动作 |
|---|---|---|
| 401 | portal token 过期/被吊销 | 终止并通知运维重做阶段 A |

### 3.2 第 2 步 — 创建会话取 session_id

```
POST http://192.168.1.125:8001/api/session/create
Authorization: Bearer <3.1 的 access_token>
Content-Type: application/json
```

**请求体（SessionCreateRequest）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `project_id` | int | 否 | 关联项目文件夹，第三方场景**不传/传 null** |

**响应（SessionCreateResponse）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `session_id` | string | **取出缓存** |
| `message` | string | 提示文本，忽略 |

**注意**：同一轮对话复用此 `session_id`（对话记忆挂在它上面）；开新话题才重建。

### 3.3 第 3 步 — 调用合同审批聊天

```
POST http://192.168.1.125:8001/api/contract/chat
Authorization: Bearer <access_token>
X-Session-ID: <session_id>
Content-Type: application/json
```

**请求体（ChatRequest）**

| 字段 | 类型 | 必填 | 说明 |
|---|---|---|---|
| `message` | string | 是 | 用户消息，如 `"请执行审批流程"` |
| `session_id` | string | 否 | 建议显式传第 2 步的值（不传则后端取 `X-Session-ID` 头兜底） |

**响应（ChatResponse）**

| 字段 | 类型 | 说明 |
|---|---|---|
| `response` | string | **智能体回复文本，业务取此字段** |
| `session_id` | string | 回显会话 ID |

---

## 4. 错误处理矩阵

| 状态码 / 响应 | 含义 | 动作 |
|---|---|---|
| 401 `portal_refresh_token 已过期` / `缺少 Refresh Token` | portal token 失效 | 通知运维重签（阶段 A） |
| 401 `缺少认证信息` / `无效的令牌` / `令牌已过期` | access_token 异常 | 回第 1 步重新换 |
| 400 `缺少 X-Session-ID` | 头缺失 | 检查请求头 |
| 401 `无权访问该会话` | session_id 不属于该账号 | 回第 2 步重建 |
| 429 `concurrency_limit` | 聊天并发满 | 稍后重试 |
| 500 `对话处理失败：...` | 智能体内部异常 | 取 `detail` 字段排障 |

---

## 5. 完整样例

### 5.1 curl 样例

```bash
BASE=http://192.168.1.125:8001
PORTAL_TOKEN="<运维交付的 portal_refresh_token>"

# 第 1 步：换 access_token
ACCESS_TOKEN=$(curl -s -X POST "$BASE/api/auth/refresh" \
  -H "X-Refresh-Token: $PORTAL_TOKEN" \
  | python -c "import sys,json;print(json.load(sys.stdin)['access_token'])")

# 第 2 步：创建会话
SESSION_ID=$(curl -s -X POST "$BASE/api/session/create" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "Content-Type: application/json" -d '{}' \
  | python -c "import sys,json;print(json.load(sys.stdin)['session_id'])")

# 第 3 步：聊天
curl -s -X POST "$BASE/api/contract/chat" \
  -H "Authorization: Bearer $ACCESS_TOKEN" \
  -H "X-Session-ID: $SESSION_ID" \
  -H "Content-Type: application/json" \
  -d "{\"message\": \"请执行审批流程\", \"session_id\": \"$SESSION_ID\"}"
```

### 5.2 fetch 样例（精简版）

```javascript
const BASE = "http://192.168.1.125:8001";
const PORTAL_TOKEN = "<portal_refresh_token>";

// 第 1 步
const { access_token } = await fetch(`${BASE}/api/auth/refresh`, {
  method: "POST",
  headers: { "X-Refresh-Token": PORTAL_TOKEN },
}).then(r => r.json());

// 第 2 步
const { session_id } = await fetch(`${BASE}/api/session/create`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${access_token}`,
    "Content-Type": "application/json",
  },
  body: "{}",
}).then(r => r.json());

// 第 3 步
const { response } = await fetch(`${BASE}/api/contract/chat`, {
  method: "POST",
  headers: {
    Authorization: `Bearer ${access_token}`,
    "X-Session-ID": session_id,
    "Content-Type": "application/json",
  },
  body: JSON.stringify({ message: "请执行审批流程", session_id }),
}).then(r => r.json());

console.log(response); // 智能体回复
```

---

## 6. 生命周期速查

| 凭证 | 有效期 | 过期处理 |
|---|---|---|
| `access_token` | 30 分钟 | 重新执行第 1 步 |
| `session_id` | 服务端会话表内长期有效 | 401 `无权访问该会话` 时重建（第 2 步） |
| `portal_refresh_token` | 默认 24h（env `PORTAL_REFRESH_TOKEN_TTL_SECONDS` 可调） | 联系运维重签（阶段 A） |

---

## 7. 中间件兼容性说明

| 中间件 | 第三方调用兼容性 |
|---|---|
| `auth_middleware`（`app/shared/utils/auth/Safety.py:518`） | `/api/auth/refresh` 在 jwt 白名单；业务接口走 Bearer 全程过 |
| `session_auth_middleware`（`Safety.py:564`） | `/api/session/create` 在 `SESSION_WHITELIST_PREFIXES`；`/api/contract/*` 需要 `X-Session-ID` 由服务账号自建自用，过归属校验 |
| CSRF 二次防线（`Safety.py:550-558`） | Bearer 鉴权天然豁免 `X-Requested-With` 头校验 |
| `idle_timeout_middleware`（`app/shared/utils/auth/idle_timeout_middleware.py`） | 第三方无 `login_session_uuid` Cookie → 直接放行（`idle_timeout_middleware.py:90-92`） |
| 并发会话踢出（`refresh_token_db.py::delete_oldest_tokens`） | 仅踢主 `refresh_tokens` 表，portal token 不计入 |

---

## 8. 配置变更提醒

| 配置项 | 类型 | 说明 |
|---|---|---|
| `PORTAL_REFRESH_TOKEN_TTL_SECONDS` | 可选修改 | 默认 86400（24h），仅在 24h 不满足第三方使用时调整；调整需同步更新部署环境 `.env` 并重启服务 |

无新增配置项；无新增数据表。

---

## 9. 变更日志

- **2026-08-19**：初版，基于现有 Portal Refresh Token 通道落盘第三方接入 `/api/contract/chat` 完整流程，零代码变更