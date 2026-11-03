"""Additive, source-grounded summary storage. Initialization is explicit only."""

import hashlib
import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from memory_store import DEFAULT_DB_PATH, RECENT_MESSAGE_LIMIT
from retention_policy import personal_evidence, retention_decision

MAX_BATCH_MESSAGES = 20
MAX_INPUT_CHARS = 12000
MAX_ENTRY_CHARS = 600
MAX_SUMMARY_ENTRIES = 16
MAX_SUMMARY_CONTEXT_CHARS = 4000
CATEGORIES = (
    "identity", "relationship", "preference", "location", "event", "correction",
    "other", "ignore",
)


class SummaryError(ValueError):
    """Summary validation or capacity failure; existing data is preserved."""


class SummaryConflictError(SummaryError):
    """Another developer job changed the version or a source changed."""


def _check_target(db_path):
    path = Path(db_path).resolve()
    if path == DEFAULT_DB_PATH.resolve():
        raise SummaryError("The original conversation database is protected; use a disposable copy")
    if not path.is_file():
        raise SummaryError("An existing disposable conversation database is required")
    return path


def init_summary_schema(db_path: str | Path) -> None:
    """Explicit migration for a disposable DB; never called by app startup/chat."""
    path = _check_target(db_path)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_summary_state (
                player_id TEXT NOT NULL,
                npc_id TEXT NOT NULL,
                version INTEGER NOT NULL CHECK (version > 0),
                covered_through_id INTEGER NOT NULL CHECK (covered_through_id > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                model TEXT NOT NULL,
                format_version INTEGER NOT NULL,
                PRIMARY KEY (player_id, npc_id)
            )
            """
        )
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS memory_summary_entries (
                player_id TEXT NOT NULL,
                npc_id TEXT NOT NULL,
                source_message_id INTEGER NOT NULL,
                statement TEXT NOT NULL,
                category TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                added_version INTEGER NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY (player_id, npc_id, source_message_id),
                CHECK (length(statement) BETWEEN 1 AND 600),
                CHECK (category IN ('identity', 'relationship', 'preference',
                    'location', 'event', 'correction', 'other'))
            )
            """
        )


def _hash(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_summary(connection, player_id, npc_id):
    # Old Phase 1 databases remain readable without running a migration.
    if connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory_summary_state'"
    ).fetchone() is None:
        return None
    row = connection.execute(
        """SELECT version, covered_through_id, created_at, updated_at, model,
                  format_version FROM memory_summary_state
           WHERE player_id=? AND npc_id=?""", (player_id, npc_id)
    ).fetchone()
    if row is None:
        return None
    entries = connection.execute(
        """SELECT source_message_id, statement, category, source_sha256,
                  added_version, created_at FROM memory_summary_entries
           WHERE player_id=? AND npc_id=? ORDER BY source_message_id""",
        (player_id, npc_id),
    ).fetchall()
    for source_id, statement, _category, digest, _version, _created in entries:
        source = connection.execute(
            "SELECT content FROM messages WHERE id=? AND player_id=? AND npc_id=? AND role='user'",
            (source_id, player_id, npc_id),
        ).fetchone()
        if source is None or _hash(source[0]) != digest or source[0].strip() != statement:
            raise SummaryError(f"Saved summary source {source_id} failed validation")
    return {
        "player_id": player_id, "npc_id": npc_id,
        **dict(zip(("version", "covered_through_id", "created_at", "updated_at",
                    "model", "format_version"), row)),
        "entries": [dict(zip(("source_message_id", "statement", "category",
                              "source_sha256", "added_version", "created_at"), entry))
                    for entry in entries],
    }


def get_summary(player_id: str, npc_id: str, db_path: str | Path):
    """Read one pair's saved summary without initializing or changing schema."""
    with closing(sqlite3.connect(db_path)) as connection, connection:
        connection.execute("BEGIN")
        return _read_summary(connection, player_id, npc_id)


def prepare_summary_batch(player_id: str, npc_id: str, db_path: str | Path):
    """Capture eligible sources and expected version, then release the snapshot."""
    path = _check_target(db_path)
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN")
        summary = _read_summary(connection, player_id, npc_id)
        watermark = summary["covered_through_id"] if summary else 0
        rows = connection.execute(
            """SELECT id, content FROM messages
               WHERE player_id=? AND npc_id=? AND role='user' AND id>?
                 AND id NOT IN (SELECT id FROM messages
                     WHERE player_id=? AND npc_id=? ORDER BY id DESC LIMIT ?)
               ORDER BY id LIMIT ?""",
            (player_id, npc_id, watermark, player_id, npc_id,
             RECENT_MESSAGE_LIMIT, MAX_BATCH_MESSAGES),
        ).fetchall()
    sources = []
    used = 0
    for message_id, content in rows:
        if used + len(content) > MAX_INPUT_CHARS:
            if not sources:
                raise SummaryError("A source exceeds the input budget; no coverage was advanced")
            break
        sources.append({"message_id": message_id, "content": content})
        used += len(content)
    return {"player_id": player_id, "npc_id": npc_id,
            "expected_version": summary["version"] if summary else 0,
            "sources": sources}


def normalized_statement(text):
    # Preserve punctuation: '-5' versus '5' and 'C++' versus 'C' can be
    # different facts. Only case/whitespace differences are redundant here.
    return " ".join(text.casefold().split())


def summary_context(summary, recent=()):
    """Bounded, quoted claims; merge exact duplicates while preserving their IDs."""
    if summary is None:
        return None
    recent_text = [normalized_statement(item["content"]) for item in recent
                   if item["role"] == "user"]
    grouped = {}
    for entry in summary["entries"]:
        if not personal_evidence(entry["statement"]).eligible:
            continue
        key = normalized_statement(entry["statement"])
        # Exact whole-statement equality only: a quote inside a denial is not
        # redundant evidence and must not erase the older, opposing claim.
        if key in recent_text:
            continue
        if key in grouped:
            grouped[key]["source_message_ids"].append(entry["source_message_id"])
        else:
            grouped[key] = {
                "source_message_ids": [entry["source_message_id"]],
                "statement": entry["statement"], "category": entry["category"],
                "status": "unverified_user_statement",
                "speaker": "player",
            }
    if not grouped:
        return None
    context = {"version": summary["version"],
               "covered_through_id": summary["covered_through_id"],
               "entries": list(grouped.values())}
    if len(json.dumps(context, ensure_ascii=False)) > MAX_SUMMARY_CONTEXT_CHARS:
        # Do not silently omit an opposing claim to satisfy a context cap.
        raise SummaryError("Summary context exceeds its budget")
    return context


def review_summary_retention(summary):
    """Read-time eligibility audit; stored rows and their provenance stay intact."""
    if summary is None:
        return []
    review = []
    for entry in summary["entries"]:
        assessment = personal_evidence(entry["statement"])
        review.append({
            "source_message_id": entry["source_message_id"],
            "stored_category": entry["category"],
            "eligible_for_personal_context": assessment.eligible,
            "reason": assessment.reason,
        })
    return review


def publish_summary_batch(batch, decisions, model: str, db_path: str | Path):
    """CAS versioned publication; no message edits, deletions, or LLM calls."""
    path = _check_target(db_path)
    sources = batch["sources"]
    if not sources:
        raise SummaryError("Cannot publish an empty batch")
    expected_ids = [source["message_id"] for source in sources]
    if (len(decisions) != len(expected_ids)
            or {d["message_id"] for d in decisions} != set(expected_ids)
            or any(d["category"] not in CATEGORIES for d in decisions)):
        raise SummaryError("Every source needs exactly one valid classification")
    categories = {d["message_id"]: d["category"] for d in decisions}
    now = datetime.now(timezone.utc).isoformat()
    player, npc = batch["player_id"], batch["npc_id"]
    with closing(sqlite3.connect(path)) as connection, connection:
        connection.execute("BEGIN IMMEDIATE")
        previous = _read_summary(connection, player, npc)
        version = previous["version"] if previous else 0
        if version != batch["expected_version"]:
            raise SummaryConflictError("Summary changed; prepare a fresh batch")
        additions = []
        for source in sources:
            row = connection.execute(
                "SELECT content FROM messages WHERE id=? AND player_id=? AND npc_id=? AND role='user'",
                (source["message_id"], player, npc),
            ).fetchone()
            if row is None or row[0] != source["content"]:
                raise SummaryConflictError("A source changed; publication cancelled")
            decision = retention_decision(source, categories[source["message_id"]])
            category = decision["effective_category"]
            if category == "ignore":
                continue
            statement = source["content"].strip()
            if not statement or len(statement) > MAX_ENTRY_CHARS:
                raise SummaryError("Selected statement exceeds the complete-message budget")
            additions.append({"source_message_id": source["message_id"],
                              "statement": statement, "category": category,
                              "source_sha256": _hash(source["content"]),
                              "added_version": version + 1, "created_at": now})
        entries = (previous["entries"] if previous else []) + additions
        if len(entries) > MAX_SUMMARY_ENTRIES:
            raise SummaryError("Summary capacity reached; no facts were discarded")
        candidate = {"version": version + 1,
                     "covered_through_id": sources[-1]["message_id"], "entries": entries}
        summary_context(candidate)  # Validate the entire payload, including JSON overhead.
        connection.executemany(
            """INSERT INTO memory_summary_entries
               (player_id, npc_id, source_message_id, statement, category,
                source_sha256, added_version, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            [(player, npc, e["source_message_id"], e["statement"], e["category"],
              e["source_sha256"], e["added_version"], e["created_at"]) for e in additions],
        )
        connection.execute(
            """INSERT INTO memory_summary_state
               (player_id, npc_id, version, covered_through_id, created_at,
                updated_at, model, format_version) VALUES (?, ?, ?, ?, ?, ?, ?, 1)
               ON CONFLICT(player_id, npc_id) DO UPDATE SET
               version=excluded.version, covered_through_id=excluded.covered_through_id,
               updated_at=excluded.updated_at, model=excluded.model""",
            (player, npc, candidate["version"], candidate["covered_through_id"],
             previous["created_at"] if previous else now, now, model),
        )
    return get_summary(player, npc, path)
