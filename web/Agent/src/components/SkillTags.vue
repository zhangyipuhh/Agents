<script setup>
import { ref } from 'vue'

// 技能标签数据
const tags = [
  { icon: '\u{1F4C4}', label: 'pdf&docx文档专家' },
  { icon: '\u{1F50D}', label: '深度调研' },
  { icon: '\u{1F4DD}', label: '报告撰写' },
  { icon: '\u{1F4CA}', label: 'PPT' },
  { icon: '\u{1F4BB}', label: 'Computer Use Expert' }
]

// 当前选中的标签
const selectedTag = ref(null)

// 处理标签点击
const handleTagClick = (index) => {
  selectedTag.value = selectedTag.value === index ? null : index
}

// 定义事件
const emit = defineEmits(['tag-select'])
</script>

<template>
  <div class="skill-tags-container">
    <div class="skill-tags-wrapper">
      <button
        v-for="(tag, index) in tags"
        :key="index"
        class="skill-tag"
        :class="{ active: selectedTag === index }"
        @click="handleTagClick(index); emit('tag-select', tag, index)"
      >
        <span class="tag-icon">{{ tag.icon }}</span>
        <span class="tag-label">{{ tag.label }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.skill-tags-container {
  width: 100%;
  padding: 16px 24px 0;
  background-color: var(--color-bg-secondary);
}

.skill-tags-wrapper {
  display: flex;
  gap: 10px;
  overflow-x: auto;
  padding-bottom: 12px;
  /* 隐藏滚动条 */
  scrollbar-width: none; /* Firefox */
  -ms-overflow-style: none; /* IE & Edge */

  &::-webkit-scrollbar {
    display: none; /* Chrome, Safari, Opera */
  }
}

.skill-tag {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background-color: var(--color-bg-primary);
  border: 1.5px solid var(--color-border);
  border-radius: var(--radius-full);
  white-space: nowrap;
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  cursor: pointer;
  transition: var(--transition-colors), var(--transition-transform), var(--transition-shadow), border-color 0.2s ease;
  flex-shrink: 0;
  position: relative;
  will-change: transform;

  &::after {
    content: '';
    position: absolute;
    inset: -2px;
    border-radius: inherit;
    background: linear-gradient(135deg, transparent 0%, rgba(99, 102, 241, 0.05) 100%);
    opacity: 0;
    transition: opacity var(--transition-fast);
    z-index: -1;
  }

  &:hover {
    background-color: var(--color-bg-hover);
    border-color: var(--color-accent-light);
    color: var(--color-accent);

    &::after {
      opacity: 1;
    }
  }

  &:active:not(:disabled) {
    transform: scale(var(--scale-active));
  }

  &.active {
    background-color: var(--color-accent-light);
    border-color: var(--color-accent);
    color: var(--color-accent);
    box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);

    &::after {
      opacity: 0;
    }
  }

  /* Ensure content is above pseudo-element */
  > * {
    position: relative;
    z-index: 1;
  }
}

.tag-icon {
  font-size: 16px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.tag-label {
  line-height: 1.2;
}
</style>
