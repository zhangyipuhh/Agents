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
    const headers = { 'Content-Type': 'application/json', ...getAuthHeaders() }
    await fetch('/api/auth/logout', {
      method: 'POST',
      headers
    })
  } catch {
    // 登出接口失败也继续清除本地数据
  } finally {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    localStorage.removeItem('user_role')
    localStorage.removeItem('username')
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
 * 刷新 JWT 令牌
 * 使用当前存储的凭据重新获取 token
 * @returns {Promise<string>} 新的 JWT 令牌
 * @throws {Error} 刷新失败时抛出错误（通常需要重新登录）
 */
export async function refreshToken() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    throw new Error('未登录，请重新登录')
  }

  // 尝试用现有 token 创建新 token（通过 session/create 觪�证 token 是否有效）
  // 如果 token 过期，需要重新登录
  try {
    const newToken = await jwtRefresh(token)
    localStorage.setItem('auth_token', newToken)
    return newToken
  } catch {
    // token 无效，需要重新登录
    localStorage.removeItem('auth_token')
    throw new Error('登录已过期，请重新登录')
  }
}

/**
 * 使用现有 token 刷新获取新 token
 * @param {string} token - 当前 JWT token
 * @returns {Promise<string>} 新的 JWT token
 */
async function jwtRefresh(token) {
  // 验证当前 token 是否仍然有效
  const sessionRes = await fetch('/api/session/create', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'Authorization': `Bearer ${token}`
    }
  })

  if (sessionRes.status === 401) {
    throw new Error('Token 已过期')
  }

  if (!sessionRes.ok) {
    throw new Error('刷新令牌失败')
  }

  // token 仍然有效，直接返回
  return token
}

/**
 * 确保认证状态有效
 * 检查 token 和 session_id 是否存在，不存在则尝试创建
 * @returns {Promise<{token: string, sessionId: string}>} 认证信息
 * @throws {Error} 认证失败时抛出错误
 */
export async function ensureAuth() {
  let token = localStorage.getItem('auth_token')
  let sessionId = localStorage.getItem('session_id')

  console.log('[调试] ensureAuth - token:', token)
  console.log('[调试] ensureAuth - token 长度:', token ? token.length : 0)

  if (!token || token === 'undefined') {
    console.error('[调试] token 无效，清除 localStorage')
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('未登录，请重新登录')
  }

  if (!sessionId) {
    console.log('[调试] 正在创建 session，token:', token)
    const sessionRes = await fetch('/api/session/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    })
    console.log('[调试] session/create 响应状态:', sessionRes.status)
    if (!sessionRes.ok) {
      const errorData = await sessionRes.json().catch(() => ({}))
      console.error('[调试] session/create 错误:', errorData)
      if (sessionRes.status === 401 || sessionRes.status === 403) {
        localStorage.removeItem('auth_token')
        localStorage.removeItem('session_id')
        throw new Error('登录已过期，请重新登录')
      }
      throw new Error('创建会话失败')
    }
    const sessionData = await sessionRes.json()
    sessionId = sessionData.session_id
    localStorage.setItem('session_id', sessionId)
  }

  return { token, sessionId }
}

/**
 * 强制刷新认证信息
 * @returns {Promise<{token: string, sessionId: string}>} 认证信息
 * @throws {Error} 认证失败时抛出错误
 */
export async function forceRefreshAuth() {
  const token = localStorage.getItem('auth_token')
  if (!token) {
    throw new Error('未登录，请重新登录')
  }

  let sessionId = localStorage.getItem('session_id')

  if (!sessionId) {
    const sessionRes = await fetch('/api/session/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    })
    if (!sessionRes.ok) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('session_id')
      throw new Error('创建会话失败')
    }
    const sessionData = await sessionRes.json()
    sessionId = sessionData.session_id
    localStorage.setItem('session_id', sessionId)
  }

  return { token, sessionId }
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
  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }
  return fetch('/api/core/merge-chunks', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      file_id: fileId,
      filename,
      total_chunks: totalChunks
    })
  }).then(res => {
    if (res.status === 401) {
      localStorage.removeItem('auth_token')
      throw new Error('认证失败，请重试')
    }
    if (res.status === 403) {
      localStorage.removeItem('session_id')
      throw new Error('403 会话无效，请重试')
    }
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
export async function createNewSession() {
  const { token } = await forceRefreshAuth()

  // 清除旧的 session_id，创建全新会话
  localStorage.removeItem('session_id')

  const headers = { 'Content-Type': 'application/json' }
  headers['Authorization'] = `Bearer ${token}`

  const sessionRes = await fetch('/api/session/create', {
    method: 'POST',
    headers
  })

  if (!sessionRes.ok) {
    if (sessionRes.status === 401 || sessionRes.status === 403) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('session_id')
      throw new Error('登录已过期，请重新登录')
    }
    throw new Error(`创建会话失败: ${sessionRes.status}`)
  }

  const sessionData = await sessionRes.json()
  const newSessionId = sessionData.session_id
  localStorage.setItem('session_id', newSessionId)
  return newSessionId
}

export async function chatStream(sessionId, message, attachments = []) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
    'Cache-Control': 'no-cache'
  }

  const token = localStorage.getItem('auth_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const sid = sessionId || localStorage.getItem('session_id') || ''
  if (sid) {
    headers['X-Session-ID'] = sid
  }

  const response = await fetch('/api/map/chat', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message,
      session_id: sid,
      geometry_data: {}
    })
  })

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('session_id')
      throw new Error('登录已过期，请重新登录')
    }
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  return response.body
}

export async function knowledgeChatStream(sessionId, message, attachments = []) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    'Accept': 'text/event-stream',
    'Cache-Control': 'no-cache'
  }

  const token = localStorage.getItem('auth_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const sid = sessionId || localStorage.getItem('session_id') || ''
  if (sid) {
    headers['X-Session-ID'] = sid
  }

  const response = await fetch('/api/map/knowledge-chat', {
    method: 'POST',
    headers,
    body: JSON.stringify({
      message,
      session_id: sid,
      geometry_data: {}
    })
  })

  if (!response.ok) {
    if (response.status === 401 || response.status === 403) {
      localStorage.removeItem('auth_token')
      localStorage.removeItem('session_id')
      throw new Error('登录已过期，请重新登录')
    }
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  return response.body
}

export async function fetchKnowledgeFiles() {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch('/api/map/knowledge/files', {
    method: 'GET',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

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
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch('/api/session/list', {
    method: 'GET',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`获取会话列表失败: ${response.status}`)
  }

  return response.json()
}

/**
 * 获取会话详情（含附件列表）
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<Object>} 会话详情
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionDetail(sessionId) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/session/${sessionId}/detail`, {
    method: 'GET',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`获取会话详情失败: ${response.status}`)
  }

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
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/session/${sessionId}/title`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ title })
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`更新标题失败: ${response.status}`)
  }

  return response.json()
}

/**
 * 获取会话附件列表
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{attachments: Array}>} 附件列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchSessionAttachments(sessionId) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/session/${sessionId}/attachments`, {
    method: 'GET',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`获取附件列表失败: ${response.status}`)
  }

  return response.json()
}

/**
 * 删除会话
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{success: boolean, message: string}>} 删除结果
 * @throws {Error} 删除失败时抛出错误
 */
export async function deleteSession(sessionId) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/session/delete/${sessionId}`, {
    method: 'DELETE',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`删除会话失败: ${response.status}`)
  }

  // 如果删除的是当前 session，清除 localStorage 中的 session_id
  const currentSessionId = localStorage.getItem('session_id')
  if (currentSessionId === sessionId) {
    localStorage.removeItem('session_id')
  }

  return response.json()
}

export async function fetchFilePreview(path) {
  await ensureAuth()

  const headers = {
    'Content-Type': 'application/json',
    ...getAuthHeaders()
  }

  const response = await fetch(`/api/map/knowledge/file-preview?path=${encodeURIComponent(path)}`, {
    method: 'GET',
    headers
  })

  if (response.status === 401 || response.status === 403) {
    localStorage.removeItem('auth_token')
    localStorage.removeItem('session_id')
    throw new Error('登录已过期，请重新登录')
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  return response.json()
}
