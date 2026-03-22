import { useState, useEffect } from 'react'
import { useAuth0 } from '@auth0/auth0-react'
import {
  fetchModels,
  indexDocuments,
  searchDocuments,
  ragAnswerStream,
  deleteCollection,
  fetchDocuments,
  setTokenGetter,
} from './api'

import ChunkCard from './components/ChunkCard'
import Collapsible from './components/Collapsible'
import HistoryItem from './components/HistoryItem'
import DocumentList from './components/DocumentList'
import StepIndicator from './components/StepIndicator'

export default function App() {
  const {
    loginWithRedirect,
    logout,
    user,
    isAuthenticated,
    isLoading,
    getAccessTokenSilently,
  } = useAuth0()

  // ---------- Models ----------
  const [models, setModels] = useState([])
  const [selectedModel, setSelectedModel] = useState('')

  useEffect(() => {
    setTokenGetter(async () => {
      if (!isAuthenticated) return null

      return await getAccessTokenSilently({
        authorizationParams: {
          audience: import.meta.env.VITE_AUTH0_AUDIENCE,
        },
      })
    })
  }, [isAuthenticated, getAccessTokenSilently])

  useEffect(() => {
    async function loadModels() {
      if (!isAuthenticated) return

      try {
        const data = await fetchModels()

        const normalized = Array.isArray(data)
          ? data.map((m) => ({
              id: m.id,
              label: m.label || m.id,
              provider: m.provider || '',
            }))
          : []

        setModels(normalized)

        if (normalized.length > 0) {
          setSelectedModel(normalized[0].id)
        }
      } catch (err) {
        console.error('Kunne ikke hente modeller:', err)
      }
    }

    loadModels()
  }, [isAuthenticated])

  // ---------- Index state ----------
  const [files, setFiles] = useState([])
  const [manualText, setManualText] = useState('')
  const [chunkSize, setChunkSize] = useState(600)
  const [overlap, setOverlap] = useState(100)
  const [indexStatus, setIndexStatus] = useState(null)
  const [indexing, setIndexing] = useState(false)

  // ---------- Search state ----------
  const [query, setQuery] = useState('')
  const [k, setK] = useState(5)
  const [minScore] = useState(0.15)
  const [scoreThreshold, setScoreThreshold] = useState(0.15)
  const [searchPoints, setSearchPoints] = useState([])
  const [searchQuery, setSearchQuery] = useState('')
  const [filteredCount, setFilteredCount] = useState(0)
  const [searching, setSearching] = useState(false)
  const [searchError, setSearchError] = useState(null)

  // ---------- RAG / history state ----------
  const [history, setHistory] = useState([])
  const [ragLoading, setRagLoading] = useState(false)
  const [ragError, setRagError] = useState(null)
  const [ragStep, setRagStep] = useState(null)
  const [streamingText, setStreamingText] = useState('')

  // ---------- Document list refresh trigger ----------
  const [docRefresh, setDocRefresh] = useState(0)

  // ---------- Handlers ----------

  async function handleIndex() {
    if (files.length > 0) {
      try {
        const docsResponse = await fetchDocuments()
        const indexed = Array.isArray(docsResponse)
          ? docsResponse
          : docsResponse?.files || docsResponse?.documents || []

        const dupes = files.map((f) => f.name).filter((n) => indexed.includes(n))

        if (dupes.length > 0) {
          const ok = confirm(
            `Disse filene er allerede indeksert:\n${dupes.join('\n')}\n\nVil du indeksere dem på nytt?`
          )
          if (!ok) return
        }
      } catch (_) {
        // ignorer og fortsett
      }
    }

    setIndexing(true)
    setIndexStatus(null)

    try {
      const res = await indexDocuments({ files, manualText, chunkSize, overlap })
      const indexedCount =
        res?.indexed ??
        res?.indexed_chunks ??
        res?.count ??
        'ukjent antall'

      setIndexStatus({
        ok: true,
        message: `Indeksert ${indexedCount} tekstbiter.`,
      })
      setDocRefresh((n) => n + 1)
      setFiles([])
      setManualText('')
    } catch (e) {
      setIndexStatus({ ok: false, message: e.message })
    } finally {
      setIndexing(false)
    }
  }

  async function handleDelete() {
    if (!confirm('Slett alle dokumenter fra databasen?')) return

    try {
      await deleteCollection()
      setSearchPoints([])
      setHistory([])
      setStreamingText('')
      setQuery('')
      setIndexStatus({ ok: true, message: 'Database tømt.' })
      setDocRefresh((n) => n + 1)
    } catch (e) {
      setIndexStatus({ ok: false, message: e.message })
    }
  }

  async function handleSearch() {
    if (!query.trim()) return

    setSearching(true)
    setSearchError(null)
    setRagError(null)
    setSearchPoints([])

    try {
      const res = await searchDocuments({
        query,
        k,
        minScore,
        scoreThreshold,
      })

      setSearchPoints(res?.points || [])
      setSearchQuery(query)
      setFilteredCount(res?.filtered_count || 0)
    } catch (e) {
      setSearchError(e.message)
    } finally {
      setSearching(false)
    }
  }

  async function handleRag() {
    if (!query.trim()) return

    setRagLoading(true)
    setRagError(null)
    setSearchError(null)
    setStreamingText('')

    try {
      let points = searchPoints
      let usedQuery = searchQuery
      let currentFilteredCount = filteredCount

      if (!points.length || searchQuery !== query) {
        setRagStep('searching')

        const res = await searchDocuments({
          query,
          k,
          minScore,
          scoreThreshold,
        })

        points = res?.points || []
        usedQuery = query
        currentFilteredCount = res?.filtered_count || 0

        setSearchPoints(points)
        setSearchQuery(query)
        setFilteredCount(currentFilteredCount)
      }

      if (!points.length) {
        setRagError(
          'Ingen relevante tekstbiter funnet. Prøv et annet spørsmål eller senk relevansterskelen.'
        )
        return
      }

      setRagStep('generating')

      let accText = ''

      for await (const event of ragAnswerStream({
        query: usedQuery,
        points,
        model: selectedModel,
      })) {
        if (event.type === 'token') {
          accText += event.text || ''
          setStreamingText(accText)
        } else if (event.type === 'done') {
          const byId = Object.fromEntries(points.map((p) => [p.chunk_id, p]))
          const usedPoints = (event.used_chunks || [])
            .map((id) => byId[id])
            .filter(Boolean)

          setHistory((prev) => [
            {
              id: Date.now(),
              query: usedQuery,
              answer: event.answer || accText,
              notes: '',
              usedPoints,
              searchPoints: points,
              filteredCount: currentFilteredCount,
              timestamp: new Date().toLocaleString('no-NO'),
            },
            ...prev,
          ])

          setStreamingText('')
          setQuery('')
        }
      }
    } catch (e) {
      setRagError(e.message)
    } finally {
      setRagLoading(false)
      setSearching(false)
      setRagStep(null)
    }
  }

  const EXAMPLE_QUESTIONS = [
    'Hva er de viktigste funnene?',
    'Hva anbefaler rapporten?',
    'Hva er konklusjonen?',
    'Hvilke risikoer er nevnt?',
    'Hvem er dokumentene rettet mot?',
  ]

  if (isLoading) {
    return (
      <div className="min-h-screen flex items-center justify-center bg-gray-50 text-gray-700">
        Laster inn autentisering…
      </div>
    )
  }

  if (!isAuthenticated) {
    return (
      <div className="min-h-screen bg-gray-50 text-gray-800 flex items-center justify-center px-4">
        <div className="max-w-md w-full bg-white border border-gray-200 rounded-xl p-6 text-center space-y-4 shadow-sm">
          <img
            src="Symbol-White.png"
            alt="Logo"
            className="w-16 h-16 mx-auto bg-gray-900 rounded-lg p-2"
          />
          <h1 className="text-2xl font-bold">RAG Demo</h1>
          <p className="text-sm text-gray-500">
            Du må logge inn for å bruke løsningen.
          </p>
          <button
            onClick={() => loginWithRedirect()}
            className="w-full py-2 px-4 rounded-lg bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 transition"
          >
            Logg inn
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="min-h-screen bg-gray-50 text-gray-800">
      <header className="bg-gray-900 text-white py-6 px-4 flex flex-col items-center gap-2">
        <img src="Symbol-White.png" alt="Logo" className="w-20 h-20" />
        <h1 className="text-2xl font-bold tracking-tight">RAG Demo</h1>
        <p className="text-sm text-gray-400 max-w-xl text-center">
          Last opp dokumenter, still spørsmål — AI svarer kun basert på dine egne kilder.
        </p>

        <div className="flex items-center gap-3 mt-2">
          <span className="text-xs text-gray-300">
            {user?.name || user?.email}
          </span>
          <button
            onClick={() =>
              logout({
                logoutParams: { returnTo: window.location.origin },
              })
            }
            className="px-3 py-1.5 rounded-lg bg-white text-gray-900 text-xs font-medium hover:bg-gray-100 transition"
          >
            Logg ut
          </button>
        </div>
      </header>

      <main className="max-w-3xl mx-auto px-4 py-8 space-y-8">
        <div className="bg-white border border-gray-200 rounded-lg px-5 py-4 text-sm text-gray-700 space-y-2 leading-relaxed">
          <p>
            <strong>Hva er dette?</strong>
            <br />
            Denne appen demonstrerer <em>Retrieval-Augmented Generation</em> (RAG) — en metode der en AI-modell svarer på spørsmål <strong>kun basert på dokumenter du selv laster opp</strong>, i stedet for generell kunnskap. Hvert svar kommer med kildehenvisning til nøyaktig hvilket dokument og hvilken side svaret er hentet fra.
          </p>
          <p>
            <strong>Slik fungerer det i tre steg:</strong>
          </p>
          <ol className="list-decimal list-inside space-y-1 pl-1">
            <li>Du laster opp dokumenter — de deles opp i tekstbiter og lagres i en vektordatabase</li>
            <li>Du stiller et spørsmål — appen finner de mest relevante tekstbitene ved hjelp av semantisk søk</li>
            <li>AI-modellen formulerer et svar <strong>kun</strong> basert på de funnede tekstbitene, med kildehenvisning</li>
          </ol>
        </div>

        <div className="flex items-center gap-3">
          <label className="text-sm font-medium text-gray-600 whitespace-nowrap">AI-modell:</label>
          <select
            value={selectedModel}
            onChange={(e) => setSelectedModel(e.target.value)}
            className="flex-1 border border-gray-300 rounded-lg px-3 py-2 text-sm bg-white"
            disabled={models.length === 0}
          >
            <option value="" disabled>
              {models.length ? 'Velg modell' : 'Laster modeller...'}
            </option>
            {models.map((m) => (
              <option key={m.id} value={m.id}>
                {m.label}
              </option>
            ))}
          </select>
        </div>

        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Steg 1 — Last inn dokumenter</h2>
          <p className="text-sm text-gray-500">
            Last opp dokumentene du ønsker at AI-en skal søke i. Støttede formater: <strong>PDF, Word (.docx) og tekstfiler (.txt)</strong>. Du kan laste opp flere filer samtidig. Dokumentene lagres i databasen til du sletter dem manuelt.
          </p>

          <input
            type="file"
            multiple
            accept=".pdf,.docx,.txt"
            onChange={(e) => setFiles(Array.from(e.target.files || []))}
            className="block w-full text-sm text-gray-500 file:mr-3 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-gray-900 file:text-white file:cursor-pointer hover:file:bg-gray-700"
          />

          {files.length > 0 && (
            <p className="text-xs text-gray-400">{files.map((f) => f.name).join(', ')}</p>
          )}

          <textarea
            placeholder="Eller lim inn tekst direkte (valgfritt)"
            value={manualText}
            onChange={(e) => setManualText(e.target.value)}
            rows={3}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm resize-none"
          />

          <Collapsible title="Avanserte innstillinger">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <label className="space-y-1">
                <span className="text-gray-600">Tekstbitstørrelse: {chunkSize} tegn</span>
                <input
                  type="range"
                  min={300}
                  max={2000}
                  value={chunkSize}
                  onChange={(e) => setChunkSize(+e.target.value)}
                  className="w-full"
                />
                <p className="text-xs text-gray-400">
                  Kortere tekstbiter gir mer presise treff, men mister kontekst. Lengre tekstbiter beholder mer sammenheng.
                </p>
              </label>

              <label className="space-y-1">
                <span className="text-gray-600">Overlapp: {overlap} tegn</span>
                <input
                  type="range"
                  min={0}
                  max={400}
                  value={overlap}
                  onChange={(e) => setOverlap(+e.target.value)}
                  className="w-full"
                />
                <p className="text-xs text-gray-400">
                  Sikrer at setninger ikke kuttes midt i en tanke ved grensen mellom to tekstbiter.
                </p>
              </label>
            </div>
          </Collapsible>

          <div className="flex gap-3">
            <div className="flex-1 space-y-1">
              <p className="text-xs text-gray-400">Klikk for å lese og lagre dokumentene i databasen.</p>
              <button
                onClick={handleIndex}
                disabled={indexing || (!files.length && !manualText.trim())}
                className="w-full py-2 px-4 rounded-lg bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 transition"
              >
                {indexing ? 'Indekserer…' : 'Indekser dokumenter'}
              </button>
            </div>

            <div className="space-y-1">
              <p className="text-xs text-gray-400">Fjerner alle lagrede dokumenter.</p>
              <button
                onClick={handleDelete}
                className="py-2 px-4 rounded-lg border border-red-300 text-red-600 text-sm hover:bg-red-50 transition"
              >
                🗑 Slett database
              </button>
            </div>
          </div>

          {indexStatus && (
            <p
              className={`text-sm px-3 py-2 rounded-lg ${
                indexStatus.ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-700'
              }`}
            >
              {indexStatus.message}
            </p>
          )}

          <div className="space-y-2">
            <p className="text-xs font-medium text-gray-500">Indekserte dokumenter</p>
            <DocumentList refreshTrigger={docRefresh} model={selectedModel} />
          </div>
        </section>

        <hr className="border-gray-200" />

        <section className="space-y-3">
          <h2 className="text-lg font-semibold">Steg 2 — Still et spørsmål</h2>
          <p className="text-sm text-gray-500">
            Skriv inn et spørsmål på norsk. Appen søker etter de mest relevante tekstbitene i dokumentene dine og genererer et AI-svar basert på funnene.
          </p>
          <p className="text-sm text-gray-400">
            <strong>Tips:</strong> Bruk gjerne konkrete og spesifikke spørsmål. Jo mer presist spørsmålet er, jo bedre treff.
          </p>

          <input
            type="text"
            placeholder="F.eks.: Hva er de viktigste funnene fra turistundersøkelsen?"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && handleRag()}
            className="w-full border border-gray-300 rounded-lg px-3 py-2 text-sm"
          />

          <div className="flex flex-wrap gap-2">
            {EXAMPLE_QUESTIONS.map((q) => (
              <button
                key={q}
                onClick={() => setQuery(q)}
                className="text-xs px-3 py-1 rounded-full border border-gray-300 text-gray-500 hover:border-blue-400 hover:text-blue-600 transition"
              >
                {q}
              </button>
            ))}
          </div>

          <Collapsible title="Avanserte søkeinnstillinger">
            <div className="grid grid-cols-2 gap-4 text-sm">
              <label className="space-y-1">
                <span className="text-gray-600">Antall tekstbiter å hente (k): {k}</span>
                <input
                  type="range"
                  min={1}
                  max={10}
                  value={k}
                  onChange={(e) => setK(+e.target.value)}
                  className="w-full"
                />
                <p className="text-xs text-gray-400">
                  Høyere verdi gir mer kontekst, men kan også introdusere mindre relevante biter.
                </p>
              </label>

              <label className="space-y-1">
                <span className="text-gray-600">Relevanterskel: {scoreThreshold.toFixed(2)}</span>
                <input
                  type="range"
                  min={0}
                  max={1}
                  step={0.05}
                  value={scoreThreshold}
                  onChange={(e) => setScoreThreshold(+e.target.value)}
                  className="w-full"
                />
                <p className="text-xs text-gray-400">
                  Tekstbiter under terskelen filtreres bort. 1.0 = identisk, 0.0 = helt urelatert. Senk hvis du får for få treff.
                </p>
              </label>
            </div>
          </Collapsible>

          <div className="flex gap-3">
            <button
              onClick={handleSearch}
              disabled={searching || !query.trim()}
              className="flex-1 py-2 px-4 rounded-lg border border-gray-900 text-gray-900 text-sm font-medium hover:bg-gray-100 disabled:opacity-40 transition"
            >
              {searching ? 'Søker…' : '🔎 Søk (vis treff)'}
            </button>

            <button
              onClick={handleRag}
              disabled={ragLoading || searching || !query.trim() || !selectedModel}
              className="flex-1 py-2 px-4 rounded-lg bg-blue-600 text-white text-sm font-medium hover:bg-blue-700 disabled:opacity-40 transition"
            >
              {ragLoading || searching ? 'Arbeider…' : '🤖 Generer RAG-svar'}
            </button>
          </div>

          {ragStep && <StepIndicator step={ragStep} />}

          {searchError && (
            <p className="text-sm bg-red-50 text-red-700 px-3 py-2 rounded-lg">{searchError}</p>
          )}
        </section>

        {ragError && (
          <p className="text-sm bg-red-50 text-red-700 px-3 py-2 rounded-lg">{ragError}</p>
        )}

        {searchPoints.length > 0 && history.length === 0 && (
          <section className="space-y-3">
            <div className="flex items-baseline justify-between">
              <h3 className="font-semibold">Tekstbiter funnet i dokumentene</h3>
              {filteredCount > 0 && (
                <span className="text-xs text-gray-400">{filteredCount} filtrert bort</span>
              )}
            </div>

            <p className="text-xs text-gray-400">
              Dette er de mest relevante delene av dine dokumenter basert på spørsmålet. Scoren viser hvor godt innholdet matcher (0–100%). Det er kun disse tekstbitene som sendes videre til AI-modellen — ingenting annet.
            </p>

            <div className="space-y-3">
              {searchPoints.map((p) => (
                <ChunkCard key={p.chunk_id} point={p} />
              ))}
            </div>
          </section>
        )}

        {streamingText && (
          <div className="bg-white border border-blue-200 rounded-lg overflow-hidden">
            <div className="bg-blue-50 border-b border-blue-200 px-4 py-2 flex items-center gap-2">
              <span className="w-3 h-3 border-2 border-blue-500 border-t-transparent rounded-full animate-spin inline-block" />
              <span className="text-sm font-medium text-blue-700">Genererer svar…</span>
            </div>

            <div className="px-4 py-3 text-sm text-gray-800 leading-relaxed whitespace-pre-wrap">
              {streamingText}
              <span className="inline-block w-0.5 h-4 bg-blue-500 animate-pulse ml-0.5 align-text-bottom" />
            </div>
          </div>
        )}

        {history.length > 0 && (
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="font-semibold">Svarhistorikk</h3>
              <button
                onClick={() => {
                  setHistory([])
                  setSearchPoints([])
                }}
                className="text-xs text-gray-400 hover:text-red-500 transition"
              >
                Tøm historikk
              </button>
            </div>

            {history.map((item, i) => (
              <HistoryItem key={item.id} item={item} index={i} />
            ))}
          </section>
        )}
      </main>
    </div>
  )
}
