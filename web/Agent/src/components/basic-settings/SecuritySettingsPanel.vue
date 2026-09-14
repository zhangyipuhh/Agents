<template>
  <div class="security-settings-panel" data-testid="security-settings-panel">
    <GroupFormSection
      group-key="auth_cookie"
      label="认证 Cookie"
      description="HttpOnly Cookie Secure / SameSite 配置"
      :fields="cookieFields"
    />
    <GroupFormSection
      group-key="auth_bootstrap"
      label="默认管理员"
      description="lifespan 启动时默认管理员创建与历史弱口令迁移"
      :fields="bootstrapFields"
    />
    <GroupFormSection
      group-key="auth_idle"
      label="闲置超时"
      description="会话 idle 超时自动退出(等保三级 §1.5)"
      :fields="idleFields"
    />
    <GroupFormSection
      group-key="mfa"
      label="MFA 双因素"
      description="TOTP 双因素认证配置"
      :fields="mfaFields"
    />
    <GroupFormSection
      group-key="registration_security"
      label="注册审批"
      description="注册审批 + IP 白名单(等保三级 §7.1.3 a/e)"
      :fields="regFields"
    />
    <GroupFormSection
      group-key="session"
      label="会话并发"
      description="聊天并发控制 + Token 有效期"
      :fields="sessionFields"
    />
  </div>
</template>

<script setup>
// 安全认证 Tab(2026-09-14 新增,渲染修复)
// 6 个 section:认证 Cookie / 默认管理员 / 闲置超时 / MFA / 注册审批 / 会话并发
import GroupFormSection from './GroupFormSection.vue';

const cookieFields = [
  { name: 'secure', label: 'Secure 标志', type: 'bool', description: 'HTTPS 下必须 true,禁止 Cookie 经明文传输' },
  { name: 'samesite', label: 'SameSite', type: 'str', placeholder: 'lax / strict / none', description: 'CSRF 防护;跨站场景用 none + secure=true' },
  { name: 'access_token_max_age', label: 'Access Token 有效期(秒)', type: 'int', description: '默认 1800(30 分钟)' },
  { name: 'refresh_token_max_age', label: 'Refresh Token 有效期(秒)', type: 'int', description: '默认 14 天' },
];

const bootstrapFields = [
  { name: 'bootstrap_enabled', label: '启用默认管理员创建', type: 'bool', description: 'lifespan 启动时无 admin 自动创建;生产环境务必先关' },
  { name: 'default_admin_username', label: '默认管理员用户名', type: 'str', description: '创建默认管理员时使用的用户名' },
  { name: 'default_admin_password', label: '默认管理员密码', type: 'str', sensitive: true, description: '首次启动自动创建,丢失需手动初始化;生产环境务必立即修改' },
  { name: 'max_concurrent_sessions', label: '同账号最大并发', type: 'int', description: '同账号最多同时在线会话数,超出踢出最旧' },
];

const idleFields = [
  { name: 'idle_timeout_enabled', label: '启用闲置超时', type: 'bool', description: '等保三级要求;开启后无操作自动登出' },
  { name: 'idle_timeout_seconds', label: '超时(秒)', type: 'int', description: '用户无操作 N 秒后自动下线,默认 1800' },
];

const mfaFields = [
  { name: 'issuer', label: 'Issuer', type: 'str', description: 'TOTP issuer 标识,显示在认证器 App 中(如 AIOps)' },
  { name: 'secret_key', label: 'Secret Key', type: 'str', sensitive: true, description: 'HMAC 签名密钥;留空保持原值' },
  { name: 'mfa_required_for_admin', label: '管理员强制 MFA', type: 'bool', description: '等保三级要求;admin 账号必须绑定 MFA' },
];

const regFields = [
  { name: 'enabled', label: '启用注册审批', type: 'bool', description: '开启后新注册用户需 admin 审批激活(IP 白名单独立配置)' },
];

const sessionFields = [
  { name: 'agent_chat_max_concurrency', label: '聊天最大并发', type: 'int', description: '单用户同时进行的聊天请求上限,超出排队' },
];
</script>