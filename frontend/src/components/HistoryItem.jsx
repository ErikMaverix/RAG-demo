import { useState } from 'react'
import ChunkCard from './ChunkCard'

export default function HistoryItem({ item, index }) {
  const [copied, setCopied] = useState(false)
  const [showSources, setShowSources] = useState(false)

  const usedPoints = Array.isArray(item?.usedPoints) ? item.usedPoints : []
  const answer = item?.answer || ''
  const query = item?.query || 'Ukjent spørsmål'
  const timestamp = item?.timestamp || ''

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(answer)
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    } catch (err) {
      console.error('Kunne ikke kopiere:', err)
      alert('Kunne ikke kopiere svaret.')
    }
  }

  function handleDownload() {
    const lines = []

    lines.push('RAG-SVAR')
    lines.push('========')
    lines.push(`Spørsmål: ${query}`)
    lines.push(`Dato: ${timestamp}`)
    lines.push('')
    lines.push('SVAR')
    lines.push('----')
    lines.push(answer)

    if (item?.notes) {
      lines.push('')
      lines.push(`Merknad: ${item.notes}`)
    }

    lines.push('')
    lines.push('KILDER BRUKT I SVARET')
    lines.push('---------------------')

    usedPoints.forEach((p) => {
      const chunkId = p?.chunk_id || 'ukjent-id'
      const source = p?.source || 'ukjent dokument'
      const page = p?.page ? ` · side ${p.page}` : ''
      const score =
        typeof p?.score === 'number'
          ? ` (relevans: ${Math.round(p.score * 100)}%)`
          : ''

      lines.push(`[${chunkId}] ${source}${page}${score}`)
      lines.push(p?.text || '')
      lines.push('')
    })

    const blob = new Blob([lines.join('\n')], {
      type: 'text/plain;charset=utf-8',
    })

    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rag-svar-${new Date().toISOString().slice(0, 10)}-${index + 1}.txt`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between gap-3">
        <span className="text-sm font-medium text-gray-700">❓ {query}</span>
        <span className="text-xs text-gray-400 shrink-0">{timestamp}</span>
      </div>

      <div className="px-4 py-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
        {answer}
      </div>

      {item?.notes && (
        <div className="mx-4 mb-2 bg-blue-50 border border-blue-200 text-blue-700 rounded-lg px-3 py-2 text-sm">
          {item.notes}
        </div>
      )}

      <div className="px-4 pb-3 flex gap-2 flex-wrap">
        <button
          onClick={handleCopy}
          className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition"
        >
          {copied ? '✓ Kopiert' : '📋 Kopier svar'}
        </button>

        <button
          onClick={handleDownload}
          className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition"
        >
          ⬇ Last ned
        </button>

        {usedPoints.length > 0 && (
          <button
            onClick={() => setShowSources((s) => !s)}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition"
          >
            {showSources ? 'Skjul kilder' : `📄 Vis ${usedPoints.length} kilder`}
          </button>
        )}
      </div>

      {showSources && usedPoints.length > 0 && (
        <div className="px-4 pb-4 space-y-2 border-t border-gray-100 pt-3">
          <p className="text-xs text-gray-400">
            Her ser du nøyaktig hvilke deler av dokumentene AI-en baserte svaret sitt på.
          </p>

          {usedPoints.map((p) => (
            <ChunkCard key={p.chunk_id || Math.random()} point={p} highlight />
          ))}
        </div>
      )}
    </div>
  )
}
