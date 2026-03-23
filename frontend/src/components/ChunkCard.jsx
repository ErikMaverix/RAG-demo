import ScoreBar from './ScoreBar'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || ''

function resolveUrl(url) {
  if (!url) return null

  // Hvis allerede full URL → bruk som den er
  if (url.startsWith('http://') || url.startsWith('https://')) {
    return url
  }

  // Hvis starter med / → legg til backend base URL
  if (url.startsWith('/')) {
    return `${API_BASE_URL}${url}`
  }

  // fallback
  return `${API_BASE_URL}/${url}`
}

export default function ChunkCard({ point, highlight = false }) {
  if (!point) return null

  const chunkId = point?.chunk_id ?? 'ukjent-id'
  const source = point?.source ?? 'ukjent dokument'
  const page = point?.page ? ` · side ${point.page}` : ''
  const text = point?.text ?? ''
  const url = resolveUrl(point?.url ?? null)
  const score = typeof point?.score === 'number' ? point.score : 0

  return (
    <div
      className={`rounded-lg border p-4 space-y-2 ${
        highlight
          ? 'border-blue-400 bg-blue-50'
          : 'border-gray-200 bg-white'
      }`}
    >
      {/* Header */}
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono font-bold text-sm text-gray-700 shrink-0">
          [{chunkId}]
        </span>

        {url ? (
          <a
            href={url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-blue-600 hover:underline truncate"
          >
            {source}
            {page} ↗
          </a>
        ) : (
          <span className="text-xs text-gray-400 truncate">
            {source}
            {page}
          </span>
        )}
      </div>

      {/* Score */}
      <ScoreBar score={score} />

      {/* Text */}
      <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap break-words">
        {text}
      </p>
    </div>
  )
}
