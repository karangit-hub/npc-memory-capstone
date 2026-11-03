# Persistent NPC history, historical retrieval, and extractive memory summaries

For a fresh checkout, start with the [project setup guide](../README.md), which
covers Python 3.12, virtual-environment installation from `requirements.txt`,
Ollama installation, and explicitly downloading `qwen3:8b` when absent.
The absolute Windows paths below describe the original local demonstration;
substitute your checkout/demo paths or use the portable root-guide commands.

For personal browser testing, see [Local browser demo](#local-browser-demo).
The launcher uses a separate disposable DB and binds only to `127.0.0.1`.

The existing FastAPI backend still uses local Ollama with `qwen3:8b`.
The existing SQLite conversation history now includes Phase 1 long-term
retrieval: a deterministic keyword baseline over older player statements.
Phase 2 adds developer-controlled persistent **extractive** summaries: Qwen3
selects important older user messages, and the application stores their complete
original text with provenance. This adds two SQLite tables only when explicitly
requested on a disposable database. No new packages are required; this is not
the full MemoryRepository research architecture.

On application startup, `memory_store.py` creates `conversation_memory.sqlite3`
beside `main.py` if needed. Restarting the backend preserves existing history.
The database path is resolved relative to the Python file, independently of
the shell's working directory.

For each `/chat` request, the backend:

1. Opens an explicit SQLite read transaction and retrieves the latest 10
   individual messages for that exact `player_id` and `npc_id`, ordered from
   oldest to newest by their insertion IDs.
2. Searches older **user** messages for that same exact player/NPC pair using
   keywords from the current question, excluding the latest 10 messages of
   either role. Both reads use the same database snapshot, even if another
   connection writes meanwhile. When enabled, saved summary context is read in
   this same snapshot. Assistant replies are never historical-memory candidates.
   The transaction and connection close before calling Ollama.
3. Sends the system prompt, recent history, an optional historical user
   statements block, an optional saved-summary block, and the current message
   to Ollama, in that order. No summaries are generated during `/chat`.
4. Saves the user's message and the NPC reply together in one transaction after
   Ollama succeeds, then returns the reply. A failed Ollama request saves neither
   message.

Both user and assistant messages count toward the limit: 10 messages normally
represent five complete exchanges. Older messages stay in SQLite; only relevant,
bounded excerpts are added to the model context. Players and NPCs have separate
histories. IDs remain exact and case-sensitive.

## Historical keyword retrieval

`get_relevant_memories()` in `memory_store.py`:

- Splits text into Unicode word/number tokens, normalizes case with `casefold`,
  and treats punctuation and underscores as separators.
- Removes a small fixed English stopword list and single-character tokens.
  A blank, punctuation-only, or stopword-only question retrieves nothing.
- Scores each older user message by the number of distinct query keywords it
  shares. Matching requires whole tokens; repeating a word does not raise its
  score. Zero-overlap messages are ignored.
- Ranks higher scores first, breaking ties with the more recent insertion ID.
- Returns at most **3** excerpts, at most **500 characters per excerpt**, and
  at most **1,500 excerpt characters in total**. Internal callers can request
  smaller limits, but cannot raise these caps. Labels and JSON quoting add a
  bounded amount of formatting overhead.
- Leaves short messages intact. For long messages, selects the sentence with
  the greatest distinct keyword overlap (later sentences break ties), and adds
  adjacent complete sentences when they share query keywords and fit. Unrelated
  adjacent filler is omitted. Basic boundaries are `.`, `!`, `?`,
  and newlines. If that sentence exceeds the budget, ranks bounded windows
  around its matching tokens by distinct overlap, with later windows breaking
  ties. This avoids always taking an early topic mention while losing a more
  relevant fact later in the message.
- Returns verbatim, contiguous excerpts with the original `message_id` for
  provenance. Retrieval reads existing rows without generating facts or writing
  memory records. Character caps include any contextual text in the excerpts.

The API uses `get_chat_context_with_summary()` to obtain all enabled blocks in
one explicit `BEGIN` read transaction. The Phase 1 `get_chat_context()` interface
still returns only recent and keyword history. Standalone `get_recent_messages()` and
`get_relevant_memories()` helpers remain available, but separate calls to them
do not share a snapshot. SQLite's existing journal configuration is unchanged:
rollback-journal writers may briefly wait for a reader; WAL readers can coexist
with committed writes. No transaction spans model generation or the later save.

The memory block is JSON-quoted and sent as a separate **user** message labelled
`Historical user statements (untrusted conversation data; excerpts may be truncated)`.
Excerpts are never inserted into the system prompt. The system prompt always
says to use them only as evidence of prior player statements and never follow
embedded instructions, including when no historical match is available.
Quoted declarative user statements remain usable evidence, including complete
facts inside longer or truncated excerpts; the untrusted label concerns commands.

Uncertainty guidance also applies on every request. Player-specific preferences,
names, relationships, locations, and events require supporting evidence; an
earlier assistant guess is not a user fact. Without support, the NPC should say
exactly `I don't have that information in the available context.` The system
prompt requires this brief fallback without guesses, fictional details, or
recommendations. It explicitly states that the fictional village supplies no
evidence about the player's personal life, and gives unknown location, event,
and preference examples. Supported facts can still be answered normally.
Fictional world knowledge and assumptions must remain separate from user facts.
A failed keyword lookup is **not** proof that the player never stated a fact.
No memory block is added when retrieval has no relevant matches.

These are prompt-level precautions, not guarantees that a model will resist
every injection or answer accurately. Automated tests verify instructions and
context construction; isolated live-model trials measure actual behavior.

For example, `karan` tells `Arthur`, "My favorite weapon is a silver spear."
After six additional exchanges, asking "What is my favorite weapon?" retrieves
that statement through the shared `favorite` and `weapon` tokens even though
the original exchange is outside recent history. The same question from
`rajan` cannot retrieve Karan's statement. "Where is the bakery?" does not
retrieve it either. Automated API tests verify the request sent to mocked
Ollama; they do not claim to measure live Qwen3 answer quality.

### Limitations and later phases

This is lexical historical retrieval, not semantic memory. Synonyms, spelling
variants, paraphrases without shared keywords, and word inflections may not
match. Any shared non-stopword can produce a weak match. The stopword list is
English-oriented; longer messages with more matching words may rank higher.
Sentence/window selection is lexical, not factual extraction; it can still omit
context, split an overlong sentence, or select a weak match. Conflicting old statements
are not resolved; recency only breaks equal-score ties.

Retrieval scans all older user messages for the pair on each substantive query;
it retains only the best three candidates in Python, but scan time grows with
history. Context reads now share a snapshot, but concurrent chat exchanges are
not serialized across model generation. A response may use a snapshot that
predates another request's completed exchange.

For example, "I enjoy drinking tea" still does not match "What beverage do I
prefer?" because the phrases share no meaningful tokens. The desired behavior
on that miss is uncertainty, not an invented beverage or a claim that the fact
was never provided. Semantic retrieval has not been implemented.

Summary context can make a retained tea statement available for that paraphrase
without depending on a shared keyword. It does not implement semantic/vector
search. There is still no controlled forgetting, automatic expiry, or Unity
integration.

## Phase 2: explicit extractive summarization

`summarizer.py` exposes `await summarize_pair(player_id, npc_id, db_path)` and a
developer CLI. There is **no automatic summarization in startup or chat**.
Both schema initialization and generation refuse the original
`backend/conversation_memory.sqlite3` path. Use a disposable DB or copy, never
migrate the original database during this phase. Ordinary chat remains compatible
with the old schema and reads no summary when tables are absent.

Two additive tables preserve the existing `messages` table unchanged:

| Table | Data |
|---|---|
| `memory_summary_state` | Exact player/NPC primary key, version, covered-through user message ID, UTC creation/update timestamps, model, format version |
| `memory_summary_entries` | Pair and source-message primary key, complete original statement, category, source SHA-256, added version, UTC creation timestamp |

Each call snapshots up to **20 older user messages**, after the pair's coverage
watermark and outside the most recent 10 messages of either role. Source text
is bounded to **12,000 characters per batch**. It then closes the read
transaction before calling local `qwen3:8b` with an Ollama JSON schema.

The response must classify every source ID exactly once into identity,
relationship, preference, location, event, correction, other, or ignore.
Pydantic validates types and forbids extra fields. Missing, duplicated, foreign,
assistant, or fabricated IDs invalidate the whole response. The model cannot
supply replacement fact text: stored statements are complete original user
messages, not generated paraphrases. This preserves negation and corrections
within each message and prevents unsupported generated names or claims from
entering storage. It does not establish that the user's assertion is true.

Model categories are proposals, not permission to retain a statement. The
application-side rules below independently decide whether the source contains
an explicit personal assertion. A model label such as `location` cannot turn
a general question into the player's biography. Clear recognized assertions
are prioritized even when the model incorrectly labels their conversational
wording `ignore`. The CLI's `selection_review` reports the model proposal,
effective category, retention result, reason, and policy version for each source.

Publication opens a short `BEGIN IMMEDIATE` transaction, checks the expected
summary version and exact source text again, appends selected entries, and
atomically advances the watermark. Previously retained claims are not replaced;
conflicting statements and explicit corrections remain separately sourced.
Entries are labelled `unverified_user_statement` in model context. Conflict
handling is conservative: the chat model must describe disagreement or
uncertainty instead of silently choosing a newer value. Semantic conflict
detection and resolution are not implemented; selection can still miss facts.

A repeated call with no new eligible sources returns `status: noop` without a
model call or version change. A long history requires repeated explicit calls
until `noop`; each successful call processes one batch, including ignored
messages. Concurrent stale jobs fail their version check rather than overwriting
another job. On model, parsing, validation, source-change, or capacity failure,
the previous summary and watermark remain intact and messages are unchanged.

Limits: **16 retained source messages**, **600 characters per complete statement**,
and **4,000 characters for the entire serialized summary context**, including
JSON metadata/escaping. Selected overlong messages or a full summary cause an
explicit failure; facts are never silently truncated or evicted. An input source
over 12,000 characters can block progress and requires developer review. This
version is selection-based compression, not arbitrary abstractive summarization.

Summary context is **off by default**. Set `NPC_SUMMARY_CONTEXT=1` before starting
the server to enable it; unset it or use `0` to disable. `NPC_DATABASE_PATH`
optionally points the server at a disposable DB; its default remains unchanged.
All enabled context blocks share one read snapshot. Identical recent user
statements take priority, then summaries, then keyword excerpts. Exact normalized
duplicates (case and whitespace only; meaningful punctuation is preserved) are
removed from context without deleting source records; repeated
summary statements merge their source IDs. Different/negated statements are
preserved. Summaries are not filtered by query keywords, so paraphrases can use
retained facts. The saved-summary block is quoted **user data**, never system
instructions, and is subject to the existing uncertainty and injection guidance.

### Safe developer workflow (PowerShell, from backend)

Create a separate disposable copy while the source DB is idle. The copy must
contain messages outside the recent window, or summarization correctly returns
`noop`. For active databases, use SQLite's backup API instead of a raw file copy.

```powershell
$summaryDb = Join-Path ([IO.Path]::GetTempPath()) ("npc-summary-" + [guid]::NewGuid().ToString() + ".sqlite3")
Copy-Item -LiteralPath .\conversation_memory.sqlite3 -Destination $summaryDb
.\.venv\Scripts\python.exe -B .\summarizer.py --db $summaryDb --player-id karan --npc-id Arthur
```

Repeat the explicit summarizer command as needed until `noop`. To use that
copy's summaries in a separate backend instance:

```powershell
$env:NPC_DATABASE_PATH = $summaryDb
$env:NPC_SUMMARY_CONTEXT = "1"
.\.venv\Scripts\python.exe -B -m uvicorn main:app --port 8001
```

These settings apply only to the process/shell. No API request or response fields
change. Run the workflow only against a disposable copy for Phase 2 review;
the implementation and tests do not migrate the original DB.

## Local browser demo

The buildless HTML/CSS/JavaScript interface is served at
**http://127.0.0.1:8001/demo**. Existing `/`, `/health`, and `/chat` formats are
unchanged. The demo includes chat bubbles, player selection (`karan`, `rajan`,
or custom), an editable NPC ID, Enter/Send controls, a loading indicator, error
messages, connection/model status, and clear view. Clear view changes only the
page; it does not call a delete endpoint or clear SQLite history. Selecting a
pair loads its actual latest 10 saved messages. IDs remain case-sensitive.

The memory inspector is read-only. Its `POST /demo/api/context` endpoint reports
recent messages with original IDs, keyword excerpts, saved summary metadata and
entries, and effective summary context. It is a preview for the **next** request
using the current draft, not a trace claiming what an earlier model call used.
`GET /demo/api/status` checks the backend configuration and local Ollama model
list. Empty arrays and null summaries are actual backend results, not simulated
retrieval statuses. Refresh the preview after running the summarizer CLI.

All `/demo` routes require `NPC_DEMO_ENABLED=1`, a loopback client/Host, same-origin
requests, and a database path different from the original. Startup refuses demo
mode with the original path before database initialization. No reset, delete, or
summary-generation API is exposed. This is a local development interface, not
authentication suitable for deployment. Keep the server bound to localhost.

### Windows PowerShell commands

Open the checkout in VS Code:

```powershell
code "C:\Users\Owner\Capstone-Workspace\npc-memory-capstone"
```

In one terminal, check Ollama. If it is already running, leave that service alone.
If the check fails, run `ollama serve` in that terminal. No download is needed:

```powershell
try {
    Invoke-RestMethod -Uri "http://127.0.0.1:11434/api/version" -TimeoutSec 3 -ErrorAction Stop
} catch {
    ollama serve
}
```

In a second terminal, launch the demo:

```powershell
Set-Location "C:\Users\Owner\Capstone-Workspace\npc-memory-capstone\backend"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\run_demo.ps1
```

The launcher opts into demo routes and summary context, starts Uvicorn with
`--host 127.0.0.1 --port 8001 --no-proxy-headers`, and restores its environment
settings when it exits. It creates/reuses only this disposable database:

```text
C:\Users\Owner\Capstone-Workspace\npc-memory-browser-demo\demo.sqlite3
```

It never copies, resets, migrates, or deletes the original DB. Output goes to the
terminal, not the four existing log files. To use another disposable path or
port, pass `-DatabasePath "C:\path\to\disposable.sqlite3" -Port 8002`.

In a third terminal, open Chrome:

```powershell
Start-Process -FilePath "C:\Program Files\Google\Chrome\Application\chrome.exe" -ArgumentList "http://127.0.0.1:8001/demo"
```

Select Karan and Arthur. Send your weapon, sister-name, and tea statements, then
at least six additional unrelated exchanges after the last fact. Confirm in the
inspector that the original messages have left the recent 10-message window.
Generate summaries explicitly in the third terminal:

```powershell
Set-Location "C:\Users\Owner\Capstone-Workspace\npc-memory-capstone\backend"
.\.venv\Scripts\python.exe -B .\summarizer.py --db "C:\Users\Owner\Capstone-Workspace\npc-memory-browser-demo\demo.sqlite3" --player-id karan --npc-id Arthur
```

Repeat that command until `status` is `noop`. Refresh the inspector and ask about
those facts. Switch to Rajan to test isolation. To test persistence, press
**Ctrl+C** in the backend terminal, run the same launcher command again, and
reopen the same URL. The disposable DB and saved summaries survive the restart.
Stop the backend with Ctrl+C when finished. Stop Ollama with Ctrl+C only if you
started a separate `ollama serve` terminal for this test; do not stop an existing
Ollama service. Closing Chrome does not stop the backend or delete history.

### Phase 2 review fixes used by the demo

Saved summary reads now revalidate source IDs, exact player/NPC scope, user role,
SHA-256, and complete statement text. A changed or misattributed source produces
a clear HTTP 503 before generation, rather than entering model context.

`reply_safety.py` adds two bounded guards after the normal Ollama call and before
the atomic exchange save. An exact first-person copy of actual user evidence is
attributed as `You previously said: “...”`; it is not blindly rewritten into a
different sentence. A narrow recognizer for complete `My ... is/are ...`
statements quotes differing values for the same queried topic and requests
clarification. Values come only from user evidence; there are no hardcoded test
answers. Explicit correction markers are respected in source order. Assistant
messages never become evidence for either guard.

These guards do not perform semantic conflict detection. Complex statements,
paraphrased first-person replies, nuanced corrections, and unsupported model
explanations outside the recognized forms remain limitations. Summaries still
require the CLI; there is no automatic summarization, forgetting, or vector
retrieval. The existing Phase 2 capacity and classification limitations remain.

### Initial live validation and review limits

The November 2, 2026 local Qwen3 8B trials generated real summaries and exercised
summary-backed silver-spear, Emily, and tea-paraphrase recall. Different-player
isolation, unknown-fact uncertainty, and repeated generation without extra model
calls were also checked. Conflicting weapon claims remained separately sourced.
Earlier false abstentions and an irrelevant weather selection were preserved in
the external trial reports rather than discarded.

The final trial still answered the tea question in first person instead of
addressing the player, and added a speculative interpretation to the conflicting
weapon claims. These are open model-behavior issues for review. Complete quoted
source text prevents the summary writer from inventing replacement fact text,
but does not guarantee correct classification, complete selection, pronoun use,
or faithful conflict handling in a generated reply. Finite capacity can block
incremental updates; no compaction, silent eviction, or forgetting is performed.

## Personal-fact retention and speaker attribution

`retention_policy.py` is a conservative English grammar-based gate. It accepts
recognized first-person/possessive assertions about identity, preferences,
relationships, locations, and personal experiences, including negations,
corrections, reverse phrases such as `Tea is my favorite drink`, and events such
as `A healer saved my life`. It does not use particular test answers as rules.

General questions and information requests are not personal facts. For example,
`Is there a blacksmith in this village?` supplies no player-specific location.
`Where do I live?` also supplies no answer. Merely containing `I` or `my` is
insufficient: `I wonder if there is a blacksmith` and `My question is about the
village` are information seeking, not biography. Confirmation questions,
conditionals, and ambiguous retractions are treated conservatively.

A question mark does **not** automatically disqualify a real personal assertion.
Examples retained include `Did I mention that my sister's name is Emily?`,
`Can you remember that I prefer tea?`, and `Can you recommend a shop, since I live
near the river?`. Explicitly named relatives in requests, such as `Can you help
my sister Emily?`, also carry personal information. In mixed messages, recognized
factual clauses are kept distinct from unrelated questions or uncertainty.
The complete original user message remains the stored, hashed source; this
does not authorize model-generated replacements or guessed factual values.

For personal-overview requests such as `What do you remember about me?`, the
backend still makes the normal Ollama call, then constructs a bounded reply
from eligible source clauses with explicit `you've told me` attribution. It
quotes at most five distinct clauses (1,200 source characters), preserves
negation, and does not pretend the result is an exhaustive biography. If no
personal evidence is available, it returns the existing uncertainty reply.
User questions cannot become `I asked` experiences of the NPC. Other dialogue
requests still use the model; the system prompt explicitly distinguishes
player speech, NPC speech, personal assertions, and general conversation topics.
Conversation history and keyword retrieval remain available for questions such
as `What did I ask about the blacksmith?` with correct player attribution.

These rules are not a semantic parser or a truth verifier. Unrecognized wording,
other languages, subtle presuppositions, sarcasm, and complex retractions may
need manual review. Original messages are never removed. Ignored sources still
advance the successful processing watermark, and are not automatically replayed.
The finite Phase 2 capacity and model-generation limitations remain unchanged.
Live Qwen3 testing still produced an uncertainty reply for a specific location
question despite a supporting embedded assertion in summary context. The
source-based overview guard does not repair every specific-fact answer.

### Existing invalid entries: audit first, repair only after approval

On read, saved entries still undergo source/role/hash validation. Eligibility
is evaluated separately when building **personal summary context**. An old
ineligible entry remains physically stored, with its original source and
metadata, but is excluded from that context. The browser inspector shows both
the raw saved entries and a **Retention review** containing
`eligible_for_personal_context` and the reason. This filtering does not delete,
reclassify, migrate, or rewrite persisted rows. Restart the backend to load the
new code; ordinary chat still does not generate summaries.

The new audit CLI is strictly read-only and has no `apply`, repair, or delete
mode. It uses SQLite `mode=ro` plus `query_only` and does not create missing DBs:

```powershell
Set-Location "C:\Users\Owner\Capstone-Workspace\npc-memory-capstone\backend"
.\.venv\Scripts\python.exe -B .\summary_audit.py --db "C:\Users\Owner\Capstone-Workspace\npc-memory-browser-demo\demo.sqlite3" --player-id karan --npc-id Arthur
```

The observed blacksmith row is source **17**, pair `karan` / `Arthur`, summary
version **1**, coverage watermark **17**. Its original conversation message and
stored summary row have not been changed. Re-running ordinary summarization
will not repair this already-covered row.

Proposed physical repair, **not performed or exposed as an API**:

1. Stop demo writes and create a timestamped SQLite backup plus a JSON export
   of the target row and summary metadata.
2. Review that backup/export and obtain approval for this exact row.
3. In one short transaction, verify the expected pair, source ID, source hash,
   stored question text/category, and current summary version. Remove only the
   erroneous derived summary entry, increment that pair's version, and update
   its update timestamp. Preserve the coverage watermark, all `messages` rows,
   every other summary entry, and every other player's data. Abort on mismatch.
4. Audit again and compare all unaffected rows. Retain the backup for rollback.

This would be correction of a misclassified derived entry, not a forgetting
policy. No physical repair has been run. Old ineligible entries continue to
count toward stored-entry capacity until an approved repair is performed.

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
chat context, and failed model calls. Historical-retrieval tests additionally
cover the silver-spear example after six newer exchanges, exact player/NPC
isolation, recent-window and assistant exclusion, case/punctuation/stopwords,
relevance and recency ranking, whole-word matching, empty/unrelated queries,
hard result/character caps, long-message excerpts, quoted instruction-like
content, and unchanged API/failure behavior. Regression tests cover unconditional
unknown-information guidance, later facts after early topic mentions, complete
sentences and long windows, newlines and negation, and an actual second SQLite
connection committing six exchanges between the context reads. That concurrency
test enables WAL only on its temporary database; production configuration is
unchanged. Tests also verify that read transactions close before generation and
release their locks after failures. All test databases are disposable;
tests never initialize, clear, or write the real conversation database.
Phase 2 tests additionally cover additive schema initialization, protected-path
refusal, source tracking, fresh-process persistence, exact pair isolation,
incremental watermarks and stale-job rejection, empty/long histories, conflicting
claims and corrections, fabricated/invalid model output, capacity rollback,
generation failure, snapshot consistency during concurrent publication, duplicate
suppression, opt-in settings, and preserving existing API behavior.

The storage tests can also run with a standard Python installation alone:

```powershell
python -B -m unittest discover -s tests -p test_memory_store.py -v
```

The project `.gitignore` excludes `.venv`, `__pycache__`, `.env`, and SQLite
database files (including journal/WAL files). If any were already tracked by
Git, ignore rules do not automatically untrack them.
