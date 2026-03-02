# Deployment Guide: Farmer RAG

Strategies and resources for deploying the backend (FastAPI) and frontend (Next.js).

---

## Architecture Overview

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│  Next.js        │────▶│  FastAPI        │────▶│  Supabase       │
│  (Frontend)     │     │  (Backend)      │     │  (PostgreSQL +   │
│                 │     │                 │     │   Auth + pgvector)│
└─────────────────┘     └────────┬────────┘     └─────────────────┘
                                 │
                                 ▼
                        ┌─────────────────┐
                        │  OpenAI API     │
                        │  Open-Meteo     │
                        └─────────────────┘
```

**Existing hosted services:** Supabase (DB + Auth) is already cloud-hosted. You mainly need to deploy backend + frontend.

---

## Recommended Strategy: Easiest Path

| Component | Platform | Why |
|-----------|----------|-----|
| **Frontend** | [Vercel](https://vercel.com) | Best Next.js support, zero config, free tier |
| **Backend** | [Railway](https://railway.app) or [Render](https://render.com) | Simple Python deploy, env vars, free/low-cost tiers |

**Alternative (all-in-one):** Deploy both on [Railway](https://railway.app) — one project, two services.

---

## Backend Deployment

### Option A: Railway (Recommended)

**Pros:** Simple, supports Python, env vars, auto-deploy from Git, free $5/month credit  
**Cons:** Credit expires; paid after

**Steps:**
1. Sign up at [railway.app](https://railway.app)
2. New Project → Deploy from GitHub (select `farmer-rag` repo)
3. Root directory: `farmer-rag` (or backend folder)
4. **Build command:** `pip install -r requirements.txt`
5. **Start command:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
6. Add environment variables (see below)
7. Railway assigns a URL like `https://farmer-rag-production.up.railway.app`

**Procfile (optional):**
```
web: uvicorn src.api.main:app --host 0.0.0.0 --port $PORT
```

### Option B: Render

**Pros:** Free tier, easy Python deploys  
**Cons:** Free tier sleeps after inactivity

**Steps:**
1. [render.com](https://render.com) → New → Web Service
2. Connect GitHub repo
3. **Build:** `pip install -r requirements.txt`
4. **Start:** `uvicorn src.api.main:app --host 0.0.0.0 --port $PORT`
5. Add env vars
6. **Environment:** Python 3

### Option C: Google Cloud Run

**Pros:** Pay per request, scales to zero  
**Cons:** More setup, Docker required

**Steps:**
1. Create `Dockerfile.backend` (see below)
2. Build: `gcloud builds submit --tag gcr.io/PROJECT_ID/farmer-rag-api`
3. Deploy: `gcloud run deploy farmer-rag-api --image gcr.io/PROJECT_ID/farmer-rag-api --platform managed --allow-unauthenticated`

### Option D: Fly.io

**Pros:** Global edge, good free tier  
**Cons:** CLI-based

**Steps:**
1. Install Fly CLI: `brew install flyctl`
2. `fly launch` in farmer-rag directory
3. Use Dockerfile or `fly.toml` with build config

---

## Frontend Deployment

### Option A: Vercel (Recommended)

**Pros:** Built for Next.js, zero config, automatic previews, free tier  
**Cons:** Serverless cold starts (usually fine)

**Steps:**
1. Sign up at [vercel.com](https://vercel.com)
2. Import project from GitHub → select `farmer_rag_frontend` (or repo root)
3. **Root directory:** `farmer_rag_frontend` (if monorepo)
4. **Environment variables:**
   - `NEXT_PUBLIC_API_BASE_URL` = your backend URL (e.g. `https://farmer-rag.up.railway.app`)
   - `NEXT_PUBLIC_SUPABASE_URL` = Supabase project URL
   - `NEXT_PUBLIC_SUPABASE_ANON_KEY` = Supabase anon key
5. Deploy → Vercel assigns `https://farmer-rag-frontend.vercel.app`

**Supabase:** Add your Vercel URL to Supabase Auth → URL Configuration → Redirect URLs.

### Option B: Netlify

**Pros:** Simple, good free tier  
**Cons:** Next.js support slightly less seamless than Vercel

**Steps:**
1. [netlify.com](https://netlify.com) → Add new site → Import from Git
2. Build command: `cd farmer_rag_frontend && npm run build`
3. Publish directory: `farmer_rag_frontend/.next` (or use Next.js runtime)
4. Add env vars

### Option C: Railway (with Backend)

Deploy both in one Railway project:
- Service 1: Backend (Python)
- Service 2: Frontend (Node: `npm run build && npm run start`)

---

## Environment Variables

### Backend (`.env` or platform config)

| Variable | Required | Default | Notes |
|----------|----------|---------|-------|
| `OPENAI_API_KEY` | ✅ | — | From OpenAI |
| `DATABASE_URL` | ✅ | — | Supabase: `postgresql+asyncpg://postgres:PASSWORD@db.xxx.supabase.co:5432/postgres` |
| `DATABASE_URL_SYNC` | ✅ | — | Same, `postgresql://` (no asyncpg) |
| `SUPABASE_URL` | ✅ | — | `https://xxx.supabase.co` |
| `SUPABASE_ANON_KEY` | ✅ | — | From Supabase dashboard |
| `SUPABASE_SERVICE_ROLE_KEY` | ✅ | — | For admin operations |
| `SUPABASE_JWKS_URL` | ✅ | — | `https://xxx.supabase.co/auth/v1/.well-known/jwks.json` |
| `PRIMARY_MODEL` | | `gpt-4o` | LLM model |
| `VECTOR_BACKEND` | | `pgvector` | Use pgvector |

**Supabase:** Enable pgvector in your Supabase project (Database → Extensions → add `vector`).

### Frontend

| Variable | Required | Notes |
|----------|----------|-------|
| `NEXT_PUBLIC_API_BASE_URL` | ✅ | Backend URL (e.g. `https://api.farmer-rag.railway.app`) |
| `NEXT_PUBLIC_SUPABASE_URL` | ✅ | Supabase project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | ✅ | Supabase anon key |

---

## CORS & Auth

**Backend:** Ensure your FastAPI app allows the frontend origin. In `src/api/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=[os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

Set `CORS_ORIGINS=https://your-frontend.vercel.app` in backend env.

**Supabase:** Add production URLs to:
- Authentication → URL Configuration → Site URL, Redirect URLs

---

## Database & Migrations

**Supabase:** Your DB is already hosted. Ensure:
1. pgvector extension enabled
2. Migrations applied: `alembic upgrade head` (run once locally or in a CI job)

**First-time setup:** Run migrations against Supabase DB URL before deploying.

---

## Sample Dockerfile for Backend (Cloud Run / Fly.io)

```dockerfile
FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends libpq5 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY alembic/ ./alembic/
COPY alembic.ini .

ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

EXPOSE 8000

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

---

## Quick Checklist

- [ ] Supabase: pgvector enabled, migrations run
- [ ] Backend: Deploy to Railway/Render, set env vars
- [ ] Frontend: Deploy to Vercel, set `NEXT_PUBLIC_API_BASE_URL`
- [ ] Supabase Auth: Add production URLs

- [ ] CORS: Backend allows frontend origin
- [ ] Test: Login → Chat → Ask a question

---

## Cost Summary (Free / Low Tiers)

| Service | Free Tier | Notes |
|---------|-----------|-------|
| Vercel | 100GB bandwidth | Usually enough for demos |
| Railway | $5 credit/month | ~500 hrs |
| Render | 750 hrs/month | Free tier sleeps |
| Supabase | 500MB DB, 50K MAU | Free tier |
| OpenAI | Pay per use | ~$0.01–0.10 per chat |

**Recommended for demo:** Vercel (frontend) + Railway (backend) + Supabase (existing).
