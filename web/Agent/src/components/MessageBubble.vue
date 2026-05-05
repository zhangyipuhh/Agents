<script setup>
import { ref, computed } from 'vue'
import { formatFileSize, getFileExtension } from '../utils/api.js'

const props = defineProps({
  type: {
    type: String,
    default: 'user',
    validator: (value) => ['user', 'ai'].includes(value)
  },
  content: {
    type: [String, Object],
    default: ''
  },
  attachments: {
    type: Array,
    default: () => []
  }
})

// 思考过程展开状态
const isThinkingExpanded = ref(false)
const isFeatureExpanded = ref(false)

// 切换思考过程显示
const toggleThinking = () => {
  isThinkingExpanded.value = !isThinkingExpanded.value
}

// 切换功能详情显示
const toggleFeature = () => {
  isFeatureExpanded.value = !isFeatureExpanded.value
}

const isUserMessage = computed(() => props.type === 'user')

const hasAttachments = computed(() => props.attachments && props.attachments.length > 0)

const getFileIconColor = (filename) => {
  const ext = getFileExtension(filename)
  const colorMap = {
    pdf: '#EF4444',
    doc: '#3B82F6', docx: '#3B82F6',
    xls: '#10B981', xlsx: '#10B981', csv: '#10B981',
    jpg: '#8B5CF6', jpeg: '#8B5CF6', png: '#8B5CF6', gif: '#8B5CF6',
    txt: '#6B7280', md: '#6B7280',
    ppt: '#F59E0B', pptx: '#F59E0B',
  }
  return colorMap[ext] || '#9CA3AF'
}

// AI 消息的完整内容示例
const aiMessageContent = {
  status: '好的，我已收到您的请求，正在处理中。',
  thinkingTime: '1.55s',
  greeting: '你好！我是 MiniMax Agent，很高兴为你服务。',
  introduction: '我是一个人工智能助手，可以帮助你完成各种复杂任务，包括：',
  features: [
    {
      title: '信息检索与研究',
      description: '网络搜索、网页内容提取、多媒体分析'
    },
    {
      title: '文档处理',
      description: 'PDF、Word、Excel 文档的创建、编辑和转换'
    },
    {
      title: '数据分析',
      description: '股票信息查询、财务数据分析'
    },
    {
      title: '内容创作',
      description: '报告撰写、PPT演示文稿生成'
    },
    {
      title: '多媒体生成',
      description: '图片生成、视频制作、音频合成',
      hasExpand: true
    }
  ]
}
</script>

<template>
  <div class="message-bubble" :class="[type]">
    <!-- 用户消息 -->
    <div v-if="isUserMessage" class="user-message">
      <div class="bubble-content">
        <div v-if="hasAttachments" class="bubble-attachments">
          <div
            v-for="(att, idx) in attachments"
            :key="idx"
            class="bubble-attachment-tag"
          >
            <svg class="att-icon" viewBox="0 0 20 20" fill="currentColor" :style="{ color: getFileIconColor(att.original_name || att.filename) }">
              <path fill-rule="evenodd" d="M4 4a2 2 0 012-2h4.586A2 2 0 0112 2.586L15.414 6A2 2 0 0116 7.414V16a2 2 0 01-2 2H6a2 2 0 01-2-2V4z" clip-rule="evenodd"/>
            </svg>
            <span class="att-name">{{ att.original_name || att.filename }}</span>
            <span v-if="att.size" class="att-size">{{ formatFileSize(att.size) }}</span>
          </div>
        </div>
        <div v-if="content" class="bubble-text">{{ content }}</div>
      </div>
    </div>

    <!-- AI 消息 -->
    <div v-else class="ai-message">
      <div class="ai-content-wrapper">
        <!-- 状态提示 -->
        <p class="status-text">{{ aiMessageContent.status }}</p>

        <!-- 思考时间 -->
        <div class="thinking-section" @click="toggleThinking">
          <span class="thinking-time">已思考 {{ aiMessageContent.thinkingTime }}</span>
          <svg
            class="expand-icon"
            :class="{ expanded: isThinkingExpanded }"
            viewBox="0 0 20 20"
            fill="currentColor"
          >
            <path fill-rule="evenodd" d="M7.293 14.707a1 1 0 010-1.414L10.586 10 7.293 6.707a1 1 0 011.414-1.414l4 4a1 1 0 010 1.414l-4 4a1 1 0 01-1.414 0z" clip-rule="evenodd"/>
          </svg>
        </div>

        <!-- 思考过程详情（可展开） -->
        <div v-if="isThinkingExpanded" class="thinking-details">
          <p>正在分析您的请求...</p>
          <p>识别任务类型：综合查询</p>
          <p>调用相关技能模块...</p>
          <p>生成回复内容...</p>
        </div>

        <!-- 欢迎语 -->
        <p class="greeting-text">{{ aiMessageContent.greeting }}</p>

        <!-- 功能介绍 -->
        <p class="introduction-text">{{ aiMessageContent.introduction }}</p>

        <!-- 功能列表 -->
        <ul class="feature-list">
          <li v-for="(feature, index) in aiMessageContent.features" :key="index" class="feature-item">
            <span class="bullet">•</span>
            <div class="feature-content">
              <strong>{{ feature.title }}</strong>
              <span class="feature-desc"> - {{ feature.description }}</span>
              <button
                v-if="feature.hasExpand"
                class="expand-btn"
                @click="toggleFeature"
              >
                <svg
                  class="arrow-icon"
                  :class="{ expanded: isFeatureExpanded }"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path fill-rule="evenodd" d="M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z" clip-rule="evenodd"/>
                </svg>
              </button>
            </div>
          </li>
        </ul>

        <!-- 功能详情（可展开） -->
        <div v-if="isFeatureExpanded" class="feature-details">
          <ul class="detail-list">
            <li>AI 图像生成：使用 DALL-E、Midjourney 等模型创建高质量图像</li>
            <li>视频编辑与合成：自动剪辑、特效添加、字幕生成</li>
            <li>音频处理：语音合成、音乐生成、音频转文字</li>
            <li>多模态融合：图文结合、音视频协同创作</li>
          </ul>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.message-bubble {
  width: 100%;
  margin-bottom: 24px;
  animation: messageSlideIn 0.4s cubic-bezier(0.4, 0, 0.2, 1);
  contain: layout style paint;

  &:last-child {
    margin-bottom: 0;
  }
}

/* 消息入场动画 */
@keyframes messageSlideIn {
  from {
    opacity: 0;
    transform: translateY(16px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

/* 用户消息样式 */
.user-message {
  display: flex;
  justify-content: flex-end;
  width: 100%;
}

.bubble-content {
  max-width: 70%;
  padding: 12px 16px;
  background-color: var(--color-accent);
  color: white;
  border-radius: 12px 12px 4px 12px;
  font-size: var(--font-size-base);
  line-height: var(--line-height-normal);
  word-wrap: break-word;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.15);
  transition: var(--transition-shadow);

  &:hover {
    box-shadow: 0 4px 12px rgba(99, 102, 241, 0.25);
  }
}

.bubble-attachments {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-bottom: 8px;
}

.bubble-attachment-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 3px 8px;
  background-color: rgba(255, 255, 255, 0.2);
  border-radius: 6px;
  font-size: 12px;
}

.att-icon {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.att-name {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.att-size {
  opacity: 0.7;
  font-size: 11px;
}

.bubble-text {
  white-space: pre-wrap;
}

/* AI 消息样式 */
.ai-message {
  display: flex;
  justify-content: flex-start;
  width: 100%;
}

.ai-content-wrapper {
  max-width: 85%;
  font-size: var(--font-size-base);
  line-height: 1.6;
  color: var(--color-text-primary);
}

/* 状态提示 */
.status-text {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin-bottom: 8px;
}

/* 思考时间 */
.thinking-section {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-sm);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform);
  margin-bottom: 16px;
  position: relative;

  &::before {
    content: '';
    position: absolute;
    inset: 0;
    border-radius: inherit;
    background-color: var(--color-bg-active);
    opacity: 0;
    transition: opacity var(--transition-fast);
  }

  &:hover {
    &::before {
      opacity: 1;
    }
  }

  &:active:not(:disabled) {
    transform: scale(var(--scale-active));
  }

  /* Ensure content is above pseudo-element */
  > * {
    position: relative;
    z-index: 1;
  }
}

.thinking-time {
  font-size: 13px;
  color: var(--color-text-muted);
}

.expand-icon {
  width: 14px;
  height: 14px;
  color: var(--color-text-muted);
  transition: transform 0.2s ease;

  &.expanded {
    transform: rotate(90deg);
  }
}

/* 思考过程详情 */
.thinking-details {
  padding: 12px 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  margin-bottom: 16px;
  font-size: 13px;
  color: var(--color-text-secondary);
  line-height: 1.8;
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);

  p {
    margin-bottom: 4px;
    transition: var(--transition-opacity);

    &:last-child {
      margin-bottom: 0;
    }
  }
}

@keyframes expandIn {
  from {
    opacity: 0;
    transform: translateY(-8px);
    max-height: 0;
  }
  to {
    opacity: 1;
    transform: translateY(0);
    max-height: 500px;
  }
}

/* 欢迎语 */
.greeting-text {
  font-weight: var(--font-weight-normal);
  margin-bottom: 12px;
  color: var(--color-text-primary);
}

/* 功能介绍 */
.introduction-text {
  margin-bottom: 12px;
  color: var(--color-text-primary);
}

/* 功能列表 */
.feature-list {
  list-style: none;
  padding-left: 0;
  margin: 0;
}

.feature-item {
  display: flex;
  gap: 8px;
  margin-bottom: 10px;
  line-height: 1.6;
}

.bullet {
  color: var(--color-accent);
  font-weight: bold;
  flex-shrink: 0;
}

.feature-content {
  flex: 1;

  strong {
    font-weight: var(--font-weight-semibold);
    color: var(--color-text-primary);
  }

  .feature-desc {
    color: var(--color-text-secondary);
  }
}

/* 展开按钮 */
.expand-btn {
  display: inline-flex;
  align-items: center;
  padding: 2px 4px;
  background: transparent;
  border: none;
  cursor: pointer;
  color: var(--color-accent);
  vertical-align: middle;
  margin-left: 4px;

  &:hover {
    opacity: 0.8;
  }
}

.arrow-icon {
  width: 16px;
  height: 16px;
  transition: transform 0.2s ease;

  &.expanded {
    transform: rotate(180deg);
  }
}

/* 功能详情 */
.feature-details {
  margin-top: 12px;
  padding: 16px;
  background-color: var(--color-bg-tertiary);
  border-radius: var(--radius-md);
  border-left: 3px solid var(--color-accent);
  animation: expandIn 0.3s cubic-bezier(0.4, 0, 0.2, 1);
}

.detail-list {
  list-style: none;
  padding-left: 0;

  li {
    position: relative;
    padding-left: 20px;
    margin-bottom: 8px;
    font-size: 13px;
    color: var(--color-text-secondary);
    line-height: 1.6;
    transition: var(--transition-colors);

    &:hover {
      color: var(--color-text-primary);
    }

    &::before {
      content: '';
      position: absolute;
      left: 6px;
      top: 9px;
      width: 6px;
      height: 6px;
      border-radius: 50%;
      background-color: var(--color-accent-light);
      transition: background-color var(--transition-fast), transform var(--transition-fast);

      li:hover & {
        background-color: var(--color-accent);
        transform: scale(1.3);
      }
    }

    &:last-child {
      margin-bottom: 0;
    }
  }
}
</style>
