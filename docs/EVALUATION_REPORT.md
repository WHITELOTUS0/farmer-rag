# Homework 3 Evaluation Report
## Farmer RAG Agricultural Advisory Agent

---

## A. Architecture Evolution

### HW2 Baseline
In Homework 2, the Farmer RAG system used a **linear pipeline architecture**: a single-agent flow where the LLM processed queries, optionally called tools (weather, market, knowledge base), and generated responses in a sequential manner. The pipeline was essentially: **Query → Retrieve → Generate → Respond**. State was minimal—mainly the current query and tool outputs. There was no explicit separation between planning, execution, and verification.

### HW3 Evolution
For Homework 3, we refactored to a **role-based multi-node architecture** using LangGraph:

- **Planning node (`reasoning_node`)**: Decides the next action—whether to call a tool (and which one) or generate a final response. Uses ReAct-style reasoning with structured JSON output.
- **Execution node (`tool_executor_node`)**: Executes the selected tool (weather, market, knowledge base) and records results in state.
- **Critique node (`verification_node`)**: Verifies response groundedness by extracting claims and checking them against retrieved sources.

**Graph structure:** `START → reasoning → [execute_tool | verify] → [reasoning | END]`

**Why we changed:**
1. **Modularity**: Each node has a single, well-defined responsibility. Planning, execution, and verification can evolve independently.
2. **Adaptive control**: The graph structure allows routing decisions (e.g., re-retrieval on low groundedness, tool retries on failure) without modifying core logic.
3. **Observability**: Each step is logged and traceable. Failures can be attributed to a specific node.
4. **Extensibility**: Adding new tools or verification logic only touches the relevant node.

---

## B. Memory Design Rationale

### Two-Tier Memory
We chose a **two-tier memory model**:

**Short-term (session-level):** `AgentState` holds the current conversation turn—tool calls, retrieved sources, verification results—during agent execution. This state is discarded after the response is generated.

**Persistent (database):** PostgreSQL stores:
- Conversations and messages (for cross-session continuity)
- User profiles (farms, crops, location)
- Tool calls (for debugging and analytics)
- Advisories (groundedness scores, source citations)

### Rationale
1. **Cross-session continuity**: Farmers can return days later and ask follow-ups ("Remember when you told me about fertilizer?"). Loading conversation history from the DB enables this.
2. **Personalization**: User profiles (farms, crops, growth stages) improve advice relevance without re-asking.
3. **Auditability**: Storing tool calls and advisories supports quality monitoring and debugging.
4. **Cost control**: Short-term state avoids storing every intermediate result; only final outcomes are persisted.

### Write Policy
- **Immediate**: User and assistant messages saved after each exchange; tool calls and advisories saved after each agent run.
- **Read**: On conversation load, we fetch all messages for the conversation and build history for the agent.

### Pruning Strategy (documented in `docs/memory_strategy.md`)
- **Conversation-level**: Archive after 90 days.
- **Message-level**: Summarize conversations with >50 messages.
- **Tool call**: Aggregate older tool calls; keep recent ones for analysis.

---

## C. Metrics & Results

### Metrics (5 quantitative)
1. **Groundedness score**: Fraction of claims supported by retrieved sources (0–1).
2. **Tool selection accuracy**: F1 score of expected vs. called tools.
3. **Task completion rate**: Whether the agent answered the question (binary; 0 or 1).
4. **Iterations before convergence**: Number of reasoning steps before final response.
5. **Hallucination frequency**: Ratio of unsupported claims to total claims.

### Results Table (from evaluation run 2026-02-19)

| Test ID | Query | Category | Groundedness | Tool Accuracy | Completion | Iterations | Passed |
|---------|-------|----------|--------------|---------------|------------|------------|--------|
| kb_001 | What is the recommended spacing for maize? | knowledge | 1.00 | 1.00 | 1.00 | 2 | ✅ |
| kb_002 | What is the recommended spacing for beans? | knowledge | 0.50 | 1.00 | 1.00 | 2 | ❌ |
| kb_003 | What is the recommended spacing for tomatoes? | knowledge | 0.50 | 1.00 | 1.00 | 2 | ✅ |
| kb_004 | What is the weather in Kigali today? | weather | 1.00 | 1.00 | 1.00 | 2 | ✅ |
| kb_005 | When should I harvest maize and how do I dry it? | knowledge | 1.00 | 1.00 | 1.00 | 3 | ✅ |
| complex_001 | Tell me about the maize planting area requirements. | complex | 1.00 | 1.00 | 1.00 | 2 | ✅ |

**Summary:** 5 passed, 1 failed. Avg groundedness: 0.83. Avg tool accuracy: 1.00. Avg completion rate: 1.00. Avg hallucination frequency: 0.17. Test cases aligned with ingested docs (sample_ingest.txt + TAS 4402-2010). Beans spacing (kb_002) scored 0.50 groundedness, below threshold.

*Generate latest: `python scripts/run_evaluation.py --output docs/evaluation_results.md`*

---

## D. Failure Case Deep Dive

### Failure: `object of type 'NoneType' has no len()`

**What happened:**  
When a user asked a follow-up question ("How can I do weed control?" after a weather query), the agent returned: *"I apologize, but I encountered an error: object of type 'NoneType' has no len()"*

**Why it happened:**  
Several code paths called `len()` on values that could be `None`:

1. **State access**: `state.get("retrieved_sources", [])` returns `None` when the key exists with value `None`, not `[]`. So `len(retrieved_sources)` failed when the verifier tried to format the groundedness footer.
2. **Verification output**: The verification LLM sometimes returned non-list JSON (e.g., `{"claims": [...]}` instead of `[...]`). Iterating over that with `for v in verifications` worked until we tried to use `len(verified_claims)` when `verified_claims` was `None`.
3. **Tool executor**: When updating `retrieved_sources`, `state.get("retrieved_sources", [])` could return `None` when the key was explicitly set to `None`, leading to `None + sources` errors.

**How we fixed it:**
- Replaced `state.get("key", [])` with `state.get("key") or []` everywhere we expected a list, so `None` is normalized to `[]`.
- Added `or []` after `_extract_claims` and `_verify_claims` to guarantee list outputs.
- Added `if not isinstance(verifications, list): verifications = []` in the verifier before iterating.
- Added guards for `None` in the graph’s state merge logic before calling `.extend()` on `messages`, `tool_calls`, and `retrieved_sources`.

**What improved:**
- Follow-up questions no longer crash; the agent handles conversational continuity reliably.
- Defensive patterns (`x or []`, `(lst or [])`) are applied consistently across the codebase.
- The verifier robustly handles malformed LLM outputs.

---

## E. Scalability Reflection (½ page)

### 1,000 Users
**What would fail first:** Database connection pool and synchronous tool execution.  
**Why:** Each chat request holds a DB connection and blocks on LLM + retrieval + verification. With 1,000 concurrent users, connection exhaustion and high latency would occur. Embedding and vector search would also become a bottleneck.  
**Mitigations:** Connection pooling, async I/O, read replicas, caching for frequent queries, and rate limiting.

### High-Stakes Domain (e.g., pesticide dosage, crop failure)
**What would fail first:** Groundedness guarantees and edge-case handling.  
**Why:** The current verification catches *some* unsupported claims but cannot guarantee correctness. Hallucinated dosages could cause real harm.  
**Mitigations:** Stricter verification thresholds, human-in-the-loop for critical recommendations, citation requirements, and domain-specific validation (e.g., dosage ranges).

### Regulated Industry (e.g., FDA, agricultural regulations)
**What would fail first:** Auditability, reproducibility, and compliance.  
**Why:** Regulators require traceability: which model version, which sources, full reasoning trail. Our logs and advisories help but are not a full audit trail. There is no formal versioning of prompts or retrieval logic.  
**Mitigations:** Immutable audit logs, versioned prompts and models, full input/output/source capture, and compliance-oriented retention and access controls.

---

## 4. Contribution Statement

### Technical Contributions
- [Team member name]: [e.g., Implemented role-based graph architecture, reasoning node, tool executor]
- [Team member name]: [e.g., Built evaluation metrics and test suite, verification node]
- [Team member name]: [e.g., Database schema, memory persistence, chat API integration]

### Evaluation/Debugging Contributions
- [Team member name]: [e.g., Designed test cases, ran evaluation suite, analyzed failure modes]
- [Team member name]: [e.g., Debugged NoneType failure, added defensive checks, improved prompts]

*Each team member should fill in their specific contributions before submission.*

---

## Appendix: Grading Rubric Self-Check

| Category | Weight | Self-Assessment |
|----------|--------|-----------------|
| Multi-Agent / Role Architecture | 25 | Explicit Planning/Execution/Critique nodes; clear interfaces |
| Persistent State Management | 20 | Two-tier memory; DB persistence; pruning strategy documented |
| Evaluation Framework | 20 | 5 metrics; 6 test cases; structured results table |
| Adaptive Control Logic | 15 | Re-retrieval, tool retries, iteration limits; visible in logs |
| Failure Analysis Depth | 10 | NoneType case: what, why, fix, improvement |
| Documentation & Clarity | 10 | Memory strategy, checklist, this report |
