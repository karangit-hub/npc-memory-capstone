"""Read-only summary eligibility audit. No repair/delete/apply operation exists."""

import argparse
import json
import sqlite3
from contextlib import closing
from pathlib import Path

from summary_store import _read_summary, review_summary_retention


def audit_summary(player_id, npc_id, db_path):
    uri = Path(db_path).resolve().as_uri() + "?mode=ro"
    with closing(sqlite3.connect(uri, uri=True)) as connection, connection:
        connection.execute("PRAGMA query_only=ON")
        connection.execute("BEGIN")
        summary = _read_summary(connection, player_id, npc_id)
    return {"player_id": player_id, "npc_id": npc_id,
            "summary_version": summary["version"] if summary else None,
            "covered_through_id": summary["covered_through_id"] if summary else None,
            "entries": review_summary_retention(summary), "storage_changed": False}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--player-id", required=True)
    parser.add_argument("--npc-id", required=True)
    arguments = parser.parse_args()
    print(json.dumps(audit_summary(arguments.player_id, arguments.npc_id, arguments.db), indent=2))
