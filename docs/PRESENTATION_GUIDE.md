# Project Presentation Guide (4 min + 1 min Q&A)

Use this to prepare for the agentic system presentation.

---

## 1. Clear Problem (~45 sec)

**Real-world problem:** Smallholder farmers in East Africa need actionable agricultural advice—when to plant, how to control pests, when to harvest—but they lack reliable, personalized guidance. Generic answers are not enough.

**Why an agent, not a single response?**
- **Multi-source synthesis**: Farmers need weather + market prices + knowledge base combined (e.g., "Should I plant maize now?").
- **Adaptive behavior**: If the first retrieval is weak, the agent re-retrieves. If a tool fails, it retries.
- **Verification**: The agent checks its own answers against sources (groundedness) before responding.
- **Memory**: Farmers return later and ask follow-ups; the agent uses conversation history and farm context.

---

## 2. Agent Architecture (~1 min)

**Diagram** (use the one in `README.md` or this simplified version):

```
┌─────────────────────────────────────────────────────────────────┐
│  Farmer Query  →  PLANNING (Reasoning)  →  Decide: Tool or Done?  │
│                              ↓                                   │
│  EXECUTION (Tools)  →  Weather | Market | Knowledge Base         │
│                              ↓                                   │
│  CRITIQUE (Verification)  →  Low groundedness? → Re-retrieve     │
│                              ↓                                   │
│  Response (with sources)  →  Stored in DB (memory)                │
└─────────────────────────────────────────────────────────────────┘
```

**Talking points:**
- **LLM**: OpenAI for reasoning and verification.
- **Tools**: Weather (Open-Meteo), Market (mock), Knowledge Base (pgvector over ingested docs).
- **Memory**: Short-term (AgentState during run) + Persistent (PostgreSQL: conversations, tool calls, advisories).
- **Decision flow**: Observe → Reason → Decide → Act → Evaluate → Update → Repeat (LangGraph loop).

---

## 3. True Agentic Behavior (~30 sec)

- **Autonomy**: Agent chooses which tools to call and when to stop.
- **Multi-step reasoning**: ReAct-style; can call multiple tools in sequence.
- **Tool usage**: Only when needed (greetings skip tools).
- **Memory**: Loads conversation history and farmer profile (farms, crops) for context.
- **Adaptive control**: Re-retrieval on low groundedness; tool retries on failure; loop detection.

---

## 4. Demo Scenario (~1.5 min)

**Recommended strong scenario:** Use the chat UI and show one of these:

| Scenario | Why it's strong |
|----------|-----------------|
| **"What is the recommended spacing for maize?"** | KB tool → retrieval → verification → grounded response with sources. |
| **"What is the weather in Kigali today?"** | Weather tool → real API → response. |
| **"My maize is at flowering stage. What should I do about pests and when should I harvest?"** | Multi-part query → KB tool → synthesis across sources. |

**Demo flow:**
1. Open chat UI (frontend).
2. Ask the question.
3. Point out: tool status (if visible), streaming response, source citations.
4. Optionally: show a follow-up ("Tell me more about drying") to demonstrate memory.

**If using terminal:** Run the agent and show logs with `Observe → Reason → Decide → Act → Evaluate`.

---

## 5. Technical Understanding (~30 sec)

**Design choices:**
- Role-based (Planning/Execution/Critique) instead of one big prompt → modularity, easier debugging.
- Two-tier memory → balance between context and cost.
- Verification step → reduces hallucinations; we can re-retrieve if groundedness is low.

**Limitations:**
- Chunks lack crop/topic metadata → filtered retrieval often falls back to unfiltered, lower confidence.
- Verifier can be strict → some correct answers get low groundedness.
- Weather/market tools are external; KB quality depends on ingested docs.

**Trade-offs:**
- More steps (reasoning + verify) → higher latency, but more reliable.
- Storing tool calls and advisories → auditability vs. storage cost.

---

## 6. Deployment Checklist

- [ ] Backend running: `uvicorn src.api.main:app --reload`
- [ ] Frontend running: `npm run dev` (in farmer_rag_frontend)
- [ ] DB + env configured (PostgreSQL, OpenAI key)
- [ ] At least one document ingested (sample_ingest.txt or TAS PDF)
- [ ] Test the demo scenario before presenting

---

## Quick Reference: File Locations

| Item | Path |
|------|------|
| Architecture diagram | `README.md` |
| Evaluation report | `docs/EVALUATION_REPORT.md` |
| Chat UI | `farmer_rag_frontend/app/(app)/chat/page.tsx` |
| Agent graph | `src/agent/graph.py` |
| Tools | `src/tools/` |
