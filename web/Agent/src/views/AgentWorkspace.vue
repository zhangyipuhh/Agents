<!--
  Agent Workspace（主聊天界面）
  - 路由：/
  - 业务范围：ChatArea + QueueStatusBanner + HumanApprovalBox + InputBox
            + SessionFileDrawer + FilePreviewModal + DislikeDialog
  - 数据/方法来源：通过 inject('chatWorkspace') 拿到 App.vue 提供的状态与方法
    （详见 src/App.vue 中 chatWorkspace 的组装逻辑）
  - 迁移历史：2026-08-XX 接入 vue-router 后，原 App.vue 内
    `<main v-if="currentPage === 'agent'">` + SessionFileDrawer/FilePreviewModal/
    DislikeDialog 三段抽到本组件

  2026-08-08 修复：chatWorkspace 改为 reactive(...) 包裹后，模板中所有 ws.<ref>
  由 Vue 编译器自动解包（Vue 3.4+ template compiler 对 reactive 属性访问递归 unref）。
  模板中大部分 ws.<ref> 直接写即可，无需 .value；唯独 ws.sessionId 和
  ws.isStreaming 因为它们本身是 reactive({ value: ... }) 形态（不是 ref），
  需要显式 .value 才能拿到字符串/布尔值。
  详见 .trae/documents/file-preview-modal-auto-open-bug.md。
-->
<template>
  <main class="content-area" :class="{ 'empty-layout': isEmptyState }">
    <ChatArea
      v-if="!isEmptyState"
      :messages="ws.messages"
      :is-streaming="ws.isStreaming.value"
      :session-name="ws.sessionTitle"
      @regenerate="ws.handleRegenerate"
      @like="ws.handleLike"
      @dislike="ws.handleDislike"
      @copy="ws.handleCopy"
      @open-subagent-drawer="ws.openSubAgentDrawer"
      @open-session-file-drawer="ws.handleOpenSessionFileDrawer"
    />

    <div v-if="isEmptyState" class="welcome-title">Agent, 让你的运维工作更轻松</div>

    <div class="queue-banner-wrapper">
      <QueueStatusBanner
        :queue-status="ws.queueStatus"
        :is-visible="ws.isQueueBannerVisible"
      />
    </div>

    <HumanApprovalBox
      v-if="ws.approvalMode"
      :questions="ws.approvalData.questions"
      @submit="ws.handleApprovalSubmit"
      @cancel="ws.handleApprovalCancel"
    />
    <template v-else>
      <InputBox
        :session-id="ws.sessionId.value"
        :is-streaming="ws.isStreaming.value"
        :is-stop-pending="ws.toolStopPending"
        :bound-agent-name="ws.agentName || ''"
        :bound-agent-display-name="ws.agentDisplayName || ''"
        :current-project="ws.currentProject"
        :project-locked="!ws.canEditProject"
        :allowed-agents="ws.allowedAgents"
        :is-admin="ws.isAdmin"
        :ensure-session="ws.ensureSessionForFirstOp"
        @send="ws.handleSendMessage"
        @tool-action="ws.handleToolAction"
        @new-chat="ws.newSession"
        @stop="ws.handleStopMessage"
        @agent-switched="ws.handleAgentSwitched"
        @project-lock-change="ws.setProjectLockedByUpload"
        @select-project="handleSelectProject"
        @create-project="ws.openCreateProjectDialog"
        @pick-existing="ws.openPickProjectDialog"
      />
    </template>

    <!-- 2026-07-01 新增：会话文件空间抽屉（chat 业务专用） -->
    <SessionFileDrawer
      :visible="ws.sessionFileDrawerVisible"
      :file-tree="ws.sessionFileTree"
      :loading="ws.sessionFileDrawerLoading"
      :error="ws.sessionFileDrawerError"
      :session-id="ws.sessionId.value"
      @close="ws.closeSessionFileDrawer"
      @file-click="ws.handleSessionFileClick"
    />

    <!-- 2026-07-01 新增：文件预览弹窗（chat 业务专用） -->
    <FilePreviewModal
      :is-open="ws.filePreviewOpen"
      :content="ws.filePreviewData.content"
      :file-type="ws.filePreviewData.fileType"
      :file-name="ws.filePreviewData.fileName"
      :loading="ws.filePreviewData.loading"
      :preview-mode="ws.filePreviewData.previewMode"
      :file-url="ws.filePreviewData.fileUrl"
      @close="ws.handleCloseFilePreview"
    />

    <!-- 2026-07-02 新增：AI 回复点踩反馈弹窗（chat 业务专用） -->
    <DislikeDialog
      v-model:visible="ws.dislikeDialog.visible"
      :message-id="ws.dislikeDialog.messageId"
      :session-id="ws.dislikeDialog.sessionId"
      :message-content="ws.dislikeDialog.messageContent"
      :ai-reply="ws.dislikeDialog.aiReply"
      :agent-name="ws.dislikeDialog.agentName"
      @submitted="ws.handleDislikeSubmitted"
    />
  </main>
</template>

<script setup>
import { inject, computed } from 'vue'
import ChatArea from '../components/ChatArea.vue'
import InputBox from '../components/InputBox.vue'
import HumanApprovalBox from '../components/HumanApprovalBox.vue'
import QueueStatusBanner from '../components/QueueStatusBanner.vue'
import SessionFileDrawer from '../components/SessionFileDrawer.vue'
import FilePreviewModal from '../components/FilePreviewModal.vue'
import DislikeDialog from '../components/DislikeDialog.vue'

/**
 * chatWorkspace 由 App.vue 在 setup 同步 provide。
 * 注入失败（开发态未挂载）时显式报错，避免沉默失败。
 */
const ws = inject('chatWorkspace', null)

if (!ws) {
  throw new Error(
    '[AgentWorkspace] 必须由 App.vue 通过 provide("chatWorkspace") 注入；' +
    '请确认 main.js 已接入 router 且 App.vue 模板使用 <router-view /> 渲染。'
  )
}

/**
 * 空态判定：与原 App.vue 一致（messages 数组空 → 居中欢迎语）
 */
const isEmptyState = computed(() => ws.messages.length === 0)

/**
 * select-project 事件：参数为 null 时为「解除项目」，否则为「选择项目」
 */
function handleSelectProject(project) {
  if (project === null) {
    ws.handleProjectSelectNone()
  } else {
    ws.handleProjectPick(project)
  }
}
</script>

<style scoped>
/**
 * 关键 layout 类双保险
 * 2026-08-XX 修复：这些类同时定义在全局 styles/layout.css 中，
 * 此处再写一份 scoped 副本，避免以下两种边界情况导致坍缩：
 * 1) Vite HMR 加载顺序异常，全局 layout.css 晚于 AgentWorkspace 渲染
 * 2) 浏览器缓存的旧 main.css chunk 缺少 layout.css 内容
 * 后续若 layout.css 已稳定，可移除此处副本；目前双保险零成本。
 */
.content-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background-color: var(--color-bg-secondary);
}
.content-area.empty-layout {
  justify-content: center;
  align-items: center;
}
.content-area.empty-layout > * {
  width: 100%;
  max-width: 900px;
}
.welcome-title {
  font-size: 32px;
  font-weight: var(--font-weight-bold);
  color: #1E5AA8;
  margin-bottom: 32px;
  text-align: center;
}
.queue-banner-wrapper {
  padding: 0 40px;
}
.content-area.empty-layout .queue-banner-wrapper {
  padding: 0;
}
</style>