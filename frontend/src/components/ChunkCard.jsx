import ScoreBar from './ScoreBar'

export default function ChunkCard({ point, highlight = false }) {
  return (
    <div className={`rounded-lg border p-4 space-y-2 ${highlight ? 'border-blue-400 bg-blue-50' : 'border-gray-200 bg-white'}`}>
      <div className="flex items-center justify-between">
        <span className="font-mono font-bold text-sm text-gray-700">[{point.chunk_id}]</span>
        {point.url ? (
          <a
            href={point.url}
            target="_blank"
            rel="noreferrer"
            className="text-xs text-blue-600 hover:underline"
          >
            {point.source}{point.page ? ` · side ${point.page}` : ''} ↗
          </a>
        ) : (
          <span className="text-xs text-gray-400">
            {point.source}{point.page ? ` · side ${point.page}` : ''}
          </span>
        )}
      </div>
      <ScoreBar score={point.score} />
      <p className="text-sm text-gray-600 leading-relaxed whitespace-pre-wrap">{point.text}</p>
    </div>
  )
}
