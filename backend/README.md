# Persistent NPC chat history and basic long-term retrieval

The existing FastAPI backend still uses local Ollama with `qwen3:8b`.
The existing SQLite conversation history now includes Phase 1 long-term
retrieval: a deterministic keyword baseline over older player statements.
It uses Python's standard library, adds no dependencies or schema changes,
and does not implement the full MemoryRepository research architecture.

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
   connection writes meanwhile. Assistant replies are never historical-memory
   candidates. The transaction and connection close before calling Ollama.
3. Sends the system prompt, recent history, an optional historical user
   statements block, and the current message to Ollama, in that order.
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

The API uses `get_chat_context()` to obtain both blocks in one explicit `BEGIN`
read transaction. The existing standalone `get_recent_messages()` and
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

There is no summarization, semantic/vector retrieval, forgetting, retention
policy, or Unity integration in this phase. A sensible next step is evaluating
older-fact recall and irrelevant-memory rates against a fixed set of questions,
including conflicts and paraphrases, before expanding the memory architecture.

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

The storage tests can also run with a standard Python installation alone:

```powershell
python -B -m unittest discover -s tests -p test_memory_store.py -v
```

The project `.gitignore` excludes `.venv`, `__pycache__`, `.env`, and SQLite
database files (including journal/WAL files). If any were already tracked by
Git, ignore rules do not automatically untrack them.
