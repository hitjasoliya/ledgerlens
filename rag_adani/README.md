# RAG Adani — Financial Document Q&A Chatbot

A CLI-based Retrieval-Augmented Generation (RAG) chatbot that ingests financial PDFs, indexes them with hybrid search, and answers natural-language questions with page-number citations.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Layer 1 — Interaction (main.py)                            │
│  CLI: --ingest <pdf> | --chat                               │
├─────────────────────────────────────────────────────────────┤
│  Layer 2 — Orchestration (orchestrator/engine.py)           │
│  RAGEngine: embed → search → generate → cite                │
├──────────────────────────┬──────────────────────────────────┤
│  Layer 3 — Data          │  Layer 4 — Intelligence          │
│  ingestion/parser.py     │  intelligence/embedder.py        │
│  ingestion/chunker.py    │  intelligence/generator.py       │
│  ingestion/pipeline.py   │  (Gemini text-embedding-004      │
│  (pdfplumber +           │   + Gemini 2.0 Flash)            │
│   unstructured + tiktoken)│                                  │
├──────────────────────────┴──────────────────────────────────┤
│  Layer 5 — Storage (storage/es_client.py)                   │
│  Elasticsearch 8.x: BM25 + dense_vector + RRF hybrid       │
└─────────────────────────────────────────────────────────────┘
```

## Prerequisites

| Requirement | Version |
|-------------|---------|
| Python | 3.11+ |
| Docker & Docker Compose | Latest |
| Google Gemini API Key | Free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey) |

## Setup

### 1. Clone the repository

```bash
git clone https://github.com/Powermind-Hackathon/ps2_kingslayer.git
cd ps2_kingslayer/rag_adani
```

### 2. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Gemini API key (get one free at [aistudio.google.com/apikey](https://aistudio.google.com/apikey)):

```
GEMINI_API_KEY=your-gemini-api-key-here
ES_HOST=http://localhost:9200
ES_INDEX=rag_chunks
CHUNK_SIZE=500
CHUNK_OVERLAP=50
TOP_K=5
```

### 3. Start Elasticsearch & Kibana

```bash
docker-compose up -d
```

Wait ~30 seconds for Elasticsearch to be ready. Verify:

```bash
curl http://localhost:9200
```

Kibana is available at [http://localhost:5601](http://localhost:5601) for debugging.

### 4. Create a virtual environment & install dependencies

```bash
# Create venv
python -m venv venv

# Activate — Windows:
venv\Scripts\activate
# Activate — macOS/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

## Usage

### Ingest a PDF

```bash
python main.py --ingest path/to/annual_report.pdf
```

This will:
1. Parse the PDF (pdfplumber + unstructured for table pages)
2. Chunk text into 500-token segments with 50-token overlap
3. Generate embeddings via Gemini (text-embedding-004, 768 dims)
4. Index all chunks in Elasticsearch with hybrid mappings

Output:
```
──────────────── Ingesting: annual_report.pdf ────────────────

Step 1/4: Parsing PDF...
  ✓ 42 page(s) extracted

Step 2/4: Chunking text...
  ✓ 128 chunk(s) created

Step 3/4: Generating embeddings...
  Embedding chunks ━━━━━━━━━━━━━━━━ 128/128 0:00:04

Step 4/4: Indexing in Elasticsearch...
  Indexing chunks  ━━━━━━━━━━━━━━━━ 128/128 0:00:01

╭─ Summary ────────────────────────────────────────────────╮
│ ✓ Ingestion complete!                                    │
│   Source:          annual_report.pdf                      │
│   Pages parsed:    42                                    │
│   Chunks created:  128                                   │
│   Chunks indexed:  128                                   │
╰──────────────────────────────────────────────────────────╯
```

### Start a chat session

```bash
python main.py --chat
```

### Example Q&A Session

```
╭──────────────────────────────────────────────────────────╮
│  📊 RAG Financial Document Q&A                           │
│                                                          │
│  Ask questions about your ingested documents.            │
│  Type exit or press Ctrl+C to quit.                      │
╰──────────────────────────────────────────────────────────╯

✓ Engine ready. Start asking questions!

You: What was the total revenue for FY2024?

╭─ Answer ─────────────────────────────────────────────────╮
│ The total revenue for FY2024 was $45.2 billion,          │
│ representing a 12% increase year-over-year.              │
│ [Sources: p3, p7]                                        │
╰──────────────────────────────────────────────────────────╯
  → Page 3 (p3_c1)
  → Page 7 (p7_c2)

You: How did operating expenses change?

╭─ Answer ─────────────────────────────────────────────────╮
│ Operating expenses increased to $28.1 billion,           │
│ primarily driven by increased R&D investment.            │
│ [Sources: p7, p12]                                       │
╰──────────────────────────────────────────────────────────╯
  → Page 7 (p7_c2)
  → Page 12 (p12_c0)

You: What is the CEO's favorite color?

╭─ Answer ─────────────────────────────────────────────────╮
│ Not found in the document.                               │
╰──────────────────────────────────────────────────────────╯
  → No specific citations

You: exit
👋 Goodbye!
```

## Run the smoke test

```bash
python -m tests.smoke_test
```

This creates the ES index, inserts 2 dummy chunks with fake embeddings, runs a hybrid search, and verifies results are returned.

## Project Structure

```
rag_adani/
├── docker-compose.yml           # Elasticsearch 8.x + Kibana
├── .env.example                 # Environment variable template
├── .gitignore                   # Keeps venv, .env, caches out of git
├── requirements.txt             # Python dependencies
├── README.md                    # This file
│
├── main.py                      # Layer 1: CLI (--ingest / --chat)
│
├── Sample/                      # Place your PDF files here for ingestion
│
├── orchestrator/
│   ├── __init__.py
│   └── engine.py                # Layer 2: RAG engine + conversation memory
│
├── ingestion/
│   ├── __init__.py
│   ├── parser.py                # Layer 3: pdfplumber + unstructured parsing
│   ├── chunker.py               # Layer 3: tiktoken sliding-window chunker
│   └── ingest_pipeline.py       # Layer 3: parse → chunk → embed → index
│
├── intelligence/
│   ├── __init__.py
│   ├── embedder.py              # Layer 4: OpenAI embedding wrapper
│   └── generator.py             # Layer 4: GPT-4o-mini generation + system prompt
│
├── storage/
│   ├── __init__.py
│   └── es_client.py             # Layer 5: ES index + hybrid search (RRF)
│
├── utils/
│   ├── __init__.py
│   └── config.py                # Centralised .env config loader
│
└── tests/
    └── smoke_test.py            # Integration smoke test
```

## Configuration Reference

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | — | Your Google Gemini API key — free at [aistudio.google.com](https://aistudio.google.com/apikey) |
| `ES_HOST` | `http://localhost:9200` | Elasticsearch URL |
| `ES_INDEX` | `rag_chunks` | Index name for document chunks |
| `CHUNK_SIZE` | `500` | Token count per chunk |
| `CHUNK_OVERLAP` | `50` | Overlapping tokens between chunks |
| `TOP_K` | `5` | Number of chunks retrieved per query |

## Troubleshooting

| Problem | Solution |
|---------|----------|
| `ConnectionError: Failed to connect to Elasticsearch` | Run `docker-compose up -d` and wait 30s |
| `ValueError: GEMINI_API_KEY is not set` | Check your `.env` file has a valid key |
| `unstructured` import error | Run `pip install "unstructured[pdf]"` — parser falls back to pdfplumber if missing |
| Empty answers / "Not found" | Make sure you ran `--ingest` first with the same ES index |

## License

Built for the Powermind Hackathon 2026.
