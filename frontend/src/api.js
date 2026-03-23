const BASE = import.meta.env.VITE_API_BASE_URL

if (!BASE) {
  throw new Error('Mangler VITE_API_BASE_URL i miljøvariablene')
}

// Token provider (settes fra App.jsx)
let getToken = null

export function setTokenGetter(fn) {
  getToken = fn
}

async function getAuthHeaders(extraHeaders = {}) {
  const headers = { ...extraHeaders }

  if (getToken) {
    try {
      const token = await getToken()
      if (token) {
        headers.Authorization = `Bearer ${token}`
      }
    } catch (err) {
      console.warn('Kunne ikke hente token:', err)
    }
  }

  return headers
}

async function parseErrorResponse(response) {
  try {
    const data = await response.json()
    return data?.detail || data?.message || response.statusText
  } catch {
    try {
      return await response.text()
    } catch {
      return response.statusText
    }
  }
}

async function ensureOk(response) {
  if (!response.ok) {
    const message = await parseErrorResponse(response)
    throw new Error(message || 'Ukjent feil')
  }
  return response
}

export async function fetchModels() {
  const response = await fetch(`${BASE}/models`, {
    headers: await getAuthHeaders(),
  })
  await ensureOk(response)
  return response.json()
}

export async function indexDocuments({ files = [], manualText = '', chunkSize = 600, overlap = 100 }) {
  const form = new FormData()

  for (const file of files) {
    form.append('files', file)
  }

  form.append('manual_text', manualText || '')
  form.append('chunk_size', String(chunkSize))
  form.append('overlap', String(overlap))

  const response = await fetch(`${BASE}/index`, {
    method: 'POST',
    headers: await getAuthHeaders(),
    body: form,
  })

  await ensureOk(response)
  return response.json()
}

export async function searchDocuments({ query, k = 5, minScore = 0.15, scoreThreshold = 0.15 }) {
  const response = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: await getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      query,
      top_k: k,
      min_score: minScore,
      score_threshold: scoreThreshold,
    }),
  })

  await ensureOk(response)
  return response.json()
}

export async function ragAnswer({ query, points, model }) {
  const response = await fetch(`${BASE}/rag`, {
    method: 'POST',
    headers: await getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      query,
      points,
      model,
    }),
  })

  await ensureOk(response)
  return response.json()
}

export async function deleteCollection() {
  const response = await fetch(`${BASE}/collection`, {
    method: 'DELETE',
    headers: await getAuthHeaders(),
  })

  await ensureOk(response)
  return response.json()
}

export async function fetchDocuments() {
  const response = await fetch(`${BASE}/documents`, {
    headers: await getAuthHeaders(),
  })
  await ensureOk(response)
  return response.json()
}

export async function deleteDocument(filename) {
  const response = await fetch(`${BASE}/documents/${encodeURIComponent(filename)}`, {
    method: 'DELETE',
    headers: await getAuthHeaders(),
  })

  await ensureOk(response)
  return response.json()
}

export async function* ragAnswerStream({ query, points, model }) {
  const response = await fetch(`${BASE}/rag/stream`, {
    method: 'POST',
    headers: await getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({
      query,
      points,
      model,
    }),
  })

  await ensureOk(response)

  if (!response.body) {
    throw new Error('Streaming er ikke tilgjengelig')
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break

    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''

    for (const line of lines) {
      const trimmed = line.trim()
      if (!trimmed.startsWith('data: ')) continue

      const payload = trimmed.slice(6)

      if (!payload || payload === '[DONE]') continue

      try {
        yield JSON.parse(payload)
      } catch (err) {
        console.warn('Feil parsing av stream:', payload)
      }
    }
  }
}

export async function summarizeDocument(filename, model) {
  const response = await fetch(`${BASE}/summarize/${encodeURIComponent(filename)}`, {
    method: 'POST',
    headers: await getAuthHeaders({
      'Content-Type': 'application/json',
    }),
    body: JSON.stringify({ model }),
  })

  await ensureOk(response)
  return response.json()
}

export async function openSecureFile(url) {
  if (!url) return

  const [path, hash] = url.split('#')

  const response = await fetch(`${BASE}${path}`, {
    headers: await getAuthHeaders(),
  })

  await ensureOk(response)

  const blob = await response.blob()
  const blobUrl = URL.createObjectURL(blob)
  const finalUrl = hash ? `${blobUrl}#${hash}` : blobUrl

  window.open(finalUrl, '_blank', 'noopener,noreferrer')

  setTimeout(() => {
    URL.revokeObjectURL(blobUrl)
  }, 60000)
}
