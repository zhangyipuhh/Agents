/**
 * InputBox contenteditable 编辑器的 DOM 工具。
 * 负责读取文本、序列化服务器引用、定位光标和替换触发范围，不管理组件状态。
 */

const MENTION_PREFIX = '⟦引用服务器：'
const MENTION_SUFFIX = '⟧'

function isServerChip(node) {
  return node?.nodeType === Node.ELEMENT_NODE && node.dataset?.triggerId === 'server'
}

function appendSerializedNode(node, state) {
  if (node.nodeType === Node.TEXT_NODE) {
    state.text += node.textContent || ''
    return
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return
  if (node.tagName === 'BR') {
    state.text += '\n'
    return
  }
  if (isServerChip(node)) {
    const name = node.dataset.businessName || ''
    const serverType = node.dataset.serverType || ''
    state.text += `${MENTION_PREFIX}${name}${MENTION_SUFFIX}`
    if (name && !state.seen.has(name)) {
      state.seen.add(name)
      state.referencedServers.push({ name, server_type: serverType })
    }
    return
  }
  for (const child of node.childNodes) appendSerializedNode(child, state)
}

function serializeNode(node) {
  const state = { text: '', referencedServers: [], seen: new Set() }
  appendSerializedNode(node, state)
  return state
}

/**
 * 序列化编辑器 DOM。
 * @param {HTMLElement} root - contenteditable 编辑器根节点
 * @returns {{text: string, referencedServers: Array<{name: string, server_type: string}>}} 序列化结果
 */
export function serializeEditor(root) {
  if (!root) return { text: '', referencedServers: [] }
  const state = serializeNode(root)
  return {
    text: state.text,
    referencedServers: state.referencedServers,
  }
}

function containsNode(root, node) {
  return node === root || root?.contains?.(node)
}

function collectBefore(node, target, offset, state) {
  if (node === target) {
    if (node.nodeType === Node.TEXT_NODE) {
      state.text += (node.textContent || '').slice(0, offset)
    } else if (node.nodeType === Node.ELEMENT_NODE) {
      Array.from(node.childNodes).slice(0, offset).forEach((child) => appendSerializedNode(child, state))
    }
    return true
  }
  if (!node.childNodes) return false
  for (const child of node.childNodes) {
    if (collectBefore(child, target, offset, state)) return true
    appendSerializedNode(child, state)
  }
  return false
}

/**
 * 获取光标之前的可搜索文本。
 * @param {HTMLElement} root - contenteditable 编辑器根节点
 * @param {Selection|null} selection - 当前浏览器 Selection
 * @returns {{text: string, range: Range}|null} 光标前文本与 Range；光标不在编辑器内时返回 null
 */
export function getTextBeforeCaret(root, selection) {
  if (!root || !selection || selection.rangeCount === 0) return null
  const range = selection.getRangeAt(0)
  if (!range.collapsed || !containsNode(root, range.startContainer)) return null
  const state = { text: '', referencedServers: [], seen: new Set() }
  if (!collectBefore(root, range.startContainer, range.startOffset, state)) return null
  return { text: state.text, range: range.cloneRange() }
}

/**
 * 将当前连续文本节点中的触发范围替换为服务器 Chip。
 * @param {Object} options - 替换参数
 * @param {HTMLElement} options.root - 编辑器根节点
 * @param {Range} options.range - 从触发字符到光标的范围
 * @param {number} options.charIndex - 触发字符在文本节点中的起始偏移
 * @param {Object} options.server - 服务器对象
 * @param {Function} options.createChip - Chip 创建函数
 * @returns {HTMLElement|null} 新建 Chip；参数不合法时返回 null
 */
export function replaceTriggerRangeWithServerChip({ root, range, charIndex, server, createChip }) {
  const node = range?.startContainer
  if (!root || !range || !createChip || node?.nodeType !== Node.TEXT_NODE) return null
  if (range.endContainer !== node || !containsNode(root, node)) return null
  const text = node.textContent || ''
  const start = Math.max(0, Math.min(charIndex, text.length))
  const end = Math.max(start, Math.min(range.endOffset, text.length))
  const parent = node.parentNode
  if (!parent) return null
  const fragment = document.createDocumentFragment()
  if (start > 0) fragment.appendChild(document.createTextNode(text.slice(0, start)))
  const chip = createChip(server)
  if (!chip) return null
  fragment.appendChild(chip)
  if (end < text.length) fragment.appendChild(document.createTextNode(text.slice(end)))
  parent.replaceChild(fragment, node)
  setCaretAfter(chip)
  return chip
}

/**
 * 将光标移动到原子节点之后。
 * @param {Node} node - 需要定位光标的节点
 * @returns {void}
 */
export function setCaretAfter(node) {
  const parent = node?.parentNode
  if (!parent) return
  const offset = Array.prototype.indexOf.call(parent.childNodes, node) + 1
  const range = document.createRange()
  range.setStart(parent, offset)
  range.collapse(true)
  const selection = window.getSelection()
  selection.removeAllRanges()
  selection.addRange(range)
}
