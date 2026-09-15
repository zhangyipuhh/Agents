<template>
  <div class="llm-settings-panel" data-testid="llm-settings-panel">
    <GroupFormSection
      group-key="llm"
      label="主模型"
      description="主对话 LLM 配置,影响所有智能体默认推理"
      :fields="llmFields"
    />
    <GroupFormSection
      group-key="vision_llm"
      label="视觉模型"
      description="图片理解专用 LLM,空则与主模型共用"
      :fields="visionFields"
    />
    <GroupFormSection
      group-key="mcp_sampling"
      label="MCP Sampling 模型"
      description="MCP Server 回调用的 LLM 凭证,可独立配置"
      :fields="samplingFields"
    />
    <GroupFormSection
      group-key="contract_llm"
      label="合同 LLM"
      description="合同路由专用 LLM,独立凭证隔离,空时回退到主模型"
      :fields="contractFields"
    />
  </div>
</template>

<script setup>
// LLM 模型 Tab(2026-09-14 新增,渲染修复)
// 4 个 section:主模型 / 视觉模型 / MCP Sampling / 合同 LLM
// 视觉风格与 EmailSettingsManager 同款
import GroupFormSection from './GroupFormSection.vue';

// 2026-09-15:固定枚举字段改下拉框(model_type × 4 + parallel_tool_calls × 2)
const MODEL_TYPE_OPTIONS = ['openai', 'anthropic', 'ollama', 'google', 'deepseek'];
const PARALLEL_TOOL_CALLS_OPTIONS = ['none', 'true', 'false'];

const llmFields = [
  { name: 'model_type', label: '模型类型', type: 'select', options: MODEL_TYPE_OPTIONS, description: 'openai / anthropic / ollama / google / deepseek' },
  { name: 'model_name', label: '模型名称', type: 'str', description: '如 gpt-4o / claude-sonnet-4 / qwen2.5:32b' },
  { name: 'model_api_key', label: 'API Key', type: 'str', sensitive: true, description: '凭据,留空保持原值' },
  { name: 'model_api_base', label: 'API Base URL', type: 'str', description: 'OpenAI 兼容端点 / Ollama 本地地址' },
  { name: 'model_temperature', label: '温度', type: 'float', description: '0-1 之间,越高越发散' },
  { name: 'is_multimodal', label: '多模态', type: 'bool', description: '是否支持图片输入' },
  { name: 'parallel_tool_calls', label: '并行工具调用', type: 'select', options: PARALLEL_TOOL_CALLS_OPTIONS, description: 'none = 走 LLM 全局;true/false 强制覆盖' },
  { name: 'ollama_reasoning', label: 'Ollama 推理', type: 'bool', description: '启用 Ollama 原生推理字段' },
  { name: 'ollama_timeout', label: 'Ollama 超时(秒)', type: 'int', description: '单次请求超时时间' },
];

const visionFields = [
  { name: 'model_type_vision', label: '模型类型', type: 'select', options: MODEL_TYPE_OPTIONS, description: 'openai / anthropic / google 等' },
  { name: 'model_name_vision', label: '模型名称', type: 'str', description: '如 gpt-4o / claude-sonnet-4(支持 vision)' },
  { name: 'model_api_key_vision', label: 'API Key', type: 'str', sensitive: true, description: '视觉模型凭据,留空保持原值' },
  { name: 'model_api_base_vision', label: 'API Base URL', type: 'str', description: '视觉模型 API 端点' },
  { name: 'model_temperature_vision', label: '温度', type: 'float', description: '0-1 之间,视觉模型默认 0.2 较稳定' },
];

const samplingFields = [
  { name: 'mcp_sampling_model_type', label: '模型类型', type: 'select', options: MODEL_TYPE_OPTIONS, description: 'MCP Sampling 调用的模型类型' },
  { name: 'mcp_sampling_model_name', label: '模型名称', type: 'str', description: 'MCP Sampling 回调用的具体模型' },
  { name: 'mcp_sampling_model_api_key', label: 'API Key', type: 'str', sensitive: true, description: 'MCP Sampling 凭据,留空保持原值' },
  { name: 'mcp_sampling_model_api_base', label: 'API Base URL', type: 'str', description: 'MCP Sampling API 端点' },
  { name: 'mcp_sampling_model_temperature', label: '温度', type: 'float', description: 'MCP Sampling 采样温度' },
  { name: 'mcp_sampling_is_multimodal', label: '多模态', type: 'bool', description: 'MCP Sampling 是否需要多模态能力' },
];

const contractFields = [
  { name: 'model_type', label: '模型类型', type: 'select', options: MODEL_TYPE_OPTIONS, description: '合同路由独立模型类型' },
  { name: 'model_name', label: '模型名称', type: 'str', description: '合同路由专用模型名' },
  { name: 'model_api_key', label: 'API Key', type: 'str', sensitive: true, description: '合同路由独立凭据,留空保持原值' },
  { name: 'model_api_base', label: 'API Base URL', type: 'str', description: '合同路由 API 端点' },
  { name: 'model_temperature', label: '温度', type: 'float', description: '合同路由采样温度' },
  { name: 'is_multimodal', label: '多模态', type: 'bool', description: '合同路由模型是否支持多模态' },
  { name: 'parallel_tool_calls', label: '并行工具调用', type: 'select', options: PARALLEL_TOOL_CALLS_OPTIONS, description: 'Ollama 默认 true 可能与 file_chunk_read_progress 单 superstep 写冲突,推荐 false' },
];
</script>