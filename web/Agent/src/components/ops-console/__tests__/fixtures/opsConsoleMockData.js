// -*- coding:utf-8 -*-
/**
 * 运维控制台 mock 数据 fixture（仅供单元测试使用，禁止生产代码 import）
 *
 * 背景：
 * - 2026-08-05 UI 迁移阶段，本文件曾位于 ``src/data/ops-console/mockData.js``，
 *   并被 ``OpsConsoleApp.vue`` 生产代码直接 import，作为日志文件夹列表
 *   ``logFolders`` 的占位数据。
 * - 2026-08-12 改造：本目录迁入 ``__tests__/fixtures/``，生产代码不再持有
 *   前端 mock；``OpsConsoleApp.vue`` 改为 ``logFolders = ref([])``，由未来
 *   落地的后端接口 ``GET /api/admin/log-folders`` 填充。
 *
 * 数据结构（与原版保持一致，方便后续替换）：
 * - logFolders: Array<LogFolder>
 *   - name: string               文件夹名
 *   - files: Array<LogFile>      该文件夹下的日志文件
 *     - name: string             文件名
 *     - size: string             显示用大小（已格式化）
 *     - time: string             修改时间
 *
 * @returns {Array<Object>} 模拟的日志文件夹列表（4 个文件夹 / 10 个文件）
 */
export const logFolders = [
  { name: '应用日志', files: [
    { name: 'app-2026-08-03.log', size: '12.4 MB', time: '今天 17:32' },
    { name: 'app-2026-08-02.log', size: '10.1 MB', time: '昨天 23:59' },
    { name: 'app-2026-08-01.log', size: '9.8 MB',  time: '8月1日 23:59' },
  ]},
  { name: '系统日志', files: [
    { name: 'system.log', size: '45.2 MB', time: '今天 17:35' },
    { name: 'kernel.log', size: '8.6 MB',  time: '今天 16:02' },
  ]},
  { name: '安全日志', files: [
    { name: 'auth-2026-08-03.log', size: '3.2 MB', time: '今天 17:30' },
    { name: 'firewall.log',       size: '6.7 MB', time: '今天 15:44' },
  ]},
  { name: '数据库日志', files: [
    { name: 'slow-query.log',  size: '18.9 MB', time: '今天 17:28' },
    { name: 'mysql-error.log', size: '2.1 MB',  time: '今天 09:12' },
    { name: 'binlog.000847',   size: '1.1 GB',  time: '今天 17:36' },
  ]},
]
