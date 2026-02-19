# 🌾 Farmer RAG Advisory System (Backend)

Backend API for an AI-powered agricultural advisory system for smallholder farmers in East Africa. This service provides RAG-based responses, weather/market tools, document ingestion, and pgvector search via FastAPI.

## 🎯 Project Overview

This system implements a **RAG-enabled agent** that:

- Retrieves information from agricultural knowledge bases
- Fetches real-time weather forecasts
- Provides market price guidance
- Verifies responses for groundedness (factual accuracy)

Built for **04-801-W3 Agentic AI: Fundamentals and Applications** at Carnegie Mellon University.

## 🏗️ Architecture (Backend)

```text
┌─────────────────────────────────────────────────────────────────┐
│                    FARMER RAG SYSTEM                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              LANGGRAPH AGENT ORCHESTRATOR                 │   │
│  │                                                           │   │
│  │   ┌─────────┐    ┌───────────┐    ┌──────────────┐      │   │
│  │   │Reasoning│───▶│Tool Select│───▶│Tool Execute  │      │   │
│  │   └─────────┘    └───────────┘    └──────────────┘      │   │
│  │        │                                  │               │   │
│  │        └──────────────────────────────────┘               │   │
│  │                        │                                  │   │
│  │                        ▼                                  │   │
│  │              ┌──────────────────┐                        │   │
│  │              │   VERIFICATION   │                        │   │
│  │              │  (Groundedness)  │                        │   │
│  │              └──────────────────┘                        │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐             │
│  │   Weather   │  │   Market    │  │  Knowledge  │             │
│  │    Tool     │  │    Tool     │  │  Base Tool  │             │
│  │(Open-Meteo) │  │   (Mock)    │  │ (ChromaDB)  │             │
│  └─────────────┘  └─────────────┘  └─────────────┘             │
│                                                                  │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │               FASTAPI BACKEND (THIS REPO)                 │   │
│  │   /chat  /documents  /search  /admin  /auth               │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 📋 Requirements

## 🚀 Quick Start (Backend)

### 1. Prerequisites

- Python 3.10+
- PostgreSQL (Supabase recommended)
- OpenAI API key

### 2. Installation

```bash
# Clone the repository
git clone <repo-url>
cd farmer-rag

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file and add your API key
cp .env.example .env
# Edit .env and add OPENAI_API_KEY=sk-your-key
```

### 3. Run the Backend API

```bash
# Run the FastAPI backend
uvicorn src.api.main:app --reload --port 8000
```

### 4. Access API Docs

Open [http://localhost:8000/docs](http://localhost:8000/docs) in your browser.

## 📁 Project Structure

```text
farmer-rag/
├── src/
│   ├── agent/           # LangGraph agent implementation
│   │   ├── graph.py     # Main agent graph
│   │   ├── nodes/       # Reasoning, tool execution, verification
│   │   └── prompts/     # System and verification prompts
│   │
│   ├── retrieval/       # RAG components
│   │   ├── vector_store.py   # ChromaDB wrapper
│   │   ├── retriever.py      # Search interface
│   │   └── chunking/         # Semantic chunking
│   │
│   ├── tools/           # External tool implementations
│   │   ├── weather.py   # Open-Meteo integration
│   │   ├── market.py    # Market price tool
│   │   └── knowledge.py # Knowledge base tool
│   │
│   ├── verification/    # Groundedness checking
│   │
│   ├── ingestion/       # Document processing
│   │   ├── pipeline.py  # Ingestion orchestration
│   │   └── drive/       # Google Drive integration
│   │
│   ├── database/        # PostgreSQL models
│   │
│   └── ui/              # Legacy Gradio interface (optional)
│
├── scripts/             # Utility scripts
├── docker/              # Docker configuration
└── data/                # Document storage
```

## 🔧 Configuration

Key settings in `.env`:

```env
# Required
OPENAI_API_KEY=sk-your-key

# Model settings
PRIMARY_MODEL=gpt-4o
VERIFICATION_MODEL=gpt-4o-mini
MODEL_TEMPERATURE=0.3

# RAG settings
CONFIDENCE_THRESHOLD=0.80
RETRIEVAL_TOP_K=5

# Database (Supabase recommended)
DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/farmer_rag
DATABASE_URL_SYNC=postgresql://user:pass@host:5432/farmer_rag

# Supabase Auth
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_ANON_KEY=...
SUPABASE_SERVICE_ROLE_KEY=...
SUPABASE_JWKS_URL=https://<project-ref>.supabase.co/auth/v1/.well-known/jwks.json
```

## 🧪 Testing

```bash
pytest -q
```

## 📚 Adding Documents

### Via API (Upload)

POST `/documents/ingest` (multipart form-data with `file`)

### Via API (Google Drive)

POST `/documents/drive-sync` with optional `folder_id`

### Required Drive Files

- `credentials.json` (OAuth client secrets)
- `token.json` is generated after first OAuth login

### Google OAuth Setup

1. **Create OAuth Credentials**:
   - Go to [Google Cloud Console](https://console.cloud.google.com/)
   - Navigate to **APIs & Services** → **Credentials**
   - Create OAuth 2.0 Client ID (Web application)
   - Download credentials as `credentials.json`

2. **Configure OAuth Consent Screen**:
   - Go to **APIs & Services** → **OAuth consent screen**
   - Set app to "Testing" mode (for development)
   - Add test users: Click **"+ ADD USERS"** and add your email(s)
   - Add authorized redirect URI: `http://localhost:3000/auth/google/callback` (or your production URL)

3. **Set Environment Variable** (optional):
   ```bash
   GOOGLE_OAUTH_REDIRECT_URI=http://localhost:3000/auth/google/callback
   ```

**Note**: If you see "access_denied" error, make sure your email is added as a test user in the OAuth consent screen.

## 🐳 Docker Deployment

```bash
# Build and run
cd docker
docker-compose up -d

# With pgAdmin for database management
docker-compose --profile tools up -d
```

## 📊 Implementation Trace

The system logs all reasoning steps and tool calls. Example trace:

```text
[REASONING] User asks about fertilizer for maize
[TOOL_CALL] query_agricultural_knowledge(query="fertilizer maize", crop_type="maize")
[TOOL_RESULT] Found 3 relevant documents
[REASONING] Need weather info for timing
[TOOL_CALL] get_weather_forecast(latitude=-1.94, longitude=29.87)
[TOOL_RESULT] 20% rain probability next 3 days
[RESPONSE] Generated advisory with citations
[VERIFICATION] Extracted 4 claims, 4 supported
[GROUNDEDNESS] Score: 1.00 (100%)
```

## 🔒 Verification Module

The groundedness scoring follows a two-stage pipeline:

1. **Claim Extraction**: LLM extracts factual claims from response
2. **Citation Matching**: Each claim verified against sources
3. **Score Calculation**: `supported_claims / total_claims`

Threshold: Responses with score < 0.80 are flagged as potentially unreliable.

## ✅ Backend Endpoints (Core)

- `POST /chat` (SSE streaming; `?stream=false` for JSON)
- `POST /documents/ingest`
- `POST /documents/drive-sync`
- `POST /search`
- `GET/POST/PATCH/DELETE /farms`
- `GET/POST/PATCH/DELETE /crops`
- `GET /auth/me`
- `GET/PUT /admin/config/{key}`
- `POST /admin/embeddings/rebuild`
- `GET /admin/jobs/{id}`
- `GET /metrics` (Prometheus)

## 👥 Contributors

- Glorry Sibomana

## 📄 License

MIT License - see [LICENSE](LICENSE)
