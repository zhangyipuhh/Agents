<template>
  <div class="misc-settings-panel" data-testid="misc-settings-panel">
    <GroupFormSection
      group-key="word_output"
      label="Word 输出"
      description="Word 报告输出高亮颜色与目录配置"
      :fields="wordFields"
    />
    <GroupFormSection
      group-key="demonstration"
      label="演示模式"
      description="演示模式总开关"
      :fields="demoFields"
    />
    <GroupFormSection
      group-key="mcp_tags"
      label="MapAgent MCP 标签"
      description="map_agent 加载 MCP 工具时使用的标签过滤"
      :fields="mcpTagsFields"
    />
    <GroupFormSection
      group-key="skills"
      label="Skills"
      description="Skills 系统根路径与 Bootstrap 配置"
      :fields="skillsFields"
    />
    <GroupFormSection
      group-key="devops"
      label="DevOps 凭据"
      description="Fernet 密钥与 servers.yaml 路径(SSH 凭据加密存储)"
      :fields="devopsFields"
    />
    <GroupFormSection
      group-key="system"
      label="系统开关"
      description="邮件系统 / 脚本扫描总开关"
      :fields="systemFields"
    />
  </div>
</template>

<script setup>
// 其他 Tab(2026-09-14 新增,渲染修复)
// 6 个 section:Word 输出 / 演示模式 / MapAgent MCP 标签 / Skills / DevOps 凭据 / 系统开关
import GroupFormSection from './GroupFormSection.vue';

const wordFields = [
  { name: 'highlight_color', label: '高亮颜色(HEX)', type: 'str', placeholder: 'FF0000', description: 'Word 报告内关键词高亮色,不含 #' },
  { name: 'output_dir', label: '输出目录', type: 'str', description: 'Word 报告输出目录(相对项目根)' },
];

const demoFields = [
  { name: 'demonstration_report_enabled', label: '启用演示报告', type: 'bool', description: '演示模式下自动生成示例报告' },
];

const mcpTagsFields = [
  { name: 'map_mcp_tags', label: 'MapAgent MCP 标签(JSON)', type: 'json', placeholder: '["地图", "GIS"]', description: 'map_agent 加载 MCP 工具时的标签白名单;空 = 不过滤' },
];

const skillsFields = [
  { name: 'skills_enabled', label: '启用 Skills', type: 'bool', description: '总开关;关闭则所有智能体不加载 skills' },
  { name: 'skills_paths', label: 'Skills 根路径(逗号分隔)', type: 'str', description: 'Skills 根路径,逗号分隔多个路径' },
  { name: 'skills_bootstrap_path', label: 'Bootstrap 路径', type: 'str', description: '子智能体维度 bootstrap 路径(可覆盖全局默认)' },
];

const devopsFields = [
  { name: 'credential_key', label: 'Fernet 密钥', type: 'str', sensitive: true, description: '用于加密 devops_servers 表的密码字段;留空保持原值' },
  { name: 'servers_config_path', label: 'servers.yaml 路径', type: 'str', description: 'DevOps 服务器配置文件路径' },
];

const systemFields = [
  { name: 'email_enabled', label: '邮件系统总开关', type: 'bool', description: '关闭则不加载邮件相关组件' },
  { name: 'script_scan_enabled', label: '脚本扫描总开关', type: 'bool', description: '关闭则巡检脚本扫描功能不可用' },
];
</script>