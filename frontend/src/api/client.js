import axios from 'axios'

const api = axios.create({
  baseURL: '/api',
  timeout: 60000,
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
  send(sessionId, message) {
    return api.post(`/sessions/${sessionId}/chat`, { message })
  },
}

// 报告
export const reportApi = {
  // 获取报告
  get(sessionId, aiSummary = '') {
    return api.get(`/sessions/${sessionId}/report`, {
      params: { ai_summary: aiSummary }
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
