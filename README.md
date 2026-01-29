# 🌾 Farmer RAG Advisory System

An AI-powered agricultural advisory system for smallholder farmers in East Africa, providing personalized recommendations for maize, beans, and tomatoes based on weather, market prices, and agronomic best practices.

## 🎯 Project Overview

This system implements a **RAG-enabled agent** that:
- Retrieves information from agricultural knowledge bases
- Fetches real-time weather forecasts
- Provides market price guidance
- Verifies responses for groundedness (factual accuracy)

Built for **04-801-W3 Agentic AI: Fundamentals and Applications** at Carnegie Mellon University.

## 🏗️ Architecture

```
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
│  │                    GRADIO UI                              │   │
│  │   [Chat] [Documents] [Admin]                              │   │
│  └──────────────────────────────────────────────────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

## 📋 Requirements

### HW2 Compliance

| Module | Implementation | Status |
|--------|---------------|--------|
| **Retrieval Module** | ChromaDB + Semantic Chunking + Metadata Extraction | ✅ |
| **Tool-Calling Module** | Weather API + Market Tool + RAG + ReAct Loop | ✅ |
| **Verification Module** | Claim Extraction + Citation Matching + Groundedness Score | ✅ |

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10+
- PostgreSQL (optional, for persistent farmer data)
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

### 3. Run the Application

```bash
# Launch the Gradio UI
python scripts/run_app.py

# Or with options
python scripts/run_app.py --share  # Create public link
python scripts/run_app.py --port 8080  # Custom port
```

### 4. Access the UI
Open http://localhost:7860 in your browser.

## 📁 Project Structure

```
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
│   └── ui/              # Gradio interface
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

# Database (optional)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/farmer_rag
```

## 🧪 Testing

```bash
# Test the agent
python scripts/test_agent.py

# Test with specific query
python scripts/test_agent.py "When should I apply fertilizer?"

# Test tools only
python scripts/test_agent.py --tools-only
```

## 📚 Adding Documents

### Via UI
1. Go to the Documents tab
2. Upload PDF or DOCX files
3. Or paste text directly

### Via Script
```bash
python scripts/ingest_local.py /path/to/documents --recursive
```

### Via Google Drive
1. Set `GOOGLE_DRIVE_FOLDER_ID` in `.env`
2. Add `credentials.json` from Google Cloud Console
3. Use the sync feature in Admin panel

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

```
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

## 👥 Contributors

- Glorry Sibomana

## 📄 License

MIT License - see [LICENSE](LICENSE)
