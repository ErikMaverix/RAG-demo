import { useState } from 'react'
import ChunkCard from './ChunkCard'

export default function HistoryItem({ item, index }) {
  const [copied, setCopied] = useState(false)
  const [showSources, setShowSources] = useState(false)

  function handleCopy() {
    navigator.clipboard.writeText(item.answer)
    setCopied(true)
    setTimeout(() => setCopied(false), 2000)
  }

  function handleDownload() {
    const lines = []
    lines.push('RAG-SVAR')
    lines.push('========')
    lines.push(`Spørsmål: ${item.query}`)
    lines.push(`Dato: ${item.timestamp}`)
    lines.push('')
    lines.push('SVAR')
    lines.push('----')
    lines.push(item.answer)
    if (item.notes) {
      lines.push('')
      lines.push(`Merknad: ${item.notes}`)
    }
    lines.push('')
    lines.push('KILDER BRUKT I SVARET')
    lines.push('---------------------')
    item.usedPoints.forEach(p => {
      lines.push(`[${p.chunk_id}] ${p.source}${p.page ? ` · side ${p.page}` : ''} (relevans: ${Math.round(p.score * 100)}%)`)
      lines.push(p.text)
      lines.push('')
    })

    const blob = new Blob([lines.join('\n')], { type: 'text/plain;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `rag-svar-${new Date().toISOString().slice(0, 10)}-${index + 1}.txt`
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <div className="bg-white border border-gray-200 rounded-lg overflow-hidden">
      {/* Question */}
      <div className="bg-gray-50 border-b border-gray-200 px-4 py-2 flex items-center justify-between">
        <span className="text-sm font-medium text-gray-700">❓ {item.query}</span>
        <span className="text-xs text-gray-400">{item.timestamp}</span>
      </div>

      {/* Answer */}
      <div className="px-4 py-3 text-sm text-gray-800 leading-relaxed">
        {item.answer}
      </div>

      {item.notes && (
        <div className="mx-4 mb-2 bg-blue-50 border border-blue-200 text-blue-700 rounded-lg px-3 py-2 text-sm">
          {item.notes}
        </div>
      )}

      {/* Actions */}
      <div className="px-4 pb-3 flex gap-2">
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
        {item.usedPoints.length > 0 && (
          <button
            onClick={() => setShowSources(s => !s)}
            className="text-xs px-3 py-1.5 rounded-lg border border-gray-300 text-gray-600 hover:bg-gray-100 transition"
          >
            {showSources ? 'Skjul kilder' : `📄 Vis ${item.usedPoints.length} kilder`}
          </button>
        )}
      </div>

      {/* Sources (collapsible) */}
      {showSources && item.usedPoints.length > 0 && (
        <div className="px-4 pb-4 space-y-2 border-t border-gray-100 pt-3">
          <p className="text-xs text-gray-400">Her ser du nøyaktig hvilke deler av dokumentene AI-en baserte svaret sitt på.</p>
          {item.usedPoints.map(p => (
            <ChunkCard key={p.chunk_id} point={p} highlight />
          ))}
        </div>
      )}
    </div>
  )
}
