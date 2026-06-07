# CapitalQuery — Enterprise RAG Document Intelligence

CapitalQuery is an enterprise-grade Retrieval-Augmented Generation (RAG) platform designed to make complex financial PDF documents — earnings releases, board outcomes, annual reports — interactively queryable in natural language with page-level citations.

Unlike generic chatbot wrappers, CapitalQuery implements a layout-aware visual ingestion pipeline (using deep-learning-based region detection and table reconstruction) and enforces strict database-backed Role-Based Access Control (RBAC) via JWT tokens.

---

## Architecture Overview

```
                                  +---------------------------------------+
                                  |               Frontend                |
                                  |         React 19 + Vite + TS          |
                                  |         http://localhost:5173         |
                                  +-------------------+-------------------+
                                                      |
                                                      | REST API (JWT Bearer)
                                                      v
+---------------------------------------------------------------------------------------------------------+
|                                         Backend — FastAPI (Python 3.10)                                 |
|                                             http://localhost:8000                                       |
|                                                                                                         |
|  +--------------------+    +-----------------------------+    +------------------+    +--------------+  |
|  |     Auth & RBAC    |    |  Visual Ingestion Pipeline  |    |  RAG Orchestrator|    | Intelligence |  |
|  | - JWT verification |    |  - PyMuPDF Page Renderer    |    |  - Memory (6-turn|    | - Embedder   |  |
|  | - User Management  |    |  - LayoutParser (PubLayNet) |    |  - Hybrid Search |    |   (Ollama)   |  |
|  | - bcrypt hashing   |    |  - Table Transformer (TATR) |    |  - RRF Merge     |    | - Generator  |  |
|  | - SQLAlchemy CRM   |    |  - Chunker (tiktoken)       |    |  - Citation      |    |   (Gemini)   |  |
|  +---------+----------+    +--------------+--------------+    +--------+---------+    +-------+------+  |
+------------|------------------------------|----------------------------|----------------------|---------+
             |                              |                            |                      |
             v                              v                            v                      v
  +--------------------+        +-----------------------+      +-------------------+  +-------------------+
  | PostgreSQL (User)  |        | Figures Directory     |      | Elasticsearch     |  | Ollama & Gemini   |
  | localhost:5432     |        | static/figures/*.png  |      | localhost:9200    |  | Local Embed/Gemini|
  +--------------------+        +-----------------------+      +-------------------+  +-------------------+
```

---

## Key Features

### 1. Visual Layout-Aware Ingestion Pipeline
Instead of relying on crude plain-text parsing that scrambles multicolumn text and tables, CapitalQuery processes PDFs visually:
* **Page Rendering**: Pages are rendered to 200 DPI images using `PyMuPDF` (`fitz`).
* **Visual Region Detection**: `LayoutParser` (with a pre-trained PubLayNet model) segments each page into logical zones: `text`, `title`, `list`, `table`, and `figure`.
* **Table Reconstruction**: Microsoft's **Table Transformer (TATR)** model processes visual table zones, converting rows and columns into clean Markdown tables. When TATR returns empty cells, it automatically falls back to layout-aligned `pdfplumber` extraction.
* **Figure Extraction**: Image figures are cropped and stored as PNGs in `static/figures/` for citation purposes, accompanied by a deterministic metadata description.
* **Atomic Chunking**: Tables and figures are chunked as single, atomic blocks (never split across chunks), preserving semantic relationships.

### 2. Database-backed Access Control (RBAC)
* **Two Roles**: `admin` and `employee`.
* **Document Scopes**:
  * **Ephemeral Ingestion**: PDFs uploaded during a chat session live only for the duration of that session (`is_persistent: false`) and are purged on `/api/session/end`.
  * **Persistent Library**: Documents are indexed long-term (`is_persistent: true`). Access can be marked `public` (accessible to all) or mapped to specific user IDs in the access control list (ACL).
* **Search-Time ACL Filtering**: Every query executes a strict 4-branch security filter in Elasticsearch, checking session ID, owner ID, public flags, and explicit allowed-user lists before returning context.

### 3. High-Fidelity Retrieval & Citations
* **Hybrid Search**: Fuses dense vector search (768-dimensional local Ollama `embeddinggemma` embeddings with cosine similarity) and BM25 lexical keyword matching.
* **Reciprocal Rank Fusion (RRF)**: Merges the results of lexical and vector matches with a constant `K = 60` to guarantee high relevance.
* **Citation Grounding**: Gemini is prompted to cite specific pages. The orchestrator parses citations from the response, matches them against the retrieved document chunks, and provides page-level citation metadata.

---

## Prerequisites

| Technology | Recommended Version | Purpose |
| :--- | :--- | :--- |
| **Python / Conda** | `Miniconda3` (Python 3.10) | Backend runtime & deep learning packages |
| **Node.js** | `≥ 18` | Frontend building and dev server |
| **Docker & Compose** | Latest | Hosts Elasticsearch and PostgreSQL databases |
| **Ollama (Local)** | Running model: `embeddinggemma` | Local embedding generation (no API key or network calls required) |
| **Gemini API Key** | — | Answer synthesis / LLM generator |

---

## Quick Start

### 1. Spin Up Database Services (Elasticsearch & PostgreSQL)

Start the Docker Compose containers:
```bash
docker compose up -d
```

Confirm that the services are healthy:
```bash
docker compose ps
```
* Note: A default administrator account is automatically seeded into the database on startup:
  * **Username**: `admin`
  * **Password**: `admin123`
  * **Role**: `admin`

### 2. Backend Setup (Miniconda)

We recommend using **Miniconda** to manage Python packages because deep learning packages (PaddlePaddle, LayoutParser, PyTorch) require specific binary dependencies.

```bash
cd backend

# Create and activate the conda environment
conda create -n kingslayer python=3.10 -y
conda activate kingslayer

# Install backend dependencies
pip install -r requirements.txt

# Configure environment variables
cp .env.example .env
# Edit .env and paste your GEMINI_API_KEY
```

Start the FastAPI backend server:
```bash
uvicorn app.main:app --reload --port 8000
```
* The API will run at **http://localhost:8000**
* Interactive OpenAPI documentation is available at **http://localhost:8000/docs**
* Verify API health at **http://localhost:8000/health**

### 3. Frontend Setup

```bash
cd frontend

# Install packages
npm install

# Start the local development server
npm run dev
```
* The React application will run at **http://localhost:5173**

---

## Running Verification Tests

The codebase includes comprehensive tests to verify database, auth, layout ingestion, and search integration. Make sure you are inside the active Conda environment.

### 1. Database & JWT Authentication Integration Tests
Tests password hashing, user registration, JWT generation, and RBAC endpoint guards:
```bash
cd backend
python -m tests.auth_test
```

### 2. Visual Layout Ingestion Pipeline Tests
Runs the full page rendering, PubLayNet model segmentation, TATR table extraction, and tiktoken chunking pipeline on a sample PDF:
```bash
cd backend
python -m tests.layout_test
```

### 3. Full System Smoke Tests
Verifies Elasticsearch connectivity, index mappings creation, hybrid RRF search execution, page rendering, and layout detection:
```bash
cd backend
python -m tests.smoke_test
```
> [!WARNING]
> The smoke test deletes and recreates the `rag_chunks` Elasticsearch index for a clean test run. Do not execute this test in a production environment.

---

## CLI Usage (Terminal Mode)

CapitalQuery features a Rich-powered CLI mode for terminal-based document ingestion and interactive chat without launching the web application.

```bash
cd backend
conda activate kingslayer

# Ingest a PDF file into the database
python -m rag --ingest sample_pdfs/AEL_Earnings_Presentation_Q2-FY26.pdf

# Start an interactive CLI chat session
python -m rag --chat
```
Inside the CLI chat:
* Type a question and hit **Enter** to see the answer generated with layout-aware context.
* Source citation page numbers will be printed directly underneath the response.
* Type `q`, `quit`, or `exit` to exit the session.

---

## Environment Variables Reference

### Backend (`backend/.env`)

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `GEMINI_API_KEY` | — | **Required.** Your Google Gemini API Key (for LLM generation) |
| `EMBEDDING_MODEL` | `embeddinggemma` | Ollama embedding model name |
| `EMBEDDING_DIMS` | `768` | Dimension size of the embedding model |
| `OLLAMA_HOST` | `http://localhost:11434` | Local Ollama host URL endpoint |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch service host URL |
| `ES_INDEX` | `rag_chunks` | Index name for vector storage |
| `CHUNK_SIZE` | `500` | Token limit for body text chunks |
| `CHUNK_OVERLAP` | `50` | Overlap token size between chunks |
| `TOP_K` | `5` | Number of chunks retrieved per search method (lexical/vector) |
| `DATABASE_URL` | `postgresql://postgres:postgres@localhost:5432/capitalquery` | PostgreSQL connection string |
| `JWT_SECRET` | `super_secret_jwt_key_change_me_in_production` | Secret key used for signing JWT tokens |
| `JWT_ALGORITHM` | `HS256` | JWT signing algorithm |
| `JWT_ACCESS_TOKEN_EXPIRE_MINUTES` | `1440` | Duration (in minutes) before JWT token expires |
| `LAYOUT_MODEL` | `lp://PubLayNet/ppyolov2_r50vd_dcn_365e` | PubLayNet layout model layoutparser string |
| `LAYOUT_CONFIDENCE_THRESHOLD` | `0.5` | Minimum confidence score to accept detected regions |
| `RENDER_DPI` | `200` | Page rendering resolution (DPI) |
| `TABLE_MODEL` | `microsoft/table-transformer-structure-recognition-v1.1-all` | Hugging Face model path for Table Transformer |
| `TABLE_DEVICE` | `cpu` | Device execution mapping (`cpu` or `cuda`) |
| `FIGURE_CAPTION_MAX_CHARS`| `400` | Maximum length of character description for visual figures |

### Frontend (`frontend/.env.development`)

| Variable | Default Value | Description |
| :--- | :--- | :--- |
| `VITE_API_URL` | `http://localhost:8000` | FastAPI backend URL endpoint |

---

## API Endpoints Reference

| Method | Endpoint | Authorization | Description |
| :--- | :--- | :--- | :--- |
| `GET` | `/health` | None | Liveness check |
| `POST` | `/api/auth/login` | None | Exchange credentials for a JWT token |
| `GET` | `/api/auth/me` | User / Admin | Get profile of the current authenticated user |
| `GET` | `/api/users` | Admin Only | List all registered users |
| `POST` | `/api/users` | Admin Only | Register a new user |
| `DELETE`| `/api/users/{id}` | Admin Only | Delete a user from the database |
| `POST` | `/api/ingest` | User / Admin | Visual PDF upload (multipart/form-data) |
| `POST` | `/api/chat` | User / Admin | Submit message and run hybrid vector-lexical RAG |
| `POST` | `/api/chat/clear` | User / Admin | Reset current user's session chat history |
| `POST` | `/api/session/end`| User / Admin | Purge ephemeral chunks & clear session |

---

## Technical Details & Troubleshooting

### 1. LayoutParser Weights Downloading
On the first PDF ingestion, `LayoutParser` attempts to download the pre-trained Paddle model weights from Facebook's storage (`dl.fbaipublicfiles.com`). 
* **Issue**: If the request fails due to corporate firewall policies or connection timeouts, the ingestion pipeline will log the error and **gracefully fall back** to the plain-text parser using `pdfplumber`.
* **Fix**: If you need visual layout parsing in an offline environment, pre-download the model and override `LAYOUT_MODEL` with the path to the local model weights file.

### 2. CPU vs. GPU PaddlePaddle Configuration
By default, the backend configures `paddlepaddle` for CPU execution.
* If you run the backend on a GPU-enabled instance, replace `paddlepaddle` with `paddlepaddle-gpu` in `backend/requirements.txt` to speed up visual segmentation and table reconstruction.

### 3. Bcrypt Password Length Error
* **Context**: FastAPI context validations sometimes wrap password verification dry-runs with `passlib`, which triggers `ValueError: password cannot be longer than 72 bytes` due to a library bug in newer bcrypt versions.
* **Fix**: CapitalQuery bypasses `passlib` entirely. It calls the native `bcrypt` package directly in `backend/app/auth.py` for clean, secure hashing and comparison without limits.

### 4. Elasticsearch Connection Failures
* Ensure Docker Compose is fully running and that `docker compose ps` shows `healthy`.
* If the FastAPI backend is running inside a Docker container rather than the host machine, update `ES_HOST` in `.env` to `http://elasticsearch:9200` instead of `http://localhost:9200`.

---

## Team

**Powermind — PS2 KingSlayer**
* Built as a production-grade enterprise document-intelligence solution.
