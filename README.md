# LedgerLens

Enterprise RAG platform for financial documents. Upload PDFs (earnings releases, annual reports, board outcomes), ask questions in natural language, get cited answers grounded in your data.

> **Pipeline:** IBM Docling for layout-aware ingestion (tables with merged cells, charts, text). Hybrid search (dense + BM25) with RRF merge. Gemini for answer generation. JWT-based RBAC.

---

## Quick Start

```bash
# 1. Databases
docker compose up -d

# 2. Backend
conda create -n ledgerlens python=3.11 -y
conda activate ledgerlens
cd backend
pip install docling fastapi uvicorn python-dotenv pydantic sqlalchemy psycopg2-binary PyJWT bcrypt "elasticsearch>=8.0,<9.0" tiktoken python-multipart rich requests google-generativeai PyMuPDF
cp .env.example .env   # add your GEMINI_API_KEY
uvicorn app.main:app --port 8000

# 3. Frontend
cd frontend
npm install
npm run dev
```

| Service | URL |
|---------|-----|
| Frontend | http://localhost:5173 |
| Backend API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Elasticsearch | http://localhost:9200 |
| Kibana | http://localhost:5601 |

**Default login:** `admin` / `admin123`

---

## Architecture

```
PDF Upload → Docling DocumentConverter
              ├── Tables (markdown, merged cells preserved)
              ├── Charts/Figures (captions extracted)
              ├── Text (reading order, headings, lists)
              └── Chunking (token-bounded, type-aware)
                    ↓
              Ollama Embeddings (embeddinggemma, 768d)
                    ↓
              Elasticsearch (dense_vector + BM25)
                    ↓
User Query → Hybrid Search (kNN + BM25 → RRF merge)
                    ↓
              Gemini Flash → Cited Answer
                    ↓
              [Sources: p3, p7]
```

---

## Features

- **Docling ingestion** — IBM's document converter handles complex financial tables (merged cells, multi-level headers), reading order, and chart detection in a single pass
- **Hybrid search** — dense vector (cosine similarity) + BM25 keyword matching with Reciprocal Rank Fusion
- **Page-level citations** — every answer includes source page references verified against retrieved chunks
- **RBAC** — admin/employee roles, persistent vs ephemeral documents, per-user access control lists
- **Dark terminal theme** — JetBrains Mono, `#0a0e0f` background, `#00c896` accent

---

## Environment Variables

| Variable | Default | Description |
|:---|:---|:---|
| `GEMINI_API_KEY` | — | **Required.** Google Gemini API key |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch URL |
| `ES_INDEX` | `rag_chunks` | Index name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama server URL |
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama model for embeddings |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ledgerlens` | PostgreSQL connection |
| `JWT_SECRET` | — | **Required.** JWT signing secret |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Token lifetime |
| `CHUNK_SIZE` | `500` | Token limit per chunk |
| `TOP_K` | `5` | Chunks retrieved per search |

---

## API Endpoints

| Method | Path | Auth | Purpose |
|--------|------|------|---------|
| `GET` | `/health` | None | Health check |
| `POST` | `/api/auth/login` | None | JWT login |
| `GET` | `/api/auth/me` | User | Current user profile |
| `GET` | `/api/users` | Admin | List users |
| `POST` | `/api/users` | Admin | Create user |
| `DELETE` | `/api/users/{id}` | Admin | Delete user |
| `POST` | `/api/ingest` | User | Upload PDF for ingestion |
| `POST` | `/api/chat` | User | RAG chat |
| `POST` | `/api/chat/clear` | User | Clear session history |
| `POST` | `/api/session/end` | User | End session, purge ephemeral chunks |
| `GET` | `/api/cache/{file}` | User | Serve cached page images |
| `POST` | `/api/admin/layout-preview` | Admin | Preview PDF layout regions |

---

## Prerequisites

- **Docker** — Elasticsearch 8.14 + PostgreSQL 15
- **Ollama** — running locally with `embeddinggemma` model
- **Gemini API key** — from Google AI Studio
- **Python 3.11** + **Node.js 18+**
