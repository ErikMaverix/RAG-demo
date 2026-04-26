import { useState } from 'react'

export default function Collapsible({ title, children, defaultOpen = false }) {
  const [open, setOpen] = useState(defaultOpen)
  return (
    <div className="border border-mvx-border rounded-xl overflow-hidden">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex justify-between items-center px-4 py-3 bg-mvx-surface hover:bg-mvx-border/40 text-sm font-medium text-white transition"
      >
        {title}
        <span className="text-mvx-muted">{open ? '▲' : '▼'}</span>
      </button>
      {open && <div className="px-4 py-3 bg-mvx-bg">{children}</div>}
    </div>
  )
}
