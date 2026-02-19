# Memory Management Strategy

## Overview

The Farmer RAG system implements a two-tier memory architecture:
1. **Short-term memory**: Session-level context (in-memory during agent execution)
2. **Persistent memory**: Database-backed storage (PostgreSQL)

## Memory Types

### Short-Term Memory (Session-Level)

**What it stores:**
- Current conversation turn state (AgentState)
- Tool execution results for the current query
- Retrieved sources for the current query
- Verification results

**Lifecycle:**
- Created at the start of each agent invocation
- Accumulates during the reasoning loop
- Discarded after response is generated

**Implementation:**
- Stored in `AgentState` TypedDict
- Flows through LangGraph nodes
- Not persisted to database

### Persistent Memory (Database)

**What it stores:**

1. **User Preferences** (`user_profiles` table)
   - Name, phone, region, language
   - Location (lat/lon)
   - Farm and crop information

2. **Task History** (`conversations` and `messages` tables)
   - All conversations with titles, tags, summaries
   - All messages (user and assistant)
   - Message metadata (groundedness scores, tools called, sources used)

3. **Tool Outputs** (`tool_calls` table)
   - Tool name, input, output
   - Success/failure status
   - Timestamps

4. **Performance Metrics** (`advisories` table)
   - Groundedness scores
   - Verification results
   - Source citations

5. **Structured Intermediate State** (`document_chunks` table)
   - Vector embeddings of knowledge base
   - Source metadata
   - Chunk relationships

## Memory Policies

### Write Policy

**When memory is written:**

1. **Immediate writes:**
   - User messages: Saved immediately when received
   - Assistant messages: Saved after generation completes
   - Tool calls: Saved after each tool execution
   - Conversations: Created when first message is sent

2. **Batch writes:**
   - Document chunks: Written during ingestion
   - Embeddings: Generated and stored during ingestion

3. **Update writes:**
   - Conversation titles: Auto-generated from first message
   - Conversation tags: Updated when user edits
   - User profiles: Updated when user changes settings

**What gets written:**
- All user inputs (for conversation continuity)
- All agent responses (for history)
- Tool execution results (for debugging and analysis)
- Verification metrics (for quality tracking)
- Source citations (for transparency)

### Read Policy

**When memory is read:**

1. **On conversation load:**
   - Load all messages for the conversation
   - Load conversation metadata (title, tags, summary)
   - Load associated tool calls

2. **On agent invocation:**
   - Load conversation history (last N messages)
   - Load user profile (farms, crops, location)
   - Load relevant past advisories (for context)

3. **On retrieval:**
   - Query vector store for relevant chunks
   - Filter by metadata (crop type, topic, etc.)

**What gets read:**
- Last 10 messages (configurable) for context window
- User profile for personalized advice
- Relevant knowledge base chunks (top-k retrieval)

## Memory Pruning Strategy

### Problem: Infinite Growth

Without pruning, the database will grow indefinitely:
- Conversations accumulate over time
- Messages accumulate per conversation
- Tool calls accumulate per conversation
- Old data becomes less relevant

### Solution: Multi-Tier Pruning

#### 1. Conversation-Level Pruning

**Strategy:** Archive or summarize old conversations

**Implementation:**
- Conversations older than 90 days are marked as "archived"
- Archived conversations are excluded from default queries
- Option to manually archive conversations
- Summaries generated for long conversations (>50 messages)

**Code location:** `src/api/routes/conversations.py`

```python
# Future implementation:
# - Auto-archive conversations after 90 days
# - Generate summaries for long conversations
# - Allow users to manually archive
```

#### 2. Message-Level Pruning

**Strategy:** Keep recent messages, summarize old ones

**Implementation:**
- Keep last 50 messages per conversation (configurable)
- Older messages are summarized into a "context summary"
- Summary stored in `conversation.summary` field
- Original messages can be soft-deleted (marked as archived)

**Code location:** `src/database/models.py` (Conversation.summary field)

#### 3. Tool Call Pruning

**Strategy:** Keep recent tool calls, aggregate old ones

**Implementation:**
- Keep tool calls from last 30 days
- Aggregate older tool calls by tool name and date
- Store aggregated statistics (count, success rate, avg execution time)
- Original tool calls can be archived

**Code location:** `src/database/models.py` (ToolCall table)

#### 4. Vector Store Pruning

**Strategy:** Remove outdated or low-quality chunks

**Implementation:**
- Remove chunks from deleted documents
- Remove chunks with very low similarity scores (<0.3) after re-embedding
- Option to rebuild embeddings periodically
- Keep only top-k chunks per document (by relevance)

**Code location:** `src/retrieval/db_vector_store.py`

### Pruning Schedule

**Automated pruning (future):**
- Daily: Check for conversations to archive
- Weekly: Generate summaries for long conversations
- Monthly: Aggregate old tool calls
- Quarterly: Rebuild vector embeddings

**Manual pruning:**
- Admin can trigger pruning via `/admin/documents/cleanup`
- Users can delete individual conversations
- Users can archive conversations

## Cross-Session Memory Demonstration

### Example Scenario

**Session 1 (Day 1):**
```
User: "When should I plant maize?"
Agent: "Plant maize at the start of the rainy season, typically March-April in East Africa..."
[Conversation saved with title "Maize planting timing"]
```

**Session 2 (Day 5):**
```
User: "Remember when you told me about planting maize?"
Agent: "Yes! I recommended planting at the start of the rainy season (March-April)..."
[Agent loads previous conversation from database]
```

**Implementation:**
- Conversation history loaded from `messages` table
- Agent uses `conversation_history` parameter in `agent.run()`
- Previous context informs current response

**Code location:** `src/api/routes/chat.py` (lines 79-84)

```python
history_result = await db.execute(
    select(Message)
    .where(Message.conversation_id == convo.id)
    .order_by(Message.created_at.asc())
)
history = _build_history(list(history_result.scalars().all()))
```

## Memory Efficiency

### Current State
- **Conversations**: Unlimited (grows with usage)
- **Messages**: Unlimited per conversation
- **Tool calls**: Unlimited per conversation
- **Vector chunks**: Grows with document ingestion

### Future Optimizations
1. **Compression**: Summarize old conversations
2. **Archiving**: Move old data to cold storage
3. **Indexing**: Optimize database queries
4. **Caching**: Cache frequently accessed conversations
5. **Partitioning**: Partition tables by date

## Configuration

Memory settings can be configured via environment variables:

```bash
# Conversation history length
CONVERSATION_HISTORY_LENGTH=10

# Auto-archive after days
CONVERSATION_ARCHIVE_DAYS=90

# Max messages per conversation before summarization
MAX_MESSAGES_BEFORE_SUMMARY=50
```

## Monitoring

Track memory usage:
- Total conversations
- Total messages
- Total tool calls
- Vector store size
- Database size

Available via `/admin/summary` endpoint.
