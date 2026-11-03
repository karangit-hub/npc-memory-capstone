import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
from pydantic import ValidationError

from memory_store import init_db, save_conversation
from summarizer import summarize_pair
from summary_store import SummaryError, get_summary


class SummarizerTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "summary.sqlite3"
        init_db(self.db_path)
        self.client = SimpleNamespace(chat=AsyncMock())

    def seed(self):
        save_conversation("karan", "Arthur", "My sister's name is Emily.",
                          "Your mother is named Jane.", self.db_path)
        for index in range(6):
            save_conversation("karan", "Arthur", f"Weather discussion {index}", "Fine weather.", self.db_path)

    def output(self, value):
        text = value if isinstance(value, str) else json.dumps(value)
        self.client.chat.return_value = SimpleNamespace(message=SimpleNamespace(content=text))

    async def run_summary(self):
        return await summarize_pair("karan", "Arthur", self.db_path, client=self.client)

    async def test_real_source_selection_structured_format_and_idempotent_retry(self):
        self.seed()
        self.output({"decisions": [{"message_id": 1, "category": "relationship"},
                                   {"message_id": 3, "category": "ignore"}]})
        result = await self.run_summary()
        self.assertEqual(result["status"], "updated")
        self.assertEqual(result["processed_source_ids"], [1, 3])
        self.assertEqual(result["summary"]["entries"][0]["statement"], "My sister's name is Emily.")
        arguments = self.client.chat.await_args.kwargs
        self.assertEqual(arguments["model"], "qwen3:8b")
        self.assertEqual(arguments["format"]["type"], "object")
        self.assertFalse(arguments["stream"])
        self.assertFalse(arguments["think"])
        supplied = json.loads(arguments["messages"][1]["content"])["source_user_messages"]
        self.assertEqual([s["message_id"] for s in supplied], [1, 3])
        self.assertNotIn("Jane", json.dumps(arguments["messages"]))
        retry = await self.run_summary()
        self.assertEqual(retry["status"], "noop")
        self.assertEqual(retry["summary"], result["summary"])
        self.client.chat.assert_awaited_once()

    async def test_empty_history_does_not_call_model(self):
        result = await self.run_summary()
        self.assertEqual(result, {"status": "noop", "processed_source_ids": [], "summary": None})
        self.client.chat.assert_not_awaited()

    async def test_fabricated_text_unknown_ids_assistant_ids_and_invalid_json_are_rejected(self):
        self.seed()
        invalid = [
            "not JSON",
            {"decisions": [{"message_id": 1, "category": "relationship", "statement": "Her name is Alice"}, {"message_id": 3, "category": "ignore"}]},
            {"decisions": [{"message_id": 2, "category": "relationship"}, {"message_id": 3, "category": "ignore"}]},
            {"decisions": [{"message_id": 999, "category": "relationship"}, {"message_id": 3, "category": "ignore"}]},
            {"decisions": [{"message_id": 1, "category": "relationship"}]},
            {"decisions": [{"message_id": 1, "category": "relationship"}, {"message_id": 1, "category": "ignore"}]},
            {"decisions": [{"message_id": "1", "category": "relationship"}, {"message_id": 3, "category": "ignore"}]},
            {"decisions": [{"message_id": 1, "category": "invented"}, {"message_id": 3, "category": "ignore"}]},
        ]
        for value in invalid:
            with self.subTest(value=value):
                self.output(value)
                with self.assertRaises((ValidationError, SummaryError)):
                    await self.run_summary()
                self.assertIsNone(get_summary("karan", "Arthur", self.db_path))

    async def test_failed_generation_and_validation_preserve_previous_summary(self):
        self.seed()
        self.output({"decisions": [{"message_id": 1, "category": "relationship"}, {"message_id": 3, "category": "ignore"}]})
        previous = (await self.run_summary())["summary"]
        for index in range(6):
            save_conversation("karan", "Arthur", f"More weather {index}", "Fine weather.", self.db_path)
        self.client.chat.side_effect = httpx.ConnectError("Ollama unavailable")
        with self.assertRaises(httpx.ConnectError):
            await self.run_summary()
        self.assertEqual(get_summary("karan", "Arthur", self.db_path), previous)
        self.client.chat.side_effect = None
        self.output("{}")
        with self.assertRaises(ValidationError):
            await self.run_summary()
        self.assertEqual(get_summary("karan", "Arthur", self.db_path), previous)

    async def test_no_database_transaction_is_held_while_model_runs(self):
        self.seed()

        async def generate(**kwargs):
            # A separate writer must commit before this simulated generation
            # returns, in default rollback-journal mode.
            save_conversation("other", "Arthur", "Concurrent request", "Noted.", self.db_path)
            return SimpleNamespace(message=SimpleNamespace(content=json.dumps({"decisions": [
                {"message_id": 1, "category": "relationship"}, {"message_id": 3, "category": "ignore"}]})))

        self.client.chat.side_effect = generate
        self.assertEqual((await self.run_summary())["status"], "updated")

    async def test_application_review_overrides_question_label_and_preserves_question_like_fact(self):
        save_conversation("karan", "Arthur", "Is there a blacksmith in this village?", "A guess.", self.db_path)
        save_conversation("karan", "Arthur", "Can you remember that I prefer tea?", "Noted.", self.db_path)
        for index in range(6):
            save_conversation("karan", "Arthur", f"Clouds {index}", "Fair weather.", self.db_path)
        self.output({"decisions": [{"message_id": 1, "category": "location"},
                                   {"message_id": 3, "category": "ignore"},
                                   {"message_id": 5, "category": "other"}]})
        result = await self.run_summary()
        self.assertEqual([e["source_message_id"] for e in result["summary"]["entries"]], [3])
        review = {row["source_message_id"]: row for row in result["selection_review"]}
        self.assertFalse(review[1]["retained"])
        self.assertEqual(review[1]["model_category"], "location")
        self.assertTrue(review[3]["retained"])


if __name__ == "__main__":
    unittest.main()
