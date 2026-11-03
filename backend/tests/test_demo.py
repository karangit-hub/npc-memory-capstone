import json
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack, closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient

import main
from memory_store import get_recent_messages, save_conversation
from summary_store import init_summary_schema, prepare_summary_batch, publish_summary_batch


class DemoTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        self.db_path = Path(directory) / "demo.sqlite3"
        for name, value in [("DATABASE_PATH", self.db_path), ("DEMO_ENABLED", True),
                            ("SUMMARY_CONTEXT_ENABLED", True)]:
            stack.enter_context(patch.object(main, name, value))
        self.model = stack.enter_context(patch.object(main.llm, "chat", new_callable=AsyncMock))
        self.model.return_value = SimpleNamespace(message=SimpleNamespace(content="Welcome."))
        self.client = stack.enter_context(TestClient(main.app, base_url="http://127.0.0.1:8001", client=("127.0.0.1", 45000)))

    def seed(self, statement="I study astronomy."):
        save_conversation("karan", "Arthur", statement, "Noted.", self.db_path)
        for index in range(6):
            save_conversation("karan", "Arthur", f"Clouds {index}", "Fair weather.", self.db_path)
        init_summary_schema(self.db_path)
        batch = prepare_summary_batch("karan", "Arthur", self.db_path)
        publish_summary_batch(batch, [{"message_id": s["message_id"],
                                      "category": "other" if s["message_id"] == 1 else "ignore"}
                                     for s in batch["sources"]], "qwen3:8b", self.db_path)

    def test_browser_and_assets_are_served_without_changing_original_endpoints(self):
        response = self.client.get("/demo")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Memory inspector", response.text)
        self.assertIn("/demo/assets/app.js", response.text)
        self.assertIn("frame-ancestors 'none'", response.headers["content-security-policy"])
        for asset in ["styles.css", "app.js"]:
            self.assertEqual(self.client.get("/demo/assets/" + asset).status_code, 200)
        self.assertEqual(self.client.get("/demo/assets/main.py").status_code, 404)
        self.assertEqual(self.client.get("/").json(), {"message": "NPC Memory Backend is running!"})
        self.assertEqual(self.client.get("/health").json(), {"status": "healthy"})

    def test_demo_is_opt_in_local_only_and_origin_restricted(self):
        with patch.object(main, "DEMO_ENABLED", False):
            self.assertEqual(self.client.get("/demo").status_code, 404)
        self.assertEqual(self.client.get("/demo", headers={"Host": "untrusted.example"}).status_code, 403)
        self.assertEqual(self.client.get("/demo", headers={"Origin": "https://untrusted.example"}).status_code, 403)
        with TestClient(main.app, base_url="http://127.0.0.1:8001", client=("192.0.2.1", 45001)) as remote:
            self.assertEqual(remote.get("/demo").status_code, 403)

    def test_demo_refuses_original_database_before_initialization(self):
        with patch.object(main, "DEFAULT_DB_PATH", self.db_path):
            with self.assertRaisesRegex(RuntimeError, "requires a separate"):
                with TestClient(main.app):
                    pass

    def test_context_preview_reports_actual_ids_summary_and_exact_pair(self):
        self.seed()
        before = self.db_path.read_bytes()
        response = self.client.post("/demo/api/context", json={"player_id": "karan", "npc_id": "Arthur", "message": "What do I study?"})
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["context_kind"], "preview_for_next_request")
        self.assertEqual(len(data["recent_messages"]), 10)
        self.assertIn("message_id", data["recent_messages"][0])
        self.assertEqual(data["saved_summary"]["entries"][0]["source_message_id"], 1)
        self.assertEqual(data["saved_summary"]["entries"][0]["statement"], "I study astronomy.")
        self.assertTrue(data["summary_context_enabled"])
        self.assertEqual(self.db_path.read_bytes(), before)
        other = self.client.post("/demo/api/context", json={"player_id": "rajan", "npc_id": "Arthur", "message": "What do I study?"}).json()
        self.assertEqual(other["recent_messages"], [])
        self.assertIsNone(other["saved_summary"])
        self.model.assert_not_awaited()

    def test_context_has_no_reset_or_generation_endpoints(self):
        for endpoint in ["/demo/api/reset", "/demo/api/summarize", "/demo/api/delete"]:
            self.assertEqual(self.client.post(endpoint).status_code, 404)

    def test_status_reports_real_model_availability_and_failure(self):
        with patch("demo.httpx.AsyncClient") as factory:
            get = factory.return_value.__aenter__.return_value.get
            get.return_value = httpx.Response(200, json={"models": [{"name": "qwen3:8b"}]}, request=httpx.Request("GET", "http://127.0.0.1:11434/api/tags"))
            data = self.client.get("/demo/api/status").json()
            self.assertTrue(data["ollama_available"])
            self.assertTrue(data["model_installed"])
            self.assertEqual(data["database_path"], str(self.db_path))
            get.side_effect = httpx.ConnectError("Unavailable")
            data = self.client.get("/demo/api/status").json()
            self.assertFalse(data["ollama_available"])
            self.assertIsNone(data["model_installed"])

    def test_first_person_guard_keeps_chat_format_and_saves_attributed_response(self):
        self.seed()
        self.model.return_value.message.content = "I study astronomy."
        response = self.client.post("/chat", json={"player_id": "karan", "npc_id": "Arthur", "message": "What do I study?"})
        self.assertEqual(response.json(), {"npc_id": "Arthur", "reply": 'You previously said: “I study astronomy.”'})
        self.assertEqual(get_recent_messages("karan", "Arthur", db_path=self.db_path)[-1]["content"], response.json()["reply"])

    def test_conflict_guard_quotes_claims_without_accepting_model_explanation(self):
        save_conversation("karan", "Arthur", "My favorite color is amber.", "Noted.", self.db_path)
        save_conversation("karan", "Arthur", "My favorite color is violet.", "Noted.", self.db_path)
        self.model.return_value.message.content = "Maybe you like a mix of both."
        response = self.client.post("/chat", json={"player_id": "karan", "npc_id": "Arthur", "message": "What is my favorite color?"})
        self.assertEqual(response.status_code, 200)
        self.assertIn("I'm not sure which is current", response.json()["reply"])
        self.assertNotIn("Maybe", response.json()["reply"])
        self.model.assert_awaited_once()

    def test_changed_summary_source_returns_clear_error_without_calling_model(self):
        self.seed()
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("UPDATE messages SET content='Changed fixture' WHERE id=1")
        response = self.client.post("/chat", json={"player_id": "karan", "npc_id": "Arthur", "message": "What do I study?"})
        self.assertEqual(response.status_code, 503)
        self.assertIn("source 1 failed validation", response.json()["detail"])
        self.model.assert_not_awaited()

    def test_overview_preserves_api_format_and_correct_player_attribution(self):
        self.seed("My sister's name is Mira.")
        save_conversation("karan", "Arthur", "Is there a blacksmith in this village?", "No idea.", self.db_path)
        self.model.return_value.message.content = "I also recall asking about the village's history and a blacksmith."
        response = self.client.post("/chat", json={"player_id": "karan", "npc_id": "Arthur", "message": "What do you remember about me?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(set(response.json()), {"npc_id", "reply"})
        self.assertIn("you've told me", response.json()["reply"])
        self.assertIn("Mira", response.json()["reply"])
        self.assertNotIn("blacksmith", response.json()["reply"])
        self.assertEqual(get_recent_messages("karan", "Arthur", db_path=self.db_path)[-1]["content"], response.json()["reply"])


if __name__ == "__main__":
    unittest.main()
