// -*- coding:utf-8 -*-
/**
 * GroupFormSection 测试(2026-09-14 新增,渲染修复)
 *
 * 覆盖:
 * - 加载成功后表单输入框渲染 + 字段类型映射(str/int/float/bool/json/sensitive)
 * - bool 字段渲染为 .switch 切换控件 + 点击切换 formData 值
 * - sensitive 字段渲染为 password input + placeholder「留空保持不变」
 * - json 字段渲染为 textarea
 * - 保存按钮触发 updateSystemSettingsGroup + 敏感字段空串不传 payload
 * - 重置按钮触发 confirm + resetSystemSettingsGroup
 * - 加载失败显示 alert.error
 * - 保存成功显示 alert.success
 */
import { mount, flushPromises } from '@vue/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../utils/api.js', () => ({
  fetchSystemSettingsGroup: vi.fn(),
  updateSystemSettingsGroup: vi.fn(),
  resetSystemSettingsGroup: vi.fn(),
}));

import GroupFormSection from '../basic-settings/GroupFormSection.vue';
import * as api from '../../utils/api.js';

const SAMPLE_CONFIG = {
  model_name: 'gpt-4o',
  model_temperature: 0.7,
  model_api_key: '****abcd',  // 已脱敏 → 显示为 password input
  b: true,                    // 对应 bool 测试字段 name='b'
  j: '["https://app.example.com"]',
  max_concurrent: 5,
};

describe('GroupFormSection', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    api.fetchSystemSettingsGroup.mockResolvedValue({
      group_key: 'test',
      tab: 'test',
      label: '测试组',
      config: SAMPLE_CONFIG,
      updated_at: '2026-09-14T10:00:00',
      updated_by: 'admin',
    });
    api.updateSystemSettingsGroup.mockResolvedValue({
      config: SAMPLE_CONFIG,
      updated_at: '2026-09-14T10:00:00',
      updated_by: 'admin',
    });
    api.resetSystemSettingsGroup.mockResolvedValue({
      config: {},
      updated_at: '2026-09-14T10:00:00',
      updated_by: 'admin',
    });
  });

  it('调用 fetchSystemSettingsGroup(groupKey) 加载配置', async () => {
    mount(GroupFormSection, {
      props: { groupKey: 'llm', label: '主模型', fields: [{ name: 'model_name', label: '模型名', type: 'str' }] },
    });
    await flushPromises();
    expect(api.fetchSystemSettingsGroup).toHaveBeenCalledWith('llm');
  });

  it('加载成功后表单输入框渲染 + 显示「最后更新」', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'llm', label: '主模型',
        fields: [{ name: 'model_name', label: '模型名', type: 'str' }],
      },
    });
    await flushPromises();
    const input = wrapper.find('[data-testid="field-input-model_name"]');
    expect(input.exists()).toBe(true);
    expect(input.element.value).toBe('gpt-4o');
    expect(wrapper.find('[data-testid="updated-at"]').text()).toContain('2026-09-14T10:00:00');
    expect(wrapper.find('[data-testid="updated-at"]').text()).toContain('admin');
  });

  it('str 字段渲染为 text input', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
    });
    await flushPromises();
    const input = wrapper.find('[data-testid="field-input-a"]');
    expect(input.element.tagName).toBe('INPUT');
    expect(input.attributes('type')).toBe('text');
  });

  it('int / float 字段渲染为 number input 带正确 step', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [
          { name: 'i', label: 'I', type: 'int' },
          { name: 'f', label: 'F', type: 'float' },
        ],
      },
    });
    await flushPromises();
    const i = wrapper.find('[data-testid="field-input-i"]');
    expect(i.attributes('type')).toBe('number');
    expect(i.attributes('step')).toBe('1');
    const f = wrapper.find('[data-testid="field-input-f"]');
    expect(f.attributes('step')).toBe('0.01');
  });

  it('bool 字段渲染为 .switch + checkbox + 状态文本', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'b', label: 'B', type: 'bool' }] },
    });
    await flushPromises();
    const sw = wrapper.find('[data-testid="field-switch-b"]');
    expect(sw.exists()).toBe(true);
    const cb = sw.find('input[type="checkbox"]');
    expect(cb.exists()).toBe(true);
    // SAMPLE_CONFIG.b=true → 开启
    expect(sw.find('.switch-label').text()).toBe('开启');
  });

  it('bool 字段点击 checkbox 切换 + 状态文本同步', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'b', label: 'B', type: 'bool' }] },
    });
    await flushPromises();
    const sw = wrapper.find('[data-testid="field-switch-b"]');
    const cb = sw.find('input[type="checkbox"]');
    // happy-dom 下 native change 不会自动翻转 checked,手动构造 change 事件
    // 模拟初始 checked=true → 翻转成 false 的事件
    cb.element.checked = false;
    await cb.trigger('change');
    expect(sw.find('.switch-label').text()).toBe('关闭');
  });

  it('sensitive 字段渲染为 password input + placeholder「留空保持不变」', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'k', label: 'K', type: 'str', sensitive: true }] },
    });
    await flushPromises();
    const input = wrapper.find('[data-testid="field-input-k"]');
    expect(input.attributes('type')).toBe('password');
    expect(input.attributes('placeholder')).toBe('留空保持不变');
  });

  it('json 字段渲染为 textarea + 解析失败 alert', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'j', label: 'J', type: 'json' }] },
    });
    await flushPromises();
    const ta = wrapper.find('[data-testid="field-input-j"]');
    expect(ta.element.tagName).toBe('TEXTAREA');
    // 输入非法 JSON 后保存 → alert 警告
    await ta.setValue('not valid json');
    await wrapper.find('[data-testid="save-btn"]').trigger('click');
    await flushPromises();
    // updateSystemSettingsGroup 仍被调用(payload 含原值),alert.error 出现
    expect(api.updateSystemSettingsGroup).toHaveBeenCalled();
    expect(wrapper.find('[data-testid="error-alert"]').exists()).toBe(true);
  });

  it('multiline 字段渲染为 textarea', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'm', label: 'M', type: 'str', multiline: true }] },
    });
    await flushPromises();
    const ta = wrapper.find('[data-testid="field-input-m"]');
    expect(ta.element.tagName).toBe('TEXTAREA');
    expect(ta.attributes('rows')).toBe('4');
  });

  it('保存按钮触发 updateSystemSettingsGroup + 敏感字段空串不传 payload', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'llm', label: '主模型',
        fields: [
          { name: 'model_name', label: '模型名', type: 'str' },
          { name: 'model_api_key', label: 'API Key', type: 'str', sensitive: true },
        ],
      },
    });
    await flushPromises();
    // 模拟用户清空 API Key(留空 = 保持原值)
    const apiKeyInput = wrapper.find('[data-testid="field-input-model_api_key"]');
    await apiKeyInput.setValue('');
    await wrapper.find('[data-testid="save-btn"]').trigger('click');
    await flushPromises();
    expect(api.updateSystemSettingsGroup).toHaveBeenCalled();
    const [calledKey, calledPayload] = api.updateSystemSettingsGroup.mock.calls.at(-1);
    expect(calledKey).toBe('llm');
    expect(calledPayload).not.toHaveProperty('model_api_key');  // 敏感字段空串 → 不传
    expect(calledPayload).toHaveProperty('model_name');           // 普通字段照常传
  });

  it('保存成功后显示 alert.success「保存成功,需重启服务生效」', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
    });
    await flushPromises();
    await wrapper.find('[data-testid="save-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="success-alert"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="success-alert"]').text()).toContain('保存成功');
  });

  it('保存失败显示 alert.error 含后端 message', async () => {
    api.updateSystemSettingsGroup.mockRejectedValueOnce(new Error('校验失败:xxx'));
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
    });
    await flushPromises();
    await wrapper.find('[data-testid="save-btn"]').trigger('click');
    await flushPromises();
    expect(wrapper.find('[data-testid="error-alert"]').exists()).toBe(true);
    expect(wrapper.find('[data-testid="error-alert"]').text()).toContain('校验失败:xxx');
  });

  it('加载失败显示 alert.error', async () => {
    api.fetchSystemSettingsGroup.mockRejectedValueOnce(new Error('网络异常'));
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="error-alert"]').text()).toContain('网络异常');
  });

  it('重置按钮触发 confirm + 用户取消时 resetSystemSettingsGroup 不调用', async () => {
    const originalConfirm = window.confirm;
    let confirmCalls = 0;
    window.confirm = vi.fn(() => { confirmCalls += 1; return false; });
    try {
      const wrapper = mount(GroupFormSection, {
        props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
      });
      await flushPromises();
      await wrapper.find('[data-testid="reset-btn"]').trigger('click');
      await flushPromises();
      expect(confirmCalls).toBeGreaterThan(0);
      expect(api.resetSystemSettingsGroup).not.toHaveBeenCalled();
    } finally {
      window.confirm = originalConfirm;
    }
  });

  it('重置按钮触发 confirm + 用户确认时调 resetSystemSettingsGroup + 显示 success', async () => {
    const originalConfirm = window.confirm;
    window.confirm = vi.fn(() => true);
    try {
      const wrapper = mount(GroupFormSection, {
        props: { groupKey: 'g', label: 'G', fields: [{ name: 'a', label: 'A', type: 'str' }] },
      });
      await flushPromises();
      await wrapper.find('[data-testid="reset-btn"]').trigger('click');
      await flushPromises();
      expect(api.resetSystemSettingsGroup).toHaveBeenCalledWith('g');
      expect(wrapper.find('[data-testid="success-alert"]').text()).toContain('已重置');
    } finally {
      window.confirm = originalConfirm;
    }
  });

  it('description 透传到 .group-card-desc', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        description: '这是组描述',
        fields: [{ name: 'a', label: 'A', type: 'str' }],
      },
    });
    await flushPromises();
    expect(wrapper.find('.group-card-desc').text()).toBe('这是组描述');
  });

  it('field.description 透传到 .form-help', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [{ name: 'a', label: 'A', type: 'str', description: '字段说明文本' }],
      },
    });
    await flushPromises();
    expect(wrapper.find('.form-help').text()).toBe('字段说明文本');
  });

  it('required 字段显示必填星号', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [{ name: 'a', label: 'A', type: 'str', required: true }],
      },
    });
    await flushPromises();
    expect(wrapper.find('.required-mark').exists()).toBe(true);
    expect(wrapper.find('.required-mark').text()).toBe('*');
  });

  it('section header 显示 group_key chip(后端组 key)', async () => {
    const wrapper = mount(GroupFormSection, {
      props: { groupKey: 'auth_cookie', label: '认证 Cookie', fields: [{ name: 'secure', label: 'Secure', type: 'bool' }] },
    });
    await flushPromises();
    expect(wrapper.find('.group-key-chip').exists()).toBe(true);
    expect(wrapper.find('.group-key-chip').text()).toBe('auth_cookie');
  });

  it('section header 统计配置项数量与敏感字段数量', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [
          { name: 'a', label: 'A', type: 'str' },
          { name: 'b', label: 'B', type: 'bool' },
          { name: 'c', label: 'C', type: 'str', sensitive: true },
        ],
      },
    });
    await flushPromises();
    const meta = wrapper.find('.group-card-meta').text();
    expect(meta).toContain('配置项');
    expect(meta).toContain('3');
    expect(meta).toContain('敏感字段');
    expect(meta).toContain('1');
  });

  it('每个字段显示 field-key chip(后端字段名)与 field-type chip(类型)', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [
          { name: 'model_name', label: '模型名', type: 'str' },
          { name: 'is_enabled', label: '启用', type: 'bool' },
          { name: 'count', label: '计数', type: 'int' },
        ],
      },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="field-key-model_name"]').text()).toBe('model_name');
    expect(wrapper.find('[data-testid="field-type-model_name"]').text()).toBe('str');
    expect(wrapper.find('[data-testid="field-key-is_enabled"]').text()).toBe('is_enabled');
    expect(wrapper.find('[data-testid="field-type-is_enabled"]').text()).toBe('bool');
    expect(wrapper.find('[data-testid="field-type-count"]').text()).toBe('int');
  });

  it('敏感字段 type chip 显示 secret + 锁图标', async () => {
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [{ name: 'api_key', label: 'API Key', type: 'str', sensitive: true }],
      },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="field-type-api_key"]').text()).toBe('secret');
    expect(wrapper.find('.sensitive-mark').exists()).toBe(true);
  });

  it('bool 字段显示当前值预览 chip', async () => {
    api.fetchSystemSettingsGroup.mockResolvedValueOnce({
      group_key: 'g', tab: 'g', label: 'G',
      config: { feature: true },
      updated_at: null, updated_by: null,
    });
    const wrapper = mount(GroupFormSection, {
      props: {
        groupKey: 'g', label: 'G',
        fields: [{ name: 'feature', label: '启用特性', type: 'bool' }],
      },
    });
    await flushPromises();
    expect(wrapper.find('[data-testid="field-current-feature"]').text()).toContain('true');
  });
});