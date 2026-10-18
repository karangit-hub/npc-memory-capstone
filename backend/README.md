# Persistent NPC chat history

The existing FastAPI backend still uses local Ollama with `qwen3:8b`.
Phase 3 adds basic SQLite conversation history using Python's built-in
`sqlite3` module. It adds no dependencies and does not implement the full
MemoryRepository research architecture.

On application startup, `memory_store.py` creates `conversation_memory.sqlite3`
beside `main.py` if needed. Restarting the backend preserves existing history.
The database path is resolved relative to the Python file, independently of
the shell's working directory.

For each `/chat` request, the backend:

1. Retrieves the latest 10 individual messages for that exact `player_id` and
   `npc_id`, ordered from oldest to newest by their insertion IDs.
2. Sends the system prompt, stored history, and current message to Ollama.
3. Saves the user's message and the NPC reply together in one transaction after
   Ollama succeeds, then returns the reply. A failed Ollama request saves neither
   message.

Both user and assistant messages count toward the limit: 10 messages normally
represent five complete exchanges. Older messages stay in SQLite but are not
included in the model context. Players and NPCs have separate histories.

The endpoints and JSON formats remain unchanged:

- `GET /` returns `{"message": "NPC Memory Backend is running!"}`.
- `GET /health` returns `{"status": "healthy"}`.
- `POST /chat` accepts `{"player_id": "alice", "npc_id": "guard", "message": "Hello"}`
  and returns `{"npc_id": "guard", "reply": "..."}`.

## Run the backend

From `npc-memory-capstone/backend` in PowerShell, with the existing virtual
environment and local Ollama server available:

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn main:app --reload
```

## Run automated tests

From the same directory:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
```

Tests use the standard-library `unittest` framework and temporary SQLite files.
API tests use the existing FastAPI/httpx dependencies and mock Ollama; they do
not require a running model or modify the real conversation database. Coverage
includes persistence across connections, player/NPC isolation, chronological
retrieval, retrieval limits, atomic saves, startup initialization, API formats,
chat context, and failed model calls.

The storage tests can also run with a standard Python installation alone:

```powershell
python -B -m unittest discover -s tests -p test_memory_store.py -v
```

The project `.gitignore` excludes `.venv`, `__pycache__`, `.env`, and SQLite
database files (including journal/WAL files). If any were already tracked by
Git, ignore rules do not automatically untrack them.
