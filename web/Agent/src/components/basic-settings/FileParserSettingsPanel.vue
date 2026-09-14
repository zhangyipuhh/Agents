<template>
  <div class="file-parser-settings-panel" data-testid="file-parser-settings-panel">
    <GroupFormSection
      group-key="file_parser"
      label="文件解析"
      description="远程文件解析服务配置;本地解析失败时降级到此服务"
      :fields="fields"
    />
  </div>
</template>

<script setup>
// 文件解析 Tab(2026-09-14 新增,渲染修复)
// 1 个 section:文件解析
import GroupFormSection from './GroupFormSection.vue';

const fields = [
  { name: 'file_parser_enabled', label: '启用远程解析', type: 'bool', description: '总开关;关闭则只用本地解析' },
  { name: 'file_parser_server_url', label: '解析服务地址', type: 'str', description: '远程文件解析服务地址,支持 /parse 接口' },
  { name: 'file_parser_output_format', label: '输出格式', type: 'str', placeholder: 'json / md', description: 'json: 结构化结果 / md: 纯文本' },
  { name: 'file_parser_max_file_size', label: '最大文件大小(MB)', type: 'int', description: '超出此大小拒绝解析' },
  { name: 'file_parser_api_url', label: 'API 地址', type: 'str', description: '解析服务 API 网关地址(可能与 server_url 不同)' },
  { name: 'file_parser_max_retries', label: '最大轮询重试', type: 'int', description: '异步解析任务最大轮询次数' },
  { name: 'file_parser_poll_interval', label: '轮询间隔(秒)', type: 'float', description: '异步任务状态查询间隔' },
  { name: 'file_parser_timeout', label: '请求超时(秒)', type: 'int', description: '单次 HTTP 请求超时' },
];
</script>