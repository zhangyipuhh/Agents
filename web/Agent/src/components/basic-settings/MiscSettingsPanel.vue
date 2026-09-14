<template>
  <div>
    <GroupFormSection group-key="word_output" label="Word 输出" :fields="wordFields" />
    <GroupFormSection group-key="demonstration" label="演示模式" :fields="demoFields" />
    <GroupFormSection group-key="mcp_tags" label="MapAgent MCP 标签" :fields="mcpTagsFields" />
    <GroupFormSection group-key="skills" label="Skills" :fields="skillsFields" />
    <GroupFormSection group-key="devops" label="DevOps 凭据" :fields="devopsFields" />
    <GroupFormSection group-key="system" label="系统开关" :fields="systemFields" />
  </div>
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const wordFields = [
  { name: 'highlight_color', label: '高亮颜色(HEX)', type: 'str', placeholder: 'FF0000' },
  { name: 'output_dir', label: '输出目录', type: 'str' },
];

const demoFields = [
  { name: 'demonstration_report_enabled', label: '启用演示报告', type: 'bool' },
];

const mcpTagsFields = [
  { name: 'map_mcp_tags', label: 'MapAgent MCP 标签(JSON)', type: 'json' },
];

const skillsFields = [
  { name: 'skills_enabled', label: '启用 Skills', type: 'bool' },
  { name: 'skills_paths', label: 'Skills 根路径(逗号分隔)', type: 'str' },
  { name: 'skills_bootstrap_path', label: 'Bootstrap 路径', type: 'str' },
];

const devopsFields = [
  { name: 'credential_key', label: 'Fernet 密钥', type: 'str', sensitive: true },
  { name: 'servers_config_path', label: 'servers.yaml 路径', type: 'str' },
];

const systemFields = [
  { name: 'email_enabled', label: '邮件系统总开关', type: 'bool' },
  { name: 'script_scan_enabled', label: '脚本扫描总开关', type: 'bool' },
];
</script>
