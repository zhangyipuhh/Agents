/* ============================================
   用户认证相关 API
   ============================================ */

/**
 * 用户登录
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @param {string} captchaKey - 验证码 key
 * @param {string} captchaCode - 验证码输入值
 * @returns {Promise<{access_token: string, role: string, username: string, expires_in: number}>} 登录结果
 * @throws {Error} 登录失败时抛出错误
 */
export async function login(username, password, captchaKey, captchaCode) {
  const response = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      captcha_key: captchaKey,
      captcha_code: captchaCode
    })
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '登录失败')
  }

  return response.json()
}

/**
 * 用户注册
 * @param {string} username - 用户名
 * @param {string} password - 密码
 * @param {string} confirmPassword - 确认密码
 * @returns {Promise<{message: string}>} 注册结果
 * @throws {Error} 注册失败时抛出错误
 */
export async function register(username, password, confirmPassword) {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      confirm_password: confirmPassword
    })
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '注册失败')
  }

  return response.json()
}

/**
 * 获取验证码图片
 * @returns {Promise<{captcha_key: string, captcha_image: string}>} 验证码 key 和 Base64 编码的验证码图片
 * @throws {Error} 获取验证码失败时抛出错误
 */
export async function getCaptcha() {
  const response = await fetch('/api/auth/captcha', {
    method: 'GET'
  })

  if (!response.ok) {
    throw new Error('获取验证码失败')
  }

  return response.json()
}

/**
 * 用户登出
 * 清除本地存储的认证信息，调用后端登出接口删除 Session
 * @throws {Error} 登出失败时抛出错误
 */
export async function logout() {
  try {
    const headers = { 'Content-Type': 'application/json' }
    const token = localStorage.getItem('auth_token')
    if (token) headers['Authorization'] = `Bearer ${token}`
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers,
      credentials: 'include'
    })
  } catch {
  } finally {
    clearAuth()
  }
}

/**
 * 修改用户密码
 * @param {number} userId - 用户ID
 * @param {string} oldPassword - 旧密码
 * @param {string} newPassword - 新密码
 * @returns {Promise<{message: string}>} 修改结果
 * @throws {Error} 修改密码失败时抛出错误
 */
export async function updatePassword(userId, oldPassword, newPassword) {
  if (!userId) {
    throw new Error('用户ID无效，请重新登录')
  }

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/users/${userId}/password`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword })
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '修改密码失败')
  }

  return response.json()
}

/**
 * 修改用户名
 * @param {number} userId - 用户ID
 * @param {string} newUsername - 新用户名
 * @returns {Promise<{message: string, new_username: string}>} 修改结果及新用户名
 * @throws {Error} 修改用户名失败时抛出错误
 */
export async function updateUsername(userId, newUsername) {
  if (!userId) {
    throw new Error('用户ID无效，请重新登录')
  }

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/users/${userId}/username`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ new_username: newUsername })
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '修改用户名失败')
  }

  return response.json()
}

/* ============================================
   认证状态管理
   ============================================ */

const CHUNK_SIZE = 256 * 1024

function generateFileId() {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
}

/**
 * 获取认证请求头
 * 从 localStorage 中读取 token 和 session_id 构建请求头
 * @returns {Object} 包含 Authorization 和 X-Session-ID 的请求头对象
 */
export function getAuthHeaders() {
  const headers = {}
  const token = localStorage.getItem('auth_token')
  const sessionId = localStorage.getItem('session_id')
  console.log('[调试] getAuthHeaders - token:', token ? token.substring(0, 20) + '...' : null)
  console.log('[调试] getAuthHeaders - sessionId:', sessionId)
  if (token && token !== 'undefined') {
    headers['Authorization'] = `Bearer ${token}`
  }
  if (sessionId && sessionId !== 'undefined') {
    headers['X-Session-ID'] = sessionId
  }
  console.log('[调试] getAuthHeaders - 返回的headers:', Object.keys(headers))
  return headers
}

/**
 * 清除本地存储的认证信息
 */
export function clearAuth() {
  localStorage.removeItem('auth_token')
  localStorage.removeItem('session_id')
  localStorage.removeItem('user_role')
  localStorage.removeItem('username')
}

/**
 * 调用 /api/auth/refresh 刷新 Access Token
 * 浏览器自动携带 HttpOnly Cookie 中的 Refresh Token
 * @returns {Promise<{access_token: string, token_type: string, expires_in: number}>}
 * @throws {Error} 刷新失败时抛出错误
 */
async function refreshAccessToken() {
  const response = await fetch('/api/auth/refresh', {
    method: 'POST',
    credentials: 'include',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || 'Refresh Token 已失效，请重新登录')
  }
  return response.json()
}

/**
 * 验证 Access Token 有效性
 * 调用 /api/auth/validate 检查当前 Access Token 是否有效
 * @returns {Promise<{username: string, role: string}>}
 * @throws {Error} Token 无效或过期时抛出错误
 */
export async function validateToken() {
  const token = localStorage.getItem('auth_token')
  if (!token) throw new Error('未登录')
  const response = await fetch('/api/auth/validate', {
    headers: { 'Authorization': `Bearer ${token}` }
  })
  if (!response.ok) throw new Error('Token 已过期或无效')
  return response.json()
}

/**
 * 统一 API 请求包装器
 * 自动注入 Authorization 和 X-Session-ID 头
 * 401 时静默调用 /api/auth/refresh 重试一次
 * @param {string} url - 请求地址
 * @param {Object} options - fetch 选项
 * @param {boolean} _retried - 内部使用，标记是否已重试
 * @returns {Promise<Response>} fetch Response
 * @throws {Error} 认证失败或请求失败时抛出错误
 */
export async function fetchWithAuth(url, options = {}, _retried = false) {
  const headers = { ...(options.headers || {}) }
  const token = localStorage.getItem('auth_token')
  const sessionId = localStorage.getItem('session_id')
  if (token && token !== 'undefined') {
    headers['Authorization'] = `Bearer ${token}`
  }
  if (sessionId && sessionId !== 'undefined') {
    headers['X-Session-ID'] = sessionId
  }
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401 && !_retried) {
    try {
      const data = await refreshAccessToken()
      localStorage.setItem('auth_token', data.access_token)
      headers['Authorization'] = `Bearer ${data.access_token}`
      return fetch(url, { ...options, headers })
    } catch {
      clearAuth()
      throw new Error('登录已过期，请重新登录')
    }
  }
  if (response.status === 403) {
    throw new Error('403 会话无效，请重试')
  }
  return response
}

/**
 * 刷新 JWT 令牌
 * 使用当前存储的凭据重新获取 token
 * @returns {Promise<string>} 新的 JWT 令牌
 * @throws {Error} 刷新失败时抛出错误（通常需要重新登录）
 */
export async function refreshToken() {
  const data = await refreshAccessToken()
  localStorage.setItem('auth_token', data.access_token)
  return data.access_token
}

/**
 * 强制刷新认证信息
 * @returns {Promise<{token: string}>} 认证信息
 * @throws {Error} 认证失败时抛出错误
 */
export async function forceRefreshAuth() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    throw new Error('未登录，请重新登录')
  }
  return { token }
}

/* ============================================
   文件上传相关 API
   ============================================ */

function uploadChunk(fileId, chunkIndex, totalChunks, filename, chunkBlob) {
  return new Promise((resolve, reject) => {
    const formData = new FormData()
    formData.append('chunk', chunkBlob, `chunk_${chunkIndex}`)
    formData.append('file_id', fileId)
    formData.append('chunk_index', String(chunkIndex))
    formData.append('total_chunks', String(totalChunks))
    formData.append('filename', filename)

    const xhr = new XMLHttpRequest()
    xhr.open('POST', '/api/core/upload-chunk')

    const authHeaders = getAuthHeaders()
    for (const [key, value] of Object.entries(authHeaders)) {
      xhr.setRequestHeader(key, value)
    }

    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        try {
          resolve(JSON.parse(xhr.responseText))
        } catch {
          resolve({ file_id: fileId, chunk_index: chunkIndex, received: true })
        }
      } else if (xhr.status === 401) {
        localStorage.removeItem('auth_token')
        reject(new Error('认证失败，请重试'))
      } else if (xhr.status === 403) {
        localStorage.removeItem('session_id')
        reject(new Error('403 会话无效，请重试'))
      } else {
        reject(new Error(`分片上传失败: ${xhr.status} ${xhr.statusText}`))
      }
    }

    xhr.onerror = () => reject(new Error('网络错误'))
    xhr.send(formData)
  })
}

function mergeChunks(fileId, filename, totalChunks) {
  return fetchWithAuth('/api/core/merge-chunks', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId, filename, total_chunks: totalChunks })
  }).then(res => {
    if (!res.ok) {
      return res.json().then(err => { throw new Error(err.detail || '合并失败') })
    }
    return res.json()
  })
}

export async function uploadFileInChunks(file, onProgress, onCancel) {
  await forceRefreshAuth()

  const fileId = generateFileId()
  const totalChunks = Math.ceil(file.size / CHUNK_SIZE) || 1
  let completedChunks = 0
  let cancelled = false

  const cancelFn = () => {
    cancelled = true
  }

  if (onCancel) {
    onCancel(cancelFn)
  }

  const uploadPromise = (async () => {
    for (let i = 0; i < totalChunks; i++) {
      if (cancelled) {
        throw new Error('上传已取消')
      }

      const start = i * CHUNK_SIZE
      const end = Math.min(start + CHUNK_SIZE, file.size)
      const chunkBlob = file.slice(start, end)

      try {
        await uploadChunk(fileId, i, totalChunks, file.name, chunkBlob)
      } catch (err) {
        if (err.message === '认证失败，请重试' || err.message.includes('403')) {
          await forceRefreshAuth()
          await uploadChunk(fileId, i, totalChunks, file.name, chunkBlob)
        } else {
          throw err
        }
      }

      completedChunks++
      if (onProgress) {
        // 分片上传阶段最多占 80%，合并阶段占 20%
        const uploadProgress = Math.round((completedChunks / totalChunks) * 80)
        onProgress(uploadProgress)
      }
    }

    if (cancelled) {
      throw new Error('上传已取消')
    }

    try {
      const result = await mergeChunks(fileId, file.name, totalChunks)
      return result
    } catch (err) {
      if (err.message === '认证失败，请重试' || err.message.includes('403')) {
        await forceRefreshAuth()
        const result = await mergeChunks(fileId, file.name, totalChunks)
        return result
      }
      throw err
    }
  })()

  return uploadPromise
}

export function formatFileSize(bytes) {
  if (bytes === 0) return '0 B'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const k = 1024
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${(bytes / Math.pow(k, i)).toFixed(i > 0 ? 1 : 0)} ${units[i]}`
}

export function getFileExtension(filename) {
  const parts = filename.split('.')
  return parts.length > 1 ? parts.pop().toLowerCase() : ''
}

/**
 * 创建新会话
 * 使用当前认证信息创建新的聊天会话
 * @returns {Promise<string>} 新会话 ID
 * @throws {Error} 创建会话失败时抛出错误
 */

/**
 * 会话创建锁，防止重复创建
 */
let isCreatingSession = false
let pendingSessionPromise = null

/**
 * 创建新会话
 * 使用当前认证信息创建新的聊天会话，带有防重复创建机制
 * @returns {Promise<string>} 新会话 ID
 * @throws {Error} 创建会话失败时抛出错误
 */
export async function createNewSession() {
  if (isCreatingSession && pendingSessionPromise) {
    return pendingSessionPromise
  }
  isCreatingSession = true
  pendingSessionPromise = (async () => {
    try {
      localStorage.removeItem('session_id')
      const response = await fetchWithAuth('/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' }
      })
      if (!response.ok) throw new Error(`创建会话失败: ${response.status}`)
      const sessionData = await response.json()
      const newSessionId = sessionData.session_id
      localStorage.setItem('session_id', newSessionId)
      return newSessionId
    } finally {
      isCreatingSession = false
      pendingSessionPromise = null
    }
  })()
  return pendingSessionPromise
}

export async function chatStream(sessionId, message, attachments = [], resume = null) {
  const sid = sessionId || localStorage.getItem('session_id') || ''
  const response = await fetchWithAuth('/api/map/chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Session-ID': sid
    },
    body: JSON.stringify({
      message: resume ? '' : message,
      session_id: sid,
      geometry_data: {},
      attachments,
      ...(resume ? { resume } : {})
    })
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  return response.body
}

export async function knowledgeChatStream(sessionId, message, attachments = [], resume = null) {
  const sid = sessionId || localStorage.getItem('session_id') || ''
  const response = await fetchWithAuth('/api/map/knowledge-chat', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Accept': 'text/event-stream',
      'Cache-Control': 'no-cache',
      'X-Session-ID': sid
    },
    body: JSON.stringify({
      message: resume ? '' : message,
      session_id: sid,
      geometry_data: {},
      attachments,
      ...(resume ? { resume } : {})
    })
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  return response.body
}

export async function fetchKnowledgeFiles() {
  const response = await fetchWithAuth('/api/map/knowledge/files', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  return response.json()
}

/* ============================================
   会话历史管理 API
   ============================================ */

/**
 * 获取当前用户的会话列表
 * @returns {Promise<{sessions: Array}>} 会话列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionList() {
  const response = await fetchWithAuth('/api/session/list', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取会话列表失败: ${response.status}`)
  return response.json()
}

/**
 * 获取会话详情（含附件列表）
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<Object>} 会话详情
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionDetail(sessionId) {
  const response = await fetchWithAuth(`/api/session/${sessionId}/detail`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取会话详情失败: ${response.status}`)
  return response.json()
}

/**
 * 更新会话标题
 * @param {string} sessionId - 会话 ID
 * @param {string} title - 新标题
 * @returns {Promise<{success: boolean, message: string}>} 更新结果
 * @throws {Error} 更新失败时抛出错误
 */
export async function updateSessionTitle(sessionId, title) {
  const response = await fetchWithAuth(`/api/session/${sessionId}/title`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ title })
  })
  if (!response.ok) throw new Error(`更新标题失败: ${response.status}`)
  return response.json()
}

/**
 * 获取会话附件列表
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{attachments: Array}>} 附件列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionAttachments(sessionId) {
  const response = await fetchWithAuth(`/api/session/${sessionId}/attachments`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取附件列表失败: ${response.status}`)
  return response.json()
}

/**
 * 获取会话历史消息
 * 从 LangGraph Checkpoint 中恢复指定会话的对话历史
 * @param {string} sessionId - 会话 ID
 * @param {number} limit - 返回消息数量限制，默认 50 条，设为 0 表示返回所有
 * @returns {Promise<{session_id: string, messages: Array, total: number}>} 历史消息
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionMessages(sessionId, limit = 50) {
  const queryParams = limit > 0 ? `?limit=${limit}` : ''
  const response = await fetchWithAuth(`/api/session/${sessionId}/messages${queryParams}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取历史消息失败: ${response.status}`)
  return response.json()
}

/**
 * 删除会话
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{success: boolean, message: string}>} 删除结果
 * @throws {Error} 删除失败时抛出错误
 */
export async function deleteSession(sessionId) {
  const response = await fetchWithAuth(`/api/session/delete/${sessionId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`删除会话失败: ${response.status}`)
  const currentSessionId = localStorage.getItem('session_id')
  if (currentSessionId === sessionId) {
    localStorage.removeItem('session_id')
  }
  return response.json()
}

export async function fetchFilePreview(path) {
  const response = await fetchWithAuth(
    `/api/map/knowledge/file-preview?path=${encodeURIComponent(path)}`,
    { method: 'GET', headers: { 'Content-Type': 'application/json' } }
  )
  if (!response.ok) throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  return response.json()
}
