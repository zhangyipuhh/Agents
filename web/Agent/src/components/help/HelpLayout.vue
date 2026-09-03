<!--
  帮助页三栏 layout 容器
  - 顶部：HelpTopBar 品牌栏
  - 左侧：HelpSidebar 目录导航
  - 中部：渲染当前 markdown 内容
  - 右侧：HelpToc anchor 索引

  数据流：
   1. onMounted → loadIndex() 拉取目录树
   2. 默认选中第一个文档（overview）
   3. 用户点击左侧导航 → loadDoc() 切换内容
   4. markdown → safeMarkdown 渲染（marked + DOMPurify）
   5. headings 来自 extractHeadings(md)
-->
<template>
  <div class="help-root">
    <HelpTopBar :show-close="showClose" :close-mode="closeMode" @close="handleClose" />
    <div class="help-body">
      <HelpSidebar
        v-if="navTree.length > 0"
        :tree="navTree"
        :active-path="activePath"
        @select="handleSelect"
      />
      <main class="help-content" ref="contentRef">
        <div v-if="loading" class="help-state help-state--loading">
          <span class="help-spinner" aria-hidden="true"></span>
          <span>正在加载文档...</span>
        </div>
        <div v-else-if="error" class="help-state help-state--error">
          <div class="help-state-title">加载失败</div>
          <div class="help-state-desc">{{ error }}</div>
          <button type="button" class="help-retry-btn" @click="reloadCurrent">重试</button>
        </div>
        <div v-else-if="notFound" class="help-state help-state--notfound">
          <div class="help-state-title">文档不存在</div>
          <div class="help-state-desc">路径 <code>{{ activePath }}</code> 未在帮助目录中找到</div>
        </div>
        <article v-else class="help-article" v-html="renderedContent" />
      </main>
      <HelpToc
        v-if="headings.length > 0 && !loading && !error"
        :headings="headings"
        :active-id="activeAnchorId"
        @jump="handleAnchorJump"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch, nextTick, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import HelpTopBar from './HelpTopBar.vue'
import HelpSidebar from './HelpSidebar.vue'
import HelpToc from './HelpToc.vue'
import { loadIndex, loadDoc, extractHeadings } from '../../utils/help-loader.js'
import { safeMarkdown } from '../../utils/sanitize-marked.js'

const router = useRouter()

const navTree = ref([])
const activePath = ref('')
const rawMarkdown = ref('')
const loading = ref(false)
const error = ref('')
const notFound = ref(false)
const activeAnchorId = ref('')
const contentRef = ref(null)

/**
 * 是否可通过 window.close() 真正关闭 Tab
 * 仅当 Tab 是脚本打开的（window.opener 存在）时返回 true
 * @returns {boolean}
 */
function canWindowClose() {
  if (typeof window === 'undefined') return false
  try {
    return Boolean(window.opener)
  } catch (_) {
    return false
  }
}

/**
 * 关闭模式：
 * - 'close'：脚本 window.close() 真正关闭（仅对被脚本打开的 Tab 生效）
 * - 'back'：window.close() 无效 → 降级为 router.push('/') 返回主会话
 * 2026-09-03 修复：之前依赖 window.opener 判定"是否显示关闭按钮"，
 * 但 Sidebar.vue 使用 `noopener,noreferrer` 打开新 Tab 后 window.opener 为 null，
 * 导致关闭按钮不显示，用户反馈"帮助页面打开后关不上"。
 * 现策略：始终显示关闭按钮；能否真的关闭由 canWindowClose 决定；
 * 不能关闭时按钮文案变为"返回主页"并跳回主 Tab。
 */
const closeMode = computed(() => (canWindowClose() ? 'close' : 'back'))

/** 给模板使用的别名 —— 始终为 true，永远显示关闭按钮 */
const showClose = computed(() => true)

/** 渲染后的 HTML（marked + DOMPurify） */
const renderedContent = computed(() => {
  if (!rawMarkdown.value) return ''
  return safeMarkdown(rawMarkdown.value)
})

/** 当前文档的 headings */
const headings = computed(() => extractHeadings(rawMarkdown.value))

/**
 * 加载目录树（仅一次）
 * @returns {Promise<void>}
 */
async function initIndex() {
  try {
    const data = await loadIndex()
    navTree.value = data.tree || []
    // 默认选中第一个有 path 的节点
    const first = findFirstLeaf(navTree.value)
    if (first) {
      // 先用 flag 抑制 watch 重复触发，再主动调用 loadDocContent（避免 initIndex 与 watch 双触发）
      skipNextWatch.value = true
      activePath.value = first
      await loadDocContent(first)
    }
  } catch (err) {
    error.value = err?.message || '加载目录失败'
  }
}

/** watch(activePath) 抑制 flag（用于 initIndex 主动加载避免重复请求） */
const skipNextWatch = ref(false)

/**
 * 递归查找目录树第一个叶子节点 path
 * @param {Array} nodes
 * @returns {string|null}
 */
function findFirstLeaf(nodes) {
  if (!Array.isArray(nodes)) return null
  for (const n of nodes) {
    if (n.path) return n.path
    if (Array.isArray(n.children)) {
      const r = findFirstLeaf(n.children)
      if (r) return r
    }
  }
  return null
}

/**
 * 加载指定文档
 * @param {string} path
 * @returns {Promise<void>}
 */
async function loadDocContent(path) {
  loading.value = true
  error.value = ''
  notFound.value = false
  rawMarkdown.value = ''
  try {
    const md = await loadDoc(path)
    rawMarkdown.value = md
    // 等待 DOM 更新后处理 anchor
    await nextTick()
    handleInitialHash()
  } catch (err) {
    const msg = err?.message || '加载失败'
    if (msg.includes('HTTP 404')) {
      notFound.value = true
    } else {
      error.value = msg
    }
  } finally {
    loading.value = false
  }
}

/**
 * 重新加载当前文档
 * @returns {Promise<void>}
 */
async function reloadCurrent() {
  if (activePath.value) {
    await loadDocContent(activePath.value)
  }
}

/**
 * 处理左侧导航选中
 * @param {string} path
 * @returns {void}
 */
function handleSelect(path) {
  if (path === activePath.value) return
  activePath.value = path
  // 切换内容时清掉 hash
  if (typeof window !== 'undefined' && window.location.hash) {
    history.replaceState(null, '', window.location.pathname + window.location.search)
  }
}

/**
 * 处理 anchor 跳转
 * @param {string} id
 * @returns {void}
 */
function handleAnchorJump(id) {
  if (typeof window === 'undefined') return
  const el = document.getElementById(id)
  if (!el) return
  el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  history.replaceState(null, '', '#' + id)
  activeAnchorId.value = id
}

/**
 * 处理初次加载时的 hash 跳转
 * @returns {void}
 */
function handleInitialHash() {
  if (typeof window === 'undefined') return
  const hash = window.location.hash
  if (!hash || hash.length < 2) return
  const id = hash.slice(1)
  // 等待下一帧让 DOM 完成渲染
  nextTick(() => {
    const el = document.getElementById(id)
    if (el) {
      el.scrollIntoView({ behavior: 'auto', block: 'start' })
      activeAnchorId.value = id
    }
  })
}

/**
 * 处理关闭按钮（关闭当前 Tab 或返回主页面）
 * 优先级：
 *   - 'close' 模式（被脚本 window.open 打开）：window.close() 真正关闭 Tab
 *   - 'back' 模式（直接访问 /help）：router.push('/') 跳回主会话
 * @returns {void}
 */
function handleClose() {
  if (typeof window === 'undefined') return
  if (closeMode.value === 'close') {
    try {
      window.close()
      return
    } catch (_) {
      // close 失败时降级到返回主页
    }
  }
  // back 模式：路由跳回主页（兜底）
  try {
    router.push('/')
  } catch (_) {
    // 兜底：hash 路由降级
    window.location.href = '/'
  }
}

/** IntersectionObserver 实例，用于自动高亮当前 heading */
let observer = null

/**
 * 设置 IntersectionObserver 监听 scroll，自动高亮当前 heading
 * @returns {void}
 */
function setupObserver() {
  if (typeof window === 'undefined' || typeof IntersectionObserver === 'undefined') return
  observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          activeAnchorId.value = entry.target.id
        }
      }
    },
    { rootMargin: '0px 0px -80% 0px', threshold: 0 }
  )
}

/**
 * 应用 observer 到当前 headings 对应的 DOM 节点
 * @returns {void}
 */
function applyObserver() {
  if (!observer) return
  observer.disconnect()
  if (!contentRef.value) return
  for (const h of headings.value) {
    const el = contentRef.value.querySelector(`#${CSS.escape(h.id)}`)
    if (el) observer.observe(el)
  }
}

watch(headings, () => {
  nextTick(() => applyObserver())
})

watch(activePath, (val) => {
  // initIndex 主动加载时跳过（防止双触发重复请求）
  if (skipNextWatch.value) {
    skipNextWatch.value = false
    return
  }
  if (val) loadDocContent(val)
})

onMounted(async () => {
  await initIndex()
  setupObserver()
  await nextTick()
  applyObserver()
})

onBeforeUnmount(() => {
  if (observer) {
    observer.disconnect()
    observer = null
  }
})
</script>