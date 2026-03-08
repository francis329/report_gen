import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 300000, // 5 分钟，用于报告生成等长时间操作
})

// 会话管理
export const sessionsApi = {
  // 创建会话
  create(name) {
    return api.post('/sessions', { name })
  },
  // 获取会话列表
  list() {
    return api.get('/sessions')
  },
  // 获取会话详情
  get(id) {
    return api.get(`/sessions/${id}`)
  },
  // 删除会话
  delete(id) {
    return api.delete(`/sessions/${id}`)
  },
}

// 文件上传
export const uploadApi = {
  uploadFile(sessionId, file) {
    const formData = new FormData()
    formData.append('file', file)
    return api.post(`/sessions/${sessionId}/upload`, formData, {
      headers: {
        'Content-Type': 'multipart/form-data',
      },
    })
  },
}

// 聊天
export const chatApi = {
  // 普通发送（等待完整响应）
  send(sessionId, message) {
    return api.post(`/sessions/${sessionId}/chat`, { message })
  },

  // 流式发送（通过 WebSocket 接收实时回复）
  sendStreaming(sessionId, message, onChunk, onComplete, onError) {
    // 将消息作为 URL 查询参数传递，避免 WebSocket 连接后阻塞等待消息
    const wsUrl = `ws://${window.location.host}/api/sessions/${sessionId}/chat/stream?message=${encodeURIComponent(message)}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      // 连接建立后无需再发送消息，后端已通过 URL 参数接收
      console.log('WebSocket 连接已建立，消息已通过 URL 参数传递')
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'chat_chunk') {
        onChunk(msg.data.text)
      } else if (msg.type === 'chat_start') {
        console.log('AI 开始回复')
      } else if (msg.type === 'chat_complete') {
        onComplete(msg.data)
        ws.close()
      } else if (msg.type === 'error') {
        onError(msg.data.message)
        ws.close()
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error)
      if (onError) onError('连接错误')
    }

    ws.onclose = () => {
      console.log('WebSocket 连接已关闭')
    }

    return ws
  },
}

// 报告
export const reportApi = {
  // 获取报告
  get(sessionId) {
    return api.get(`/sessions/${sessionId}/report`)
  },
  // 生成智能报告（异步，通过 WebSocket 接收进度）
  generate(sessionId, userRequest) {
    return api.post(`/sessions/${sessionId}/generate-report`, {
      user_request: userRequest
    })
  },
  // 下载报告
  downloadUrl(reportId) {
    return `/api/reports/${reportId}/download`
  },
  // 查看报告链接
  viewUrl(reportId) {
    return `/api/reports/${reportId}`
  },
  // 创建 WebSocket 连接监听进度
  connectProgress(sessionId, onProgress, onError) {
    const wsUrl = `ws://${window.location.host}/ws/progress/${sessionId}`
    const ws = new WebSocket(wsUrl)

    ws.onopen = () => {
      console.log('WebSocket 连接已建立')
    }

    ws.onmessage = (event) => {
      const msg = JSON.parse(event.data)
      if (msg.type === 'progress') {
        onProgress(msg.data)
      }
    }

    ws.onerror = (error) => {
      console.error('WebSocket 错误:', error)
      if (onError) onError(error)
    }

    ws.onclose = () => {
      console.log('WebSocket 连接已关闭')
    }

    return ws
  },
  // 获取图表原始数据
  getChartData(chartId, sessionId, elementKey = null) {
    const params = { session_id: sessionId }
    if (elementKey) {
      params.element_key = elementKey
    }
    return api.get(`/charts/${chartId}/raw-data`, { params })
  },
}

// AI 配置
export const configApi = {
  setApiKey(key) {
    return api.post('/config/ai-key', null, {
      params: { api_key: key }
    })
  },
}

// 健康检查
export const healthApi = {
  check() {
    return api.get('/health')
  },
}

export default api
