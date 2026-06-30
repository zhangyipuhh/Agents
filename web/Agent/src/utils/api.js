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
    credentials: 'include',
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
 * @param {string} realName - 真实姓名
 * @param {string} phone - 手机号
 * @param {string} email - 邮箱
 * @param {string} department - 部门（选填）
 * @param {string} position - 职位（选填）
 * @param {string} captchaKey - 验证码 key
 * @param {string} captchaCode - 验证码输入值
 * @returns {Promise<{message: string}>} 注册结果
 * @throws {Error} 注册失败时抛出错误
 */
export async function register(username, password, confirmPassword, realName, phone, email, department, position, captchaKey, captchaCode) {
  const response = await fetch('/api/auth/register', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      username,
      password,
      confirm_password: confirmPassword,
      real_name: realName,
      phone,
      email,
      department,
      position,
      captcha_key: captchaKey,
      captcha_code: captchaCode
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

/**
 * 获取用户个人资料
 * @param {number} userId - 用户ID
 * @returns {Promise<{id: number, username: string, role: string, real_name: string, phone: string, email: string, department: string, position: string, created_at: string, updated_at: string}>} 用户资料
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchUserProfile(userId) {
  if (!userId) {
    throw new Error('用户ID无效，请重新登录')
  }

  const response = await fetchWithAuth(`/api/users/${userId}/profile`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '获取用户资料失败')
  }

  return response.json()
}

/**
 * 更新用户个人资料
 * @param {number} userId - 用户ID
 * @param {Object} profileData - 资料数据
 * @param {string} profileData.phone - 手机号
 * @param {string} profileData.email - 邮箱
 * @param {string} profileData.department - 部门
 * @param {string} profileData.position - 职位
 * @returns {Promise<{message: string}>} 更新结果
 * @throws {Error} 更新失败时抛出错误
 */
export async function updateUserProfile(userId, profileData) {
  if (!userId) {
    throw new Error('用户ID无效，请重新登录')
  }

  const url = `/api/users/${userId}/profile`
  console.log('[updateUserProfile] userId:', userId, 'URL:', url, 'body:', profileData)

  const response = await fetchWithAuth(url, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      phone: profileData.phone || '',
      email: profileData.email || '',
      department: profileData.department || '',
      position: profileData.position || ''
    })
  })

  if (!response.ok) {
    const responseText = await response.clone().text()
    console.error('[updateUserProfile] 响应状态:', response.status, '响应体:', responseText)
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '更新资料失败')
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
 * 判断当前是否在知识库页面
 * @returns {boolean} 是否在知识库页面
 */
function isKnowledgePage() {
  return typeof window !== 'undefined' && window.location.pathname.includes('knowledge.html')
}

/**
 * 获取认证请求头
 * 从 localStorage 中读取 token 和 session_id 构建请求头
 * 知识库页面自动使用 knowledge_session_id，与主应用隔离
 * @returns {Object} 包含 Authorization 和 X-Session-ID 的请求头对象
 */
export function getAuthHeaders() {
  const headers = {}
  const token = localStorage.getItem('auth_token')
  const sessionKey = isKnowledgePage() ? 'knowledge_session_id' : 'session_id'
  const sessionId = localStorage.getItem(sessionKey)
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
  localStorage.removeItem('knowledge_session_id')
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
 * 申请门户子 refresh_token
 *
 * 由门户导航页（PortalApp）在 iframe 加载完成时调用，从后端获取一张
 * 与正常 refresh_token 等效但独立存储的子 token；再经 postMessage
 * 推送给第三方 iframe。第三方可像普通 SPA 一样用此 token 反复换 access_token。
 *
 * 鉴权：依赖现有 fetchWithAuth 的 Authorization: Bearer <access_token> 注入，
 *      401 时自动尝试一次 refresh 并重试。
 *
 * @returns {Promise<{portal_refresh_token: string, expires_in: number, expires_at: string}>}
 *          门户子 refresh_token 颁发结果（明文仅此一次返回）
 * @throws {Error} 鉴权失败或存储失败时抛出错误
 */
export async function issuePortalRefreshToken() {
  const response = await fetchWithAuth('/api/auth/issue-portal-refresh-token', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })

  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || '颁发门户子 refresh_token 失败')
  }

  return response.json()
}

/**
 * 统一 API 请求包装器
 * 自动注入 Authorization 和 X-Session-ID 头
 * 知识库页面自动使用 knowledge_session_id，与主应用隔离
 * 外部已传入的 X-Session-ID 不会被覆盖
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
  const sessionKey = isKnowledgePage() ? 'knowledge_session_id' : 'session_id'
  const sessionId = localStorage.getItem(sessionKey)
  if (token && token !== 'undefined') {
    headers['Authorization'] = `Bearer ${token}`
  }
  // 只有外部未显式传入 X-Session-ID 时，才从 localStorage 补充
  if (!headers['X-Session-ID'] && sessionId && sessionId !== 'undefined') {
    headers['X-Session-ID'] = sessionId
  }
  const response = await fetch(url, { ...options, headers })
  if (response.status === 401 && !_retried) {
    let data
    try {
      data = await refreshAccessToken()
    } catch {
      clearAuth()
      throw new Error('登录已过期，请重新登录')
    }
    localStorage.setItem('auth_token', data.access_token)
    headers['Authorization'] = `Bearer ${data.access_token}`
    const retryResponse = await fetch(url, { ...options, headers })
    if (retryResponse.status === 401) {
      localStorage.removeItem('session_id')
      localStorage.removeItem('knowledge_session_id')
      throw new Error('会话无效，请重新登录')
    }
    return retryResponse
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
 * @param {string} storageKey - 存储 session_id 的 localStorage key，默认为 'session_id'
 * @param {number|null} projectId - 2026-06-30 新增；项目 ID，传入时把会话绑定到项目
 * @returns {Promise<string>} 新会话 ID
 * @throws {Error} 创建会话失败时抛出错误
 */
export async function createNewSession(storageKey = 'session_id', projectId = null) {
  if (isCreatingSession && pendingSessionPromise) {
    return pendingSessionPromise
  }
  isCreatingSession = true
  pendingSessionPromise = (async () => {
    try {
      localStorage.removeItem(storageKey)
      const response = await fetchWithAuth('/api/session/create', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(projectId ? { project_id: projectId } : {})
      })
      if (!response.ok) throw new Error(`创建会话失败: ${response.status}`)
      const sessionData = await response.json()
      const newSessionId = sessionData.session_id
      localStorage.setItem(storageKey, newSessionId)
      return newSessionId
    } finally {
      isCreatingSession = false
      pendingSessionPromise = null
    }
  })()
  return pendingSessionPromise
}

/* ============================================
   项目文件夹 API（2026-06-30 新增）
   ============================================ */

/**
 * 创建新项目
 * @param {string} name - 项目名称
 * @param {string} uuid - 项目的 uuid（约定 = 创建时的 session_id）
 * @returns {Promise<{success: boolean, message: string, project: Object}>} 创建结果
 * @throws {Error} 创建失败时抛出错误
 */
export async function createProject(name, uuid) {
  const response = await fetchWithAuth('/api/project/create', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, uuid })
  })
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `创建项目失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取当前用户的项目列表
 * @returns {Promise<{projects: Array<{id, name, uuid, user_id, created_at}>}>} 项目列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchProjectList() {
  const response = await fetchWithAuth('/api/project/list', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取项目列表失败: ${response.status}`)
  return response.json()
}

/**
 * 获取单个项目详情
 * @param {number} projectId - 项目主键 ID
 * @returns {Promise<{project: Object}>} 项目信息
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchProjectInfo(projectId) {
  const response = await fetchWithAuth(`/api/project/${projectId}/info`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取项目详情失败: ${response.status}`)
  return response.json()
}

/**
 * 将会话绑定到指定项目
 * @param {string} sessionId - 目标会话 ID
 * @param {number} projectId - 目标项目 ID
 * @returns {Promise<{success: boolean, message: string}>} 绑定结果
 * @throws {Error} 绑定失败时抛出错误
 */
export async function bindSessionToProject(sessionId, projectId) {
  const response = await fetchWithAuth('/api/project/session/bind', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId, project_id: projectId })
  })
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `绑定项目失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 解除会话与项目的关联
 * @param {string} sessionId - 目标会话 ID
 * @returns {Promise<{success: boolean, message: string}>} 解绑结果
 * @throws {Error} 解绑失败时抛出错误
 */
export async function unbindSessionFromProject(sessionId) {
  const response = await fetchWithAuth('/api/project/session/unbind', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ session_id: sessionId })
  })
  if (!response.ok) {
    const errData = await response.json().catch(() => ({}))
    throw new Error(errData.detail || `解绑项目失败: ${response.status}`)
  }
  return response.json()
}

export async function chatStream(sessionId, message, attachments = [], resume = null, agentName = null) {
  const sid = sessionId || localStorage.getItem('session_id') || ''
  const response = await fetchWithAuth('/api/agent/chat', {
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
      ...(resume ? { resume } : {}),
      ...(agentName ? { agent_name: agentName } : {})
    })
  })
  if (!response.ok) {
    // 2026-06-15 新增：保留 status + detail 让上层识别 429 排队场景
    let body = null
    try { body = await response.json() } catch {}
    const err = new Error(body?.detail?.message || `HTTP ${response.status}: ${response.statusText}`)
    err.status = response.status
    err.detail = body?.detail || null
    throw err
  }
  return response.body
}

export async function knowledgeChatStream(sessionId, message, attachments = [], resume = null) {
  const sid = sessionId || localStorage.getItem('knowledge_session_id') || ''
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
  if (!response.ok) {
    // 2026-06-15 新增：保留 status + detail 让上层识别 429 排队场景
    let body = null
    try { body = await response.json() } catch {}
    const err = new Error(body?.detail?.message || `HTTP ${response.status}: ${response.statusText}`)
    err.status = response.status
    err.detail = body?.detail || null
    throw err
  }
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
  const knowledgeSessionId = localStorage.getItem('knowledge_session_id')
  if (knowledgeSessionId === sessionId) {
    localStorage.removeItem('knowledge_session_id')
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

/* ============================================
   Admin 管理相关 API
   ============================================ */

/**
 * 获取用户列表（admin 专用）
 * @returns {Promise<{users: Array}>} 用户列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchUserList() {
  const response = await fetchWithAuth('/api/users', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取用户列表失败: ${response.status}`)
  return response.json()
}

/**
 * 创建用户（admin 专用）
 * @param {Object} userData - 用户数据
 * @param {string} userData.username - 用户名
 * @param {string} userData.password - 密码
 * @param {string} userData.role - 角色
 * @param {string} userData.real_name - 真实姓名
 * @param {string} userData.phone - 手机号
 * @param {string} userData.email - 邮箱
 * @param {string} userData.department - 部门
 * @param {string} userData.position - 职位
 * @returns {Promise<{message: string, user_id: number}>} 创建结果
 * @throws {Error} 创建失败时抛出错误
 */
export async function createUser(userData) {
  const response = await fetchWithAuth('/api/users', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData)
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `创建用户失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新用户（admin 专用）
 * @param {number} userId - 用户ID
 * @param {Object} userData - 用户数据
 * @param {string} userData.real_name - 真实姓名
 * @param {string} userData.phone - 手机号
 * @param {string} userData.email - 邮箱
 * @param {string} userData.department - 部门
 * @param {string} userData.position - 职位
 * @param {string} userData.role - 角色
 * @returns {Promise<{message: string}>} 更新结果
 * @throws {Error} 更新失败时抛出错误
 */
export async function updateUser(userId, userData) {
  const response = await fetchWithAuth(`/api/users/${userId}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(userData)
  })
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}))
    throw new Error(errorData.detail || `更新用户失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 删除用户（admin 专用）
 * @param {number} userId - 用户ID
 * @returns {Promise<{message: string}>} 删除结果
 * @throws {Error} 删除失败时抛出错误
 */
export async function deleteUser(userId) {
  const response = await fetchWithAuth(`/api/users/${userId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`删除用户失败: ${response.status}`)
  return response.json()
}

/**
 * 强制用户下线（admin 专用）
 * @param {number} userId - 用户ID
 * @returns {Promise<{message: string, deleted_tokens: number}>} 操作结果
 * @throws {Error} 操作失败时抛出错误
 */
export async function kickUser(userId) {
  const response = await fetchWithAuth(`/api/users/${userId}/kick`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`强制下线失败: ${response.status}`)
  return response.json()
}

/**
 * 获取在线用户列表（admin 专用）
 * @returns {Promise<{online_users: Array}>} 在线用户列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchOnlineUsers() {
  const response = await fetchWithAuth('/api/users/online', {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取在线用户失败: ${response.status}`)
  return response.json()
}

/**
 * 获取指定用户的所有会话（admin 专用）
 * @param {number} userId - 用户ID
 * @returns {Promise<{sessions: Array}>} 会话列表
 * @throws {Error} 获取失败时抛出错误
 */
export async function fetchUserSessions(userId) {
  const response = await fetchWithAuth(`/api/users/${userId}/sessions`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`获取用户会话失败: ${response.status}`)
  return response.json()
}

/**
 * Admin 强制删除任意会话
 * @param {string} sessionId - 会话 ID
 * @returns {Promise<{success: boolean, message: string}>} 删除结果
 * @throws {Error} 删除失败时抛出错误
 */
export async function adminDeleteSession(sessionId) {
  const response = await fetchWithAuth(`/api/session/admin/${sessionId}`, {
    method: 'DELETE',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`删除会话失败: ${response.status}`)
  return response.json()
}

/**
 * Admin 按用户名搜索会话
 * @param {string} username - 用户名关键字
 * @returns {Promise<{sessions: Array}>} 会话列表
 * @throws {Error} 搜索失败时抛出错误
 */
export async function searchSessionsByUsername(username) {
  const response = await fetchWithAuth(`/api/session/admin/search?username=${encodeURIComponent(username)}`, {
    method: 'GET',
    headers: { 'Content-Type': 'application/json' }
  })
  if (!response.ok) throw new Error(`搜索会话失败: ${response.status}`)
  return response.json()
}

// ============================================================
// MCP 管理 API（2026-06-23 新增）
// 对应后端 mcp_admin_router 的 /api/admin/mcp/* 端点
// ============================================================

/**
 * 获取 MCP 服务器列表
 * @returns {Promise<Array<{name: string, enabled: boolean}>>} 服务器配置列表
 * @throws {Error} 请求失败时抛出错误
 */
export async function listMcpServers() {
  const response = await fetchWithAuth('/api/admin/mcp/servers', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 创建 MCP 服务器配置
 * @param {Object} config - 服务器配置对象
 * @param {string} config.name - 服务器名称
 * @param {string} config.type - 传输类型（sse|stdio|streamable_http）
 * @param {string} [config.url] - SSE/HTTP 模式的 URL
 * @returns {Promise<Object>} 创建结果
 * @throws {Error} 创建失败时抛出错误（含后端 detail 信息）
 */
export async function createMcpServer(config) {
  const response = await fetchWithAuth('/api/admin/mcp/servers', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 更新 MCP 服务器配置
 * @param {string} name - 服务器名称
 * @param {Object} config - 待更新的配置对象
 * @returns {Promise<Object>} 更新结果
 * @throws {Error} 更新失败时抛出错误
 */
export async function updateMcpServer(name, config) {
  const response = await fetchWithAuth(`/api/admin/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(config),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 删除 MCP 服务器配置
 * @param {string} name - 服务器名称
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 删除失败时抛出错误
 */
export async function deleteMcpServer(name) {
  const response = await fetchWithAuth(`/api/admin/mcp/servers/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `删除 MCP 服务器失败: ${response.status}`)
  }
}


/* ============================================
   智能体管理 API（2026-06-24 新增）
   ============================================ */

/**
 * 列出所有智能体（含 config_schema 完整数据）
 * @returns {Promise<Array>} 智能体列表
 */
export async function fetchAdminAgentList() {
  const response = await fetchWithAuth('/api/admin/agents')
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取智能体列表失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取单个智能体完整配置
 * @param {string} name - 智能体名称
 * @returns {Promise<Object>} 智能体完整配置（含 agent_config_overrides）
 */
export async function fetchAdminAgentConfig(name) {
  const response = await fetchWithAuth(`/api/admin/agents/${encodeURIComponent(name)}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取智能体配置失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 新增智能体
 * @param {Object} payload - { name, display_name, description, agents_md_path, config_schema, mcp_tags, enabled, sort_order }
 * @returns {Promise<Object>} 新创建的智能体记录
 */
export async function createAdminAgent(payload) {
  const response = await fetchWithAuth('/api/admin/agents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `新增智能体失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 删除智能体（级联清理工具/技能绑定）
 * @param {string} name - 智能体名称
 * @returns {Promise<void>}
 */
export async function deleteAdminAgent(name) {
  const response = await fetchWithAuth(`/api/admin/agents/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `删除智能体失败: ${response.status}`)
  }
}

/**
 * 启用 / 禁用智能体
 * @param {string} name - 智能体名称
 * @param {boolean} enabled - 目标状态
 * @returns {Promise<Object>} 更新后的记录
 */
export async function setAdminAgentEnabled(name, enabled) {
  const response = await fetchWithAuth(`/api/admin/agents/${encodeURIComponent(name)}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新智能体启用状态失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新智能体基本信息（display_name / description）
 * @param {string} name - 智能体名称
 * @param {Object} payload - { display_name, description }
 * @returns {Promise<Object>} 更新后的记录
 */
export async function updateAdminAgent(name, payload) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新智能体信息失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 全量替换 config_schema
 * @param {string} name - 智能体名称
 * @param {Object} configSchema - 三层嵌套字典
 * @returns {Promise<Object>} 更新后的记录
 */
export async function updateAdminAgentConfigSchema(name, configSchema) {
  const response = await fetchWithAuth(`/api/admin/agents/${encodeURIComponent(name)}/config-schema`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ config_schema: configSchema }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新 config_schema 失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 增量添加 config_schema 字段
 * @param {string} name - 智能体名称
 * @param {string} section - root / state_fields / context_fields
 * @param {string} fieldName - 字段名
 * @param {Object} fieldDef - { type, default }
 * @returns {Promise<Object>} 更新后的记录
 */
export async function addAdminAgentConfigField(name, section, fieldName, fieldDef) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/config-schema/field`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section, field_name: fieldName, field_def: fieldDef }),
    }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `添加字段失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 直接覆盖 config_schema 中已存在的字段（无需先删后加）
 * @param {string} name - 智能体名称
 * @param {string} section - root / state_fields / context_fields
 * @param {string} fieldName - 字段名
 * @param {Object} fieldDef - { type, default }
 * @returns {Promise<Object>} 更新后的记录
 */
export async function updateAdminAgentConfigField(name, section, fieldName, fieldDef) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/config-schema/field`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ section, field_name: fieldName, field_def: fieldDef }),
    }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `修改字段失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 增量删除 config_schema 字段
 * @param {string} name - 智能体名称
 * @param {string} section - root / state_fields / context_fields
 * @param {string} fieldName - 字段名
 * @returns {Promise<Object>} 更新后的记录
 */
export async function deleteAdminAgentConfigField(name, section, fieldName) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/config-schema/field?section=${encodeURIComponent(section)}&field_name=${encodeURIComponent(fieldName)}`,
    { method: 'DELETE' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `删除字段失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取字段模板列表（用于新增字段时下拉选择）
 * @param {string} section - 字段所属段：root / state_fields / context_fields
 * @returns {Promise<Array<{field_name, type, default}>>} 字段模板列表
 */
export async function fetchAgentConfigFieldTemplates(section = 'root') {
  const response = await fetchWithAuth(`/api/admin/agents/field-templates?section=${encodeURIComponent(section)}`)
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取字段模板失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 校验 AGENTS.md 路径是否存在
 * @param {string} path - AGENTS.md 文件路径
 * @returns {Promise<{path, exists, is_file}>} 校验结果
 */
export async function validateAgentMdPath(path) {
  const response = await fetchWithAuth('/api/admin/agents/validate-md-path', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ path }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `校验 AGENTS.md 路径失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 检查智能体 name 是否唯一
 * @param {string} name - 智能体名称
 * @returns {Promise<{name, available}>} 校验结果
 */
export async function checkAgentNameUnique(name) {
  const response = await fetchWithAuth(
    `/api/admin/agents/check-name?name=${encodeURIComponent(name)}`
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `name 唯一性校验失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 启用/禁用 MCP 服务器
 * @param {string} name - 服务器名称
 * @param {boolean} enabled - 是否启用
 * @returns {Promise<Object>} 切换结果
 * @throws {Error} 切换失败时抛出错误
 */
export async function toggleMcpServer(name, enabled) {
  const response = await fetchWithAuth(
    `/api/admin/mcp/servers/${encodeURIComponent(name)}/toggle?enabled=${enabled}`,
    { method: 'POST' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 获取指定 MCP 服务器的工具方法列表
 * @param {string} name - 服务器名称
 * @returns {Promise<Array<{method_name: string, enabled: boolean}>>} 方法列表
 * @throws {Error} 请求失败时抛出错误
 */
export async function listMcpMethods(name) {
  const response = await fetchWithAuth(
    `/api/admin/mcp/servers/${encodeURIComponent(name)}/methods`,
    { method: 'GET' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 刷新指定 MCP 服务器的工具方法列表（重新拉取远端方法清单）
 * @param {string} name - 服务器名称
 * @returns {Promise<{methods_count: number}>} 刷新结果，含方法数量
 * @throws {Error} 刷新失败时抛出错误
 */
export async function refreshMcpMethods(name) {
  const response = await fetchWithAuth(
    `/api/admin/mcp/servers/${encodeURIComponent(name)}/refresh-methods`,
    { method: 'POST' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

/**
 * 启用/禁用指定 MCP 服务器的某个工具方法
 * @param {string} serverName - 服务器名称
 * @param {string} method - 方法名称
 * @param {boolean} enabled - 是否启用
 * @returns {Promise<Object>} 切换结果
 * @throws {Error} 切换失败时抛出错误
 */
export async function toggleMcpMethod(serverName, method, enabled) {
  const response = await fetchWithAuth(
    `/api/admin/mcp/servers/${encodeURIComponent(serverName)}/methods/${encodeURIComponent(method)}/toggle?enabled=${enabled}`,
    { method: 'POST' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

// ============================================================
// Agent 列表 API（2026-06-23 新增）
// ============================================================

/**
 * 获取可用 Agent 列表（供 MCP 配置页选择绑定 Agent 使用）
 * @returns {Promise<Array<{name: string, display_name: string}>>} Agent 列表
 * @throws {Error} 请求失败时抛出错误
 */
export async function fetchAgentList() {
  const response = await fetchWithAuth('/api/agent/list', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `HTTP ${response.status}`)
  }
  return response.json()
}

// ============================================================
// 工具管理 API（2026-06-25 新增）
// 对应后端 tool_admin_router 的 /api/admin/tools/* 端点
// 以及 agent_admin_router 的 /api/admin/agents/{name}/tool-bindings 端点
// ============================================================

/**
 * 列出所有已注册工具
 * 调用 GET /api/admin/tools，优先读缓存（仅 enabled=TRUE），
 * 缓存为空时回退 DB 查询所有工具（含禁用项，供 admin 查看）。
 * @returns {Promise<Array<Object>>} 工具元数据列表，每项包含
 *   name / display_name / category / description / module_path /
 *   file_path / args_schema / return_description /
 *   function_description / enabled
 * @throws {Error} 请求失败时抛出错误（含后端 detail 信息）
 */
export async function listTools() {
  const response = await fetchWithAuth('/api/admin/tools', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取工具列表失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 列出未注册工具文件（源码扫描，GET 语义）
 * 调用 GET /api/admin/tools/unregistered，用 ast.parse 扫描
 * app/core/tools/ 和 app/shared/tools/skills/ 下所有 .py 文件，
 * 找出未在 DB 注册的 @tool 函数。
 * @returns {Promise<Array<Object>>} 未注册工具列表，每项包含
 *   name / file_path / module_path / args_schema /
 *   return_description / function_description
 * @throws {Error} 请求失败时抛出错误
 */
export async function listUnregisteredTools() {
  const response = await fetchWithAuth('/api/admin/tools/unregistered', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取未注册工具列表失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 注册新工具
 * 调用 POST /api/admin/tools，写 DB 后刷新缓存。
 * 必填字段：name / category / module_path / file_path。
 * @param {Object} payload - 工具配置
 * @param {string} payload.name - 工具唯一标识
 * @param {string} [payload.display_name] - 展示名称
 * @param {string} payload.category - 工具分类
 * @param {string} [payload.description] - 工具描述
 * @param {string} payload.module_path - Python 模块路径
 * @param {string} payload.file_path - 源文件相对路径
 * @param {Object} [payload.args_schema] - 参数 schema 字典
 * @param {string} [payload.return_description] - 返回值类型描述
 * @param {string} [payload.function_description] - 函数完整描述
 * @param {boolean} [payload.enabled=true] - 是否启用
 * @param {number} [payload.sort_order=0] - 排序权重
 * @returns {Promise<Object>} 新创建的工具记录（含反序列化后的 args_schema）
 * @throws {Error} name 已存在(409) / 缺少必需键(400) / 服务未初始化(500) 时抛出错误
 */
export async function registerTool(payload) {
  const response = await fetchWithAuth('/api/admin/tools', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `注册工具失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新工具配置
 * 调用 PUT /api/admin/tools/{name}，全量更新工具的可变字段，写 DB 后刷新缓存。
 * 注意：name 不可修改（由 URL path 指定）；module_path / file_path 不可改。
 * @param {string} name - 工具名称（URL path 参数）
 * @param {Object} payload - 待更新字段（None 字段会被 service 层用默认值替换，需传完整配置）
 * @param {string} [payload.display_name] - 展示名称
 * @param {string} [payload.category] - 工具分类
 * @param {string} [payload.description] - 工具描述
 * @param {Object} [payload.args_schema] - 参数 schema 字典
 * @param {string} [payload.return_description] - 返回值类型描述
 * @param {string} [payload.function_description] - 函数完整描述
 * @param {boolean} [payload.enabled] - 是否启用
 * @param {number} [payload.sort_order] - 排序权重
 * @returns {Promise<Object>} 更新后的工具记录
 * @throws {Error} 工具不存在(404) / 字段非法(400) / 服务未初始化(500) 时抛出错误
 */
export async function updateTool(name, payload) {
  const response = await fetchWithAuth(`/api/admin/tools/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新工具失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 删除工具
 * 调用 DELETE /api/admin/tools/{name}，写 DB 后失效缓存。
 * 后端返回 204 No Content（无响应体），本函数无返回值。
 * @param {string} name - 工具名称
 * @returns {Promise<void>} 无返回值
 * @throws {Error} 工具不存在(404) / 服务未初始化(500) 时抛出错误
 */
export async function deleteTool(name) {
  const response = await fetchWithAuth(`/api/admin/tools/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  // 204 No Content 无响应体，不能调用 response.json()
  if (!response.ok && response.status !== 204) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `删除工具失败: ${response.status}`)
  }
}

/**
 * 启用/禁用工具
 * 调用 PUT /api/admin/tools/{name}/enabled，写 DB 后刷新缓存
 * （enabled=TRUE 时加入缓存，enabled=FALSE 时从缓存移除）。
 * @param {string} name - 工具名称
 * @param {boolean} enabled - True 启用 / False 禁用
 * @returns {Promise<Object>} 更新后的工具记录
 * @throws {Error} 工具不存在(404) / 服务未初始化(500) 时抛出错误
 */
export async function setToolEnabled(name, enabled) {
  const response = await fetchWithAuth(`/api/admin/tools/${encodeURIComponent(name)}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新工具启用状态失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 扫描未注册工具文件（POST 语义，主动触发）
 * 调用 POST /api/admin/tools/scan，与 GET /unregistered 功能相同，
 * 但用 POST 表达副作用语义（扫描是较重操作）。
 * @returns {Promise<Array<Object>>} 未注册工具列表，每项包含
 *   name / file_path / module_path / args_schema /
 *   return_description / function_description
 * @throws {Error} 服务未初始化(500) 时抛出错误
 */
export async function scanTools() {
  const response = await fetchWithAuth('/api/admin/tools/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `扫描工具失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取指定智能体的工具绑定列表
 * 调用 GET /api/admin/agents/{name}/tool-bindings。
 * @param {string} name - 智能体名称
 * @returns {Promise<{agent_name: string, tool_bindings: Array}>} 工具绑定列表
 * @throws {Error} 智能体不存在(404) 时抛出错误
 */
export async function getAgentToolBindings(name) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/tool-bindings`,
    { method: 'GET' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取工具绑定失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新指定智能体的工具绑定列表（全量替换）
 * 调用 PUT /api/admin/agents/{name}/tool-bindings。
 * @param {string} name - 智能体名称
 * @param {Array<Object>} bindings - 工具绑定列表，每项含
 *   tool_name（必填）/ tool_type（默认 "builtin"）/ enabled（默认 True）/ sort_order（默认 0）
 * @returns {Promise<Object>} 更新结果
 * @throws {Error} 智能体不存在(404) / 校验失败(422) 时抛出错误
 */
export async function updateAgentToolBindings(name, bindings) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/tool-bindings`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bindings }),
    }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新工具绑定失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取指定智能体可绑定的工具列表（内置 + MCP）
 * 调用 GET /api/admin/agents/{name}/available-tools
 * 供前端 AgentManager 工具绑定 Tab 使用：一次性返回内置工具 + MCP tool 列表
 * （MCP tool 已按 server.method 复合名展开，前端直接展示 + 选择）。
 * @param {string} name - 智能体名称
 * @returns {Promise<{
 *   agent_name: string,
 *   builtin: Array<{
 *     name: string,              // 函数名（如 get_current_time），用于 binding.tool_name
 *     display_name: string,
 *     category: string,           // 分类（前端展示分组）
 *     description: string,
 *     module_path: string,
 *     file_path: string,          // 含文件名（如 app/core/tools/BaseTools.py）
 *     file_basename: string,      // 文件名不含 .py（前端展示 "BaseTools.get_current_time"）
 *   }>,
 *   mcp: Array<{
 *     server_name: string,        // server 名（如 amap）
 *     server_display_name: string,// server 显示名（如 "高德地图"）
 *     method_name: string,        // method 名（如 search）
 *     display_name: string,
 *     description: string,
 *     tool_name: string,          // "server.method" 复合名（如 "amap.search"），用于 binding.tool_name
 *     enabled: boolean,
 *   }>
 * }>}
 * @throws {Error} 请求失败时抛出错误（含后端 detail 信息）
 */
export async function fetchAgentAvailableTools(name) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/available-tools`,
    { method: 'GET' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取可绑定工具列表失败: ${response.status}`)
  }
  return response.json()
}

// ============================================================
// Skill 管理 API（2026-06-29 新增）
// 对应后端 skill_admin_router 的 /api/admin/skills/* 端点
// 以及 agent_admin_router 的 /api/admin/agents/{name}/(skill-bindings|available-skills) 端点
// ============================================================

/**
 * 列出所有已注册 skill
 * 调用 GET /api/admin/skills，优先读缓存（仅 enabled=TRUE），
 * 缓存为空时回退 DB 查询所有 skill（含禁用项，供 admin 查看）。
 * @returns {Promise<Array<Object>>} skill 元数据列表，每项包含
 *   name / display_name / category / description / location /
 *   base_dir / content / enabled / sort_order
 * @throws {Error} 请求失败时抛出错误（含后端 detail 信息）
 */
export async function listSkills() {
  const response = await fetchWithAuth('/api/admin/skills', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取 skill 列表失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 列出未注册 skill 文件（源码扫描，GET 语义）
 * 调用 GET /api/admin/skills/unregistered，扫描默认根
 * （app/skills、.agents/skills）与用户扩展路径下的 SKILL.md，
 * 找出未在 DB 注册的 skill。
 * @returns {Promise<Array<Object>>} 未注册 skill 列表，每项包含
 *   name / description / location / base_dir
 * @throws {Error} 请求失败时抛出错误
 */
export async function listUnregisteredSkills() {
  const response = await fetchWithAuth('/api/admin/skills/unregistered', { method: 'GET' })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取未注册 skill 列表失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 注册新 skill
 * 调用 POST /api/admin/skills，写 DB 后刷新缓存。
 * 必填字段：name / category。
 * @param {Object} payload - skill 配置
 * @param {string} payload.name - skill 唯一标识（与 SKILL.md frontmatter 一致）
 * @param {string} [payload.display_name] - 展示名称
 * @param {string} payload.category - skill 分类
 * @param {string} [payload.description] - skill 描述
 * @param {string} [payload.location] - SKILL.md 文件绝对路径
 * @param {string} [payload.base_dir] - SKILL.md 所在目录绝对路径
 * @param {string} [payload.content] - 去除 frontmatter 后的正文
 * @param {boolean} [payload.enabled=true] - 是否启用
 * @param {number} [payload.sort_order=0] - 排序权重
 * @returns {Promise<Object>} 新创建的 skill 记录
 * @throws {Error} name 已存在(409) / 缺少必需键(400) / 服务未初始化(500) 时抛出错误
 */
export async function registerSkill(payload) {
  const response = await fetchWithAuth('/api/admin/skills', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `注册 skill 失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新 skill 配置
 * 调用 PUT /api/admin/skills/{name}，全量更新 skill 的可变字段，写 DB 后刷新缓存。
 * 注意：name 不可修改（由 URL path 指定）；location / base_dir / content
 * 涉及源文件位置与内容，修改需谨慎，调用方需传入完整配置。
 * @param {string} name - skill 名称（URL path 参数）
 * @param {Object} payload - 待更新字段
 * @param {string} [payload.display_name] - 展示名称
 * @param {string} [payload.category] - skill 分类
 * @param {string} [payload.description] - skill 描述
 * @param {string} [payload.location] - SKILL.md 文件绝对路径
 * @param {string} [payload.base_dir] - SKILL.md 所在目录绝对路径
 * @param {string} [payload.content] - 去除 frontmatter 后的正文
 * @param {boolean} [payload.enabled] - 是否启用
 * @param {number} [payload.sort_order] - 排序权重
 * @returns {Promise<Object>} 更新后的 skill 记录
 * @throws {Error} skill 不存在(404) / 字段非法(400) / 服务未初始化(500) 时抛出错误
 */
export async function updateSkill(name, payload) {
  const response = await fetchWithAuth(`/api/admin/skills/${encodeURIComponent(name)}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新 skill 失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 删除 skill
 * 调用 DELETE /api/admin/skills/{name}，写 DB 后失效缓存。
 * 后端返回 204 No Content（无响应体），本函数无返回值。
 * @param {string} name - skill 名称
 * @returns {Promise<void>} 无返回值
 * @throws {Error} skill 不存在(404) / 服务未初始化(500) 时抛出错误
 */
export async function deleteSkill(name) {
  const response = await fetchWithAuth(`/api/admin/skills/${encodeURIComponent(name)}`, {
    method: 'DELETE',
  })
  // 204 No Content 无响应体，不能调用 response.json()
  if (!response.ok && response.status !== 204) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `删除 skill 失败: ${response.status}`)
  }
}

/**
 * 启用/禁用 skill
 * 调用 PUT /api/admin/skills/{name}/enabled，写 DB 后刷新缓存
 * （enabled=TRUE 时加入缓存，enabled=FALSE 时从缓存移除）。
 * @param {string} name - skill 名称
 * @param {boolean} enabled - True 启用 / False 禁用
 * @returns {Promise<Object>} 更新后的 skill 记录
 * @throws {Error} skill 不存在(404) / 服务未初始化(500) 时抛出错误
 */
export async function setSkillEnabled(name, enabled) {
  const response = await fetchWithAuth(`/api/admin/skills/${encodeURIComponent(name)}/enabled`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ enabled }),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新 skill 启用状态失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 扫描未注册 skill 文件（POST 语义，主动触发）
 * 调用 POST /api/admin/skills/scan，与 GET /unregistered 功能相同，
 * 但用 POST 表达副作用语义（扫描是较重操作）。
 * @returns {Promise<Array<Object>>} 未注册 skill 列表，每项包含
 *   name / description / location / base_dir
 * @throws {Error} 服务未初始化(500) 时抛出错误
 */
export async function scanSkills() {
  const response = await fetchWithAuth('/api/admin/skills/scan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `扫描 skill 失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取指定智能体的 skill 绑定列表
 * 调用 GET /api/admin/agents/{name}/skill-bindings。
 * 返回 agents.skill_bindings JSONB 字段快照。
 * @param {string} name - 智能体名称
 * @returns {Promise<{agent_name: string, skill_bindings: Array<{skill_name: string, enabled: boolean, sort_order: number}>}>} skill 绑定列表
 * @throws {Error} 智能体不存在(404) 时抛出错误
 */
export async function getAgentSkillBindings(name) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/skill-bindings`,
    { method: 'GET' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取 skill 绑定失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 更新指定智能体的 skill 绑定列表（全量替换）
 * 调用 PUT /api/admin/agents/{name}/skill-bindings。
 * @param {string} name - 智能体名称
 * @param {Array<Object>} bindings - skill 绑定列表，每项含
 *   skill_name（必填）/ enabled（默认 True）/ sort_order（默认 0）
 * @returns {Promise<{agent_name: string, skill_bindings: Array}>} 更新结果
 * @throws {Error} 智能体不存在(404) / 校验失败(422) 时抛出错误
 */
export async function updateAgentSkillBindings(name, bindings) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/skill-bindings`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bindings }),
    }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `更新 skill 绑定失败: ${response.status}`)
  }
  return response.json()
}

/**
 * 获取指定智能体可绑定的 skill 列表
 * 调用 GET /api/admin/agents/{name}/available-skills
 * 返回 DB skills 表中 enabled=TRUE 的 skill，每项含
 * name / display_name / category / description。
 * @param {string} name - 智能体名称
 * @returns {Promise<{agent_name: string, skills: Array<{name: string, display_name: string, category: string, description: string}>}>} 可绑定 skill 列表
 * @throws {Error} 请求失败时抛出错误（含后端 detail 信息）
 */
export async function fetchAgentAvailableSkills(name) {
  const response = await fetchWithAuth(
    `/api/admin/agents/${encodeURIComponent(name)}/available-skills`,
    { method: 'GET' }
  )
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(detail.detail || `获取可绑定 skill 列表失败: ${response.status}`)
  }
  return response.json()
}
