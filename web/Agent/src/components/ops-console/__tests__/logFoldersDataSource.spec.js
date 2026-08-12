// -*- coding:utf-8 -*-
/**
 * logFolders 数据源契约测试
 *
 * 背景：
 * - 2026-08-05~08-11 期间，OpsConsoleApp.vue 直接 import 前端 mock
 *   （``src/data/ops-console/mockData.js``），mock 数据被打进 Vite 生产
 *   bundle 污染 Docker 镜像。
 * - 2026-08-12 改造：mock 迁入 ``__tests__/fixtures/opsConsoleMockData.js``，
 *   OpsConsoleApp.vue 改为本地 ``ref([])`` 等待后端 ``/api/admin/log-folders``
 *   落地。
 *
 * 本测试覆盖：
 *   - P0：新 fixture 文件可被 import 且导出 ``logFolders`` 是非空数组
 *   - P0：OpsConsoleApp.vue 源码不再包含旧 mock 路径字符串
 *         （防止后续误回退到 ``src/data/`` 目录）
 *   - P1：OpsConsoleApp.vue 源码不再出现 ``import { logFolders }``
 *         （防止后续误把 mock fixture 引入生产 bundle）
 */
import { describe, it, expect } from 'vitest'
import { readFileSync } from 'node:fs'
import { resolve, dirname } from 'node:path'
import { fileURLToPath } from 'node:url'

import { logFolders as fixtureLogFolders } from './fixtures/opsConsoleMockData.js'

const __dirname = dirname(fileURLToPath(import.meta.url))
const opsConsoleAppPath = resolve(__dirname, '../OpsConsoleApp.vue')
const opsConsoleAppSource = readFileSync(opsConsoleAppPath, 'utf8')

describe('OpsConsole logFolders 数据源契约', () => {
  // P0：fixture 可导入 + 数据结构完整
  it('test_fixture_log_folders_importable_and_shape 新 fixture 文件可导入且 logFolders 是非空数组', () => {
    expect(Array.isArray(fixtureLogFolders)).toBe(true)
    expect(fixtureLogFolders.length).toBeGreaterThan(0)
    // 每个文件夹必须有 name + files 字段（与原 mock 保持一致）
    fixtureLogFolders.forEach((folder) => {
      expect(typeof folder.name).toBe('string')
      expect(Array.isArray(folder.files)).toBe(true)
      folder.files.forEach((file) => {
        expect(typeof file.name).toBe('string')
        expect(typeof file.size).toBe('string')
        expect(typeof file.time).toBe('string')
      })
    })
  })

  // P0：阻止生产代码再次引用 src/data 目录
  it('test_ops_console_app_no_longer_references_src_data_path OpsConsoleApp.vue 源码不再出现 src/data 路径', () => {
    expect(opsConsoleAppSource).not.toContain("'../../data/ops-console/mockData.js'")
    expect(opsConsoleAppSource).not.toContain("'../../data/ops-console/")
    expect(opsConsoleAppSource).not.toContain("'../data/ops-console/")
  })

  // P1：阻止生产代码再次 import logFolders（不论从哪）
  it('test_ops_console_app_no_import_log_folders_statement OpsConsoleApp.vue 不再出现 ``import { logFolders }`` 语句', () => {
    // 允许 ``const logFolders = ref([])``，禁止 ``import { logFolders ...`` 前缀
    expect(opsConsoleAppSource).not.toMatch(/^\s*import\s*\{[^}]*\blogFolders\b[^}]*\}/m)
  })

  // P1：OpsConsoleApp.vue 仍保留 logFolders 本地 ref，供后端接口落地时填充
  it('test_ops_console_app_declares_local_log_folders_ref OpsConsoleApp.vue 仍声明本地 logFolders ref', () => {
    expect(opsConsoleAppSource).toMatch(/const\s+logFolders\s*=\s*ref\s*\(\s*\[\s*\]\s*\)/)
  })
})
