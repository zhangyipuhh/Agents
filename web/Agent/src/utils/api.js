const CHUNK_SIZE = 256 * 1024

function generateFileId() {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
}

export function getAuthHeaders() {
  const headers = {}
  const token = localStorage.getItem('auth_token')
  if (token) {
    headers['Authorization'] = `Bearer ${token}`
  }
  const sessionId = localStorage.getItem('session_id')
  if (sessionId) {
    headers['X-Session-ID'] = sessionId
  }
  return headers
}

export async function refreshToken() {
  const loginRes = await fetch('/api/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: 'admin', password: '123456' })
  })
  if (!loginRes.ok) {
    throw new Error('登录失败')
  }
  const loginData = await loginRes.json()
  const token = loginData.access_token
  localStorage.setItem('auth_token', token)
  return token
}

export async function ensureAuth() {
  let token = localStorage.getItem('auth_token')
  let sessionId = localStorage.getItem('session_id')

  if (!token) {
    token = await refreshToken()
  }

  if (!sessionId) {
    const sessionRes = await fetch('/api/session/create', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'Authorization': `Bearer ${token}`
      }
    })
    if (!sessionRes.ok) {
      if (sessionRes.status === 401) {
        localStorage.removeItem('auth_token')
        token = await refreshToken()
        const retryRes = await fetch('/api/session/create', {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Authorization': `Bearer ${token}`
          }
        })
        if (!retryRes.ok) {
          localStorage.removeItem('auth_token')
          throw new Error('创建会话失败')
        }
        const retryData = await retryRes.json()
        sessionId = retryData.session_id
        localStorage.setItem('session_id', sessionId)
        return { token, sessionId }
      }
      localStorage.removeItem('auth_token')
      throw new Error('创建会话失败')
    }
    const sessionData = await sessionRes.json()
    sessionId = sessionData.session_id
    localStorage.setItem('session_id', sessionId)
  }

  return { token, sessionId }
}

export async function forceRefreshAuth() {
  const token = await refreshToken()
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
      throw new Error('创建会话失败')
    }
    const sessionData = await sessionRes.json()
    sessionId = sessionData.session_id
    localStorage.setItem('session_id', sessionId)
  }

  return { token, sessionId }
}

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

export async function createNewSession() {
  // 使用 forceRefreshAuth 确保认证信息准备好
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

  if (response.status === 401) {
    localStorage.removeItem('auth_token')
    await ensureAuth()
    const retryHeaders = {
      'Content-Type': 'application/json',
      ...getAuthHeaders()
    }
    const retryResponse = await fetch('/api/map/knowledge/files', {
      method: 'GET',
      headers: retryHeaders
    })
    if (!retryResponse.ok) {
      throw new Error(`HTTP ${retryResponse.status}: ${retryResponse.statusText}`)
    }
    return retryResponse.json()
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
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

  if (response.status === 401) {
    localStorage.removeItem('auth_token')
    await ensureAuth()
    const retryHeaders = {
      'Content-Type': 'application/json',
      ...getAuthHeaders()
    }
    const retryResponse = await fetch(`/api/map/knowledge/file-preview?path=${encodeURIComponent(path)}`, {
      method: 'GET',
      headers: retryHeaders
    })
    if (!retryResponse.ok) {
      throw new Error(`HTTP ${retryResponse.status}: ${retryResponse.statusText}`)
    }
    return retryResponse.json()
  }

  if (!response.ok) {
    throw new Error(`HTTP ${response.status}: ${response.statusText}`)
  }

  return response.json()
}
