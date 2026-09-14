// -*- coding:utf-8 -*-
/**
 * 6 个 *SettingsPanel 渲染测试(2026-09-14 新增)
 *
 * 覆盖:
 * - 每个 panel 渲染对应数量的 GroupFormSection
 * - 每个 section label 正确
 * - 关键字段存在
 *
 * 这些 panel 都是简单的 fields 元数据声明组件,不做业务逻辑。
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

import LLMSettingsPanel from '../../basic-settings/LLMSettingsPanel.vue';
import FileParserSettingsPanel from '../../basic-settings/FileParserSettingsPanel.vue';
import SecuritySettingsPanel from '../../basic-settings/SecuritySettingsPanel.vue';
import NetworkSettingsPanel from '../../basic-settings/NetworkSettingsPanel.vue';
import SandboxTaskSettingsPanel from '../../basic-settings/SandboxTaskSettingsPanel.vue';
import MiscSettingsPanel from '../../basic-settings/MiscSettingsPanel.vue';

describe('LLMSettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 4 个 GroupFormSection section', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(4);
  });

  it('包含 主模型 / 视觉模型 / MCP Sampling / 合同 LLM 4 个标题', async () => {
    const wrapper = mount(LLMSettingsPanel);
    await flushPromises();
    const titles = wrapper.findAll('.group-card-title').map(n => n.text().replace(/\b[a-z][a-z_0-9]*\b/g, '').trim());
    expect(titles.some(t => t.includes('主模型'))).toBe(true);
    expect(titles.some(t => t.includes('视觉模型'))).toBe(true);
    expect(titles.some(t => t.includes('MCP Sampling 模型'))).toBe(true);
    expect(titles.some(t => t.includes('合同 LLM'))).toBe(true);
  });
});

describe('FileParserSettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 1 个 section + 文件解析标题', async () => {
    const wrapper = mount(FileParserSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(1);
    expect(wrapper.find('.group-card-title').text()).toContain('文件解析');
  });

  it('包含 8 个字段表单控件', async () => {
    const wrapper = mount(FileParserSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('.form-group')).toHaveLength(8);
  });
});

describe('SecuritySettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 6 个 section', async () => {
    const wrapper = mount(SecuritySettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(6);
  });

  it('包含 认证 Cookie / 默认管理员 / 闲置超时 / MFA / 注册审批 / 会话并发 6 个标题', async () => {
    const wrapper = mount(SecuritySettingsPanel);
    await flushPromises();
    const titles = wrapper.findAll('.group-card-title').map(n => n.text().replace(/\b[a-z][a-z_0-9]*\b/g, '').trim());
    expect(titles.some(t => t.includes('认证 Cookie'))).toBe(true);
    expect(titles.some(t => t.includes('默认管理员'))).toBe(true);
    expect(titles.some(t => t.includes('闲置超时'))).toBe(true);
    expect(titles.some(t => t.includes('MFA 双因素'))).toBe(true);
    expect(titles.some(t => t.includes('注册审批'))).toBe(true);
    expect(titles.some(t => t.includes('会话并发'))).toBe(true);
  });
});

describe('NetworkSettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 3 个 section', async () => {
    const wrapper = mount(NetworkSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(3);
  });

  it('包含 CORS 跨域 / Portal 子 Token / 第三方执行器 3 个标题', async () => {
    const wrapper = mount(NetworkSettingsPanel);
    await flushPromises();
    const titles = wrapper.findAll('.group-card-title').map(n => n.text().replace(/\b[a-z][a-z_0-9]*\b/g, '').trim());
    expect(titles.some(t => t.includes('CORS 跨域'))).toBe(true);
    expect(titles.some(t => t.includes('Portal 子 Token'))).toBe(true);
    expect(titles.some(t => t.includes('第三方执行器'))).toBe(true);
  });
});

describe('SandboxTaskSettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 2 个 section', async () => {
    const wrapper = mount(SandboxTaskSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(2);
  });

  it('包含 沙箱 / 任务调度 2 个标题', async () => {
    const wrapper = mount(SandboxTaskSettingsPanel);
    await flushPromises();
    const titles = wrapper.findAll('.group-card-title').map(n => n.text().replace(/\b[a-z][a-z_0-9]*\b/g, '').trim());
    expect(titles.some(t => t.includes('沙箱'))).toBe(true);
    expect(titles.some(t => t.includes('任务调度'))).toBe(true);
  });
});

describe('MiscSettingsPanel', () => {
  beforeEach(() => { vi.clearAllMocks(); });

  it('渲染 6 个 section', async () => {
    const wrapper = mount(MiscSettingsPanel);
    await flushPromises();
    expect(wrapper.findAll('[data-testid="group-form-section"]')).toHaveLength(6);
  });

  it('包含 Word 输出 / 演示模式 / MapAgent MCP 标签 / Skills / DevOps 凭据 / 系统开关 6 个标题', async () => {
    const wrapper = mount(MiscSettingsPanel);
    await flushPromises();
    const titles = wrapper.findAll('.group-card-title').map(n => n.text().replace(/\b[a-z][a-z_0-9]*\b/g, '').trim());
    expect(titles.some(t => t.includes('Word 输出'))).toBe(true);
    expect(titles.some(t => t.includes('演示模式'))).toBe(true);
    expect(titles.some(t => t.includes('MapAgent MCP 标签'))).toBe(true);
    expect(titles.some(t => t.includes('Skills'))).toBe(true);
    expect(titles.some(t => t.includes('DevOps 凭据'))).toBe(true);
    expect(titles.some(t => t.includes('系统开关'))).toBe(true);
  });
});