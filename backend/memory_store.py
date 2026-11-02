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
        rows = connection.execute(
            """
            SELECT role, content
            FROM messages
            WHERE player_id = ? AND npc_id = ?
            ORDER BY id DESC
            LIMIT ?
            """,
            (player_id, npc_id, limit),
        ).fetchall()

    return [{"role": role, "content": content} for role, content in reversed(rows)]


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
    keywords = _keywords(query)
    limit = min(limit, MAX_HISTORICAL_MESSAGES)
    remaining = min(max_chars, MAX_MEMORY_CHARS)
    if not keywords or not limit or not remaining:
        return []

    with closing(sqlite3.connect(db_path)) as connection:
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
    for score, message_id, content in ranked:
        if not remaining:
            break
        budget = min(MAX_EXCERPT_CHARS, remaining)
        # Keep the first matching word visible even in a long historical message.
        match = next(
            match for match in WORD_PATTERN.finditer(content)
            if match.group().casefold() in keywords
        )
        start = max(0, match.start() - budget // 4)
        excerpt = content[start:start + budget]
        memories.append({"message_id": message_id, "content": excerpt})
        remaining -= len(excerpt)
    return memories
