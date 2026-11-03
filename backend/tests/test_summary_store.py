import hashlib
import json
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import memory_store

from memory_store import DEFAULT_DB_PATH, get_chat_context_with_summary, init_db, save_conversation
from summary_store import (
    MAX_SUMMARY_CONTEXT_CHARS, SummaryConflictError, SummaryError, get_summary,
    init_summary_schema, prepare_summary_batch, publish_summary_batch, summary_context,
)


class SummaryStoreTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "summary.sqlite3"
        init_db(self.db_path)
        init_summary_schema(self.db_path)

    def save(self, statement, player="karan", npc="Arthur"):
        save_conversation(player, npc, statement, "Acknowledged.", self.db_path)

    def age(self):
        for index in range(6):
            self.save(f"Weather discussion {index}")

    def batch(self):
        return prepare_summary_batch("karan", "Arthur", self.db_path)

    def publish(self, selected, batch=None):
        batch = batch or self.batch()
        return publish_summary_batch(
            batch, [{"message_id": s["message_id"],
                     "category": selected.get(s["message_id"], "ignore")}
                    for s in batch["sources"]], "qwen3:8b", self.db_path,
        )

    def messages(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            return connection.execute("SELECT * FROM messages ORDER BY id").fetchall()

    def test_additive_initialization_preserves_existing_conversation_and_summary(self):
        self.save("My favorite weapon is a silver spear.")
        self.age()
        summary = self.publish({1: "preference"})
        before = self.messages()
        init_summary_schema(self.db_path)
        self.assertEqual(self.messages(), before)
        self.assertEqual(get_summary("karan", "Arthur", self.db_path), summary)

    def test_original_database_migration_is_refused_before_opening_it(self):
        with self.assertRaisesRegex(SummaryError, "original conversation database is protected"):
            init_summary_schema(DEFAULT_DB_PATH)

    def test_source_tracking_metadata_and_complete_negated_statement(self):
        fact = "I do not like tea. I prefer water."
        self.save(fact)
        self.age()
        before = self.messages()
        saved = self.publish({1: "preference"})
        entry = saved["entries"][0]
        self.assertEqual(entry["source_message_id"], 1)
        self.assertEqual(entry["statement"], fact)
        self.assertEqual(entry["source_sha256"], hashlib.sha256(fact.encode()).hexdigest())
        self.assertEqual(saved["version"], 1)
        self.assertEqual(saved["covered_through_id"], 3)
        self.assertEqual(entry["added_version"], 1)
        self.assertTrue(saved["created_at"])
        self.assertEqual(saved["created_at"], saved["updated_at"])
        self.assertEqual(self.messages(), before)

    def test_exact_player_and_npc_isolation(self):
        self.save("My sister's name is Emily.")
        self.age()
        self.publish({1: "relationship"})
        for player, npc in [("rajan", "Arthur"), ("Karan", "Arthur"),
                            ("karan", "arthur"), ("karan", "Merchant")]:
            with self.subTest(player=player, npc=npc):
                self.assertIsNone(get_summary(player, npc, self.db_path))

    def test_summary_survives_fresh_process(self):
        self.save("My sister's name is Emily.")
        self.age()
        saved = self.publish({1: "relationship"})
        code = ("import json,sys; from summary_store import get_summary; "
                "print(json.dumps(get_summary('karan','Arthur',sys.argv[1])))")
        result = subprocess.check_output([sys.executable, "-B", "-c", code, str(self.db_path)], text=True)
        self.assertEqual(json.loads(result), saved)

    def test_read_revalidates_statement_and_rejects_foreign_or_assistant_sources(self):
        self.save("My sister's name is Emily.")
        self.age()
        saved = self.publish({1: "relationship"})
        original = saved["entries"][0]
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE memory_summary_entries SET statement='Fabricated name'")
        with self.assertRaisesRegex(SummaryError, "failed validation"):
            get_summary("karan", "Arthur", self.db_path)
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE memory_summary_entries SET statement=?, source_message_id=2", (original["statement"],))
        with self.assertRaisesRegex(SummaryError, "failed validation"):
            get_summary("karan", "Arthur", self.db_path)
        self.save("My sister's name is Emily.", player="rajan")
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE memory_summary_entries SET source_message_id=15")
        with self.assertRaisesRegex(SummaryError, "failed validation"):
            get_summary("karan", "Arthur", self.db_path)

    def test_incremental_watermark_and_stale_job_compare_and_swap(self):
        self.save("My favorite weapon is a spear.")
        self.age()
        first_batch = self.batch()
        first = self.publish({1: "preference"}, first_batch)
        self.assertEqual(self.batch()["sources"], [])
        with self.assertRaises(SummaryConflictError):
            self.publish({1: "preference"}, first_batch)
        self.assertEqual(get_summary("karan", "Arthur", self.db_path), first)
        self.save("My sister's name is Emily.")
        self.age()
        second = self.publish({15: "relationship"})
        self.assertEqual(second["version"], 2)
        self.assertEqual([e["source_message_id"] for e in second["entries"]], [1, 15])
        self.assertEqual(second["created_at"], first["created_at"])
        self.assertNotEqual(second["updated_at"], first["updated_at"])
        self.assertEqual(self.batch()["sources"], [])

    def test_empty_and_recent_only_history_has_no_batch(self):
        self.assertEqual(self.batch()["sources"], [])
        self.save("My favorite weapon is a spear.")
        self.assertEqual(self.batch()["sources"], [])
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    def test_long_conversation_is_batched_without_skipping_messages(self):
        for index in range(60):
            self.save(f"Weather discussion {index}")
        seen = []
        while (batch := self.batch())["sources"]:
            self.assertLessEqual(len(batch["sources"]), 20)
            seen.extend(s["message_id"] for s in batch["sources"])
            self.publish({}, batch)
        self.assertEqual(seen, list(range(1, 110, 2)))
        self.assertEqual(get_summary("karan", "Arthur", self.db_path)["entries"], [])

    def test_conflicting_statements_and_explicit_correction_are_not_overwritten(self):
        claims = ["My favorite weapon is a silver spear.",
                  "My favorite weapon is an axe.",
                  "Correction: my favorite weapon is a wooden staff."]
        for claim in claims:
            self.save(claim)
        self.age()
        saved = self.publish({1: "preference", 3: "preference", 5: "correction"})
        self.assertEqual([e["statement"] for e in saved["entries"]], claims)
        self.assertTrue(all(e["status"] == "unverified_user_statement"
                            for e in summary_context(saved)["entries"]))

    def test_source_change_cancels_publication(self):
        self.save("My favorite weapon is a spear.")
        self.age()
        batch = self.batch()
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE messages SET content='Changed fixture' WHERE id=1")
        with self.assertRaisesRegex(SummaryConflictError, "source changed"):
            self.publish({1: "preference"}, batch)
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    def test_capacity_failure_does_not_partially_write_or_advance_coverage(self):
        for index in range(17):
            self.save(f"My important personal token is token{index}.")
        self.age()
        with self.assertRaisesRegex(SummaryError, "capacity"):
            self.publish({i: "other" for i in range(1, 34, 2)})
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))
        with closing(sqlite3.connect(self.db_path)) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM memory_summary_entries").fetchone()[0], 0)

    def test_json_context_budget_includes_formatting_overhead(self):
        for index in range(7):
            self.save(f"My preference {index}: " + "x" * 550)
        self.age()
        with self.assertRaisesRegex(SummaryError, "context exceeds"):
            self.publish({i: "preference" for i in range(1, 14, 2)})
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    def test_oversized_source_is_not_truncated_into_a_false_fact(self):
        self.save("My preference: " + "x" * 1000)
        self.age()
        with self.assertRaisesRegex(SummaryError, "complete-message budget"):
            self.publish({1: "preference"})
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    def test_oversized_input_does_not_advance_watermark(self):
        self.save("x" * 12001)
        self.age()
        with self.assertRaisesRegex(SummaryError, "input budget"):
            self.batch()
        self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    def test_context_deduplicates_recent_and_keyword_blocks(self):
        fact = "My favorite weapon is a silver spear."
        self.save(fact)
        self.age()
        self.publish({1: "preference"})
        recent, keywords, summary = get_chat_context_with_summary(
            "karan", "Arthur", "favorite weapon", self.db_path
        )
        self.assertEqual(keywords, [])
        self.assertEqual(summary["entries"][0]["statement"], fact)
        self.assertLessEqual(len(json.dumps(summary, ensure_ascii=False)), MAX_SUMMARY_CONTEXT_CHARS)
        self.save(fact)
        recent, keywords, summary = get_chat_context_with_summary(
            "karan", "Arthur", "favorite weapon", self.db_path
        )
        self.assertEqual(keywords, [])
        self.assertIsNone(summary)
        self.assertTrue(any(m["content"] == fact for m in recent))

    def test_negated_recent_quote_does_not_hide_older_opposing_claim(self):
        self.save("I like tea.")
        self.age()
        saved = self.publish({1: "preference"})
        context = summary_context(saved, [{"role": "user", "content": "I never said I like tea."}])
        self.assertIsNotNone(context)

    def test_duplicate_statements_merge_provenance_without_erasing_source_records(self):
        self.save("I like tea.")
        self.save("I like tea.")
        self.age()
        saved = self.publish({1: "preference", 3: "preference"})
        self.assertEqual(len(saved["entries"]), 2)
        self.assertEqual(summary_context(saved)["entries"][0]["source_message_ids"], [1, 3])

    def test_deduplication_keeps_signs_and_meaningful_punctuation(self):
        self.save("I have -5 gold.")
        self.save("I have 5 gold.")
        self.age()
        saved = self.publish({1: "other", 3: "other"})
        self.assertEqual(len(summary_context(saved)["entries"]), 2)
        recent = [{"role": "user", "content": "I have 5 gold."}]
        context = summary_context(saved, recent)
        self.assertEqual(context["entries"][0]["statement"], "I have -5 gold.")

    def test_old_schema_chat_reads_do_not_migrate_database(self):
        other = self.db_path.with_name("phase1.sqlite3")
        init_db(other)
        before = hashlib.sha256(other.read_bytes()).hexdigest()
        self.assertEqual(get_chat_context_with_summary("karan", "Arthur", "hello", other), ([], [], None))
        self.assertEqual(hashlib.sha256(other.read_bytes()).hexdigest(), before)

    def test_summary_and_conversation_reads_share_snapshot_during_publication(self):
        with closing(sqlite3.connect(self.db_path)) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
        self.save("My favorite weapon is a silver spear.")
        self.age()
        self.publish({1: "preference"})
        self.save("My sister's name is Emily.")
        self.age()
        batch = self.batch()
        read_recent = memory_store._get_recent_messages

        def read_then_publish(connection, player, npc, limit):
            history = read_recent(connection, player, npc, limit)
            self.publish({15: "relationship"}, batch)
            return history

        with patch.object(memory_store, "_get_recent_messages", side_effect=read_then_publish):
            _recent, _keywords, saved = get_chat_context_with_summary(
                "karan", "Arthur", "hello", self.db_path
            )
        self.assertEqual(saved["version"], 1)
        self.assertEqual(get_summary("karan", "Arthur", self.db_path)["version"], 2)


if __name__ == "__main__":
    unittest.main()
