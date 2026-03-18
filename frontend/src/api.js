const BASE = '/api'

export async function fetchModels() {
  const r = await fetch(`${BASE}/models`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function indexDocuments({ files, manualText, chunkSize, overlap }) {
  const form = new FormData()
  for (const f of files) form.append('files', f)
  form.append('manual_text', manualText || '')
  form.append('chunk_size', chunkSize)
  form.append('overlap', overlap)

  const r = await fetch(`${BASE}/index`, { method: 'POST', body: form })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}

export async function searchDocuments({ query, k, minScore, scoreThreshold }) {
  const r = await fetch(`${BASE}/search`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, k, min_score: minScore, score_threshold: scoreThreshold }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}

export async function ragAnswer({ query, points, model }) {
  const r = await fetch(`${BASE}/rag`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, points, model }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}

export async function deleteCollection() {
  const r = await fetch(`${BASE}/collection`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function fetchDocuments() {
  const r = await fetch(`${BASE}/documents`)
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function deleteDocument(filename) {
  const r = await fetch(`${BASE}/documents/${encodeURIComponent(filename)}`, { method: 'DELETE' })
  if (!r.ok) throw new Error(await r.text())
  return r.json()
}

export async function* ragAnswerStream({ query, points, model }) {
  const r = await fetch(`${BASE}/rag/stream`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ query, points, model }),
  })
  if (!r.ok) throw new Error(await r.text())

  const reader = r.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop()
    for (const line of lines) {
      if (line.startsWith('data: ')) {
        yield JSON.parse(line.slice(6))
      }
    }
  }
}

export async function summarizeDocument(filename, model) {
  const r = await fetch(`${BASE}/summarize/${encodeURIComponent(filename)}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ model }),
  })
  if (!r.ok) {
    const err = await r.json().catch(() => ({ detail: r.statusText }))
    throw new Error(err.detail || r.statusText)
  }
  return r.json()
}
