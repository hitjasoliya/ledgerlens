# 🔍 LedgerLens

Enterprise RAG (Retrieval-Augmented Generation) platform for precise financial document analysis. LedgerLens allows you to upload complex financial PDFs (earnings releases, annual reports, financial statements), parse them while preserving tabular layout and cell-merging structure, and query them in natural language with page-level citations grounded in source data.

Built with a dark terminal aesthetic and micro-animations, LedgerLens merges advanced document parsing, hybrid search indexing, and LLM reasoning to ensure zero hallucination and strict compliance with role-based document access.

---

## 🏗️ Architecture Flow

```
   [ Upload PDF ]
         │
         ▼
 ┌────────────────────────┐
 │   IBM Docling Parser   │ ──► Layout analysis (Tables, Figures, Headings, Text)
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │   Ollama Embeddings    │ ──► Batch embedding using 'embeddinggemma' (768d)
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │     Elasticsearch      │ ──► Persistent & session vector/sparse index
 └────────────────────────┘
         │
  [ Search Query ]
         │
         ▼
 ┌────────────────────────┐
 │     Hybrid Search      │ ──► (Dense Vector k-NN) + (Sparse BM25)
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │    RRF Merge (K=60)    │ ──► Reciprocal Rank Fusion rank blending
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │    Google Gemini API   │ ──► Generation with strict grounded constraints
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │  Citation Parser & UI  │ ──► Highlights cited page bounding boxes in preview
 └────────────────────────┘
```

---

## 📂 Project Structure

```
ledgerlens/
├── backend/
│   ├── app/                     # FastAPI Application Layer
│   │   ├── main.py              # Application entry point & API endpoints
│   │   ├── auth.py              # JWT authentication & password hashing
│   │   ├── database.py          # SQLAlchemy DB session setup
│   │   ├── models.py            # User and Document DB schemas
│   │   └── schemas.py           # Pydantic request/response schemas
│   ├── rag/                     # RAG Core Engine
│   │   ├── ingestion/           # IBM Docling parsing & chunking pipeline
│   │   ├── intelligence/        # Ollama embedder & Gemini generator
│   │   ├── orchestrator/        # RAG Engine, query routing, citation parsing
│   │   ├── storage/             # Elasticsearch hybrid search client
│   │   └── utils/               # Configuration settings & helper utilities
│   ├── requirements.txt         # Python dependencies
│   └── .env.example             # Backend environment template
├── frontend/
│   ├── src/                     # React + TypeScript source code
│   │   ├── auth/                # AuthContext & ProtectedRoute components
│   │   ├── components/          # Reusable UI, Chat, File & Admin components
│   │   ├── pages/               # Landing, Login, Admin & Employee dashboards
│   │   ├── services/            # API service calls (chat, files, users)
│   │   └── types/               # TypeScript interface definitions
│   ├── package.json             # Frontend dependencies & Vite scripts
│   └── vite.config.ts           # Vite configuration
├── docker-compose.yml           # Docker services (PostgreSQL, Elasticsearch, Kibana)
└── run.sh                       # Unified single-command system launcher
```

---

## ⚡ Core Features

- **IBM Docling Parsing Ingestion**: Layout-aware parsing that converts complex financial tables (including merged cells and multi-level headers) directly to clean Markdown. Includes automatic figure caption matching and hierarchical section heading context injection.
- **Hybrid Search with RRF**: Combines dense vector cosine similarity (via Ollama `embeddinggemma`, 768d) and sparse BM25 keyword matching, merged via a **Reciprocal Rank Fusion (RRF)** rank blending algorithm ($K=60$).
- **Hierarchical Access Control (RBAC)**: Supports roles (`admin` and `employee`), persistent document storage vs. session-ephemeral scopes, and document-level Access Control Lists (ACLs).
- **Interactive Layout Inspector**: Administrators can upload any document to view layout region breakdowns (Tables, Text, Figures, Headers) projected over rendered PDF page canvas layouts.
- **Stateful Answer Citation**: The generative engine validates LLM source indicators against retrieved document chunk scopes, returning page numbers mapped directly to vector source blocks (`[pX_cY]`).

---

## 🔐 Role & Permission Matrix

| Feature / Capability | Admin Role | Employee Role |
| :--- | :---: | :---: |
| Authenticate & Access Chat Interface | ✅ | ✅ |
| Upload Ephemeral (Session) Documents | ✅ | ✅ |
| Upload Persistent Documents | ✅ | ✅ |
| View All Persistent Documents | ✅ | 🔒 (Scope / ACL limited) |
| Manage User Registry (Create / Delete Users) | ✅ | ❌ |
| Update Document Access Lists (ACLs) | ✅ | ❌ |
| Access Interactive PDF Layout Inspector | ✅ | ❌ |

---

## 🛠️ Environment Configurations

Configure your environment variables in `backend/.env`. Refer to [config.py](backend/rag/utils/config.py) for structural defaults.

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | — | **Required.** Google AI Studio Gemini API Key |
| `JWT_SECRET` | — | **Required.** Security signing key for JWT credentials |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch server address |
| `ES_INDEX` | `rag_chunks` | Elasticsearch indexing target |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama local inference endpoint |
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama model utilized for vector generation |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/ledgerlens` | PostgreSQL primary database connection string |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Login token validity duration |
| `CHUNK_SIZE` | `500` | Sliding window token boundary size for text blocks |
| `TOP_K` | `5` | Retrieved context chunk limit passed to generation model |

---

## 🚀 Quick Start

### Prerequisites
- [Docker & Docker Desktop](https://www.docker.com/)
- Python 3.11+
- Node.js 18+ & npm
- [Ollama](https://ollama.com/) (running locally with `embeddinggemma` model pulled)

```bash
ollama pull embeddinggemma
```

### 1. Launch Databases
Start Elasticsearch and PostgreSQL services via Docker:
```bash
docker compose up -d
```
Verify database configurations in [docker-compose.yml](docker-compose.yml).

### 2. Configure Environment Variables
Duplicate `.env.example` inside the backend directory and configure your credentials:
```bash
cd backend
cp .env.example .env
# Edit .env and supply GEMINI_API_KEY and JWT_SECRET
```

### 3. Backend Setup
Create your Python environment and install dependencies:
```bash
conda create -n ledgerlens python=3.11 -y
conda activate ledgerlens
pip install -r requirements.txt
uvicorn app.main:app --port 8000
```

### 4. Frontend Setup
Install npm packages and launch the Vite development server:
```bash
cd ../frontend
npm install
npm run dev
```

### 5. Unified System Boot (Alternative)
You can launch databases, check port availability, check environment settings, verify Ollama configurations, and run both backend and frontend servers concurrently using the unified runner script:
```bash
./run.sh
```
Review launcher details in [run.sh](run.sh).

---

## 🧭 Service Mapping & Default Logins

| Service | Target URL |
| :--- | :--- |
| **Frontend UI** | [http://localhost:5173](http://localhost:5173) |
| **Backend Swagger API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Elasticsearch Node** | [http://localhost:9200](http://localhost:9200) |
| **Kibana UI Console** | [http://localhost:5601](http://localhost:5601) |

* **Default Administrator Credentials**: Username `admin` / Password `admin123`

---

## 📡 API Endpoint Registry

All endpoints require authentication headers containing a `Bearer <token>` except authentication login endpoints.

### Authentication & User Management
- `POST` `/api/auth/login`: Authenticate credentials, return JWT access token and user metadata.
- `GET` `/api/auth/me`: Fetch active user profile payload data.
- `GET` `/api/users`: List registered users (Admin authorization required).
- `POST` `/api/users`: Register a new user profile (Admin authorization required).
- `DELETE` `/api/users/{user_id}`: Remove user account (Admin authorization required).

### Document Ingestion & Storage
- `POST` `/api/ingest`: Upload PDF file, parse layout with Docling, generate vector embeddings, and store chunks.
- `GET` `/api/documents`: List uploaded documents scoped to current user permissions and ACLs.
- `PUT` `/api/documents/{id}/access`: Update access control list (ACL) for persistent documents (Admin only).
- `DELETE` `/api/documents/{id}`: Delete PostgreSQL document record and associated Elasticsearch vector chunks.

### Chat & Intelligence
- `POST` `/api/chat`: Run hybrid search (k-NN + BM25 with RRF), generate cited answer via Gemini API.
- `POST` `/api/chat/clear`: Reset chat conversation context history for the active session.
- `POST` `/api/session/end`: Purge session-ephemeral documents and clear chat context tracking logs.
- `POST` `/api/admin/layout-preview`: Extract structural page elements for interactive layout preview canvas (Admin only).

