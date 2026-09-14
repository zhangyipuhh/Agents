// -*- coding:utf-8 -*-
/**
 * BasicSettingsManager 测试(2026-09-14 渲染修复)
 *
 * 覆盖:
 * - 渲染 6 个 tab 按钮(LLM 模型 / 文件解析 / 安全认证 / 网络与集成 / 沙箱与任务 / 其他)
 * - 默认 active = 'llm'
 * - 切换 tab 后对应 panel 显示
 * - 警告条「本页配置修改后需重启服务生效」存在
 * - 主密钥卡相关 DOM 不存在(回归断言)
 *
 * 注意:BasicSettingsManager 内部 import 6 个 *SettingsPanel,这些孙组件又会 import GroupFormSection。
 * 由于 GroupFormSection 用 onMounted 异步拉 fetchSystemSettingsGroup,需要 mock 整个 api 模块,
 * 否则测试会因 fetch 调用失败而出现 unhandled rejection。
 */
import { mount, flushPromises } from '@vue/test-utils';
import { describe, it, expect, vi, beforeEach } from 'vitest';

vi.mock('../../utils/api.js', () => ({
  fetchSystemSettingsGroup: vi.fn().mockResolvedValue({
    group_key: 'mock',
    tab: 'mock',
    label: 'Mock',
    config: {},
    updated_at: null,
    updated_by: null,
  }),
  updateSystemSettingsGroup: vi.fn().mockResolvedValue({ config: {}, updated_at: null, updated_by: null }),
  resetSystemSettingsGroup: vi.fn().mockResolvedValue({ config: {}, updated_at: null, updated_by: null }),
}));

import BasicSettingsManager from '../BasicSettingsManager.vue';

describe('BasicSettingsManager', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('渲染 6 个 tab 按钮并保持预期 label 顺序', () => {
    const wrapper = mount(BasicSettingsManager);
    const tabs = wrapper.findAll('[data-testid^="basic-tab-"]');
    expect(tabs).toHaveLength(6);
    const labels = tabs.map(t => t.text().trim());
    expect(labels).toEqual(['LLM 模型', '文件解析', '安全认证', '网络与集成', '沙箱与任务', '其他']);
  });

  it('默认 active = llm(只有 llm 按钮带 active class)', () => {
    const wrapper = mount(BasicSettingsManager);
    const activeTabs = wrapper.findAll('.tab.active');
    expect(activeTabs).toHaveLength(1);
    expect(activeTabs[0].attributes('data-testid')).toBe('basic-tab-llm');
  });

  it('点击 security tab 后 active 切换到 security', async () => {
    const wrapper = mount(BasicSettingsManager);
    const securityTab = wrapper.find('[data-testid="basic-tab-security"]');
    await securityTab.trigger('click');
    expect(wrapper.vm.activeTab).toBe('security');
    const activeTabs = wrapper.findAll('.tab.active');
    expect(activeTabs).toHaveLength(1);
    expect(activeTabs[0].attributes('data-testid')).toBe('basic-tab-security');
  });

  it('渲染 6 个 panel,默认只有 llm panel 可见(v-show)', async () => {
    const wrapper = mount(BasicSettingsManager);
    await flushPromises();
    const panels = wrapper.findAll('[data-testid^="basic-panel-"]');
    expect(panels).toHaveLength(6);
    // v-show 不会从 DOM 移除,只通过 display:none 隐藏
    expect(panels[0].attributes('style') || '').not.toContain('display: none');
    for (let i = 1; i < panels.length; i++) {
      expect(panels[i].attributes('style') || '').toContain('display: none');
    }
  });

  it('警告条「本页配置修改后需重启服务生效」存在', () => {
    const wrapper = mount(BasicSettingsManager);
    const banner = wrapper.find('[data-testid="restart-banner"]');
    expect(banner.exists()).toBe(true);
    expect(banner.text()).toContain('本页配置修改后需重启服务生效');
  });

  it('主密钥卡相关 DOM 不存在(2026-09-14 渲染修复删除)', () => {
    const wrapper = mount(BasicSettingsManager);
    expect(wrapper.find('[data-testid="master-key-banner"]').exists()).toBe(false);
    expect(wrapper.find('.master-key-banner').exists()).toBe(false);
    expect(wrapper.find('.master-key-info').exists()).toBe(false);
    expect(wrapper.find('.fingerprint').exists()).toBe(false);
    expect(wrapper.text()).not.toContain('SHA256 指纹');
    expect(wrapper.text()).not.toContain('settings_secret.key');
  });

  it('可访问性:tab 按钮带 role=tab / aria-selected', () => {
    const wrapper = mount(BasicSettingsManager);
    const llmTab = wrapper.find('[data-testid="basic-tab-llm"]');
    expect(llmTab.attributes('role')).toBe('tab');
    expect(llmTab.attributes('aria-selected')).toBe('true');
    const fileParserTab = wrapper.find('[data-testid="basic-tab-file-parser"]');
    expect(fileParserTab.attributes('aria-selected')).toBe('false');
  });

  it('顶层容器带 data-testid="basic-settings-manager"', () => {
    const wrapper = mount(BasicSettingsManager);
    expect(wrapper.find('[data-testid="basic-settings-manager"]').exists()).toBe(true);
  });
});