"""
ragas_eval.py

Kjører RAGAS-evaluering mot den eksisterende FastAPI-backenden.
Forutsetter at backend kjører lokalt på http://localhost:8000.

Installer avhengigheter:
    pip install ragas datasets langchain-openai httpx python-dotenv

Miljøvariabler (.env):
    API_BASE_URL=http://localhost:8000
    AUTH0_DOMAIN=...
    AUTH0_CLIENT_ID=...
    AUTH0_CLIENT_SECRET=...
    AUTH0_AUDIENCE=...
    OPENAI_API_KEY=...        # brukes av RAGAS internt som dommer-LLM
"""

import os
import json
import httpx
from dotenv import load_dotenv
from datasets import Dataset
from ragas import evaluate
from ragas.metrics import (
    faithfulness,
    answer_relevancy,
    context_precision,
    context_recall,
)
from ragas.llms import LangchainLLMWrapper
from langchain_openai import ChatOpenAI

load_dotenv()

BASE = os.getenv("API_BASE_URL", "http://localhost:8000")
OPENAI_KEY = os.getenv("OPENAI_API_KEY", "")
TOP_K = 5
SCORE_THRESHOLD = 0.20
MODEL = "claude-sonnet-4-6"

# ---------------------------------------------------------------------------
# Auth – henter M2M-token fra Auth0 (maskin-til-maskin, ingen brukerinnlogging)
# Sett opp en M2M-applikasjon i Auth0-dashbordet og gi den samme audience som API-et.
# ---------------------------------------------------------------------------

def get_auth_token() -> str:
    domain   = os.getenv("AUTH0_DOMAIN")
    client   = os.getenv("AUTH0_CLIENT_ID")
    secret   = os.getenv("AUTH0_CLIENT_SECRET")
    audience = os.getenv("AUTH0_AUDIENCE")

    if not all([domain, client, secret, audience]):
        raise EnvironmentError(
            "Mangler Auth0-miljøvariabler. Sett AUTH0_DOMAIN, AUTH0_CLIENT_ID, "
            "AUTH0_CLIENT_SECRET og AUTH0_AUDIENCE i .env"
        )

    resp = httpx.post(
        f"https://{domain}/oauth/token",
        json={
            "client_id": client,
            "client_secret": secret,
            "audience": audience,
            "grant_type": "client_credentials",
        },
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


# ---------------------------------------------------------------------------
# Testspørsmål med fasitsvar (ground_truth)
# Oppdater ground_truth etter hvert som dere laster inn nye dokumenter.
# ---------------------------------------------------------------------------

TEST_CASES = [
    # --- Turistundersøkelser ---
    {
        "question": "Hva er de viktigste motivasjonsfaktorene for tyske turister som besøker Norge?",
        "ground_truth": "Natur, friluftsliv og autentiske opplevelser er de viktigste motivasjonsfaktorene.",
        "category": "turistundersøkelse",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilken aldersgruppe dominerer blant utenlandske fritidsturister til Norge?",
        "ground_truth": "Aldersgruppen 35–54 år er overrepresentert blant utenlandske fritidsturister.",
        "category": "turistundersøkelse",
        "critical_metric": "context_precision",
    },
    {
        "question": "Hva oppgir turister som den største utfordringen ved reise til Norge?",
        "ground_truth": "Høye priser er den hyppigst nevnte barrieren blant utenlandske turister.",
        "category": "turistundersøkelse",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hva er gjennomsnittlig oppholdstid for utenlandske turister i Norge?",
        "ground_truth": "Gjennomsnittlig oppholdstid er mellom 7 og 10 netter.",
        "category": "turistundersøkelse",
        "critical_metric": "context_precision",
    },
    {
        "question": "Hvilke aktiviteter er mest populære blant sommerturister i Norge?",
        "ground_truth": "Fjordcruise, fjellturer og byopplevelser i Bergen og Oslo er de mest populære sommeraktivitetene.",
        "category": "turistundersøkelse",
        "critical_metric": "answer_relevancy",
    },
    {
        "question": "Hva skiller britiske turister fra nederlandske turister i reisemønster?",
        "ground_truth": "Britiske turister foretrekker lengre opphold og naturopplevelser, mens nederlandske turister i større grad reiser med bobil.",
        "category": "turistundersøkelse",
        "critical_metric": "context_recall",
    },
    {
        "question": "Hvilke sesongmønstre viser turistundersøkelsen for nordlysturisme?",
        "ground_truth": "Nordlysturisme konsentreres primært til januar–mars med topp i februar.",
        "category": "turistundersøkelse",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilke kanaler bruker turister for å planlegge norgesturen?",
        "ground_truth": "Digitale kanaler, særlig søkemotorer og reiseportaler, dominerer planleggingsfasen.",
        "category": "turistundersøkelse",
        "critical_metric": "answer_relevancy",
    },
    # --- Markedsrapporter ---
    {
        "question": "Hvilke markeder er prioritert i Visit Norways nåværende strategi?",
        "ground_truth": "Tyskland, Nederland, Storbritannia og USA er blant de prioriterte markedene.",
        "category": "markedsrapport",
        "critical_metric": "context_precision",
    },
    {
        "question": "Hva er målgruppebeskrivelsen for det tyske markedet?",
        "ground_truth": "Målgruppen i det tyske markedet er naturinteresserte, ressurssterke voksne med høy betalingsvilje.",
        "category": "markedsrapport",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilke merkeverdier skal Visit Norway kommunisere internasjonalt?",
        "ground_truth": "Natur, autentisitet, bærekraft og frihet er kjerneverdiene i Visit Norways merkevare.",
        "category": "markedsrapport",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hva er Visit Norways posisjoneringsstatement overfor europeiske turister?",
        "ground_truth": "Norge posisjoneres som en premium naturopplevelse for de som ønsker noe annerledes enn massereiselivet.",
        "category": "markedsrapport",
        "critical_metric": "answer_relevancy",
    },
    {
        "question": "Hvilke vekstmarkeder utenfor Europa nevnes i strategidokumentene?",
        "ground_truth": "USA og potensielt asiatiske markeder nevnes som vekstmarkeder utenfor Europa.",
        "category": "markedsrapport",
        "critical_metric": "context_recall",
    },
    {
        "question": "Hva sier strategien om bærekraft som konkurransefortrinn?",
        "ground_truth": "Bærekraft fremheves som et differensierende konkurransefortrinn og integreres i merkevarebygging.",
        "category": "markedsrapport",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilke distribusjonskanaler vektlegges i markedsstrategien?",
        "ground_truth": "Digitale kanaler, samarbeid med turoperatører og medierelasjoner er de viktigste kanalene.",
        "category": "markedsrapport",
        "critical_metric": "context_precision",
    },
    {
        "question": "Hva er de definerte KPI-ene for Visit Norways markedsarbeid?",
        "ground_truth": "Antall gjestedøgn, markedsandel og merkekjennskap er sentrale KPI-er.",
        "category": "markedsrapport",
        "critical_metric": "context_recall",
    },
    # --- Sesong og destinasjoner ---
    {
        "question": "Hvilke destinasjoner i Norge er mest besøkt av internasjonale turister?",
        "ground_truth": "Oslo, Bergen og fjordregionene Flåm og Geiranger er mest besøkt.",
        "category": "sesong_destinasjon",
        "critical_metric": "answer_relevancy",
    },
    {
        "question": "Hva anbefales for å forlenge sommersesongen?",
        "ground_truth": "Pakketilbud for skuldersesongene mai og september samt aktiviteter for familier anbefales.",
        "category": "sesong_destinasjon",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilke vinteraktiviteter fremheves som unike norske opplevelser?",
        "ground_truth": "Nordlys, hundekjøring, skikjøring og samisk kultur fremheves som unike vinteropplevelser.",
        "category": "sesong_destinasjon",
        "critical_metric": "context_precision",
    },
    {
        "question": "Hva sier dokumentene om turistpress og overturisme i populære destinasjoner?",
        "ground_truth": "Det nevnes utfordringer med overturisme ved Preikestolen og i Flåm, og spredning av turister anbefales.",
        "category": "sesong_destinasjon",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hvilke regioner i Norge har størst vekstpotensial ifølge rapportene?",
        "ground_truth": "Nord-Norge og Innlandet løftes frem som regioner med uutnyttet vekstpotensial.",
        "category": "sesong_destinasjon",
        "critical_metric": "context_recall",
    },
    {
        "question": "Hva kjennetegner turister som reiser til fjordene versus de som reiser til byene?",
        "ground_truth": "Fjordturister er eldre og naturorienterte, byturister er yngre og kulturinteresserte.",
        "category": "sesong_destinasjon",
        "critical_metric": "answer_relevancy",
    },
    {
        "question": "Hvilke perioder er viktigst for utenlandsk turisme til Norge?",
        "ground_truth": "Juni til august er høysesong, med vekst i januar–mars for vinterturisme.",
        "category": "sesong_destinasjon",
        "critical_metric": "context_precision",
    },
    # --- Krysskilder (cross-document) ---
    {
        "question": "Hvilket marked har høyest andel gjengangere, og hva sier turistundersøkelsen om lojalitet?",
        "ground_truth": "Det tyske markedet har høy andel gjengangere med sterk lojalitet til naturdestinasjoner.",
        "category": "krysskilder",
        "critical_metric": "context_recall",
    },
    {
        "question": "Hva er sammenhengen mellom reisemotivasjon og oppholdslengde for nederlandske turister?",
        "ground_truth": "Nederlandske turister med naturmotivasjon har lengre oppholdstid enn de med bymotivasjon.",
        "category": "krysskilder",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hva sier strategidokumentene om det tyske markedet, og hva viser turistundersøkelsen fra samme år?",
        "ground_truth": "Strategien prioriterer Tyskland høyt, og undersøkelsen bekrefter høy betalingsvilje og naturfokus.",
        "category": "krysskilder",
        "critical_metric": "context_recall",
    },
    {
        "question": "Hvilke aktiviteter har høyest betalingsvilje blant utenlandske turister, og i hvilke markeder?",
        "ground_truth": "Guidede naturopplevelser og nordlysturer har høyest betalingsvilje, særlig i det tyske og britiske markedet.",
        "category": "krysskilder",
        "critical_metric": "faithfulness",
    },
    {
        "question": "Hva er Visit Norways bærekraftsbudskap, og hvordan oppfatter turister dette ifølge undersøkelsene?",
        "ground_truth": "Bærekraft kommuniseres aktivt, men turistundersøkelsene viser at bevisstheten om det er lav blant besøkende.",
        "category": "krysskilder",
        "critical_metric": "context_precision",
    },
    # Spørsmål 29: Hallusinasjonstest — forventet svar er "ikke funnet i kildene"
    {
        "question": "Hva sier dokumentene om digitale bookingvaner blant amerikanske turister?",
        "ground_truth": "Dokumentene inneholder ikke spesifikk informasjon om digitale bookingvaner blant amerikanske turister.",
        "category": "krysskilder",
        "critical_metric": "faithfulness",
        "hallucination_test": True,
    },
    {
        "question": "Hva sier dokumentene om konkurrentland som Sveits og Island i kampen om de samme turistene?",
        "ground_truth": "Sveits og Island nevnes som konkurrenter i premiumsegmentet for naturopplevelser.",
        "category": "krysskilder",
        "critical_metric": "context_recall",
    },
]


# ---------------------------------------------------------------------------
# Kall mot backend
# ---------------------------------------------------------------------------

def search(client: httpx.Client, headers: dict, query: str) -> list[dict]:
    resp = client.post(
        f"{BASE}/search",
        headers=headers,
        json={
            "query": query,
            "k": TOP_K,
            "min_score": SCORE_THRESHOLD,
            "score_threshold": SCORE_THRESHOLD,
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("points", [])


def rag_answer(client: httpx.Client, headers: dict, query: str, points: list[dict]) -> str:
    resp = client.post(
        f"{BASE}/rag",
        headers=headers,
        json={"query": query, "points": points, "model": MODEL},
        timeout=60,
    )
    resp.raise_for_status()
    return resp.json().get("answer", "")


# ---------------------------------------------------------------------------
# Bygger RAGAS-datasett
# ---------------------------------------------------------------------------

def build_dataset(token: str) -> tuple[Dataset, list[dict]]:
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    questions, answers, contexts, ground_truths, metadata = [], [], [], [], []

    with httpx.Client() as client:
        for i, tc in enumerate(TEST_CASES, 1):
            q = tc["question"]
            print(f"[{i}/{len(TEST_CASES)}] {q[:60]}...")

            try:
                points = search(client, headers, q)

                if not points:
                    print(f"  ADVARSEL: Ingen chunks funnet for spørsmål {i}")
                    ctx = ["(ingen kontekst funnet)"]
                    answer = "Jeg finner ikke dette i kildene."
                else:
                    ctx = [p["text"] for p in points]
                    answer = rag_answer(client, headers, q, points)
            except Exception as e:
                print(f"  FEIL for spørsmål {i}: {e}")
                ctx = ["(feil ved henting)"]
                answer = "(feil)"

            questions.append(q)
            answers.append(answer)
            contexts.append(ctx)
            ground_truths.append(tc["ground_truth"])
            metadata.append({
                "category": tc.get("category"),
                "critical_metric": tc.get("critical_metric"),
                "hallucination_test": tc.get("hallucination_test", False),
            })

            print(f"  Svar: {answer[:80]}...")

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts,
        "reference": ground_truths,
    })

    return dataset, metadata


# ---------------------------------------------------------------------------
# Kjør evaluering og skriv rapport
# ---------------------------------------------------------------------------

def run_evaluation():
    print("Henter Auth0-token...")
    token = get_auth_token()

    print(f"\nHenter svar fra {BASE} for {len(TEST_CASES)} spørsmål...")
    dataset, metadata = build_dataset(token)

    print("\nKjører RAGAS-evaluering (bruker OpenAI som dommer-LLM)...")

    llm = LangchainLLMWrapper(ChatOpenAI(model="gpt-4o", api_key=OPENAI_KEY))

    result = evaluate(
        dataset=dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=llm,
        raise_exceptions=False,
    )

    df = result.to_pandas()
    df["category"] = [m["category"] for m in metadata]
    df["critical_metric"] = [m["critical_metric"] for m in metadata]
    df["hallucination_test"] = [m["hallucination_test"] for m in metadata]

    # Lagre til CSV
    output_file = "ragas_results.csv"
    df.to_csv(output_file, index=False)
    print(f"\nResultater lagret til {output_file}")

    # Skriv sammendrag til terminalen
    print("\n" + "="*60)
    print("SAMMENDRAG")
    print("="*60)

    score_cols = ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]
    existing = [c for c in score_cols if c in df.columns]

    for col in existing:
        mean = df[col].mean()
        print(f"  {col:<25} {mean:.3f}")

    print("\nPer kategori:")
    for cat in df["category"].unique():
        sub = df[df["category"] == cat]
        scores = [f"{c}: {sub[c].mean():.2f}" for c in existing if c in sub.columns]
        print(f"  {cat:<25} {' | '.join(scores)}")

    # Hallusinasjonstest
    hall = df[df["hallucination_test"]]
    if not hall.empty:
        faith_score = hall["faithfulness"].values[0] if "faithfulness" in hall.columns else None
        print(f"\nHallusinasjonstest (spørsmål 29):")
        print(f"  Faithfulness-score: {faith_score:.3f}" if faith_score is not None else "  Ikke evaluert")
        if faith_score is not None and faith_score < 0.5:
            print("  ADVARSEL: Lav score — systemet kan ha hallusinert et svar.")

    print("\nFerdig.")
    return df


if __name__ == "__main__":
    run_evaluation()