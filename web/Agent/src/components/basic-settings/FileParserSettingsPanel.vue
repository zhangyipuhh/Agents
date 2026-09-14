<template>
  <GroupFormSection group-key="file_parser" label="文件解析" :fields="fields" />
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const fields = [
  { name: 'file_parser_enabled', label: '启用远程解析', type: 'bool' },
  { name: 'file_parser_server_url', label: '解析服务地址', type: 'str' },
  { name: 'file_parser_output_format', label: '输出格式', type: 'str', placeholder: 'json / md' },
  { name: 'file_parser_max_file_size', label: '最大文件大小(MB)', type: 'int' },
  { name: 'file_parser_api_url', label: 'API 地址', type: 'str' },
  { name: 'file_parser_max_retries', label: '最大轮询重试', type: 'int' },
  { name: 'file_parser_poll_interval', label: '轮询间隔(秒)', type: 'float' },
  { name: 'file_parser_timeout', label: '请求超时(秒)', type: 'int' },
];
</script>
