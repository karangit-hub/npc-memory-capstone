import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_store import get_recent_messages, init_db, save_conversation


class MemoryStoreTests(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.db_path = Path(directory.name) / "memory.sqlite3"
        init_db(self.db_path)

    def save(self, player, npc, message, reply):
        save_conversation(player, npc, message, reply, db_path=self.db_path)

    def history(self, player="player", npc="guard", limit=10):
        return get_recent_messages(player, npc, limit=limit, db_path=self.db_path)

    def test_persists_across_database_connections(self):
        self.save("player", "guard", "Hello", "Welcome")

        # Inspect the committed data through an independent connection.
        connection = sqlite3.connect(self.db_path)
        try:
            rows = connection.execute(
                "SELECT role, content FROM messages ORDER BY id"
            ).fetchall()
        finally:
            connection.close()

        self.assertEqual(rows, [("user", "Hello"), ("assistant", "Welcome")])
        self.assertEqual(
            self.history(),
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Welcome"},
            ],
        )

    def test_separates_players_and_npcs(self):
        pairs = [("alice", "guard"), ("bob", "guard"), ("alice", "merchant")]
        for player, npc in pairs:
            self.save(player, npc, f"Hello from {player}", f"I am {npc}")

        for player, npc in pairs:
            with self.subTest(player=player, npc=npc):
                self.assertEqual(
                    self.history(player, npc),
                    [
                        {"role": "user", "content": f"Hello from {player}"},
                        {"role": "assistant", "content": f"I am {npc}"},
                    ],
                )
        self.assertEqual(self.history("bob", "merchant"), [])

    def test_returns_messages_in_chronological_order(self):
        expected = []
        for index in range(3):
            self.save("player", "guard", f"Question {index}", f"Answer {index}")
            expected.extend(
                [
                    {"role": "user", "content": f"Question {index}"},
                    {"role": "assistant", "content": f"Answer {index}"},
                ]
            )
        self.assertEqual(self.history(), expected)

    def test_returns_only_the_latest_ten_messages_by_default(self):
        expected = []
        for index in range(8):
            self.save("player", "guard", f"Question {index}", f"Answer {index}")
            expected.extend(
                [
                    {"role": "user", "content": f"Question {index}"},
                    {"role": "assistant", "content": f"Answer {index}"},
                ]
            )

        self.assertEqual(self.history(), expected[-10:])
        self.assertEqual(self.history(limit=3), expected[-3:])
        # Retrieval limits do not delete older persisted messages.
        self.assertEqual(self.history(limit=100), expected)

    def test_empty_history_and_limit_boundaries(self):
        self.assertEqual(self.history(), [])
        self.save("player", "guard", "Hello", "Welcome")
        self.assertEqual(self.history(limit=0), [])
        with self.assertRaises(ValueError):
            self.history(limit=-1)

    def test_initialization_preserves_existing_history(self):
        self.save("player", "guard", "Hello", "Welcome")
        init_db(self.db_path)
        self.assertEqual(len(self.history()), 2)

    def test_failed_exchange_rolls_back_both_messages(self):
        self.save("player", "guard", "Hello", "Welcome")
        before = self.history()
        with self.assertRaises(sqlite3.IntegrityError):
            self.save("player", "guard", "Unsaved question", None)
        self.assertEqual(self.history(), before)


if __name__ == "__main__":
    unittest.main()
