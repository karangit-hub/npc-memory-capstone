import tempfile
import unittest
from contextlib import ExitStack
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi.testclient import TestClient
from ollama import ResponseError

import main
from memory_store import get_recent_messages, save_conversation


class ChatTests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        directory = stack.enter_context(tempfile.TemporaryDirectory())
        self.db_path = Path(directory) / "memory.sqlite3"
        stack.enter_context(patch.object(main, "DATABASE_PATH", self.db_path))
        self.llm_chat = stack.enter_context(
            patch.object(main.llm, "chat", new_callable=AsyncMock)
        )
        self.llm_chat.return_value = SimpleNamespace(
            message=SimpleNamespace(content="Welcome back, traveler.")
        )
        # Entering the client context runs database initialization at startup.
        self.client = stack.enter_context(TestClient(main.app))

    def post_chat(self, message="Hello"):
        return self.client.post(
            "/chat",
            json={"player_id": "alice", "npc_id": "guard", "message": message},
        )

    def history(self):
        return get_recent_messages("alice", "guard", db_path=self.db_path)

    def test_startup_initializes_database_and_preserves_endpoints(self):
        self.assertTrue(self.db_path.is_file())
        self.assertEqual(self.history(), [])
        self.assertEqual(
            self.client.get("/").json(),
            {"message": "NPC Memory Backend is running!"},
        )
        self.assertEqual(self.client.get("/health").json(), {"status": "healthy"})
        self.llm_chat.assert_not_awaited()

    def test_success_saves_both_sides_with_unchanged_response_format(self):
        response = self.post_chat()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.json(), {"npc_id": "guard", "reply": "Welcome back, traveler."}
        )
        self.assertEqual(
            self.history(),
            [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Welcome back, traveler."},
            ],
        )

    def test_ollama_receives_latest_ten_messages_for_requested_pair(self):
        for index in range(7):
            save_conversation(
                "alice", "guard", f"Question {index}", f"Answer {index}", self.db_path
            )
        save_conversation("bob", "guard", "Private", "Bob's reply", self.db_path)
        save_conversation("alice", "merchant", "Trade", "Merchant reply", self.db_path)
        expected_history = self.history()

        response = self.post_chat("What did we discuss?")
        self.assertEqual(response.status_code, 200)
        self.llm_chat.assert_awaited_once()
        arguments = self.llm_chat.await_args.kwargs
        self.assertEqual(arguments["model"], "qwen3:8b")
        self.assertFalse(arguments["stream"])
        self.assertFalse(arguments["think"])
        messages = arguments["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertIn("You are guard", messages[0]["content"])
        self.assertEqual(len(expected_history), 10)
        self.assertEqual(messages[1:-1], expected_history)
        self.assertEqual(
            messages[-1], {"role": "user", "content": "What did we discuss?"}
        )

    def test_next_request_uses_previously_saved_exchange(self):
        self.assertEqual(self.post_chat("Remember my name.").status_code, 200)
        saved = self.history()
        self.assertEqual(self.post_chat("Hello again").status_code, 200)
        self.assertEqual(self.llm_chat.await_args.kwargs["messages"][1:-1], saved)

    def test_failed_llm_requests_do_not_save_messages(self):
        self.post_chat("Existing conversation")
        before = self.history()
        for error in (
            httpx.ConnectError("Ollama is unavailable"),
            ResponseError("Model unavailable", status_code=404),
        ):
            with self.subTest(error=type(error).__name__):
                self.llm_chat.side_effect = error
                response = self.post_chat("This should not be stored")
                self.assertEqual(response.status_code, 502)
                self.assertEqual(self.history(), before)

    def test_missing_reply_does_not_save_messages(self):
        self.llm_chat.return_value.message.content = None
        self.assertEqual(self.post_chat().status_code, 502)
        self.assertEqual(self.history(), [])

    def test_missing_request_fields_are_still_rejected(self):
        response = self.client.post("/chat", json={"message": "Hello"})
        self.assertEqual(response.status_code, 422)
        self.llm_chat.assert_not_awaited()


if __name__ == "__main__":
    unittest.main()
