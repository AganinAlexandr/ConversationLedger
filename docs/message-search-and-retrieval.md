# Message Search And Retrieval

This note closes an important gap in the current MVP spec: collecting and exporting conversations is not enough unless we can reliably find the right fragments later.

The goal of this document is to define how Conversation Ledger should search saved messages without turning the raw archive into an opaque dump.

## Why this matters

Conversation Ledger is intended to be useful for:

- restoring project context after a break
- finding prior decisions, constraints, and code snippets
- assembling focused context packs for later model runs
- auditing who said what, when, and in which thread

Without an explicit search layer, the archive is technically complete but operationally weak.

## Search jobs to support

The system should support four different jobs. They are related, but not identical.

It should also support four explicit source groups for every text query:

1. all available data
2. all chats inside one selected project
3. all chats of one selected family such as Codex, ChatGPT, Claude Code, Cursor, Gemini, or DeepSeek
4. chats of one selected family inside one selected project

For some families, especially `Claude Code`, family alone is not enough. The archive should preserve both:

- `platform family`: for example `claude_code`
- `source surface`: for example `claude_web` or `cursor_claude_code_plugin`

This matters because the same family may be used through different shells while still representing one logical model/runtime family.

More generally, Conversation Ledger should avoid collapsing all source identity into one axis. In practice we need at least these distinct concepts:

- `source product`: the concrete product the user interacted with, such as `codex`, `chatgpt`, `claude_code`, `cursor`, `lovable`, `openrouter`, `antigravity`
- `source surface`: the shell or execution surface, such as `browser_web`, `cursor_plugin`, `cursor_native_picker`, `api_router`, `desktop_app`
- `runtime vendor`: the primary model vendor behind the interaction, such as `openai`, `anthropic`, `google`, `deepseek`
- `model family`: the model/runtime family when known, such as `gpt`, `claude`, `gemini`, `deepseek`

These axes must stay separate because the user may want very different searches:

- search all OpenAI-backed runs
- search only Codex and not ChatGPT
- search only Cursor-originated sessions regardless of vendor
- search Claude Code runs launched specifically through the Cursor plugin

So even when products share a vendor family, they should remain separately addressable in search unless the user explicitly asks for grouping.

### 1. Direct lookup

The user already knows roughly what they need:

- "find the message where we chose JSONL over SQLite as source of truth"
- "show the thread where we discussed Codex adapter revisions"
- "find the last mention of project_id handling"

This requires exact or near-exact search over message text and metadata.

### 2. Decision retrieval

The user remembers the outcome, but not the wording:

- "what did we decide about imports?"
- "why did we avoid storing attachments automatically?"

This requires retrieving clusters of messages that contain a claim, rationale, or tradeoff, not only keyword matches.

### 3. Task and artifact retrieval

The user needs executable context:

- "find the conversation where we wrote the collector CORS behavior"
- "show messages related to userscript install instructions"

This requires linking messages to projects, files, threads, and possibly exported artifacts.

### 4. Time-bounded reconstruction

The user wants a chronological slice:

- "show everything important from June 30, 2026"
- "reconstruct the work that led to the OpenAI adapter commit"

This requires date filters, thread grouping, and project-day views.

## Retrieval principles

These principles should govern the search layer.

1. Raw JSONL remains the source of truth.
2. SQLite is the first retrieval engine, not just a passive index.
3. Search results must return evidence, not only summaries.
4. Retrieval should prefer bounded context windows over whole-thread dumps.
5. Search must work well before adding embeddings or external services.
6. Every result should preserve provenance: project, platform, thread, message, timestamp, raw path.

## Retrieval model

Search should operate on three levels.

### Level 1. Message

The smallest searchable unit is a normalized message event.

Useful fields:

- `project_id`
- `platform`
- `source_surface`
- `runtime_vendor`
- `source_product`
- `thread_id`
- `message_id`
- `timestamp_observed`
- `role`
- `event_type`
- `content_markdown`
- `content_sha256`
- `source_url`
- `capture_adapter`
- `raw_path`

### Level 2. Message window

The default answer should usually not be a single isolated message, but a small window:

- matched message
- 1-3 messages before
- 1-3 messages after

This gives the user the rationale and continuation around the hit.

### Level 3. Session or day summary

For broad queries, results may be grouped by:

- thread
- project-day
- export artifact

This prevents search from returning a flat, noisy list.

## Search modes

The first implementation should include these modes.

### A. Metadata filter

Filter by:

- project
- source product
- platform family
- source surface
- runtime vendor
- role
- date range
- thread
- event type

This is the most deterministic layer and should exist first.

### B. Full-text search

Search over `content_markdown` with SQLite FTS5.

Why:

- fast enough for local use
- no external dependencies
- explainable ranking
- good fit for MVP and early post-MVP

### C. Phrase and proximity search

Needed for queries like:

- exact quoted fragments
- nearby terms such as "collector" close to "CORS"

This can ride on FTS5 syntax plus small application-side ranking rules.

### D. Structured retrieval

Later, we should extract or tag messages as:

- decision
- open question
- task
- bug
- rationale
- code reference

This enables more useful search than plain text alone.

## Ranking strategy

Initial ranking should remain simple and explicit.

Base score components:

1. text match score from FTS
2. recency modifier
3. project exact-match bonus
4. thread-title or thread-id exact-match bonus
5. decision/rationale tag bonus when such tags appear later

The system should avoid hiding lower-ranked but still relevant evidence. Results should show score plus explanation fields where practical.

## Result format

Search should return results as evidence packets, not raw rows only.

Minimum result shape:

```json
{
  "query": "cors userscript collector",
  "result_type": "message_window",
  "project_id": "conversation-ledger",
  "platform": "chatgpt",
  "thread_id": "abc123",
  "matched_message_id": "msg-42",
  "timestamp_observed": "2026-06-30T12:34:56Z",
  "score": 12.4,
  "match_reason": [
    "fts: cors",
    "fts: collector",
    "project exact match"
  ],
  "window": [
    { "role": "user", "content_markdown": "..." },
    { "role": "assistant", "content_markdown": "..." },
    { "role": "assistant", "content_markdown": "..." }
  ],
  "raw_path": "E:/commons/data/conversation_ledger/raw/chatgpt/2026-06/abc123.jsonl"
}
```

This structure is also suitable for future Context Packager input.

## Index extensions to add

The current SQLite index is enough for ingestion, but not yet enough for strong retrieval.

Recommended additions:

### 1. FTS table

Add an FTS5 virtual table over:

- `content_markdown`
- possibly `thread_id`
- possibly future `thread_title`

### 2. Conversation/thread table

Store per-thread metadata:

- first_seen_at
- last_seen_at
- message_count
- project_id
- platform
- optional inferred title

### 3. Search-friendly ordering fields

Persist:

- stable per-thread sequence number
- normalized day
- revision lineage if a message is revised

### 4. Optional annotations table

For future human or automated tags:

- `decision`
- `task`
- `risk`
- `open_question`
- `artifact_reference`

## Query API to aim for

The CLI and library should eventually expose operations like:

```text
python -m conversation_ledger.cli search --scope all --query "CORS userscript"
python -m conversation_ledger.cli search --scope project --project conversation-ledger --query "collector"
python -m conversation_ledger.cli search --scope family --family codex --query "\"source of truth\""
python -m conversation_ledger.cli search --scope project-family --project conversation-ledger --family chatgpt --query "decision import"
python -m conversation_ledger.cli search --scope family --family claude_code --query "plugin"   # later with optional --surface cursor_claude_code_plugin
python -m conversation_ledger.cli search --scope family --family codex --query "agent"
python -m conversation_ledger.cli search --scope family --family chatgpt --query "agent"
python -m conversation_ledger.cli search --scope all --product codex --query "agent"
python -m conversation_ledger.cli search --scope all --vendor openai --query "agent"
python -m conversation_ledger.cli thread-context --project conversation-ledger --thread abc123
python -m conversation_ledger.cli day-context --project conversation-ledger --date 2026-06-30
```

In other words, `Codex` and `ChatGPT` should not be merged into one search bucket just because both may be OpenAI-native products. Shared lineage is useful as metadata, but separate searchability is mandatory.

The HTTP layer can come later if needed; local CLI retrieval is enough for the next stage.

## Phased implementation

### Phase 1. Searchable MVP+

Add:

- SQLite FTS5 over messages
- metadata filters
- result windows
- CLI search command

This is the next practical milestone.

### Phase 2. Retrieval quality

Add:

- thread summaries
- better ranking
- inferred titles
- decision/task tagging

### Phase 3. Context packaging

Add:

- query-to-context-pack pipelines
- role-specific retrieval presets
- explicit include/exclude manifests

### Phase 4. Semantic retrieval

Only after the previous phases are solid:

- embeddings
- hybrid lexical + semantic ranking
- optional local vector index

Semantic retrieval should be an enhancement, not the first answer.

## Acceptance criteria for the search layer

The search layer should be considered useful when:

1. A direct text query finds the correct message within the first few results.
2. A project-day query reconstructs the work sequence without reading raw JSONL manually.
3. A result always includes provenance and a local evidence path.
4. Searches remain local-first and do not call external APIs.
5. Search works well on Cyrillic, code blocks, and mixed technical prose.
6. Retrieval returns bounded context windows rather than uncontrolled thread dumps.

## Recommended next move

The best next implementation step is not embeddings. It is:

1. extend the SQLite index with FTS5
2. add `search` and `thread-context` CLI commands
3. return message windows with provenance
4. validate on real archived Codex and ChatGPT sessions

That gives Conversation Ledger its first real retrieval capability and turns the archive into a working memory system instead of just a storage system.
