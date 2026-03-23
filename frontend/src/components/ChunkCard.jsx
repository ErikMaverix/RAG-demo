import ScoreBar from './ScoreBar'
import { openSecureFile } from '../api'

export default function ChunkCard({ point, highlight = false }) {
  if (!point) return null

  const chunkId = point?.chunk_id ?? 'ukjent-id'
  const source = point?.source ?? 'ukjent dokument'
  const page = point?.page ? ` · side ${point.page}` : ''
  const text = point?.text ?? ''
  const url = point?.url ?? null
  const score = typeof point?.score === 'number' ? point.score : 0
  const isPdf = source.toLowerCase().endsWith('.pdf')

  async function handleOpenFile(e) {
    e.preventDefault()

    try {
      await openSecureFile(url, source)
    } catch (err) {
      console.error('Kunne ikke åpne fil:', err)
      alert('Kunne ikke åpne eller laste ned filen.')
    }
  }

  return (
    <div
      className={`rounded-lg border p-4 space-y-2 ${
        highlight
          ? 'border-blue-400 bg-blue-50'
          : 'border-gray-200 bg-white'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono font-bold text-sm text-gray-700 shrink-0">
          [{chunkId}]
        </span>

        {url ? (
          <a
            href={url}
            onClick={handleOpenFile}
            className="text-xs text-blue-600 hover:underline truncate"
          >
            {source}
            {page} {isPdf ? '↗' : '⬇'}
          </a>
        ) : (
          <span className="text-xs text-gray-400 truncate">
            {source}
            {page}
          </span>
        )}
      </div>

      <ScoreBar score={score} />

      <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap break-words">
        {text}
      </p>
    </div>
  )
}
