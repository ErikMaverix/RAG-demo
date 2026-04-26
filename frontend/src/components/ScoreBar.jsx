export default function ScoreBar({ score }) {
  const pct = Math.round(score * 100)
  const color =
    pct >= 70 ? 'bg-mvx-signal' : pct >= 40 ? 'bg-yellow-400' : 'bg-mvx-danger'

  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="w-10 text-right text-mvx-muted">{pct}%</span>
      <div className="flex-1 h-1.5 bg-mvx-bg rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}
