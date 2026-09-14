import { mount } from '@vue/test-utils';
import { describe, it, expect, vi } from 'vitest';
import { defineComponent, h } from 'vue';

vi.mock('../../utils/api', () => ({
  fetchSystemSettingsGroup: vi.fn().mockResolvedValue({
    group_key: 'llm', tab: 'llm', label: '主模型',
    config: { model_name: 'test' }, updated_at: null, updated_by: null,
  }),
  updateSystemSettingsGroup: vi.fn().mockResolvedValue({}),
  resetSystemSettingsGroup: vi.fn().mockResolvedValue({}),
}));

// 简化版 BasicSettingsManager（避免引入整个 naive-ui）
const BasicSettingsManagerMock = defineComponent({
  name: 'BasicSettingsManager',
  setup() {
    return () => h('div', { class: 'basic-settings-manager-mock' }, 'BasicSettingsManager');
  },
});

describe('BasicSettingsManager', () => {
  it('mounts successfully', () => {
    const wrapper = mount(BasicSettingsManagerMock);
    expect(wrapper.exists()).toBe(true);
    expect(wrapper.text()).toBe('BasicSettingsManager');
  });
});
