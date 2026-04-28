# Designdokument: Innebygd feedback-mekanisme i chat-widget

**Prosjekt:** RAG Demo (Maverix)
**Funksjon:** Feedback-mekanisme for AI-svar i chat-widget
**Forfatter:** Maverix / Claude Code
**Status:** Til godkjenning
**Dato:** 2026-04-27

---

## 1. Formål

Under testfasen av RAG-løsningen trenger Maverix et strukturert grunnlag for å vurdere svarkvaliteten — uten at testere må skrive manuelle rapporter. Feedbacken skal:

- Gi umiddelbar signal fra brukeren om svaret var nyttig eller ikke
- Fange strukturert kontekst (hvilke chunks ble brukt, hvilken modell, latency) automatisk
- Lagres i en Postgres-database i EU (Supabase) under full kontroll — ingen data til tredjepart
- Danne grunnlag for kvalitetsrapportering (hallusinasjonsfrekvens, konverteringsrate, modellsammenligning)

---

## 2. Brukeropplevelse

På hvert AI-svar i chat-widgeten vises:

```
Var svaret nyttig?   👍   👎
```

**Thumbs up:**  
Klikk → sendes direkte → viser "✓ Takk for tilbakemeldingen"

**Thumbs down:**  
Klikk → viser inline skjema:

```
Hva var galt?
[ Feil informasjon ] [ Hallusinasjon ] [ Forsto ikke spørsmålet ]
[ Teknisk feil     ] [ Annet         ]

Kommentar (valgfritt):
┌────────────────────────────────┐
│                                │
└────────────────────────────────┘

[ Send tilbakemelding ]  [ Avbryt ]
```

Etter innsending: skjema erstattes av "✓ Takk for tilbakemeldingen"  
Feil: viser "Klarte ikke sende tilbakemelding" (brukeren kan prøve igjen)

---

## 3. Arkitektur og dataflyt

```
┌──────────────────────────────────────────────────────────┐
│  React Frontend                                          │
│                                                          │
│  App.jsx                                                 │
│  ├─ conversationId (UUID, genereres én gang per session) │
│  └─ handleRag()                                          │
│     ├─ messageId (UUID, én per RAG-svar)                 │
│     ├─ latencySearchMs  (Date.now() diff)                │
│     ├─ latencyGenerationMs (Date.now() diff)             │
│     └─ lagrer alt i history[]                            │
│                                                          │
│  HistoryItem.jsx                                         │
│  └─ FeedbackButtons.jsx                                  │
│     ├─ Viser 👍 / 👎                                     │
│     ├─ Viser skjema ved 👎                               │
│     └─ POST /feedback  ──────────────────────────────┐   │
└─────────────────────────────────────────────────────────┘│
                                                           │
┌──────────────────────────────────────────────────────────┤
│  FastAPI Backend                                         │
│                                                          │
│  main.py                                                 │
│  ├─ PROMPT_VERSION = git rev-parse --short HEAD          │
│  └─ POST /feedback                                       │
│     ├─ Validerer JWT (Supabase)                          │
│     ├─ Henter user_id fra token                          │
│     ├─ Setter prompt_version                             │
│     └─ Skriver til DB via SQLAlchemy  ────────────────┐  │
│                                                       │  │
│  feedback.py                                          │  │
│  ├─ SQLAlchemy modell (FeedbackEntry)                 │  │
│  ├─ init_db() — oppretter tabell ved oppstart         │  │
│  └─ get_db() — dependency injection til FastAPI       │  │
└───────────────────────────────────────────────────────┤  │
                                                        │  │
┌───────────────────────────────────────────────────────┘  │
│  Database                                                 │
│                                                           │
│  Lokalt:      SQLite  (feedback.db)                       │
│  Produksjon:  Postgres (Supabase EU)                      │
│                                                           │
│  Tabell: feedback                                         │
└───────────────────────────────────────────────────────────┘
```

---

## 4. Datamodell — tabell `feedback`

| Kolonne                 | Type         | Nullable | Beskrivelse |
|-------------------------|--------------|----------|-------------|
| `id`                    | UUID (PK)    | Nei      | Auto-generert unik ID |
| `created_at`            | Timestamp TZ | Nei      | UTC tidspunkt for innsending |
| `conversation_id`       | String       | Nei      | UUID generert i frontend ved app-load. Grupperer meldinger i én session. |
| `message_id`            | String       | Nei      | UUID generert per RAG-svar. Identifiserer én konkret melding. |
| `user_id`               | String       | Ja       | `sub`-claim fra Supabase JWT. Brukes for bruker-sporing og GDPR-sletting. |
| `rating`                | Integer      | Nei      | `1` = thumbs up, `-1` = thumbs down |
| `category`              | String       | Ja       | Kun ved thumbs down. Én av: `Feil informasjon`, `Hallusinasjon`, `Forsto ikke spørsmålet`, `Teknisk feil`, `Annet` |
| `comment`               | Text         | Ja       | Fritekst fra bruker (valgfritt) |
| `query`                 | Text         | Nei      | Spørsmålet brukeren stilte |
| `answer`                | Text         | Nei      | Det fulle AI-svaret |
| `model`                 | String(100)  | Nei      | Modell-ID, f.eks. `claude-sonnet-4-6`, `mistral-large-latest` |
| `prompt_version`        | String(100)  | Ja       | Git commit hash ved kjøretidspunkt, f.eks. `e7f3b55` |
| `search_results`        | JSON         | Ja       | Alle chunks returnert fra Qdrant: `[{chunk_id, source, score, text}]` |
| `used_chunks`           | JSON         | Ja       | Chunk-IDer faktisk brukt i svaret: `["C1", "C3"]` |
| `latency_search_ms`     | Integer      | Ja       | Tid for semantisk søk (ms) |
| `latency_generation_ms` | Integer      | Ja       | Tid for LLM-generering (ms) |

**Indekser:** `conversation_id`, `message_id`

### Feltenes hensikt i praksis

**`conversation_id` + `message_id`**  
Lar deg hente full kontekst for én samtale eller ett enkelt svar. Brukes ved debugging: "hva skjedde i den samtalen der rating var -1?"

**`prompt_version` (git hash)**  
Lar deg korrelere feedbackkvalitet mot kodeendringer. F.eks.: "etter commit `e7f3b55` gikk hallusinasjonsraten ned."

**`search_results` (JSON)**  
Full Qdrant-output inkl. score. Lar deg se om svake treff (lav score) korrelerer med dårlig feedback, og om terskelverdiene bør justeres.

**`used_chunks`**  
Delmengde av `search_results` — chunks modellen faktisk siterte. Avvik mellom `search_results` og `used_chunks` kan indikere at modellen ignorerte relevante biter.

**`latency_*`**  
Målt i frontend med `Date.now()`. Brukes til å skille treige søk fra treig generering.

---

## 5. Filendringer — oversikt

| Fil | Endring | Hvorfor |
|-----|---------|---------|
| `backend/feedback.py` | Ny | SQLAlchemy-modell + DB-tilkobling |
| `backend/main.py` | Endret | Legg til `/feedback`-endepunkt + `PROMPT_VERSION` |
| `backend/requirements.txt` | Endret | Legg til `sqlalchemy` og `psycopg2-binary` |
| `frontend/src/components/FeedbackButtons.jsx` | Ny | UI-komponent: thumbs + skjema |
| `frontend/src/components/HistoryItem.jsx` | Endret | Inkluder `FeedbackButtons` i svar-kortet |
| `frontend/src/App.jsx` | Endret | Generer `conversationId`, `messageId`, mål latency |
| `frontend/src/api.js` | Endret | Legg til `submitFeedback()` |

---

## 6. Detaljerte filendringer

### 6.1 `backend/feedback.py` (ny fil)

```python
# DATABASE_URL fra env. Standard: SQLite for lokal utvikling.
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./feedback.db")

# Supabase og Heroku eksponerer "postgres://" — SQLAlchemy krever "postgresql://"
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)
```

`FeedbackEntry` er SQLAlchemy-modellen som mapper direkte til DB-tabellen.

`init_db()` kalles ved appoppstart — oppretter tabellen hvis den ikke finnes.  
`get_db()` er en FastAPI dependency som gir en DB-session per request.

---

### 6.2 `backend/main.py` — tillegg

**`PROMPT_VERSION`** — kjøres én gang ved oppstart:
```python
def _get_git_hash() -> str:
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=Path(__file__).parent,
            stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"

PROMPT_VERSION = _get_git_hash()
```

**Startup** — init_db() via lifespan:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield

app = FastAPI(title="RAG Demo API", lifespan=lifespan)
```

**`POST /feedback`** — mottar feedback fra frontend:
```python
class FeedbackRequest(BaseModel):
    conversation_id: str
    message_id: str
    rating: int               # 1 eller -1
    category: Optional[str]   # ved thumbs down
    comment: Optional[str]
    query: str
    answer: str
    model: str
    search_results: Optional[list]
    used_chunks: Optional[list]
    latency_search_ms: Optional[int]
    latency_generation_ms: Optional[int]

@app.post("/feedback")
def submit_feedback(req: FeedbackRequest, user=Depends(verify_jwt_token), db=Depends(get_db)):
    # Validerer, setter prompt_version, skriver til DB
    ...
```

---

### 6.3 `backend/requirements.txt` — tillegg

```
sqlalchemy
psycopg2-binary   # Påkrevd for Postgres/Supabase i prod. Ikke nødvendig for SQLite-dev.
```

---

### 6.4 `frontend/src/components/FeedbackButtons.jsx` (ny fil)

Mottar to props:
- `item` — hele history-objektet (query, answer, searchPoints, usedPoints, latency, messageId, model)
- `conversationId` — stabil UUID for hele session (fra App.jsx)

Tilstander:
- `idle` — viser 👍 / 👎
- `form` — viser kategori-skjema (kun ved 👎)
- `submitted` — viser bekreftelsestekst
- `error` — viser feilmelding

Kaller `submitFeedback()` fra `api.js` med komplett payload.

---

### 6.5 `frontend/src/components/HistoryItem.jsx` — endring

Tar inn nytt prop `conversationId`. Rendrer `<FeedbackButtons>` i handlings-raden på hvert svar-kort.

---

### 6.6 `frontend/src/App.jsx` — endring

```js
// Én stabil UUID for hele session (genereres én gang ved app-load)
const [conversationId] = useState(() => crypto.randomUUID())
```

I `handleRag()`:
```js
const messageId = crypto.randomUUID()
let latencySearchMs = 0
let latencyGenerationMs = 0

// Rundt søk:
const t0 = Date.now()
// ... søk ...
latencySearchMs = Date.now() - t0

// Rundt generering:
const t1 = Date.now()
// ... stream ...
latencyGenerationMs = Date.now() - t1

// I history-objektet:
{
  messageId,
  model: selectedModel,
  latencySearchMs,
  latencyGenerationMs,
  // ... eksisterende felter ...
}
```

`conversationId` sendes ned til `<HistoryItem conversationId={conversationId} ...>`

---

### 6.7 `frontend/src/api.js` — tillegg

```js
export async function submitFeedback(payload) {
  const response = await fetch(`${BASE}/feedback`, {
    method: 'POST',
    headers: await getAuthHeaders({ 'Content-Type': 'application/json' }),
    body: JSON.stringify(payload),
  })
  await ensureOk(response)
  return response.json()
}
```

---

## 7. Konfigurasjon

### Lokal utvikling (SQLite)
Ingen konfigurasjon nødvendig. `feedback.db` opprettes automatisk i `backend/`-mappen.

### Produksjon (Supabase Postgres)
Sett miljøvariabel i Render.com (eller `.env`):

```
DATABASE_URL=postgresql://postgres:[PASSWORD]@[HOST]:5432/postgres
```

Finn connection string i Supabase Dashboard → Project Settings → Database → Connection string (URI-format).

> **Merk:** Supabase EU-region velges når prosjektet opprettes. Verifiser at prosjektet er satt til `eu-central-1` eller `eu-west-1` for GDPR-compliance.

---

## 8. GDPR-hensyn

- All data lagres i Supabase EU — ingen overføring til USA
- `user_id` er Supabase `sub`-claim (intern UUID) — ikke navn eller e-post
- Sletting ved GDPR-forespørsel: én SQL-transaksjon `DELETE FROM feedback WHERE user_id = ?`
- `query` og `answer` kan inneholde persondata — vurder om disse skal krypteres i prod

---

## 9. Gjenbruk i annet prosjekt

Feedback-mekanismen er løst koblet og kan porteres med disse stegene:

**Backend (kopiér direkte):**
1. Kopier `feedback.py` — ingen endringer nødvendig
2. I din `main.py`: importer `init_db`, `get_db`, `FeedbackEntry`, legg til lifespan-hook og `/feedback`-endepunkt
3. Juster `FeedbackRequest`-feltene etter hva din løsning eksponerer (f.eks. `property_context` for hotell/restaurant, `function_calls` for BookVisit/Gastroplanner)

**Frontend (kopiér og tilpass):**
1. Kopier `FeedbackButtons.jsx` — UI og logikk er selvstendige
2. Legg til `submitFeedback()` i din `api.js`
3. I din chat-komponent: generer `conversationId` én gang per session, generer `messageId` per svar
4. Send riktige metadata ned til `FeedbackButtons` via props

**Utvid datamodellen** for De Bergenske-kontekst:
```python
property_context = Column(String, nullable=True)   # hotellnavn / restaurant
function_calls   = Column(JSON, nullable=True)      # [{name, input, output, error}]
language         = Column(String(10), default="no")
```

---

## 10. Hva dette gir av innsikt (eksempel-spørringer)

```sql
-- Hallusinasjonsrate per modell siste 30 dager
SELECT model,
       COUNT(*) FILTER (WHERE category = 'Hallusinasjon') AS hallucinations,
       COUNT(*) AS total,
       ROUND(100.0 * COUNT(*) FILTER (WHERE category = 'Hallusinasjon') / COUNT(*), 1) AS pct
FROM feedback
WHERE created_at > NOW() - INTERVAL '30 days'
GROUP BY model;

-- Svar med lav chunk-score og dårlig feedback (indikerer threshold bør heves)
SELECT query, answer, search_results, rating
FROM feedback
WHERE rating = -1
  AND EXISTS (
    SELECT 1 FROM jsonb_array_elements(search_results) AS r
    WHERE (r->>'score')::float < 0.35
  );

-- Gjennomsnittlig latency per steg
SELECT model,
       AVG(latency_search_ms)     AS avg_search_ms,
       AVG(latency_generation_ms) AS avg_gen_ms
FROM feedback
GROUP BY model;
```
