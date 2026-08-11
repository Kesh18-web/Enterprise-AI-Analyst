# Enterprise AI Analyst Runtime & Hybrid RAG Engine 🚀

A state-of-the-art, production-grade enterprise multi-agent cognitive workspace and Hybrid RAG Engine built with **LangGraph**, **FastAPI**, **Qdrant Cloud**, **GCP Firestore**, **Redis**, and **Next.js 16**.

---

## 🌟 Architectural System Overview

The **Enterprise AI Analyst** is designed for mission-critical enterprise document analysis, compliance auditing, and intelligent information retrieval. It combines a 8-node cognitive state machine graph with multi-provider LLM orchestration and a dynamic hybrid search pipeline.

```text
                               ┌──────────────────────────────────────────────┐
                               │             User Inquiry / Query             │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │        Dual-Tier Caching Engine (0ms)        │
                               │  Exact Hash (T1) + Cosine Vector 0.75 (T2)   │
                               └──────────────────────┬───────────────────────┘
                                                      │ (Cache Miss)
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │           Input Security Guardrail           │
                               │   Jailbreak / Prompt Extraction Defense      │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │     Planner Agent (Groq Llama 3.3 70B)       │
                               │ Intent Taxonomy & Dynamic Sub-Task Splitting  │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │      Model Router Agent (Dynamic SOTA)       │
                               │ Classifies complexity -> Assigns LLM Tier    │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │            Hybrid Retrieval Node             │
                               │  BM25 Okapi + Qdrant Dense Vector Fusion      │
                               │      + HuggingFace Cross-Encoder Rerank      │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │     Analysis Agent (DeepSeek V4 Flash)       │
                               │ Multi-Doc Evidence Synthesis & Citations      │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │        Reflection & Self-Critique Node       │
                               │ Re-planning Loop if Confidence < 0.60         │
                               └──────────────────────┬───────────────────────┘
                                                      │
                                                      ▼
                               ┌──────────────────────────────────────────────┐
                               │    LLM-as-a-Judge Evaluation (Gemini 2.5)    │
                               │   Computes Groundedness & Faithfulness      │
                               └──────────────────────────────────────────────┘
```

---

## ⚙️ Core Technical Features

### 1. Multi-Provider Tier-1 LLM Orchestration
- **Primary Synthesis Engine**: OpenCode / OpenRouter **DeepSeek V4 Flash Free** (`deepseek-v4-flash-free`) for deep reasoning and multi-document synthesis.
- **Intent Classification & Planning**: **Groq Llama 3.3 70B** (`llama-3.3-70b-versatile`) for sub-millisecond intent routing and task decomposition.
- **Auditing & Evaluation**: **Google Gemini 2.5 Flash / 3.5 Flash** for rapid, high-speed LLM-as-a-Judge compliance evaluation.
- **3-Way Automated Failover**: Built-in fallbacks across OpenCode $\rightarrow$ Groq $\rightarrow$ Google Gemini to ensure zero uptime interruption.

### 2. Advanced Hybrid Retrieval & Reranking Pipeline
- **Dual Vector & Keyword Search**: Combines dense semantic vectors (`all-MiniLM-L6-v2` 384-dim) stored in **Qdrant Cloud** with exact keyword matching powered by **BM25 Okapi**.
- **Weighted Reciprocal Rank Fusion (Weighted RRF)**: Merges dense and lexical hit streams dynamically based on Planner Agent query weight allocation.
- **Cross-Encoder Reranking**: Re-scores top candidate chunks using a local HuggingFace Cross-Encoder Transformer (`cross-encoder/ms-marco-MiniLM-L-6-v2`) to eliminate hallucinated or weakly-relevant context.
- **Document Deduplication Lab**: Automated SHA-256 content hashing prevents duplicate chunk embedding generation on re-uploads.

### 3. Dual-Tier Semantic Caching Engine
- **Tier 1 (Exact Hash)**: Instant 0ms response lookup for identical raw user query strings.
- **Tier 2 (Semantic Cosine Similarity)**: Vector similarity cache calibrated at a similarity threshold of `0.75` (`all-MiniLM-L6-v2`) to capture natural language query rephrasings with sub-5ms response times.
- **Session-Scoped Isolation**: Guarantees cache entries are strictly scoped by `session_id` to eliminate cross-session data leakage.

### 4. Layered Security & Compliance Guardrails
- **Pre-LLM Guardrail**: Classifies inquiries into enterprise security taxonomies (`PROMPT_EXTRACTION`, `PERSONA_JAILBREAK`, `INSTRUCTION_OVERRIDE`) to block unauthorized system prompt leakage.
- **Post-LLM Guardrail**: Redacts sensitive PII, API tokens, and credentials prior to UI streaming.
- **Automated Citation Mapping**: Extracts, verifies, and maps numbered footnotes `[Doc N]` directly back to verified document source metadata.

### 5. Dual-Memory & Firestore Persistence
- **Short-Term Memory**: Keeps active conversation turns in state for pronoun/coreference resolution.
- **Long-Term Memory**: Compacts and synthesizes prior chat history into Firestore user documents under `users/{uid}/chat_sessions/{session_id}`.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Agent Orchestration** | LangGraph StateGraph (Python 3.12) |
| **Backend API** | FastAPI, Uvicorn, Server-Sent Events (SSE) |
| **LLM Providers** | DeepSeek V4, Groq Llama 3.3 70B, Google Gemini 2.5/3.5 |
| **Vector Database** | Qdrant Cloud Cluster |
| **Keyword Search** | BM25 Okapi (`rank-bm25`) |
| **Reranking Model** | HuggingFace Cross-Encoder (`ms-marco-MiniLM-L-6-v2`) |
| **Database & Auth** | GCP Firestore, Firebase Admin SDK |
| **Caching Layer** | Redis Cloud / In-Memory Vector Store |
| **Frontend UI** | Next.js 16 (App Router), React 19, TailwindCSS, Lucide Icons |
| **Deployment** | Railway Monorepo (Docker / Nixpacks) |

---

## 🚀 Getting Started & Local Development

### 1. Prerequisites
- Python 3.12+
- Node.js 20+
- Git

### 2. Backend Setup
```bash
# Navigate to backend directory
cd backend

# Create virtual environment
python -m venv venv

# Activate virtual environment (Windows PowerShell)
.\venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Start backend FastAPI development server
python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000
```

The backend health endpoint will be active at: `http://localhost:8000/api/v1/health`

### 3. Frontend Setup
```bash
# Open a new terminal and navigate to frontend directory
cd frontend

# Install dependencies
npm install

# Start Next.js 16 development server
npm run dev
```

Open `http://localhost:3000` in your browser to access the Analyst Command Center UI.

---

## ☁️ Deployment Guide (Railway Containerized Monorepo)

Both the backend and frontend are pre-configured for instant zero-downtime deployment on **Railway**.

### Production Configurations Included:
- **`backend/Dockerfile`**: Python 3.12 container specification.
- **`backend/Procfile`**: Uvicorn production server entrypoint.
- **`frontend/Dockerfile`**: Multi-stage standalone Next.js 16 builder.
- **`frontend/next.config.ts`**: Output standalone configuration.

### Railway Quick Setup:
1. **Backend Service**: Set Root Directory to `/backend` on Railway.
2. **Frontend Service**: Set Root Directory to `/frontend` on Railway and set `NEXT_PUBLIC_API_URL` to your live Railway backend URL.

---

## 🧪 Verification & Testing Suite

Run standalone automated verification scripts located in `backend/scripts/`:

```bash
# Test document deduplication and index hashing
python backend/scripts/test_doc_dedup.py

# Test authentication persistence
python backend/scripts/test_auth_persistence.py

# Test LLM failover fallback chains
python backend/scripts/test_llm_fallback.py
```

---

## 📄 License

This project is licensed under the MIT License — see the LICENSE file for details.
