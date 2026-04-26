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
      className={`rounded-xl border p-4 space-y-2 ${
        highlight
          ? 'border-mvx-accent/40 bg-mvx-accent/5'
          : 'border-mvx-border bg-mvx-surface'
      }`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-mono font-bold text-sm text-mvx-accent shrink-0">
          [{chunkId}]
        </span>

        {url ? (
          <a
            href={url}
            onClick={handleOpenFile}
            className="text-xs text-mvx-accent hover:underline truncate"
          >
            {source}{page} {isPdf ? '↗' : '⬇'}
          </a>
        ) : (
          <span className="text-xs text-mvx-muted truncate">
            {source}{page}
          </span>
        )}
      </div>

      <ScoreBar score={score} />

      <p className="text-sm text-white/80 leading-relaxed whitespace-pre-wrap break-words">
        {text}
      </p>
    </div>
  )
}
