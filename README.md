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
```

## Quick start

1. Create a virtual environment and activate it.
2. Copy `.env.example` to `.env` and set a local token.
3. Run `python -m conversation_ledger.cli init-storage`.
4. Start the collector with `python -m conversation_ledger.cli run-collector`.
5. Import saved files with `python -m conversation_ledger.cli scan-inbox --project your-project`.

## Environment

The code reads configuration from environment variables and supports the project conventions from `E:\commons`:

```ini
COMMONS_ROOT=E:/commons
LEDGER_DATA_ROOT=E:/commons/data/conversation_ledger
LEDGER_KNOWLEDGE_ROOT=E:/commons/knowledge/conversation_ledger
OUTPUT_ROOT=E:/output/conversation-ledger
COLLECTOR_HOST=127.0.0.1
COLLECTOR_PORT=8765
COLLECTOR_TOKEN=replace-with-random-local-token
ALLOW_PLATFORMS=codex,claude,deepseek,gemini,import
ALLOW_PROJECTS=
```

If `LEDGER_DATA_ROOT` is not set, the app defaults to `COMMONS_ROOT/data/conversation_ledger`.

## Commands

```text
python -m conversation_ledger.cli init-storage
python -m conversation_ledger.cli run-collector
python -m conversation_ledger.cli scan-inbox --project sorting-center
python -m conversation_ledger.cli import-file --project sorting-center --path path/to/chat.md
python -m conversation_ledger.cli export-thread --project sorting-center --platform import --thread chat-name
python -m conversation_ledger.cli export-day --project sorting-center --date 2026-06-30
```

## Notes

- Raw JSONL and SQLite stay outside git by default.
- SQLite is an index and convenience cache, not the source of truth.
- The current importer normalizes manual files into `import_record` events. Platform-specific browser adapters can post richer `message_final` and `message_revision` events to the collector later.

