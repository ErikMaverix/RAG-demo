import { useState, useEffect } from 'react'
import { fetchDocuments, deleteDocument, summarizeDocument } from '../api'

export default function DocumentList({ refreshTrigger, model }) {
  const [files, setFiles] = useState([])
  const [deleting, setDeleting] = useState(null)
  const [summaries, setSummaries] = useState({})
  const [summarizing, setSummarizing] = useState(null)

  useEffect(() => {
    async function loadDocuments() {
      try {
        const res = await fetchDocuments()
        const normalized = Array.isArray(res) ? res : res?.files || res?.documents || []
        setFiles(normalized)
      } catch (err) {
        console.error('Kunne ikke hente dokumenter:', err)
        setFiles([])
      }
    }
    loadDocuments()
  }, [refreshTrigger])

  async function handleDelete(filename) {
    if (!confirm(`Slett «${filename}» fra databasen?`)) return
    setDeleting(filename)
    try {
      await deleteDocument(filename)
      setFiles((prev) => prev.filter((f) => f !== filename))
      setSummaries((prev) => {
        const next = { ...prev }
        delete next[filename]
        return next
      })
    } catch (e) {
      alert(`Feil ved sletting: ${e.message}`)
    } finally {
      setDeleting(null)
    }
  }

  async function handleSummarize(filename) {
    if (summaries[filename]) {
      setSummaries((prev) => {
        const next = { ...prev }
        delete next[filename]
        return next
      })
      return
    }
    setSummarizing(filename)
    try {
      const res = await summarizeDocument(filename, model)
      const summary = res?.summary || res?.result || res?.text || 'Ingen oppsummering returnert.'
      setSummaries((prev) => ({ ...prev, [filename]: summary }))
    } catch (e) {
      alert(`Feil ved sammendrag: ${e.message}`)
    } finally {
      setSummarizing(null)
    }
  }

  if (files.length === 0) {
    return (
      <p className="text-xs text-mvx-muted italic">
        Ingen dokumenter indeksert ennå.
      </p>
    )
  }

  return (
    <ul className="space-y-2">
      {files.map((f) => (
        <li key={f} className="border border-mvx-border rounded-xl overflow-hidden">
          <div className="flex items-center justify-between bg-mvx-surface px-3 py-2">
            <span className="text-sm text-white truncate">{f}</span>
            <div className="flex gap-3 shrink-0 ml-3">
              <button
                onClick={() => handleSummarize(f)}
                disabled={summarizing === f || !model}
                className="text-xs text-mvx-accent hover:text-mvx-accent-hover disabled:opacity-40 transition"
              >
                {summarizing === f ? 'Laster…' : summaries[f] ? 'Skjul' : '📄 Sammendrag'}
              </button>
              <button
                onClick={() => handleDelete(f)}
                disabled={deleting === f}
                className="text-xs text-mvx-danger hover:opacity-70 disabled:opacity-40 transition"
              >
                {deleting === f ? 'Sletter…' : '🗑 Slett'}
              </button>
            </div>
          </div>
          {summaries[f] && (
            <div className="px-3 py-2 text-xs text-white/70 leading-relaxed border-t border-mvx-border bg-mvx-bg whitespace-pre-wrap">
              {summaries[f]}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
