<template>
  <div class="app-container">
    <!-- 侧边栏 - 会话列表 -->
    <div class="sidebar">
      <div class="sidebar-header">
        <h2>📊 智能报告生成Agent</h2>
        <el-button type="primary" @click="createSession" :icon="Plus">
          新建会话
        </el-button>
      </div>
      <div class="session-list">
        <div
          v-for="session in sessions"
          :key="session.id"
          class="session-item"
          :class="{ active: currentSessionId === session.id }"
          @click="selectSession(session.id)"
        >
          <span class="session-name">{{ session.name }}</span>
          <el-button
            class="delete-btn"
            type="danger"
            link
            :icon="Delete"
            @click.stop="deleteSession(session.id)"
          />
        </div>
        <div v-if="sessions.length === 0" class="empty-tip">
          暂无会话，点击"新建会话"开始
        </div>
      </div>
    </div>

    <!-- 主内容区 -->
    <div class="main-content">
      <div v-if="!currentSessionId" class="welcome-screen">
        <el-empty description="请选择或创建一个会话开始使用" />
      </div>

      <template v-else>
        <!-- 聊天区域 - 支持拖拽上传 -->
        <div
          class="chat-container"
          :class="{ 'drag-over': isDragOver }"
          @dragover.prevent="handleDragOver"
          @dragleave.prevent="handleDragLeave"
          @drop.prevent="handleDrop"
        >
          <!-- 拖拽提示 -->
          <div v-if="isDragOver" class="drag-overlay">
            <el-icon class="drag-icon"><UploadFilled /></el-icon>
            <div class="drag-text">释放以上传文件</div>
          </div>

          <div class="chat-messages" ref="messagesContainer">
            <div
              v-for="(msg, index) in messages"
              :key="index"
              class="message"
              :class="[msg.role, { loading: msg.isLoading, error: msg.isError }]"
            >
              <div class="message-avatar">
                <el-icon v-if="msg.role === 'user'"><User /></el-icon>
                <el-icon v-else><Cpu /></el-icon>
              </div>
              <div class="message-content">
                <div class="message-time">{{ formatTime(msg.timestamp) }}</div>
                <div class="message-text" v-html="renderMessage(msg.content)"></div>
                <!-- 报告操作按钮 -->
                <div v-if="msg.role === 'assistant' && msg.reportUrl" class="report-actions">
                  <el-button type="primary" size="small" @click="openReport(msg.reportUrl)">
                    📊 查看报告
                  </el-button>
                  <el-button type="success" size="small" @click="downloadReport(msg.reportUrl)">
                    📥 下载报告
                  </el-button>
                </div>
              </div>
            </div>
          </div>

          <!-- 输入区域 -->
          <div class="chat-input">
            <div class="input-wrapper">
              <!-- 上传按钮 -->
              <el-upload
                :action="uploadUrl"
                :show-file-list="false"
                :before-upload="beforeUpload"
                :on-success="handleUploadSuccess"
                :on-error="handleUploadError"
              >
                <el-button :icon="Upload">上传文件</el-button>
              </el-upload>
              <!-- 输入框 -->
              <el-input
                v-model="inputMessage"
                placeholder="输入分析需求，如：分析销售数据趋势..."
                @keydown.enter="sendMessage"
                :disabled="isSending"
              >
                <template #append>
                  <el-button @click="sendMessage" :loading="isSending">
                    发送
                  </el-button>
                </template>
              </el-input>
            </div>
          </div>
        </div>

        <!-- 右侧面板 -->
        <div class="side-panel">
          <!-- 已上传文件列表 -->
          <el-card v-if="currentFiles.length > 0" class="file-list-card">
            <template #header>
              <span>📁 已上传文件</span>
            </template>
            <div v-for="file in currentFiles" :key="file.id" class="file-item">
              <el-icon><Document /></el-icon>
              <span class="file-name">{{ file.filename }}</span>
              <span class="file-sheets">{{ file.sheets.length }} 个表</span>
            </div>
          </el-card>

          <!-- 数据结构预览 -->
          <el-card v-if="sheetsInfo.length > 0" class="data-card">
            <template #header>
              <span>📊 数据结构</span>
            </template>
            <div class="sheets-info">
              <div v-for="sheet in sheetsInfo" :key="sheet.sheet_name" class="sheet-item">
                <div class="sheet-header">
                  <strong>{{ sheet.file_name }}</strong>
                  <span class="sheet-name">{{ sheet.sheet_name }}</span>
                </div>
                <div class="sheet-stats">
                  {{ sheet.row_count }} 行 × {{ sheet.columns.length }} 列
                </div>
                <div class="sheet-columns">
                  <el-tag
                    v-for="col in sheet.columns.slice(0, 5)"
                    :key="col"
                    size="small"
                  >
                    {{ col }}
                  </el-tag>
                  <el-tag v-if="sheet.columns.length > 5" size="small">
                    +{{ sheet.columns.length - 5 }}
                  </el-tag>
                </div>
              </div>
            </div>
          </el-card>
        </div>
      </template>
    </div>

    <!-- API 密钥设置对话框 -->
    <el-dialog
      v-model="showApiKeyDialog"
      title="设置 AI API 密钥"
      width="400px"
    >
      <el-input
        v-model="apiKey"
        type="password"
        placeholder="请输入 DashScope API 密钥"
        show-password
      />
      <template #footer>
        <el-button @click="showApiKeyDialog = false">取消</el-button>
        <el-button type="primary" @click="saveApiKey">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  Plus, Delete, User, Cpu, Document, UploadFilled, Upload
} from '@element-plus/icons-vue'
import {
  sessionsApi,
  uploadApi,
  chatApi,
  reportApi,
  configApi
} from './api/client'

// 状态
const sessions = ref([])
const currentSessionId = ref(null)
const messages = ref([])
const inputMessage = ref('')
const isSending = ref(false)
const currentFiles = ref([])
const sheetsInfo = ref([])
const reportInfo = ref(null)
const isGeneratingReport = ref(false)
const showApiKeyDialog = ref(false)
const apiKey = ref('')
const messagesContainer = ref(null)
const isDragOver = ref(false)

// 计算属性
const uploadUrl = computed(() => {
  if (!currentSessionId.value) return ''
  return `/api/sessions/${currentSessionId.value}/upload`
})

// 方法
const loadSessions = async () => {
  try {
    const res = await sessionsApi.list()
    sessions.value = res.data.sessions
  } catch (error) {
    console.error('加载会话失败:', error)
  }
}

const createSession = async () => {
  try {
    const res = await sessionsApi.create('新会话')
    sessions.value.push(res.data.session)
    selectSession(res.data.session.id)
    ElMessage.success('会话创建成功')
  } catch (error) {
    ElMessage.error('创建会话失败')
  }
}

const selectSession = async (sessionId) => {
  currentSessionId.value = sessionId
  reportInfo.value = null

  try {
    const res = await sessionsApi.get(sessionId)
    const session = res.data.session
    messages.value = session.messages || []
    currentFiles.value = session.files || []

    // 加载 sheet 信息
    sheetsInfo.value = []
    currentFiles.value.forEach(file => {
      file.sheets.forEach(sheet => {
        sheetsInfo.value.push({
          file_name: file.filename,
          sheet_name: sheet.name,
          row_count: sheet.row_count,
          columns: sheet.columns
        })
      })
    })

    await nextTick()
    scrollToBottom()
  } catch (error) {
    console.error('加载会话详情失败:', error)
  }
}

const deleteSession = async (sessionId) => {
  try {
    await ElMessageBox.confirm('确定要删除这个会话吗？', '确认删除', {
      type: 'warning'
    })

    await sessionsApi.delete(sessionId)

    // 从列表中移除会话
    sessions.value = sessions.value.filter(s => s.id !== sessionId)

    // 如果删除的是当前会话，重置状态
    if (currentSessionId.value === sessionId) {
      currentSessionId.value = null
      messages.value = []
      currentFiles.value = []
      sheetsInfo.value = []
    }

    // 重新加载会话列表，确保数据同步
    await loadSessions()

    ElMessage.success('会话已删除')
  } catch (error) {
    if (error !== 'cancel') {
      console.error('删除会话失败:', error)
      // 显示错误提示
      const errorMsg = error.response?.data?.detail || error.message || '未知错误'
      ElMessage.error('删除会话失败：' + errorMsg)
    }
  }
}

const sendMessage = async () => {
  const message = inputMessage.value.trim()
  if (!message || !currentSessionId.value) return

  inputMessage.value = ''
  isSending.value = true

  // 1. 立即添加用户消息
  messages.value.push({
    role: 'user',
    content: message,
    timestamp: new Date().toISOString()
  })

  // 2. 添加 AI 正在处理的占位消息
  const loadingMessageIndex = messages.value.length
  messages.value.push({
    role: 'assistant',
    content: 'AI 正在分析数据，请耐心等待...',
    timestamp: new Date().toISOString(),
    isLoading: true
  })

  await nextTick()
  scrollToBottom()

  try {
    const res = await chatApi.send(currentSessionId.value, message)

    // 3. AI 处理完成，更新占位消息为实际回复
    let aiContent = res.data.response

    // 构建 AI 回复消息对象
    const aiMessage = {
      role: 'assistant',
      content: aiContent,
      timestamp: new Date().toISOString(),
      reportUrl: res.data.report_url,
      isLoading: false
    }

    // 如果有报告链接，添加提示文本
    if (res.data.report_url) {
      aiMessage.content += `\n\n---\n📊 分析报告已生成，点击下方按钮查看或下载报告`
    }

    // 替换占位消息
    messages.value[loadingMessageIndex] = aiMessage

  } catch (error) {
    // 出错时更新占位消息为错误提示
    messages.value[loadingMessageIndex] = {
      role: 'assistant',
      content: `抱歉，处理您的请求时出现错误：${error.response?.data?.detail || error.message}`,
      timestamp: new Date().toISOString(),
      isLoading: false,
      isError: true
    }
  } finally {
    isSending.value = false
    await nextTick()
    scrollToBottom()
  }
}

const beforeUpload = (file) => {
  const maxSize = 10 * 1024 * 1024
  if (file.size > maxSize) {
    ElMessage.error('文件大小超过 10MB 限制')
    return false
  }
  const validTypes = ['.csv', '.xlsx', '.xls']
  const fileName = file.name.toLowerCase()
  const isValid = validTypes.some(type => fileName.endsWith(type))
  if (!isValid) {
    ElMessage.error('只支持 CSV/Excel 文件')
    return false
  }
  return true
}

const handleUploadSuccess = (response) => {
  ElMessage.success(response.message)
  // 刷新文件列表
  currentFiles.value.push(response.file_info)
  response.file_info.sheets.forEach(sheet => {
    sheetsInfo.value.push({
      file_name: response.file_info.filename,
      sheet_name: sheet.name,
      row_count: sheet.row_count,
      columns: sheet.columns
    })
  })
}

const handleUploadError = (error) => {
  const detail = error.response?.data?.detail || '上传失败'
  ElMessage.error(detail)
}

// 拖拽上传处理
const handleDragOver = () => {
  isDragOver.value = true
}

const handleDragLeave = () => {
  isDragOver.value = false
}

const handleDrop = (event) => {
  isDragOver.value = false
  const files = event.dataTransfer.files
  if (files.length > 0) {
    const file = files[0]
    // 验证文件
    if (!beforeUpload(file)) {
      return
    }
    // 上传文件
    uploadFile(file)
  }
}

const uploadFile = async (file) => {
  try {
    const formData = new FormData()
    formData.append('file', file)
    const res = await uploadApi.uploadFile(currentSessionId.value, formData)
    handleUploadSuccess(res.data)
  } catch (error) {
    handleUploadError(error)
  }
}

const viewReport = () => {
  if (reportInfo.value) {
    window.open(reportInfo.value.download_url.replace('/download', ''), '_blank')
  }
}

const scrollToBottom = () => {
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight
  }
}

const formatTime = (timestamp) => {
  if (!timestamp) return ''
  const date = new Date(timestamp)
  return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' })
}

const saveApiKey = async () => {
  try {
    await configApi.setApiKey(apiKey.value)
    ElMessage.success('API 密钥已保存')
    showApiKeyDialog.value = false
  } catch (error) {
    ElMessage.error('保存 API 密钥失败')
  }
}

// 渲染消息内容（支持 Markdown 格式）
const renderMessage = (content) => {
  if (!content) return ''

  // 先转义 HTML 特殊字符，防止 XSS
  let html = content
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')

  // 代码块（``` ... ```）- 在换行前处理
  html = html.replace(/```(\w*)\n([\s\S]*?)```/g, (match, lang, code) => {
    return `<pre class="code-block"><code>${code.trim()}</code></pre>`
  })

  // 标题（## 标题）
  html = html.replace(/^### (.*$)/gim, '<h3>$1</h3>')
  html = html.replace(/^## (.*$)/gim, '<h2>$1</h2>')
  html = html.replace(/^# (.*$)/gim, '<h1>$1</h1>')

  // 加粗（**text**）
  html = html.replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')

  // 斜体（*text*）
  html = html.replace(/\*(.*?)\*/g, '<em>$1</em>')

  // 无序列表（- item）
  html = html.replace(/^\s*-\s+(.*$)/gim, '<li>$1</li>')
  // 包裹列表项为 ul
  html = html.replace(/(<li>.*<\/li>\n?)+/g, (match) => {
    return `<ul class="message-list">${match}</ul>`
  })

  // 有序列表（1. item）
  html = html.replace(/^\s*\d+\.\s+(.*$)/gim, '<li class="ordered">$1</li>')

  // 链接（[text](url)）
  html = html.replace(/\[(.*?)\]\((.*?)\)/g, '<a href="$2" target="_blank" class="message-link">$1</a>')

  // 换行：合并连续空行为单个换行
  html = html.replace(/\n{3,}/g, '\n')
  html = html.replace(/\n/g, '<br>')

  // 清理空的列表包裹
  html = html.replace(/<br><ul/g, '<ul')
  html = html.replace(/<\/ul><br>/g, '</ul>')

  return html
}

// 打开报告查看页面
const openReport = (reportUrl) => {
  if (reportUrl) {
    window.open(reportUrl, '_blank')
  }
}

// 下载报告
const downloadReport = (reportUrl) => {
  if (reportUrl) {
    window.open(`${reportUrl}/download`, '_blank')
  }
}

// 生命周期
onMounted(() => {
  loadSessions()
})
</script>

<style scoped>
.app-container {
  display: flex;
  height: 100vh;
  background: #f5f7fa;
}

.sidebar {
  width: 260px;
  background: white;
  border-right: 1px solid #e4e7ed;
  display: flex;
  flex-direction: column;
}

.sidebar-header {
  padding: 20px;
  border-bottom: 1px solid #e4e7ed;
}

.sidebar-header h2 {
  margin: 0 0 15px 0;
  font-size: 1.2rem;
  color: #333;
}

.sidebar-header .el-button {
  width: 100%;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  padding: 10px;
}

.session-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 15px;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: 5px;
}

.session-item:hover {
  background: #f5f7fa;
}

.session-item.active {
  background: #ecf5ff;
  color: #409eff;
}

.session-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.delete-btn {
  opacity: 0;
  transition: opacity 0.2s;
}

.session-item:hover .delete-btn {
  opacity: 1;
}

.empty-tip {
  text-align: center;
  color: #999;
  padding: 20px;
}

.main-content {
  flex: 1;
  display: flex;
  overflow: hidden;
}

.welcome-screen {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
}

.chat-container {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: white;
  margin: 20px;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.1);
  overflow: hidden;
  position: relative;
}

.chat-container.drag-over {
  border: 2px dashed #409eff;
  background: #f0f9ff;
}

.drag-overlay {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.95);
  z-index: 10;
}

.drag-icon {
  font-size: 64px;
  color: #409eff;
  margin-bottom: 16px;
}

.drag-text {
  font-size: 18px;
  color: #333;
  font-weight: 500;
}

.chat-messages {
  flex: 1;
  overflow-y: auto;
  padding: 20px;
}

.message {
  display: flex;
  margin-bottom: 20px;
}

.message.user {
  flex-direction: row-reverse;
}

.message-avatar {
  width: 40px;
  height: 40px;
  border-radius: 50%;
  background: #f0f0f0;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 1.2rem;
  flex-shrink: 0;
}

.message.user .message-avatar {
  background: #e3f2fd;
  color: #1976d2;
}

.message:not(.user) .message-avatar {
  background: #f3e5f5;
  color: #7b1fa2;
}

.message-content {
  max-width: 70%;
  margin: 0 10px;
}

.message.user .message-content {
  display: flex;
  flex-direction: column;
  align-items: flex-end;
}

.message-time {
  font-size: 0.75rem;
  color: #999;
  margin-bottom: 5px;
}

.message-text {
  background: #f0f2f5;
  padding: 8px 12px;
  border-radius: 12px;
  line-height: 1.2;
  white-space: normal;
  word-break: break-word;
  font-size: 14px;
}

.message-text p {
  margin: 0;
  line-height: 1.2;
}

.message-text h1,
.message-text h2,
.message-text h3 {
  margin: 4px 0 2px 0;
  font-weight: 600;
  line-height: 1.2;
}

.message-text h1 { font-size: 1.2rem; }
.message-text h2 { font-size: 1.05rem; }
.message-text h3 { font-size: 0.9rem; }

.message-text ul {
  margin: 2px 0;
  padding-left: 18px;
}

.message-text li {
  margin: 1px 0;
  line-height: 1.2;
}

.message-text .code-block {
  background: #2d2d2d;
  color: #f8f8f2;
  padding: 10px;
  border-radius: 6px;
  overflow-x: auto;
  margin: 6px 0;
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 0.8rem;
}

.message-text .message-link {
  color: #409eff;
  text-decoration: none;
}

.message-text .message-link:hover {
  text-decoration: underline;
}

.message.user .message-text {
  background: #409eff;
  color: white;
}

/* 加载中消息样式 */
.message.loading .message-avatar {
  animation: pulse 1.5s ease-in-out infinite;
}

.message.loading .message-text {
  background: #f8f9fa;
  color: #666;
  font-style: italic;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.5; }
}

/* 错误消息样式 */
.message.error .message-text {
  background: #fff3f3;
  color: #dc3545;
  border: 1px solid #ffc9c9;
}

.report-actions {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #e4e7ed;
  display: flex;
  gap: 8px;
}

.chat-input {
  border-top: 1px solid #e4e7ed;
  padding: 20px;
  background: white;
}

.input-wrapper {
  display: flex;
  gap: 10px;
  align-items: center;
}

.input-wrapper .el-upload {
  flex-shrink: 0;
}

.side-panel {
  width: 320px;
  padding: 20px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.file-list-card,
.data-card {
  flex-shrink: 0;
}

.file-list {
  margin-top: 15px;
}

.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px;
  background: #f8f9fa;
  border-radius: 6px;
  margin-bottom: 8px;
  font-size: 0.9rem;
}

.file-name {
  flex: 1;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.file-sheets {
  color: #666;
  font-size: 0.8rem;
}

.sheets-info {
  display: flex;
  flex-direction: column;
  gap: 15px;
}

.sheet-item {
  padding: 10px;
  background: #f8f9fa;
  border-radius: 6px;
}

.sheet-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.sheet-name {
  font-size: 0.85rem;
  color: #666;
}

.sheet-stats {
  font-size: 0.85rem;
  color: #999;
  margin-bottom: 8px;
}

.sheet-columns {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}
</style>
