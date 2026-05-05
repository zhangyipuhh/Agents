const CHUNK_SIZE = 256 * 1024

function generateFileId() {
  return `${Date.now()}-${Math.random().toString(36).substring(2, 11)}`
}

function getAuthHeaders() {
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

export async function ensureAuth() {
  let token = localStorage.getItem('auth_token')
  let sessionId = localStorage.getItem('session_id')

  if (!token) {
    const loginRes = await fetch('/api/auth/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username: 'admin', password: '123456' })
    })
    if (!loginRes.ok) {
      throw new Error('登录失败')
    }
    const loginData = await loginRes.json()
    token = loginData.access_token
    localStorage.setItem('auth_token', token)
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
    if (!res.ok) {
      return res.json().then(err => { throw new Error(err.detail || '合并失败') })
    }
    return res.json()
  })
}

export async function uploadFileInChunks(file, onProgress, onCancel) {
  await ensureAuth()

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

      await uploadChunk(fileId, i, totalChunks, file.name, chunkBlob)

      completedChunks++
      if (onProgress) {
        onProgress(Math.round((completedChunks / totalChunks) * 100))
      }
    }

    if (cancelled) {
      throw new Error('上传已取消')
    }

    const result = await mergeChunks(fileId, file.name, totalChunks)
    return result
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
