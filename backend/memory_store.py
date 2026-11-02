"""Basic persistent chat history, scoped to each player/NPC pair."""

import re
import sqlite3
from contextlib import closing
from heapq import nlargest
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).resolve().with_name("conversation_memory.sqlite3")
RECENT_MESSAGE_LIMIT = 10
MAX_HISTORICAL_MESSAGES = 3
MAX_MEMORY_CHARS = 1500
MAX_EXCERPT_CHARS = 500

# Small English baseline: punctuation splits tokens; repeated words score once.
STOPWORDS = frozenset(
    "a an and are as at be been but by can could did do does for from had has "
    "have he her here hers him his how i if in into is it its me my of on or "
    "our ours please s say she should so some t tell than that the their them "
    "then there these they this those to us was we were what when where which "
    "who why will with would you your yours remember recall re ve ll don".split()
)
WORD_PATTERN = re.compile(r"[^\W_]+", re.UNICODE)


def _keywords(text: str) -> set[str]:
    return {
        word for match in WORD_PATTERN.finditer(text)
        if len(word := match.group().casefold()) > 1 and word not in STOPWORDS
    }


def init_db(db_path: str | Path = DEFAULT_DB_PATH) -> None:
    """Create the database and index if they do not already exist."""
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                player_id TEXT NOT NULL,
                npc_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK (role IN ('user', 'assistant')),
                content TEXT NOT NULL
            )
            """
        )
        connection.execute(
            """
            CREATE INDEX IF NOT EXISTS messages_by_pair
            ON messages (player_id, npc_id, id)
            """
        )


def save_conversation(
    player_id: str,
    npc_id: str,
    user_message: str,
    npc_reply: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> None:
    """Commit both sides of a successful exchange together, or neither."""
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.executemany(
            """
            INSERT INTO messages (player_id, npc_id, role, content)
            VALUES (?, ?, ?, ?)
            """,
            [
                (player_id, npc_id, "user", user_message),
                (player_id, npc_id, "assistant", npc_reply),
            ],
        )


def get_recent_messages(
    player_id: str,
    npc_id: str,
    limit: int = RECENT_MESSAGE_LIMIT,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> list[dict[str, str]]:
    """Return the newest `limit` messages in oldest-to-newest order."""
    if limit < 0:
        raise ValueError("limit must be non-negative")

    with closing(sqlite3.connect(db_path)) as connection:
        return _get_recent_messages(connection, player_id, npc_id, limit)


def _get_recent_messages(
    connection: sqlite3.Connection, player_id: str, npc_id: str, limit: int
) -> list[dict[str, str]]:
    rows = connection.execute(
        """
        SELECT role, content FROM messages
        WHERE player_id = ? AND npc_id = ?
        ORDER BY id DESC LIMIT ?
        """,
        (player_id, npc_id, limit),
    ).fetchall()

    return [{"role": role, "content": content} for role, content in reversed(rows)]


def get_chat_context(
    player_id: str,
    npc_id: str,
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
) -> tuple[list[dict[str, str]], list[dict[str, str | int]]]:
    """Read both context blocks from one snapshot, closing it before generation."""
    with closing(sqlite3.connect(db_path)) as connection, connection:
        # Explicit BEGIN is needed: Python's legacy sqlite mode does not begin
        # a transaction for SELECT alone. The first SELECT fixes the snapshot.
        connection.execute("BEGIN")
        history = _get_recent_messages(
            connection, player_id, npc_id, RECENT_MESSAGE_LIMIT
        )
        memories = _get_relevant_memories(
            connection, player_id, npc_id, query,
            MAX_HISTORICAL_MESSAGES, MAX_MEMORY_CHARS,
        )
    return history, memories


def _memory_excerpt(content: str, keywords: set[str], budget: int) -> str:
    """Keep the best matching sentence and nearby context, verbatim and bounded."""
    if len(content) <= budget:
        return content

    # Basic sentence boundaries, not a language parser. Later sentences win
    # equal-overlap ties so an early topic mention cannot always dominate.
    sentences = list(re.finditer(r"[^.!?\n]+(?:[.!?]+|\n|$)", content))
    sentence = max(
        sentences,
        key=lambda part: (len(keywords & _keywords(part.group())), part.start()),
    )
    start, end = sentence.span()
    if end - start <= budget:
        index = sentences.index(sentence)
        if (index > 0
                and keywords & _keywords(sentences[index - 1].group())
                and end - sentences[index - 1].start() <= budget):
            start = sentences[index - 1].start()
        if (index + 1 < len(sentences)
                and keywords & _keywords(sentences[index + 1].group())
                and sentences[index + 1].end() - start <= budget):
            end = sentences[index + 1].end()
        return content[start:end].strip()

    # A sentence itself may exceed the cap. Compare short windows around every
    # matching token, rather than blindly keeping its first topic mention.
    starts = {
        max(start, min(part.start() - budget // 4, end - budget))
        for part in WORD_PATTERN.finditer(content, start, end)
        if part.group().casefold() in keywords
    }
    window_start = max(
        starts,
        key=lambda offset: (
            len(keywords & _keywords(content[offset:offset + budget])), offset
        ),
    )
    return content[window_start:window_start + budget]


def get_relevant_memories(
    player_id: str,
    npc_id: str,
    query: str,
    db_path: str | Path = DEFAULT_DB_PATH,
    *,
    limit: int = MAX_HISTORICAL_MESSAGES,
    max_chars: int = MAX_MEMORY_CHARS,
) -> list[dict[str, str | int]]:
    """Retrieve bounded excerpts of relevant older user statements, best first.

    Score distinct non-stopword overlap, breaking ties by newer insertion ID.
    Exclude the latest ten messages of either role before considering users.
    This reads existing history only; it never generates or persists memories.
    """
    if limit < 0 or max_chars < 0:
        raise ValueError("limit and max_chars must be non-negative")
    with closing(sqlite3.connect(db_path)) as connection:
        return _get_relevant_memories(
            connection, player_id, npc_id, query, limit, max_chars
        )


def _get_relevant_memories(
    connection: sqlite3.Connection,
    player_id: str,
    npc_id: str,
    query: str,
    limit: int,
    max_chars: int,
) -> list[dict[str, str | int]]:
    keywords = _keywords(query)
    limit = min(limit, MAX_HISTORICAL_MESSAGES)
    remaining = min(max_chars, MAX_MEMORY_CHARS)
    if not keywords or not limit or not remaining:
        return []

    rows = connection.execute(
        """
        SELECT id, content FROM messages
        WHERE player_id = ? AND npc_id = ? AND role = 'user'
          AND id NOT IN (
              SELECT id FROM messages
              WHERE player_id = ? AND npc_id = ?
              ORDER BY id DESC LIMIT ?
          )
        """,
        (player_id, npc_id, player_id, npc_id, RECENT_MESSAGE_LIMIT),
    )
    # Stream the archive and retain only the best three candidates in memory.
    ranked = nlargest(
        limit,
        (
            (score, message_id, content)
            for message_id, content in rows
            if (score := len(keywords & _keywords(content))) > 0
        ),
    )

    memories = []
    for _score, message_id, content in ranked:
        if not remaining:
            break
        budget = min(MAX_EXCERPT_CHARS, remaining)
        excerpt = _memory_excerpt(content, keywords, budget)
        memories.append({"message_id": message_id, "content": excerpt})
        remaining -= len(excerpt)
    return memories
