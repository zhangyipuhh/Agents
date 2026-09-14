<template>
  <div class="llm-settings-panel">
    <GroupFormSection group-key="llm" label="主模型" :fields="llmFields" />
    <GroupFormSection group-key="vision_llm" label="视觉模型" :fields="visionFields" />
    <GroupFormSection group-key="mcp_sampling" label="MCP Sampling 模型" :fields="samplingFields" />
    <GroupFormSection group-key="contract_llm" label="合同 LLM" :fields="contractFields" />
  </div>
</template>

<script setup>
import GroupFormSection from './GroupFormSection.vue';

const llmFields = [
  { name: 'model_type', label: '模型类型', type: 'str' },
  { name: 'model_name', label: '模型名称', type: 'str' },
  { name: 'model_api_key', label: 'API Key', type: 'str', sensitive: true },
  { name: 'model_api_base', label: 'API Base URL', type: 'str' },
  { name: 'model_temperature', label: '温度', type: 'float' },
  { name: 'is_multimodal', label: '多模态', type: 'bool' },
  { name: 'parallel_tool_calls', label: '并行工具调用', type: 'str', placeholder: 'none / true / false' },
  { name: 'ollama_reasoning', label: 'Ollama 推理', type: 'bool' },
  { name: 'ollama_timeout', label: 'Ollama 超时(秒)', type: 'int' },
];

const visionFields = [
  { name: 'model_type_vision', label: '模型类型', type: 'str' },
  { name: 'model_name_vision', label: '模型名称', type: 'str' },
  { name: 'model_api_key_vision', label: 'API Key', type: 'str', sensitive: true },
  { name: 'model_api_base_vision', label: 'API Base URL', type: 'str' },
  { name: 'model_temperature_vision', label: '温度', type: 'float' },
];

const samplingFields = [
  { name: 'mcp_sampling_model_type', label: '模型类型', type: 'str' },
  { name: 'mcp_sampling_model_name', label: '模型名称', type: 'str' },
  { name: 'mcp_sampling_model_api_key', label: 'API Key', type: 'str', sensitive: true },
  { name: 'mcp_sampling_model_api_base', label: 'API Base URL', type: 'str' },
  { name: 'mcp_sampling_model_temperature', label: '温度', type: 'float' },
  { name: 'mcp_sampling_is_multimodal', label: '多模态', type: 'bool' },
];

const contractFields = [
  { name: 'model_type', label: '模型类型', type: 'str' },
  { name: 'model_name', label: '模型名称', type: 'str' },
  { name: 'model_api_key', label: 'API Key', type: 'str', sensitive: true },
  { name: 'model_api_base', label: 'API Base URL', type: 'str' },
  { name: 'model_temperature', label: '温度', type: 'float' },
  { name: 'is_multimodal', label: '多模态', type: 'bool' },
  { name: 'parallel_tool_calls', label: '并行工具调用', type: 'str' },
];
</script>
