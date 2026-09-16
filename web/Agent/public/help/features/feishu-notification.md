# 飞书通知

飞书通知模块负责**飞书 channel / target 配置**与 **LLM 工具 send_feishu_message 自动路由**。

![飞书通知](/help/screenshots/features-feishu-notification/01-feishu.png)

## 前置条件

- **`.env` 必须设置 `DEVOPS_CREDENTIAL_KEY`**（Fernet 密钥，与邮件共用，base64 编码）
- 至少 1 个飞书应用（飞书开放平台 https://open.feishu.cn 创建）
- admin 角色（路由 `require_admin_or_menu_acl('messaging.feishu.*')`）
- 已配置至少 1 个目标智能体（`agent_name` 必填）

## 三层架构（2026-09-03 落地）

### 入口与界面

「消息设置 → 飞书设置」含三个孙 Tab：**应用设置**（channel 管理）、**发送策略**（target 与路由规则）、**发送测试**（单条精准测试）。

- 「+ 新建应用」：填写 app_id / app_secret（Fernet 加密存储）+ 绑定智能体
- 每个 enabled 应用启动独立 WS 监听进程，**保存即生效**（热加载，无需重启）
- 密钥字段留空表示不修改原密钥

### 表设计（通用通知渠道）

| 表 | 用途 |
|---|---|
| `notification_channels` | 渠道（飞书应用实例）|
| `notification_targets` | 目标（飞书群 / 用户）|

凭证差异一律进 `config` JSONB，service 层按 `channel_type` 分发。

### Service 层分发

```python
# notification_config_service.py
SUPPORTED_CHANNEL_TYPES = ("feishu",)
SUPPORTED_TARGET_TYPES = ("feishu.chat", "feishu.user")

FEISHU_REQUIRED_CONFIG_KEYS = (
    "app_id_encrypted",
    "app_secret_encrypted",
    "log_level",
    "agent_name",
)

FEISHU_TARGET_REQUIRED_CONFIG_KEYS = (
    "chat_id",
    "chat_type",
)

FEISHU_RECEIVE_ID_TYPES = ("chat_id", "open_id", "user_id", "email")
```

## 创建飞书 channel

### API
`POST /api/notification/channels` body：

```json
{
  "channel_type": "feishu",
  "display_name": "项目智能体飞书",
  "enabled": true,
  "config": {
    "app_id_encrypted": "fernet:gAAAAA...",
    "app_secret_encrypted": "fernet:gAAAAA...",
    "log_level": "INFO",
    "agent_name": "project"
  }
}
```

### 必填字段

| 字段 | 取值 | 说明 |
|---|---|---|
| `app_id_encrypted` | Fernet 密文（`fernet:` 前缀）| 飞书应用 App ID |
| `app_secret_encrypted` | Fernet 密文 | App Secret |
| `log_level` | `DEBUG` / `INFO` / `WARNING` / `ERROR` | SDK 日志级别 |
| `agent_name` | 已存在的智能体名 | channel 绑定的目标智能体 |

### 凭证加密链路

```python
# NotificationConfigService._ensure_fernet()
fernet = Fernet(credential_key)
ciphertext = fernet.encrypt(app_id.encode()).decode("ascii")
# 存 DB 时：config.app_id_encrypted = ciphertext
# 读 DB 时：fernet.decrypt(ciphertext.encode()).decode()
```

> ⚠️ **Fernet 加密是单向的**——前端永远不接触原始密钥。`SETTINGS_SECRET_KEY`（DEVOPS_CREDENTIAL_KEY）必须**安全**保管，丢失后无法恢复已加密的凭证。

## 创建飞书 target

### API
`POST /api/notification/targets` body：

```json
{
  "channel_id": 11,
  "target_type": "feishu.chat",
  "display_name": "运维群",
  "enabled": true,
  "config": {
    "chat_id": "oc_54d0d90...",
    "chat_type": "chat_id",
    "chat_name": "运维群"
  }
}
```

### 必填字段

| 字段 | 取值 | 说明 |
|---|---|---|
| `chat_id` | 字符串 | 群 ID / 用户 open_id |
| `chat_type` | `chat_id` / `open_id` / `user_id` / `email` | 接收方类型 |

### 可选字段

| 字段 | 说明 |
|---|---|
| `chat_name` | 群名 / 用户昵称（仅展示用）|
| `default_receive_id` | 兼容 2026-09-03 旧版 channel 的字段 |

## 设置后效果

### DB 层

- `notification_channels` 表新增行（`channel_type='feishu'`、`config` JSONB 存加密凭证）
- `notification_targets` 表新增行（关联 channel）

### WS 长连接自动启动（2026-09-10 落地）

- `notification_router` 调 `_apply_feishu_ws_change` hook
- `FeishuWebSocketManager.apply_channel_change` 启动 WS 实例
- **保存即生效**——无需重启服务

### LLM 工具路由

- LLM 调用 `send_feishu_message` 工具
- 通过 `FeishuEndpointResolver.resolve_current_endpoint(runtime.state.agent_name)` 自动路由
- `agent_name` 是唯一路由 key（admin 在创建 channel 时绑定）

## LLM 工具契约

### `send_feishu_message(content, runtime)`

- **参数**：`content: str`（Markdown 自动检测 → interactive 卡片）
- **返回**：ToolMessage（成功 / 失败）
- **路由**：runtime.state.agent_name → channel → target

### 内部实现

```python
# app/shared/tools/skills/feishu/FeishuMessageTools.py
async def send_feishu_message(content: str, runtime: ToolRuntime) -> str:
    endpoint = await resolve_current_endpoint(runtime.state.get("agent_name"))
    if endpoint is None:
        return "飞书发送配置缺失"
    client = build_lark_client(endpoint)
    await asyncio.to_thread(client.im.v1.message.create, request)
    return "ok"
```

## 发送策略

### 多个 channel 同 agent_name

- `agent_name` 一对一 channel/target
- `resolve_current_endpoint` 用 `is_default DESC + id ASC LIMIT 1` 防御脏数据
- 不支持「默认应用」概念（2026-09-11 已废弃）

### 多个 target 同 channel

- channel 与 target 是 1:N 关系
- 发送时按 `agent_name` 找到 channel，再遍历 targets 发送
- 单个 target 失败不影响其他（`asyncio.gather return_exceptions=True`）

## 飞书凭证获取

### 创建飞书应用

1. 访问 https://open.feishu.cn → 「开发者后台」 → 「创建企业自建应用」
2. 填写应用名 / 描述 / 图标
3. 在「权限管理」添加所需权限：
   - `im:message` 发送消息
   - `im:message:send_as_bot` 以应用身份发送
   - `contact:user.id:readonly` 获取用户 ID
4. 「事件订阅」添加 `im.message.receive_v1`（接收消息）
5. 「机器人」能力开启
6. 在「凭证与基础信息」获取 App ID / App Secret

### 加密保存

```python
from cryptography.fernet import Fernet
import os

key = os.environ["DEVOPS_CREDENTIAL_KEY"]  # 必须 base64 编码的 32 字节密钥
fernet = Fernet(key)
ciphertext = fernet.encrypt(b"cli_xxxxxxxxxxxx").decode("ascii")
print(ciphertext)  # 存入 channel.config.app_id_encrypted
```

## WS 热加载机制

![飞书通知滚动视图](/help/screenshots/features-feishu-notification/01-feishu.png)

### 启动时

- `lifespan` 启动期 `FeishuWebSocketManager.start_all` 扫描所有 enabled channel
- 每条 channel 独立后台线程 + 独立 lark.Client
- session_id 加 `channel_id` 命名空间（不污染主侧边栏）

### 创建 / 更新 channel

- `_apply_feishu_ws_change` hook 立即触发
- `apply_channel_change` 先 shutdown 旧实例 → 重读 DB → 启动新实例
- 响应体附 `ws_applied: bool`

### 删除 channel

- `_apply_feishu_ws_change` hook 触发 `shutdown()` 旧实例

## 常见问题

### 凭证无效？
**错误文案**：`invalid app_secret`

**修复**：
1. 检查 `app_id` / `app_secret` 是否正确
2. 重新加密保存

### WS 连接断开？
**现象**：飞书通知收不到消息

**排查**：
1. 检查 channel `enabled=true`
2. 查看后端日志是否有 `lark SDK ClientException`
3. 重新保存 channel 配置触发热加载

### send_feishu_message 工具路由失败？
**错误文案**：`飞书发送配置缺失`

**排查**：
1. 检查 channel `config.agent_name` 是否绑定到当前 runtime 的智能体
2. 检查 channel `enabled=true`
3. 检查 `NotificationConfigService` 初始化时 `credential_key` 是否正确

### 工具调用卡顿？
**原因**：`lark SDK` 同步阻塞调用 → `asyncio.to_thread` 卸载到线程池

**修复**：确保 LLM 工具是 `async def`，LangChain ToolNode 原生支持。

## 相关章节

- [智能体对话](/help/features/chat) — LLM 调用工具
- [权限管理](/help/features/permission-management) — 飞书菜单 ACL
- [常见问题 → 飞书问题](/help/faq#飞书问题) — 高频问题
