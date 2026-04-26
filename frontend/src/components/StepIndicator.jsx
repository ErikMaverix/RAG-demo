const STEPS = [
  { id: 'searching', label: 'Søker i dokumenter' },
  { id: 'generating', label: 'Genererer svar' },
]

export default function StepIndicator({ step }) {
  const activeIndex = STEPS.findIndex(s => s.id === step)

  return (
    <div className="flex items-center gap-1 py-2 text-sm">
      {STEPS.map((s, i) => {
        const isActive = i === activeIndex
        const isDone = i < activeIndex
        return (
          <div key={s.id} className="flex items-center gap-1">
            {i > 0 && (
              <div className={`h-px w-6 mx-1 ${isDone ? 'bg-mvx-signal' : 'bg-mvx-border'}`} />
            )}
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium
              ${isActive ? 'bg-mvx-accent/20 text-mvx-accent' : isDone ? 'bg-mvx-signal/20 text-mvx-signal' : 'text-mvx-muted'}`}>
              {isActive && (
                <span className="w-3 h-3 border-2 border-mvx-accent border-t-transparent rounded-full animate-spin inline-block" />
              )}
              {isDone && <span>✓</span>}
              {s.label}
            </div>
          </div>
        )
      })}
    </div>
  )
}
