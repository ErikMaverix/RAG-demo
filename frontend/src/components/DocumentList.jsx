import { useState, useEffect } from 'react'
import { fetchDocuments, deleteDocument, summarizeDocument } from '../api'

export default function DocumentList({ refreshTrigger, model }) {
  const [files, setFiles] = useState([])
  const [deleting, setDeleting] = useState(null)
  const [summaries, setSummaries] = useState({})
  const [summarizing, setSummarizing] = useState(null)

  useEffect(() => {
    fetchDocuments().then(res => setFiles(res.files)).catch(() => setFiles([]))
  }, [refreshTrigger])

  async function handleDelete(filename) {
    if (!confirm(`Slett «${filename}» fra databasen?`)) return
    setDeleting(filename)
    try {
      await deleteDocument(filename)
      setFiles(prev => prev.filter(f => f !== filename))
      setSummaries(prev => { const s = { ...prev }; delete s[filename]; return s })
    } catch (e) {
      alert(`Feil ved sletting: ${e.message}`)
    } finally {
      setDeleting(null)
    }
  }

  async function handleSummarize(filename) {
    if (summaries[filename]) {
      // Toggle off
      setSummaries(prev => { const s = { ...prev }; delete s[filename]; return s })
      return
    }
    setSummarizing(filename)
    try {
      const res = await summarizeDocument(filename, model)
      setSummaries(prev => ({ ...prev, [filename]: res.summary }))
    } catch (e) {
      alert(`Feil ved sammendrag: ${e.message}`)
    } finally {
      setSummarizing(null)
    }
  }

  if (files.length === 0) return (
    <p className="text-xs text-gray-400 italic">Ingen dokumenter indeksert ennå.</p>
  )

  return (
    <ul className="space-y-2">
      {files.map(f => (
        <li key={f} className="border border-gray-200 rounded-lg overflow-hidden">
          <div className="flex items-center justify-between bg-gray-50 px-3 py-2">
            <span className="text-sm text-gray-700 truncate">{f}</span>
            <div className="flex gap-2 shrink-0 ml-3">
              <button
                onClick={() => handleSummarize(f)}
                disabled={summarizing === f}
                className="text-xs text-blue-600 hover:text-blue-800 disabled:opacity-40 transition"
              >
                {summarizing === f ? 'Laster…' : summaries[f] ? 'Skjul' : '📄 Sammendrag'}
              </button>
              <button
                onClick={() => handleDelete(f)}
                disabled={deleting === f}
                className="text-xs text-red-500 hover:text-red-700 disabled:opacity-40 transition"
              >
                {deleting === f ? 'Sletter…' : '🗑 Slett'}
              </button>
            </div>
          </div>
          {summaries[f] && (
            <div className="px-3 py-2 text-xs text-gray-600 leading-relaxed border-t border-gray-100 bg-white">
              {summaries[f]}
            </div>
          )}
        </li>
      ))}
    </ul>
  )
}
