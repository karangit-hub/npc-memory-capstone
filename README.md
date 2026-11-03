# LLM-Powered NPCs with Persistent Memory

A capstone prototype in which Arthur, a medieval village guard, remembers
player-provided facts across conversations and backend restarts. Python and
FastAPI serve a local chat API and a buildless browser interface. Ollama runs
`qwen3:8b` locally; SQLite stores conversations and explicitly generated memory
summaries. No API key or hosted model service is required.

## Architecture and implementation status

For each chat request, the backend reads the exact player/NPC pair's latest
10 messages, relevant older user excerpts, and optional saved summaries from
one SQLite snapshot. It closes the read transaction before calling Ollama,
applies narrow source-based reply safeguards, and saves both sides of the
successful exchange atomically.

| Component | Implementation |
|---|---|
| `backend/main.py` | FastAPI `/`, `/health`, `/chat`; unchanged chat JSON format |
| `backend/memory_store.py` | Persistent history, isolation, historical keyword retrieval, consistent context reads |
| `backend/summary_store.py`, `summarizer.py` | Versioned, source-validated extractive summaries; explicit developer CLI |
| `backend/retention_policy.py`, `reply_safety.py` | Personal-fact eligibility, bounded attributed overviews, narrow conflict safeguards |
| `backend/demo.py`, `web/`, `run_demo.ps1` | Opt-in localhost browser demo and read-only memory inspector |
| `backend/summary_audit.py` | Read-only eligibility audit; no repair/delete mode |
| `backend/tests/` | Automated tests with disposable databases and mocked model responses |

Historical retrieval, explicit summaries, and the browser prototype are
implemented. Unity integration and Aftab's separate evaluation work have not
been verified as complete; this submission does not claim their completion.
Controlled forgetting and semantic/vector retrieval are not implemented.

## Software requirements

- Python **3.12** (validated with 3.12.10), including `venv` and SQLite support.
- Git, Ollama, the `qwen3:8b` model, and a modern browser such as Chrome.
- Windows PowerShell for the supplied demo launcher. The Python backend can
  also be launched directly with Uvicorn.
- Enough local memory/disk for Qwen3 8B; the model download is several GB and
  generation speed depends on your hardware. Tests do not require the model.

The five direct Python dependencies are pinned in
[`backend/requirements.txt`](backend/requirements.txt). SQLite, the test runner,
and the frontend need no additional packages or Node build step.

## Install and start Ollama

Install Ollama from [ollama.com](https://ollama.com/). Then use PowerShell:

```powershell
ollama list
# If qwen3:8b is absent, download it explicitly:
ollama pull qwen3:8b
```

Check `http://127.0.0.1:11434/api/version`. If Ollama is not already serving,
run `ollama serve` in a separate terminal and leave it running. Do not start a
second server when the Ollama desktop service is already available.

## Install the backend

From the directory in which you want the checkout:

```powershell
git clone https://github.com/karangit-hub/npc-memory-capstone.git
Set-Location .\npc-memory-capstone\backend
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r .\requirements.txt
```

For an ordinary backend instance, from `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m uvicorn main:app --host 127.0.0.1 --port 8000
```

This uses or creates `backend/conversation_memory.sqlite3` unless
`NPC_DATABASE_PATH` is explicitly set. It preserves existing messages. Summary
context and demo routes default to off. For safe personal testing, use the
separate demo database below rather than an existing conversation database.

`POST /chat` accepts `{"player_id":"karan","npc_id":"Arthur","message":"Hello"}`
and returns `{"npc_id":"Arthur","reply":"..."}`. IDs are case-sensitive.

## Run the isolated browser demo

From `backend`, with Ollama running:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
Start-Process "http://127.0.0.1:8001/demo"
```

The URL is **http://127.0.0.1:8001/demo**. Run `Start-Process` in another
terminal while the launcher is running. The launcher binds only to loopback,
enables summary context, and creates/reuses `npc-memory-browser-demo/demo.sqlite3`
beside the checkout. It never resets history or migrates the original database.
An explicit alternative is `-DatabasePath "C:\path\to\demo.sqlite3" -Port 8002`.

Select Karan, Rajan, or a custom player and Arthur or another NPC ID. Use Send
or Enter; Shift+Enter adds a newline. Clear view only clears the displayed
bubbles. The connection indicator reports backend/Ollama availability.

Open **Memory inspector** and refresh the preview to see actual recent message
IDs, keyword excerpts, persisted summary entries, source IDs, eligibility
decisions, and effective summary context. This previews the next request using
the draft; it is not a trace of the previous model call. The inspector is
read-only and provides no database-reset or summary-generation API.

## Historical retrieval and explicit summary generation

Older user messages remain in SQLite after leaving the recent 10-message
window. Keyword retrieval ranks shared normalized, non-stopword tokens and
returns at most three excerpts, with a 1,500-character total excerpt budget.
It requires shared words and does not implement semantic search.

To test summaries, tell Arthur personal facts, then have at least six unrelated
exchanges after the last fact. In another PowerShell terminal, from `backend`:

```powershell
$demoDb = Join-Path (Split-Path (Get-Location).Path -Parent) '..\npc-memory-browser-demo\demo.sqlite3'
.\.venv\Scripts\python.exe -B .\summarizer.py --db $demoDb --player-id karan --npc-id Arthur
```

Use the exact custom path instead if you supplied `-DatabasePath`. Repeat until
the result is `status: noop`, then refresh the inspector and ask about the
facts. Generation is **explicit only**; ordinary chat never creates summaries.
The CLI adds summary tables only to an existing disposable database and refuses
the original database path. Stored statements are complete user messages with
source IDs and hashes, not invented model paraphrases. Application rules reject
general questions such as the blacksmith question even if the model labels
them personal memories.

Stop the backend with Ctrl+C. Restart the same launcher and reuse the same
database to verify persistence; switch players to verify isolation. Stop
Ollama with Ctrl+C only if you started that separate process yourself.

## Run automated validation

From `backend`:

```powershell
.\.venv\Scripts\python.exe -B -m unittest discover -s tests -v
.\.venv\Scripts\python.exe -B -m pip check
```

Tests use temporary SQLite databases and mocked Ollama responses. They cover
persistence, isolation, retrieval, source validation, summary publication,
concurrent reads, attribution, API compatibility, and browser routes. A passing
suite is not a guarantee of live-model answer accuracy.

## Known limitations and data safety

- Qwen3 sometimes abstains even when a supporting home-location fact is in
  summary context. This remains unresolved. Source-based overview safeguards
  do not repair every specific-fact answer.
- Keyword retrieval misses synonyms and some paraphrases. Personal-fact
  eligibility uses conservative English grammar rules, with false negatives
  and possible misinterpretations of complex language.
- Speaker/conflict safeguards cover bounded overviews, exact copied user
  statements, and simple conflicting claims. Complex paraphrases, conflicts,
  hallucination, and prompt injection remain model-behavior limitations.
- Summaries retain at most 16 complete source messages, 600 characters each,
  and 4,000 serialized context characters. Capacity errors do not evict data;
  ignored sources are not automatically replayed. No forgetting is performed.
- Local demo routes are development tools, not production authentication.
  Player IDs scope data but are not authenticated identities. Keep the server
  on `127.0.0.1`; this is not a public multiplayer service.
- Databases, logs, environments, secrets, and local reports are excluded from
  Git. Existing invalid summary rows are filtered and auditable; they are not
  physically repaired or deleted automatically.

See the [backend guide](backend/README.md) for full algorithms, configuration,
schema, test coverage, safe audit commands, and the approval-based proposal for
correcting a previously misclassified derived summary entry.
