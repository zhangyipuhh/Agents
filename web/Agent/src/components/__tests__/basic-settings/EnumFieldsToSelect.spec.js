// -*- coding:utf-8 -*-
/**
 * 枚举字段改下拉框渲染测试(2026-09-15 新增)
 *
 * 覆盖:
 * - GroupFormSection 对 type='select' 字段渲染 <select> 元素 + 全部 options
 * - fieldTypeLabel('select') 返回 'enum'
 * - 各 panel 中固定枚举字段已改为 type='select'(10 处):
 *   - LLM:  model_type × 4 + parallel_tool_calls × 2
 *   - 安全: samesite
 *   - 文件解析: file_parser_output_format
 *   - 沙箱: sandbox_docker_mode
 */
import { mount, flushPromises } from '@vue/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../../utils/api.js', () => ({
  fetchSystemSettingsGroup: vi.fn().mockResolvedValue({
    group_key: 'mock', tab: 'mock', label: 'Mock',
    config: {}, updated_at: null, updated_by: null,
  }),
  updateSystemSettingsGroup: vi.fn().mockResolvedValue({ config: {}, updated_at: null, updated_by: null }),
  resetSystemSettingsGroup: vi.fn().mockResolvedValue({ config: {}, updated_at: null, updated_by: null }),
}));

import GroupFormSection from '../../basic-settings/GroupFormSection.vue';
import LLMSettingsPanel from '../../basic-settings/LLMSettingsPanel.vue';
import SecuritySettingsPanel from '../../basic-settings/SecuritySettingsPanel.vue';
import FileParserSettingsPanel from '../../basic-settings/FileParserSettingsPanel.vue';
import SandboxTaskSettingsPanel from '../../basic-settings/SandboxTaskSettingsPanel.vue';

const MODEL_TYPE_OPTIONS = ['openai', 'anthropic', 'ollama', 'google', 'deepseek'];
const PARALLEL_TOOL_CALLS_OPTIONS = ['none', 'true', 'false'];

describe('GroupFormSection - select 类型渲染', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('type=select 字段渲染 <select> 元素 + 全部 options + 占位 option', async () => {
    const fields = [
      {
        name: 'sample_enum',
        label: '样例枚举',
        type: 'select',
        options: ['a', 'b', 'c'],
        description: '样例',
      },
    ];
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'test', label: '测试', fields },
    });
    await flushPromises();

    const select = wrapper.find('[data-testid="field-select-sample_enum"]');
    expect(select.exists()).toBe(true);
    expect(select.element.tagName).toBe('SELECT');

    const optionValues = [...select.element.options].map(o => o.value);
    // 占位 option + 三个枚举值 = 4
    expect(optionValues).toEqual(['', 'a', 'b', 'c']);
  });

  it('fieldTypeLabel 渲染为 enum chip', async () => {
    const fields = [
      { name: 'enum_field', label: '枚举', type: 'select', options: ['x'] },
    ];
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'test', label: '测试', fields },
    });
    await flushPromises();

    const typeChip = wrapper.find('[data-testid="field-type-enum_field"]');
    expect(typeChip.text()).toBe('enum');
  });

  it('已保存值不在 options 时,渲染为「当前值」选项兜底', async () => {
    // 后端返一个旧的自定义值(用户在更早版本存进去)
    vi.mocked((await import('../../../utils/api.js')).fetchSystemSettingsGroup)
      .mockResolvedValueOnce({
        group_key: 'test', tab: 'mock', label: 'Mock',
        config: { sample_enum: 'legacy_value' },
        updated_at: null, updated_by: null,
      });

    const fields = [
      { name: 'sample_enum', label: '样例', type: 'select', options: ['a', 'b'] },
    ];
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'test', label: '测试', fields },
    });
    await flushPromises();

    const select = wrapper.find('[data-testid="field-select-sample_enum"]');
    const optionTexts = [...select.element.options].map(o => o.text);
    expect(optionTexts.some(t => t.includes('legacy_value'))).toBe(true);
  });

  it('change 事件把值写回 formData(等同于选 select 后保存)', async () => {
    const fields = [
      { name: 'pick', label: '选择', type: 'select', options: ['x', 'y'] },
    ];
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'test', label: '测试', fields },
    });
    await flushPromises();

    const select = wrapper.find('[data-testid="field-select-pick"]');
    await select.setValue('y');
    // 触发 save 验证 formData 写入
    await wrapper.find('[data-testid="save-btn"]').trigger('click');
    await flushPromises();

    // updateSystemSettingsGroup 应收到 { pick: 'y' }
    const { updateSystemSettingsGroup } = await import('../../../utils/api.js');
    const calls = updateSystemSettingsGroup.mock.calls;
    expect(calls.length).toBeGreaterThan(0);
    const lastPayload = calls[calls.length - 1][1];
    expect(lastPayload.pick).toBe('y');
  });
});

describe('LLMSettingsPanel - model_type / parallel_tool_calls 下拉化', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('主模型:model_type + parallel_tool_calls 渲染为 select', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    const select1 = wrapper.find('[data-testid="field-select-model_type"]');
    expect(select1.exists()).toBe(true);
    const opts = [...select1.element.options].map(o => o.value);
    expect(opts).toEqual(['', ...MODEL_TYPE_OPTIONS]);

    const select2 = wrapper.find('[data-testid="field-select-parallel_tool_calls"]');
    expect(select2.exists()).toBe(true);
    const opts2 = [...select2.element.options].map(o => o.value);
    expect(opts2).toEqual(['', ...PARALLEL_TOOL_CALLS_OPTIONS]);
  });

  it('视觉模型:model_type_vision 渲染为 select', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    const select = wrapper.find('[data-testid="field-select-model_type_vision"]');
    expect(select.exists()).toBe(true);
    const opts = [...select.element.options].map(o => o.value);
    expect(opts).toEqual(['', ...MODEL_TYPE_OPTIONS]);
  });

  it('MCP Sampling:mcp_sampling_model_type 渲染为 select', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    const select = wrapper.find('[data-testid="field-select-mcp_sampling_model_type"]');
    expect(select.exists()).toBe(true);
    const opts = [...select.element.options].map(o => o.value);
    expect(opts).toEqual(['', ...MODEL_TYPE_OPTIONS]);
  });

  it('合同 LLM:model_type + parallel_tool_calls 渲染为 select', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    const selectType = wrapper.findAll('[data-testid="field-select-model_type"]');
    // model_type 在 LLM / vision_llm / mcp_sampling / contract_llm 都出现,
    // 但 testid 唯一 — 实际只有第一个 (group-key=llm) 的会被 querySelector 找到。
    // 这里改用 findAll 验证数量 = 2(主模型 + 合同 LLM,因 vision/mcp 是不同字段名)
    expect(selectType.length).toBeGreaterThanOrEqual(2);

    const selectParallel = wrapper.findAll('[data-testid="field-select-parallel_tool_calls"]');
    // 主模型 + 合同 = 2
    expect(selectParallel.length).toBeGreaterThanOrEqual(2);
  });
});

describe('SecuritySettingsPanel - samesite 下拉化', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('SameSite 字段渲染为 select + lax/strict/none', async () => {
    const wrapper = mount(SecuritySettingsPanel);
    await flushPromises();
    const select = wrapper.find('[data-testid="field-select-samesite"]');
    expect(select.exists()).toBe(true);
    const opts = [...select.element.options].map(o => o.value);
    expect(opts).toEqual(['', 'lax', 'strict', 'none']);
  });
});

describe('FileParserSettingsPanel - output_format 下拉化', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('file_parser_output_format 渲染为 select + json/md', async () => {
    const wrapper = mount(FileParserSettingsPanel);
    await flushPromises();
    const select = wrapper.find('[data-testid="field-select-file_parser_output_format"]');
    expect(select.exists()).toBe(true);
    const opts = [...select.element.options].map(o => o.value);
    expect(opts).toEqual(['', 'json', 'md']);
  });
});

describe('SandboxTaskSettingsPanel - docker_mode 下拉化', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('sandbox_docker_mode 渲染为 select + local/socket/dind/k8s', async () => {
    const wrapper = mount(SandboxTaskSettingsPanel);
    await flushPromises();
    const select = wrapper.find('[data-testid="field-select-sandbox_docker_mode"]');
    expect(select.exists()).toBe(true);
    const opts = [...select.element.options].map(o => o.value);
    expect(opts).toEqual(['', 'local', 'socket', 'dind', 'k8s']);
  });
});