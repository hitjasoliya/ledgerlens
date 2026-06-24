# 🔍 LedgerLens

Enterprise RAG (Retrieval-Augmented Generation) platform for precise financial document analysis. LedgerLens allows you to upload complex PDFs (earnings releases, annual reports, financial statements), parse them preserving tabular layout and cell-merging structure, and query them in natural language with page-level citations grounded in the source data.

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
 │     Elasticsearch      │ ──► Persistent vector store
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
 │    RRF Merge (K=60)    │ ──► Reciprocal Rank Fusion blending
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │   Gemini Flash 1.5     │ ──► Generation with strict grounded constraints
 └────────────────────────┘
         │
         ▼
 ┌────────────────────────┐
 │  Citation Parser & UI  │ ──► Highlights cited page bounding boxes in preview
 └────────────────────────┘
```

---

## ⚡ Core Features

- **IBM Docling Parsing Ingestion**: Layout-aware parsing that converts complex financial tables (including merged cells and multi-level headers) directly to clean Markdown. Includes automatic figure caption matching and hierarchical heading injection.
- **Hybrid Search with RRF**: Combines dense vector cosine similarity (via Ollama `embeddinggemma`) and sparse BM25 keyword matching, merged via a **Reciprocal Rank Fusion (RRF)** rank blending algorithm.
- **Hierarchical Access Boundaries (RBAC)**: Supports roles (`admin` and `employee`), persistent document storage vs. session-ephemeral scopes, and document-level Access Control Lists (ACLs).
- **Interactive Layout Inspector**: Administrators can upload any document to view layout region breakdowns (Tables, Text, Figures, Headers) projected over rendered PDF page canvas layouts.
- **Stateful Answer Citation**: The generative engine validates LLM source indicators against retrieved document chunk scopes, returning page numbers mapped directly to vector source blocks.

---

## 🛠️ Environment Configurations

Save your environment variables inside the backend configurations. Let's see [config.py](file:///Users/kuldeepsinh/Desktop/ledgerlens/backend/rag/utils/config.py) for structural defaults.

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

### 1. Launch Databases
Start Elasticsearch and PostgreSQL services via Docker:
```bash
docker compose up -d
```
Verify databases configuration in the [docker-compose.yml](file:///Users/kuldeepsinh/Desktop/ledgerlens/docker-compose.yml).

### 2. Configure Environment variables
Duplicate `.env.example` in the backend directory and configure your keys:
```bash
cd backend
cp .env.example .env
# Edit .env and supply GEMINI_API_KEY and JWT_SECRET
```

### 3. Backend Setup
Create your conda environment and install dependencies:
```bash
conda create -n ledgerlens python=3.11 -y
conda activate ledgerlens
pip install docling fastapi uvicorn python-dotenv pydantic sqlalchemy psycopg2-binary PyJWT bcrypt "elasticsearch>=8.0,<9.0" tiktoken python-multipart rich requests google-generativeai PyMuPDF
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
You can launch databases, check ports, check environment settings, check Ollama configurations, and run both servers concurrently using the provided launcher:
```bash
./run.sh
```
Review launcher details in [run.sh](file:///Users/kuldeepsinh/Desktop/ledgerlens/run.sh).

---

## 🧭 Service Mapping & Logins

| Service | Target URL |
| :--- | :--- |
| **Frontend UI** | [http://localhost:5173](http://localhost:5173) |
| **Backend Swagger API Docs** | [http://localhost:8000/docs](http://localhost:8000/docs) |
| **Elasticsearch Node** | [http://localhost:9200](http://localhost:9200) |
| **Kibana UI Console** | [http://localhost:5601](http://localhost:5601) |

* **Default Administrator Login credentials**: `admin` / `admin123`

---

## 📡 API Endpoint Registry

All routes require authentication headers containing a Bearer token except authentication endpoints.

### Authentication & Users
- `POST` `/api/auth/login`: Authenticate credentials, return JWT and user metadata.
- `GET` `/api/auth/me`: Get active profile payload data.
- `GET`/`POST`/`DELETE` `/api/users`: Manage user registries (Admin authorization required).

### Document Ingestion & Storage
- `POST` `/api/ingest`: Receive PDF files, extract chunks, compute embeddings, and insert data.
- `GET` `/api/documents`: List uploaded database files scoped to authorization permissions.
- `PUT` `/api/documents/{id}/access`: Update access lists (ACL) for persistent files.
- `DELETE` `/api/documents/{id}`: Delete PostgreSQL document logs and Elasticsearch index references.

### Chat & Search
- `POST` `/api/chat`: Run vector searches, rank contexts using RRF, generate cited response blocks.
- `POST` `/api/chat/clear`: Clear current chat history context flags.
- `POST` `/api/session/end`: Wipe ephemeral documents and clear history tracking logs.
- `POST` `/api/admin/layout-preview`: Extract structural page elements for layout preview canvases (Admin only).

