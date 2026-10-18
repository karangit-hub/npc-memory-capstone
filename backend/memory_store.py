"""Basic persistent chat history, scoped to each player/NPC pair."""

import sqlite3
from contextlib import closing
from pathlib import Path


DEFAULT_DB_PATH = Path(__file__).resolve().with_name("conversation_memory.sqlite3")


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
    limit: int = 10,
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
