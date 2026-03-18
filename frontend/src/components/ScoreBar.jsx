export default function ScoreBar({ score }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-green-500' : pct >= 40 ? 'bg-yellow-400' : 'bg-red-400'

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-10 text-right text-gray-500">{pct}%</span>
      <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
