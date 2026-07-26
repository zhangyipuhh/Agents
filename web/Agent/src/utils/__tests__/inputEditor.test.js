/**
 * InputBox 编辑器 DOM 工具测试。
 * 覆盖服务器 Chip 的序列化、光标前文本读取和触发范围替换。
 */
import { describe, it, expect } from 'vitest'
import {
  serializeEditor,
  getTextBeforeCaret,
  replaceTriggerRangeWithServerChip,
} from '../inputEditor.js'

function createServerChip(server) {
  const chip = document.createElement('span')
  chip.dataset.triggerId = 'server'
  chip.dataset.businessName = server.business_name
  chip.dataset.serverType = server.server_type
  return chip
}

describe('inputEditor DOM 工具', () => {
  it('test_serialize_editor_preserves_inline_mentions_and_deduplicates_servers 按 DOM 顺序序列化并去重服务器', () => {
    const root = document.createElement('div')
    root.append('检查 ')
    root.append(createServerChip({ business_name: 'prod-api', server_type: 'linux' }))
    root.append(document.createElement('br'))
    root.append('然后继续 ')
    root.append(createServerChip({ business_name: 'prod-api', server_type: 'linux' }))

    expect(serializeEditor(root)).toEqual({
      text: '检查 ⟦引用服务器：prod-api⟧\n然后继续 ⟦引用服务器：prod-api⟧',
      referencedServers: [{ name: 'prod-api', server_type: 'linux' }],
    })
  })

  it('test_get_text_before_caret_returns_text_and_range 将 Chip 作为可搜索占位节点', () => {
    const root = document.createElement('div')
    root.append('请检查 ')
    root.append(createServerChip({ business_name: 'prod-api', server_type: 'linux' }))
    const textNode = document.createTextNode(' 后续')
    root.append(textNode)
    const range = document.createRange()
    range.setStart(textNode, 2)
    range.collapse(true)
    const selection = window.getSelection()
    selection.removeAllRanges()
    selection.addRange(range)

    const result = getTextBeforeCaret(root, selection)

    expect(result.text).toBe('请检查 ⟦引用服务器：prod-api⟧ 后')
    expect(result.range.startContainer).toBe(textNode)
    expect(result.range.startOffset).toBe(2)
  })

  it('test_replace_trigger_range_with_server_chip_replaces_hash_query_and_places_caret_after_chip 原子替换触发串', () => {
    const root = document.createElement('div')
    const textNode = document.createTextNode('请检查 #pro 后续')
    root.append(textNode)
    const range = document.createRange()
    range.setStart(textNode, 4)
    range.setEnd(textNode, 8)

    const chip = replaceTriggerRangeWithServerChip({
      root,
      range,
      charIndex: 4,
      server: { business_name: 'prod-api', server_type: 'linux' },
      createChip: createServerChip,
    })

    expect(chip.dataset.businessName).toBe('prod-api')
    expect(root.childNodes[0].textContent).toBe('请检查 ')
    expect(root.childNodes[1]).toBe(chip)
    expect(root.childNodes[2].textContent).toBe(' 后续')
    const selection = window.getSelection()
    expect(selection.anchorNode).toBe(root)
    expect(selection.anchorOffset).toBe(2)
  })
})
