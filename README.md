# KingSlayer — RAG Document Q&A

A Retrieval-Augmented Generation (RAG) chatbot for querying financial PDF documents with AI-powered answers and page-level citations.

Built with **FastAPI + Elasticsearch + Gemini** on the backend and **React + Vite** on the frontend.

---

## Architecture

```
┌──────────────────────────────┐      ┌──────────────────────────────────────┐
│         Frontend             │      │              Backend                 │
│  React + Vite + TypeScript   │◄────►│  FastAPI (Python)                    │
│  http://localhost:5173       │ API  │  http://localhost:8000               │
└──────────────────────────────┘      │                                      │
                                      │  ┌─────────────┐  ┌──────────────┐  │
                                      │  │  Ingestion   │  │ Orchestrator │  │
                                      │  │  ├─ Parser   │  │  └─ Engine   │  │
                                      │  │  ├─ Chunker  │  └──────────────┘  │
                                      │  │  └─ Pipeline  │                   │
                                      │  └─────────────┘  ┌──────────────┐  │
                                      │  ┌─────────────┐  │   Storage     │  │
                                      │  │Intelligence  │  │  └─ ES Client│  │
                                      │  │ ├─ Embedder  │  └──────────────┘  │
                                      │  │ └─ Generator │                    │
                                      │  └─────────────┘                    │
                                      └────────────┬───────────────────────┘
                                                   │
                                      ┌────────────▼───────────────────────┐
                                      │  Elasticsearch 8.14 + Kibana       │
                                      │  http://localhost:9200 / :5601      │
                                      └────────────────────────────────────┘
```

---

## Prerequisites

| Tool             | Version  |
| ---------------- | -------- |
| Python           | ≥ 3.9    |
| Node.js          | ≥ 18     |
| Docker & Compose | Latest   |

You also need a **Gemini API key** — get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey).

---

## Quick Start

### 1. Start Elasticsearch

```bash
docker compose up -d
```

Wait until healthy (`docker compose ps` should show `healthy` for elasticsearch).

### 2. Backend Setup

```bash
cd backend

# Create virtual environment
python -m venv .venv
source .venv/bin/activate        # macOS / Linux
# .venv\Scripts\activate         # Windows

# Install dependencies
pip install -r requirements.txt

# Configure environment
cp .env.example .env
# Edit .env and add your GEMINI_API_KEY
```

#### Start the API server

```bash
uvicorn app.main:app --reload --port 8000
```

The API will be available at **http://localhost:8000**. Check health at [http://localhost:8000/health](http://localhost:8000/health).

### 3. Frontend Setup

```bash
cd frontend

# Install dependencies
npm install

# Start dev server
npm run dev
```

The UI will be available at **http://localhost:5173**.

---

## Usage

1. **Upload a PDF** — Use the sidebar "Ingest" panel to upload a financial PDF document.
2. **Ask questions** — Type your question in the chat panel. The AI will answer using only the ingested document content.
3. **View citations** — Each answer includes page-level source citations.
4. **Clear chat** — Use the clear button to reset conversation history.

---

## API Endpoints

| Method | Endpoint          | Description                     |
| ------ | ----------------- | ------------------------------- |
| `GET`  | `/health`         | Health check                    |
| `POST` | `/api/ingest`     | Upload & ingest a PDF (multipart) |
| `POST` | `/api/chat`       | Send a message, get RAG answer  |
| `POST` | `/api/chat/clear` | Clear conversation history      |

---

## Environment Variables

### Backend (`backend/.env`)

| Variable         | Default                  | Description                        |
| ---------------- | ------------------------ | ---------------------------------- |
| `GEMINI_API_KEY`  | —                        | **Required.** Google Gemini API key |
| `ES_HOST`         | `http://localhost:9200`  | Elasticsearch URL                  |
| `ES_INDEX`        | `rag_chunks`             | Elasticsearch index name           |
| `CHUNK_SIZE`      | `500`                    | Tokens per chunk                   |
| `CHUNK_OVERLAP`   | `50`                     | Overlapping tokens between chunks  |
| `TOP_K`           | `5`                      | Number of chunks retrieved per query |

### Frontend (`frontend/.env.development`)

| Variable       | Default                 | Description       |
| -------------- | ----------------------- | ----------------- |
| `VITE_API_URL` | `http://localhost:8000`  | Backend API URL   |

---

## Project Structure

```
ps2_kingslayer/
├── docker-compose.yml          # Elasticsearch + Kibana
├── README.md
│
├── backend/
│   ├── .env.example
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py             # FastAPI app & routes
│   │   └── schemas.py          # Request/response models
│   ├── rag/
│   │   ├── ingestion/
│   │   │   ├── parser.py       # PDF parsing (pdfplumber)
│   │   │   ├── chunker.py      # Token-based text chunking
│   │   │   └── ingest_pipeline.py  # End-to-end ingestion
│   │   ├── intelligence/
│   │   │   ├── embedder.py     # Gemini embedding generation
│   │   │   └── generator.py    # Gemini LLM answer generation
│   │   ├── orchestrator/
│   │   │   └── engine.py       # RAG engine (retrieve + generate)
│   │   ├── storage/
│   │   │   └── es_client.py    # Elasticsearch vector store
│   │   └── utils/
│   │       └── config.py       # Centralised config from .env
│   ├── sample_pdfs/            # Sample PDFs for testing
│   └── tests/
│
└── frontend/
    ├── .env.development
    ├── package.json
    ├── index.html
    └── src/
        ├── App.tsx             # Main layout (sidebar + chat)
        ├── api.ts              # Backend API client
        ├── types.ts            # TypeScript interfaces
        └── components/
            ├── ChatPanel.tsx   # Chat interface
            └── IngestPanel.tsx # PDF upload panel
```

---

## Tech Stack

| Layer       | Technology                                  |
| ----------- | ------------------------------------------- |
| Frontend    | React 19, TypeScript, Vite                  |
| Backend     | FastAPI, Python                              |
| PDF Parsing | pdfplumber                                  |
| Chunking    | tiktoken (cl100k_base, 500-token windows)   |
| Embeddings  | Gemini Embedding 001 (768-dim)              |
| LLM         | Gemini 3.1 Flash Lite                       |
| Vector Store| Elasticsearch 8.14 (dense_vector + cosine)  |
| Infra       | Docker Compose                              |

---

## Team

**Powermind — PS2 KingSlayer**
