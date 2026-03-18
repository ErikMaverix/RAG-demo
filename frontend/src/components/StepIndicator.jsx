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
              <div className={`h-px w-6 mx-1 ${isDone ? 'bg-green-400' : 'bg-gray-300'}`} />
            )}
            <div className={`flex items-center gap-1.5 px-2 py-1 rounded-full text-xs font-medium
              ${isActive ? 'bg-blue-100 text-blue-700' : isDone ? 'bg-green-100 text-green-700' : 'text-gray-400'}`}>
              {isActive && (
                <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin inline-block" />
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
