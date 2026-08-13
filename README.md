# 🔍 LedgerLens

Enterprise RAG (Retrieval-Augmented Generation) platform for precise financial document analysis. LedgerLens enables users to upload complex financial PDFs (earnings releases, annual reports, financial statements), parse them while preserving tabular layout and cell-merging structure, and query them in natural language with verifiable page-level citations grounded in source data.

Built with a dark terminal aesthetic, LedgerLens employs a production-grade microservices architecture, advanced layout-aware parsing, hybrid vector/keyword search with Reciprocal Rank Fusion, and LLM generation with strict role-based document access control.

---

## 🏗️ Architecture Flow & Services Overview

```
                                    ┌──────────────────────┐
                                    │  React TypeScript UI │
                                    │     (Port 5173)      │
                                    └──────────┬───────────┘
                                               │ HTTP / REST
                                               ▼
                                    ┌──────────────────────┐
                                    │  FastAPI API Gateway │
                                    │     (Port 8000)      │
                                    └──────────┬───────────┘
                                               │
               ┌───────────────────────────────┼───────────────────────────────┐
               │ Forward                       │ Forward                       │ Forward
               ▼                               ▼                               ▼
    ┌────────────────────┐          ┌────────────────────┐          ┌────────────────────┐
    │  Identity Service  │          │ Ingestion Service  │          │ RAG Engine Service │
    │    (Port 8001)     │          │    (Port 8002)     │          │    (Port 8003)     │
    └──────────┬─────────┘          └──────────┬─────────┘          └──────────┬─────────┘
               │                               │                               │
               ▼                               ▼                               ▼
    ┌────────────────────┐          ┌────────────────────┐          ┌────────────────────┐
    │  PostgreSQL + Redis│          │    IBM Docling     │          │   Elasticsearch    │
    │  (Users & Tokens)  │          │  Parser + Ollama   │          │ (Hybrid kNN + BM25)│
    └────────────────────┘          └────────────────────┘          └────────────────────┘
                                                                               │
                                                                               ▼
                                                                    ┌────────────────────┐
                                                                    │ Google Gemini 2.5  │
                                                                    │ Grounded Generator │
                                                                    └────────────────────┘
```

---

## 📂 Project Structure

```
ledgerlens/
├── services/                     # Microservices Architecture
│   ├── identity/                 # Auth, User Management, JWT & Redis Revocation (Port 8001)
│   ├── ingestion/                # PDF layout parsing (Docling), chunking & embedding (Port 8002)
│   ├── rag/                      # Hybrid search, RRF rank blending, Gemini generator (Port 8003)
│   └── gateway/                  # API Gateway, reverse proxy, JWT auth injection (Port 8000)
├── packages/common/src/common/   # Shared domain models, Pydantic schemas, database & search
├── frontend/                     # React + TypeScript + Vite workspace (Port 5173)
├── sample_pdfs/                  # Sample financial reports for testing
├── docker-compose.yml            # Containerized PostgreSQL 16, Redis 7, Elasticsearch 8.12
├── requirements.txt              # Shared Python dependencies
├── .env.example                  # Environment configuration template
└── run.sh                        # Unified single-command launcher for all microservices
```

---

## ⚡ Core Features

- **IBM Docling Ingestion Pipeline**: Layout-aware document parsing converting complex financial tables (including merged cells and multi-level headers) directly into clean Markdown, preserving table geometry and section hierarchy.
- **Hybrid Search with RRF**: Combines dense vector cosine similarity (via Ollama `embeddinggemma`, 768d) and sparse BM25 keyword search in Elasticsearch, blended using **Reciprocal Rank Fusion (RRF)** ($K=60$).
- **Microservices Architecture**: Decoupled domain services (Identity, Ingestion, RAG Engine, API Gateway) for non-blocking parallel processing, horizontal scaling, and isolated context boundaries.
- **Role-Based Access Control (RBAC)**: Support for `admin` and `employee` roles, persistent file storage vs. session-ephemeral scopes, and strict document Access Control Lists (ACLs) enforced inside the vector retrieval layer.
- **Instant Token Revocation**: Redis-backed blocklist storing invalidated JWT signatures upon logout or credential changes for immediate session termination.
- **Grounded Citation Generation**: Uses Google Gemini LLM with low-temperature constraints and strict prompt engineering to generate answers mapped directly to source page numbers (`[pX_cY]`).

---

## 🧭 Service Mapping & Default Credentials

| Service / Layer | URL Endpoint | Port | Description |
| :--- | :--- | :---: | :--- |
| **Frontend Workspace** | [http://localhost:5173](http://localhost:5173) | `5173` | React + Vite dark terminal interface |
| **API Gateway** | [http://localhost:8000](http://localhost:8000) | `8000` | Central Reverse Proxy & Swagger Docs (`/docs`) |
| **Identity Service** | [http://localhost:8001](http://localhost:8001) | `8001` | Authentication & User Management API |
| **Ingestion Service** | [http://localhost:8002](http://localhost:8002) | `8002` | Async PDF Layout Parsing & Vector Ingestion |
| **RAG Engine Service** | [http://localhost:8003](http://localhost:8003) | `8003` | Retrieval, Hybrid Search & Gemini Generation |
| **Elasticsearch Node** | [http://localhost:9200](http://localhost:9200) | `9200` | Vector & Keyword Search Engine |
| **PostgreSQL DB** | `localhost:5432` | `5432` | Relational Metadata & Chat History Storage |
| **Redis Cache** | `localhost:6379` | `6379` | Token Revocation & Job Status Queue |

* **Default Administrator Credentials**: `admin` / `admin123`

---

## 🔐 Role & Permission Matrix

| Feature / Capability | Admin Role | Employee Role |
| :--- | :---: | :---: |
| Authenticate & Access Chat Workspace | ✅ | ✅ |
| Upload Ephemeral (Session) Documents | ✅ | ✅ |
| Upload Persistent Documents | ✅ | ✅ |
| View All Persistent Documents | ✅ | 🔒 (Scope / ACL limited) |
| Manage User Registry (Create / Delete Users) | ✅ | ❌ |
| Update Document Access Control Lists (ACLs) | ✅ | ❌ |
| Wipe Entire Document Index & Cache | ✅ | ❌ |

---

## 🛠️ Environment Configurations

Create a `.env` file at the root level using `.env.example` as a reference. Configuration defaults are maintained in [packages/common/src/common/config.py](packages/common/src/common/config.py).

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | — | **Required.** Google AI Studio Gemini API Key |
| `JWT_SECRET` | — | **Required.** Signing key for JWT authentication |
| `GENERATION_MODEL` | `gemini-2.5-flash` | Gemini model used for grounded chat generation |
| `DATABASE_URL` | `postgresql://postgres:postgrespassword@localhost:5432/ledgerlens` | Primary relational database URL |
| `REDIS_URL` | `redis://localhost:6379/0` | Redis instance for blocklist & task state |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch server endpoint |
| `ES_INDEX` | `ledgerlens_chunks` | Elasticsearch target index name |
| `OLLAMA_HOST` | `http://localhost:11434` | Ollama service address for vector embeddings |
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama model utilized for dense embeddings |

---

## 🚀 Quick Start

### Prerequisites
- [Docker & Docker Desktop](https://www.docker.com/)
- Python 3.11+
- Node.js 18+ & npm
- [Ollama](https://ollama.com/) (Optional: for local vector embeddings)

```bash
# Pull vector embedding model if using Ollama
ollama pull embeddinggemma
```

### 1. Configure Environment
Create `.env` at root level from the template and set your `GEMINI_API_KEY`:
```bash
cp .env.example .env
# Edit .env and supply your GEMINI_API_KEY
```

### 2. Unified System Boot (Recommended)
The single-command launcher starts database services, verifies ports, and runs all microservices and frontend concurrently:
```bash
chmod +x run.sh
./run.sh
```

### 3. Manual / Step-by-Step Setup

#### A. Launch Database Stack
```bash
docker compose up -d postgres redis elasticsearch
```

#### B. Install Python Dependencies
```bash
pip install -r requirements.txt
export PYTHONPATH="$(pwd)/packages/common/src:$(pwd)"
```

#### C. Launch Microservices
Run each service in separate terminal windows:
```bash
# 1. Identity Service
uvicorn services.identity.main:app --port 8001

# 2. Ingestion Service
uvicorn services.ingestion.main:app --port 8002

# 3. RAG Engine Service
uvicorn services.rag.main:app --port 8003

# 4. API Gateway
uvicorn services.gateway.main:app --port 8000
```

#### D. Launch Frontend Workspace
```bash
cd frontend
npm install
npm run dev
```

---

## 📡 API Endpoint Registry

All routes require authentication headers containing a `Bearer <token>` except authentication endpoints (`/api/auth/login`).

### Authentication & Users
- `POST` `/api/auth/login`: Authenticate credentials, return JWT and profile details.
- `GET` `/api/auth/me`: Fetch active user profile metadata.
- `GET` `/api/users`: List registered users (Admin only).
- `POST` `/api/users`: Create a new user profile (Admin only).
- `DELETE` `/api/users/{user_id}`: Delete user account (Admin only).

### Document Ingestion & Storage
- `POST` `/api/ingest`: Receive PDF files, extract chunks, compute embeddings, insert data.
- `GET` `/api/documents`: List uploaded files filtered by RBAC and ACL permissions.
- `GET` `/api/ingest/jobs/{job_id}`: Poll background ingestion job status (`pending` / `processing` / `completed` / `failed`).
- `PUT` `/api/documents/{id}/access`: Update Access Control List (ACL) permissions (Admin only).
- `DELETE` `/api/documents/{id}`: Remove document record, PDF binary, and vector chunks.
- `DELETE` `/api/embeddings`: Wipe total document store, vector chunks, and uploads.

### Chat & Search Engine
- `POST` `/api/chat`: Execute RRF hybrid search and generate grounded response with page citations.
- `GET`/`POST` `/api/chat/sessions`: List or create chat session threads.
- `GET` `/api/chat/sessions/{id}`: Fetch session history and message timeline.
- `POST` `/api/chat/clear`: Reset chat history for a session.
- `POST` `/api/chat/delete`: Remove session thread and associated messages.
- `POST` `/api/session/end`: Purge session-ephemeral files and reset chat state.
