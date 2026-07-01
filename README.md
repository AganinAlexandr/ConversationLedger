# Conversation Ledger

Conversation Ledger is a local-first archive for working LLM conversations. The MVP keeps raw events append-only in JSONL, builds a SQLite index for retrieval, imports manually saved chat files, and exports selected sessions back to Markdown without changing the raw archive.

The implementation follows the storage split described in [E:\commons\project_infra_reorganization.md](E:\commons\project_infra_reorganization.md):

- `repo`: versioned code in this repository
- `commons/data/conversation_ledger`: raw events, normalized metadata, imports, SQLite index
- `commons/knowledge/conversation_ledger`: spec, schemas, decisions
- `output/conversation-ledger`: temporary diagnostics and test exports

## MVP scope

- Local collector bound to `127.0.0.1`
- Bearer token authentication from `.env`
- Browser adapter userscript for Codex and ChatGPT
- Codex thread snapshot import for Codex-native chat history
- Append-only JSONL raw storage
- Deduplication by `event_id` and stable content identity
- Idempotent import of `.txt`, `.md`, `.html`, `.json`
- SQLite session index
- Markdown export by thread or by project-day
- Tests for append-only storage, deduplication, revision flow, import, and export

## Repository layout

```text
src/conversation_ledger/
  cli.py
  collector.py
  config.py
  exporter.py
  importer.py
  index.py
  models.py
  storage.py
tests/
schemas/
userscripts/
```

## Quick start

1. Create a virtual environment and activate it.
2. Copy `.env.example` to `.env` and set a local token.
3. Run `python -m conversation_ledger init-storage`.
4. Start the collector with `python -m conversation_ledger run-collector`.
5. Start the local shell with `python -m conversation_ledger run-shell`.
6. Import saved files with `python -m conversation_ledger scan-inbox --project your-project`.

For a one-shot local startup on Windows, you can also run:

```text
powershell -ExecutionPolicy Bypass -File .\start_conversation_ledger.ps1
```

This launcher checks the configured collector and shell ports, starts missing servers in separate PowerShell windows, and opens the shell UI in a browser by default.

## Environment

The code reads configuration from environment variables and supports the project conventions from `E:\commons`:

```ini
COMMONS_ROOT=E:/commons
LEDGER_DATA_ROOT=E:/commons/data/conversation_ledger
LEDGER_KNOWLEDGE_ROOT=E:/commons/knowledge/conversation_ledger
OUTPUT_ROOT=E:/output/conversation-ledger
COLLECTOR_HOST=127.0.0.1
COLLECTOR_PORT=8765
SHELL_HOST=127.0.0.1
SHELL_PORT=8766
COLLECTOR_TOKEN=replace-with-random-local-token
ALLOW_PLATFORMS=codex,chatgpt,claude,claude_code,cursor,deepseek,gemini,import
ALLOW_PROJECTS=
```

If `LEDGER_DATA_ROOT` is not set, the app defaults to `COMMONS_ROOT/data/conversation_ledger`.

## Commands

```text
python -m conversation_ledger init-storage
python -m conversation_ledger run-collector
python -m conversation_ledger run-shell
python -m conversation_ledger scan-inbox --project sorting-center
python -m conversation_ledger import-file --project sorting-center --path path/to/chat.md
python -m conversation_ledger import-codex-thread --project sorting-center --path path/to/codex-thread.json
python -m conversation_ledger export-thread --project sorting-center --platform import --thread chat-name
python -m conversation_ledger export-day --project sorting-center --date 2026-06-30
```

## Codex thread snapshots

For Codex-native history, the first bridge is a snapshot import path rather than a browser userscript. It accepts JSON shaped like a Codex thread history response and converts `turns/items` into archive events:

- `userMessage` -> `message_final`
- `agentMessage` from completed turns -> `message_final`
- `agentMessage` from in-progress turns -> `message_revision`

Use:

```text
python -m conversation_ledger import-codex-thread --project sorting-center --path path/to/codex-thread.json
```

## Browser adapter

The first browser adapter lives in [userscripts/conversation-ledger-openai.user.js](/E:/Projects/OpenAI/ConversationLedger/userscripts/conversation-ledger-openai.user.js). It is a Tampermonkey-compatible userscript with two profiles:

- `Codex`: `codex.openai.com` and `chatgpt.com/codex*`
- `ChatGPT`: `chatgpt.com/*` and `chat.openai.com/*`

What it does:

- observes rendered conversation turns only, not composer input before send
- shows a floating `recording / paused / error` badge
- lets you pause capture locally
- sends events only to the local collector on `127.0.0.1`
- emits `message_final` and `message_revision`

Suggested setup:

1. Install Tampermonkey or a similar userscript manager.
2. Start the local collector.
3. Open the userscript file and install it in the manager.
4. Use the script menu to set `project_id`, local collector URL, and bearer token.
5. Open Codex or ChatGPT and verify that the status badge switches to `recording`.

## Retrieval design

The original MVP spec is strong on capture and export, but weaker on how a user later finds the right information inside saved conversations. That gap is now captured in [message-search-and-retrieval.md](/E:/Projects/OpenAI/ConversationLedger/docs/message-search-and-retrieval.md).

The recommended next layer is:

- SQLite FTS5 over saved messages
- metadata filters by project/platform/date/thread
- bounded message windows as results
- CLI search and thread-context commands

The first search interface is designed around four explicit source groups:

1. `scope=all`: search across all saved data
2. `scope=project`: search across chats inside one project
3. `scope=family`: search across one platform family such as `Codex`, `ChatGPT`, `Claude Code`, `Cursor`, `Gemini`, or `DeepSeek`
4. `scope=project-family`: search one platform family inside one chosen project

Important nuance: for families like `Claude Code`, the archive should preserve not only the family but also the execution surface. In practice this means:

- `platform=claude_code`
- `source_surface=claude_web` for direct browser use at `https://claude.ai`
- `source_surface=cursor_claude_code_plugin` for direct Claude Code use through the Cursor plugin

So search can stay grouped by family when needed, while still retaining the exact capture origin for later refinement.

Another important nuance: products that share a vendor ecosystem should still remain separately searchable. For example, `Codex` and `ChatGPT` may both sit in the OpenAI orbit, but they should remain distinct source products in the archive because the user may need search over one but not the other. The same principle applies to vendor-agnostic shells like `Cursor`, `Lovable`, or `OpenRouter`.

The retrieval model is therefore moving toward separate fields for:

- `platform`: the operational family used for high-level grouping
- `source_product`: the concrete product the user interacted with
- `runtime_vendor`: the underlying vendor lineage
- `source_surface`: the shell or execution surface

Example commands:

```text
python -m conversation_ledger.cli search --scope all --query "source of truth"
python -m conversation_ledger.cli search --scope project --project conversation-ledger --query "collector"
python -m conversation_ledger.cli search --scope family --family chatgpt --query "imports"
python -m conversation_ledger.cli search --scope project-family --project conversation-ledger --family codex --query "userscript"
python -m conversation_ledger.cli search --scope all --product codex --query "agent"
python -m conversation_ledger.cli search --scope all --vendor openai --query "agent"
python -m conversation_ledger.cli search --scope family --family claude_code --surface cursor_claude_code_plugin --query "plugin"
python -m conversation_ledger.cli thread-context --project conversation-ledger --thread abc123
python -m conversation_ledger.cli day-context --project conversation-ledger --date 2026-06-30
```

## Local shell

The minimal viewer shell runs as a personal local web app on `SHELL_HOST:SHELL_PORT`. It is intended for your own archive inspection, not for multi-user operation. It provides:

- a tree of saved chats grouped by project and source product
- filters for family, product, vendor, and execution surface
- full-text search in the same window
- inline thread and day context rendering without leaving the shell
- richer in-window formatting for markdown, lists, code blocks, tables, and highlighted search hits

Start it with:

```text
python -m conversation_ledger.cli run-shell
```

Then open `http://127.0.0.1:8766/` or your configured shell address in a browser.

## Notes

- Raw JSONL and SQLite stay outside git by default.
- SQLite is an index and convenience cache, not the source of truth.
- The current importer normalizes manual files into `import_record` events. Platform-specific browser adapters can post richer `message_final` and `message_revision` events to the collector later.
- `https://chatgpt.com/codex` redirected to `https://chatgpt.com/` in the unauthenticated browser session I could inspect, so the Codex profile is implemented as a strong first-pass adapter and should be smoke-tested in an authenticated session.
