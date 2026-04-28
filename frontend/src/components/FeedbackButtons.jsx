import { useState } from 'react'
import { submitFeedback } from '../api'

const CATEGORIES = [
  'Feil informasjon',
  'Hallusinasjon',
  'Forsto ikke spørsmålet',
  'Teknisk feil',
  'Annet',
]

export default function FeedbackButtons({ item, conversationId }) {
  const [state, setState] = useState('idle') // 'idle' | 'form' | 'submitted' | 'error'
  const [category, setCategory] = useState('')
  const [comment, setComment] = useState('')
  const [submitting, setSubmitting] = useState(false)

  async function send(rating, cat = null, com = '') {
    setSubmitting(true)
    try {
      await submitFeedback({
        conversation_id: conversationId,
        message_id: item.messageId,
        rating,
        category: cat || null,
        comment: com.trim() || null,
        query: item.query,
        answer: item.answer,
        model: item.model,
        search_results: (item.searchPoints || []).map((p) => ({
          chunk_id: p.chunk_id,
          source: p.source,
          score: p.score,
          text: p.text,
        })),
        used_chunks: (item.usedPoints || []).map((p) => p.chunk_id),
        latency_search_ms: item.latencySearchMs ?? null,
        latency_generation_ms: item.latencyGenerationMs ?? null,
      })
      setState('submitted')
    } catch {
      setState('error')
    } finally {
      setSubmitting(false)
    }
  }

  if (state === 'submitted') {
    return (
      <span className="text-xs text-mvx-signal">✓ Takk for tilbakemeldingen</span>
    )
  }

  if (state === 'error') {
    return (
      <button
        onClick={() => setState('idle')}
        className="text-xs text-mvx-danger hover:underline"
      >
        Klarte ikke sende — prøv igjen
      </button>
    )
  }

  return (
    <div className="space-y-2 w-full">
      <div className="flex items-center gap-2">
        <span className="text-xs text-mvx-muted">Nyttig svar?</span>
        <button
          onClick={() => send(1)}
          disabled={submitting || state === 'form'}
          title="Bra svar"
          className="text-sm px-2.5 py-1 rounded-lg border border-mvx-border text-white/60 hover:border-mvx-signal hover:text-mvx-signal disabled:opacity-40 transition"
        >
          👍
        </button>
        <button
          onClick={() => setState('form')}
          disabled={submitting}
          title="Dårlig svar"
          className={`text-sm px-2.5 py-1 rounded-lg border transition disabled:opacity-40 ${
            state === 'form'
              ? 'border-mvx-danger text-mvx-danger'
              : 'border-mvx-border text-white/60 hover:border-mvx-danger hover:text-mvx-danger'
          }`}
        >
          👎
        </button>
      </div>

      {state === 'form' && (
        <div className="bg-mvx-bg border border-mvx-border rounded-xl p-3 space-y-3">
          <p className="text-xs font-medium text-white/80">Hva var galt?</p>

          <div className="flex flex-wrap gap-2">
            {CATEGORIES.map((cat) => (
              <button
                key={cat}
                onClick={() => setCategory(cat)}
                className={`text-xs px-3 py-1.5 rounded-lg border transition ${
                  category === cat
                    ? 'border-mvx-accent bg-mvx-accent/10 text-mvx-accent'
                    : 'border-mvx-border text-white/60 hover:border-mvx-accent/60 hover:text-white/80'
                }`}
              >
                {cat}
              </button>
            ))}
          </div>

          <textarea
            placeholder="Kommentar (valgfritt)"
            value={comment}
            onChange={(e) => setComment(e.target.value)}
            rows={2}
            className="w-full bg-mvx-surface border border-mvx-border rounded-xl px-3 py-2 text-xs text-white placeholder-mvx-muted resize-none focus:outline-none focus:border-mvx-accent transition"
          />

          <div className="flex gap-2">
            <button
              onClick={() => send(-1, category, comment)}
              disabled={submitting || !category}
              className="text-xs px-3 py-1.5 rounded-lg bg-mvx-accent text-white hover:bg-mvx-accent-hover disabled:opacity-40 transition"
            >
              {submitting ? 'Sender…' : 'Send tilbakemelding'}
            </button>
            <button
              onClick={() => { setState('idle'); setCategory(''); setComment('') }}
              disabled={submitting}
              className="text-xs px-3 py-1.5 rounded-lg border border-mvx-border text-white/60 hover:text-white/80 transition"
            >
              Avbryt
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
