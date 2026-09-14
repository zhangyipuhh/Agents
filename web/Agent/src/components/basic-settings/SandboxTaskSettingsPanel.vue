<template>
  <div>
    <GroupFormSection group-key="sandbox" label="沙箱" :fields="sandboxFields" />
    <GroupFormSection group-key="task_scheduler" label="任务调度" :fields="schedulerFields" />
  </div>
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const sandboxFields = [
  { name: 'sandbox_docker_mode', label: 'Docker 模式', type: 'str', placeholder: 'local / socket / dind / k8s' },
  { name: 'sandbox_docker_host', label: 'Docker Host', type: 'str' },
  { name: 'sandbox_image', label: '镜像名', type: 'str' },
  { name: 'sandbox_max_memory_mb', label: '内存上限(MB)', type: 'int' },
  { name: 'sandbox_max_cpu_percent', label: 'CPU 上限(%)', type: 'int' },
  { name: 'sandbox_network_enabled', label: '启用网络', type: 'bool' },
  { name: 'sandbox_default_timeout', label: '默认超时(秒)', type: 'int' },
  { name: 'sandbox_container_workspace', label: '容器工作目录', type: 'str' },
  { name: 'sandbox_host_workspace_prefix', label: '宿主机工作目录前缀', type: 'str' },
  { name: 'sandbox_k8s_namespace', label: 'K8s 命名空间', type: 'str' },
  { name: 'sandbox_fallback_to_local', label: '降级到本地', type: 'bool' },
];

const schedulerFields = [
  { name: 'task_scheduler_enabled', label: '启用调度器', type: 'bool' },
  { name: 'task_scheduler_timezone', label: '时区', type: 'str' },
  { name: 'task_scheduler_max_concurrency', label: '最大并发', type: 'int' },
];
</script>
