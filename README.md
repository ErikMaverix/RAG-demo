# RAG Demo — React + FastAPI

## Oppsett

### Backend
```bash
cd backend
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
export ANTHROPIC_API_KEY="sk-ant-..."   # kun nødvendig for Claude-modeller
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd frontend
npm install
npm run dev
```

Åpne http://localhost:5173
