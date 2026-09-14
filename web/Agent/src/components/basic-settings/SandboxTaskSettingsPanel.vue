<template>
  <div class="sandbox-task-settings-panel" data-testid="sandbox-task-settings-panel">
    <GroupFormSection
      group-key="sandbox"
      label="沙箱"
      description="Docker 沙箱容器配置(沙箱 Agent 运行环境)"
      :fields="sandboxFields"
    />
    <GroupFormSection
      group-key="task_scheduler"
      label="任务调度"
      description="后台定时任务调度器配置"
      :fields="schedulerFields"
    />
  </div>
</template>

<script setup>
// 沙箱与任务 Tab(2026-09-14 新增,渲染修复)
// 2 个 section:沙箱 / 任务调度
import GroupFormSection from './GroupFormSection.vue';

const sandboxFields = [
  { name: 'sandbox_docker_mode', label: 'Docker 模式', type: 'str', placeholder: 'local / socket / dind / k8s', description: 'local: 直接调用本机 docker;socket: 挂载 docker.sock;dind: docker-in-docker;k8s: 通过 k8s API' },
  { name: 'sandbox_docker_host', label: 'Docker Host', type: 'str', description: 'tcp://x.x.x.x:2375 或 unix:///var/run/docker.sock' },
  { name: 'sandbox_image', label: '镜像名', type: 'str', description: '沙箱 Agent 启动的基础镜像' },
  { name: 'sandbox_max_memory_mb', label: '内存上限(MB)', type: 'int', description: '容器内存硬限制,超出 OOM' },
  { name: 'sandbox_max_cpu_percent', label: 'CPU 上限(%)', type: 'int', description: 'CPU 配额百分比,100 = 1 核' },
  { name: 'sandbox_network_enabled', label: '启用网络', type: 'bool', description: '默认关闭以隔离沙箱;联网场景需评估风险' },
  { name: 'sandbox_default_timeout', label: '默认超时(秒)', type: 'int', description: '沙箱内任务默认执行超时' },
  { name: 'sandbox_container_workspace', label: '容器工作目录', type: 'str', description: '容器内 workspace 挂载点' },
  { name: 'sandbox_host_workspace_prefix', label: '宿主机工作目录前缀', type: 'str', description: '宿主机侧 workspace 根目录' },
  { name: 'sandbox_k8s_namespace', label: 'K8s 命名空间', type: 'str', description: 'Docker 模式为 k8s 时生效' },
  { name: 'sandbox_fallback_to_local', label: '降级到本地', type: 'bool', description: 'Docker 不可用时降级到本地执行(谨慎开启,隔离性下降)' },
];

const schedulerFields = [
  { name: 'task_scheduler_enabled', label: '启用调度器', type: 'bool', description: '关闭则所有定时任务不执行' },
  { name: 'task_scheduler_timezone', label: '时区', type: 'str', placeholder: 'Asia/Shanghai', description: 'cron 表达式解析时区;影响所有任务执行时间' },
  { name: 'task_scheduler_max_concurrency', label: '最大并发', type: 'int', description: '调度器同时执行的最大任务数,超出排队' },
];
</script>