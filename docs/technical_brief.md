# HW2 Technical Brief — Farmer RAG Advisory System

Course: 04-801-W3 Agentic AI: Fundamentals and Applications  
Assignment: HW2 — Building the Agent  
Project: Daily Farm Advisory Agent (Maize–Beans–Tomato Systems)

## 1) Project Overview

This project implements a RAG-enabled agent that provides personalized agricultural guidance for smallholder farmers in East Africa. The agent synthesizes (1) agricultural extension documents stored in a vector database, (2) real-time weather data, and (3) market price signals to produce actionable advisories. The system follows the HW2 requirements for retrieval, tool-calling, and verification, with a ReAct-style reasoning loop and groundedness scoring. The implementation is designed for daily usage, but in HW2 we focus on a single interaction loop with tool use, retrieval, and verification.  

Reference: HW2 requirements and rubric are summarized in the assignment PDF. [HW2 PDF](file:///Users/glorry/Projects/GitHub/School/farmer-rag/HW2_%20Building%20the%20agent.pdf)

## 2) System Architecture (Agentic Loop)

**Core loop**:
1. **Observe**: Gather farmer context (location, crops, stage).
2. **Reason**: Decide whether to use retrieval or tools.
3. **Act**: Call tools (weather, market, RAG).
4. **Respond**: Synthesize advice with citations.
5. **Verify**: Extract claims and compute groundedness.

Implementation highlights:
- **Orchestrator**: LangGraph prebuilt ReAct agent.
- **LLM**: OpenAI GPT-4o (primary), GPT-4o-mini (verification).
- **Vector DB**: Chroma (local persistence).
- **UI**: Gradio (demo interface).

## 3) Retrieval Module (Memory)

### 3.1 Ingestion
Documents are ingested from PDF/DOCX/TXT and chunked into semantically coherent segments before embedding. Each chunk is stored with metadata including source ID, source name, and optional farm/crop tags.

### 3.2 Advanced Chunking Strategy
We use **semantic chunking** with LangChain’s `SemanticChunker` rather than a naive fixed-size splitter. This preserves instructional context in agronomic manuals (e.g., fertilizer guidance and timing are often spread across multiple sentences that should remain together).

Justification:
- Agronomic advice is often procedural and context-heavy.
- Semantic chunking avoids fragmenting steps or mixing unrelated topics.
- Improves retrieval relevance for multi-step questions.

### 3.3 Vector Store
ChromaDB stores embeddings for each chunk, supporting similarity search with optional metadata filters. The retriever includes:
- Filtered search (crop/topic/stage),
- Fallback to unfiltered search when filters return no results,
- Threshold fallback when similarity scores are low.

## 4) Tool-Calling Module

We implemented three tools and wired them into the ReAct loop:

1. **Weather Tool** (Open-Meteo API)  
   Returns current conditions, daily forecast, and agricultural summary (rain probability, water balance).

2. **Market Prices Tool** (Mock data)  
   Returns realistic price ranges, regional variation, and seasonal trend signals.

3. **Knowledge Base Tool (RAG)**  
   Retrieves agronomic guidance from the vector database, returning top-k chunks with citations.

These tools are defined with LangChain `@tool` decorators and integrated into LangGraph’s ReAct agent, which decides when to call tools vs. answer directly.

## 5) Verification Module (Guardrails)

To mitigate hallucinations, we added a self-evaluation step that computes a **groundedness score**:

1. **Claim Extraction**  
   Uses a strict Pydantic schema via `PydanticOutputParser` to extract factual claims.

2. **Evidence Matching**  
   Embeds each claim and compares to retrieved source chunks (cosine similarity).

3. **Groundedness Score**  
   Score = supported claims / total claims.

If extraction fails, a sentence-splitting fallback is used to avoid blocking results.

## 6) Failure Analysis + Fix

**Failure**: Retrieval often returned 0 results despite ingested documents.  
**Cause**: Filtering and similarity thresholds excluded relevant chunks; also some filters used unsupported operators in Chroma.  
**Fix**:
- Added unfiltered fallback when filters return no results.
- Added threshold fallback when all scores fall below the confidence threshold.
- Updated metadata filters to use supported operators.

This directly improved retrieval robustness and ensured the agent could ground responses with citations.

## 7) Implementation Trace

We generated a successful multi-step trace using `scripts/run_trace.py`:
- **Weather tool** called for forecast.
- **Market tool** called for maize prices.
- **RAG tool** called for agronomic best practices.
- **Verification** computed groundedness score.

Trace logs are saved in `logs/trace_YYYYMMDD_HHMMSS.json` and LangSmith captures a full reasoning trace when enabled.

## 8) Contribution Statement (Template)

- **Glorry Sibomana**: System design, RAG ingestion pipeline, tool implementation, evaluation/verification module, UI integration, and HW2 trace preparation.

## 9) Summary

This implementation meets HW2 requirements by:
- Building a retrieval module with advanced chunking and persistence,
- Implementing external tools and a ReAct-style loop,
- Adding verification with groundedness scoring,
- Producing an implementation trace for evaluation.

The system is functional and extensible toward a production-grade advisory platform with persistent farmer state, messaging, and admin controls.
