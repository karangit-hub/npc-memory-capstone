import sqlite3
import tempfile
import unittest
from pathlib import Path

from memory_store import (
    get_recent_messages,
    get_relevant_memories,
    init_db,
    save_conversation,
)


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

    def age_history(self, player="player", npc="guard", exchanges=6):
        for index in range(exchanges):
            self.save(player, npc, f"Weather discussion {index}", "Clear skies.")

    def memories(self, query="What is my favorite weapon?", **kwargs):
        return get_relevant_memories(
            "player", "guard", query, self.db_path, **kwargs
        )

    def test_retrieves_old_user_fact_without_modifying_storage(self):
        fact = "My favorite weapon is a silver spear."
        self.save("player", "guard", fact, "Understood.")
        self.age_history()
        before = self.history(limit=100)
        self.assertEqual(self.memories(), [{"message_id": 1, "content": fact}])
        self.assertNotIn({"role": "user", "content": fact}, self.history())
        self.assertEqual(self.history(limit=100), before)

    def test_excludes_exactly_the_recent_ten_messages_of_both_roles(self):
        self.save("player", "guard", "My favorite weapon is a spear.", "Noted.")
        self.age_history(exchanges=4)
        self.assertEqual(self.memories(), [])
        self.age_history(exchanges=1)
        # The initial exchange has just left the ten-message window.
        self.assertEqual([m["message_id"] for m in self.memories()], [1])

    def test_excludes_assistant_only_claims(self):
        self.save("player", "guard", "Hello there.", "Your favorite weapon is an axe.")
        self.age_history()
        self.assertEqual(self.memories(), [])

    def test_isolates_exact_player_and_npc_ids(self):
        self.save("alice", "guard", "My favorite weapon is a spear.", "Noted.")
        self.save("player", "merchant", "My favorite weapon is a bow.", "Noted.")
        self.save("Player", "guard", "My favorite weapon is a sword.", "Noted.")
        self.save("player", "Guard", "My favorite weapon is an axe.", "Noted.")
        for player, npc in [("alice", "guard"), ("player", "merchant"),
                            ("Player", "guard"), ("player", "Guard")]:
            self.age_history(player, npc)
        self.age_history()
        self.assertEqual(self.memories(), [])

    def test_normalizes_case_punctuation_and_stopwords(self):
        self.save("player", "guard", "MY FAVORITE-WEAPON: a SILVER spear!", "Noted.")
        self.age_history()
        self.assertEqual(len(self.memories("What IS my favorite, weapon?!")), 1)
        for query in ("What is my?", "!!!", "", " \n "):
            with self.subTest(query=query):
                self.assertEqual(self.memories(query), [])

    def test_ranks_overlap_before_recency_and_recency_breaks_ties(self):
        self.save("player", "guard", "My favorite weapon is a spear.", "Noted.")
        self.save("player", "guard", "A weapon hangs here.", "Noted.")
        self.save("player", "guard", "Another weapon is nearby.", "Noted.")
        self.save("player", "guard", "Weapon weapon weapon.", "Noted.")
        self.save("player", "guard", "The garden has flowers.", "Noted.")
        self.age_history()
        # Repeating a keyword does not inflate its score; unrelated rows are absent.
        self.assertEqual([m["message_id"] for m in self.memories()], [1, 7, 5])

    def test_matches_whole_words_not_substrings(self):
        self.save("player", "guard", "The spearman carries a shield.", "Noted.")
        self.age_history()
        self.assertEqual(self.memories("spear"), [])

    def test_no_history_or_unrelated_query_returns_no_memories(self):
        self.assertEqual(self.memories(), [])
        self.save("player", "guard", "My favorite weapon is a spear.", "Noted.")
        self.age_history()
        self.assertEqual(self.memories("Where is the bakery?"), [])

    def test_caps_result_count_and_excerpt_character_budget(self):
        for index in range(5):
            self.save("player", "guard", f"Weapon {index}: " + "x" * 2000, "Noted.")
        self.age_history()
        memories = self.memories("weapon", limit=100, max_chars=10000)
        self.assertEqual(len(memories), 3)
        self.assertEqual(sum(len(m["content"]) for m in memories), 1500)
        self.assertTrue(all(len(m["content"]) <= 500 for m in memories))
        self.assertEqual([m["message_id"] for m in memories], [9, 7, 5])
        small = self.memories("weapon", max_chars=60)
        self.assertEqual(sum(len(m["content"]) for m in small), 60)
        self.assertEqual(len(self.memories("weapon", limit=1)), 1)

    def test_excerpt_includes_match_near_end_of_long_message(self):
        self.save("player", "guard", "Introductory text. " * 200 +
                  "My favorite weapon is a silver spear.", "Noted.")
        self.age_history()
        excerpt = self.memories()[0]["content"]
        self.assertIn("silver spear", excerpt)
        self.assertLessEqual(len(excerpt), 500)

    def test_retrieval_limit_boundaries(self):
        self.save("player", "guard", "My favorite weapon is a spear.", "Noted.")
        self.age_history()
        self.assertEqual(self.memories(limit=0), [])
        self.assertEqual(self.memories(max_chars=0), [])
        for options in ({"limit": -1}, {"max_chars": -1}):
            with self.subTest(options=options), self.assertRaises(ValueError):
                self.memories(**options)


if __name__ == "__main__":
    unittest.main()
