import hashlib
import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from memory_store import init_db, inspect_chat_context, save_conversation
from retention_policy import personal_evidence
from summary_audit import audit_summary
from summary_store import get_summary, init_summary_schema, prepare_summary_batch, publish_summary_batch, summary_context


class PersonalEvidenceTests(unittest.TestCase):
    def test_general_questions_and_world_topics_are_not_personal_facts(self):
        for text in ["Is there a blacksmith in this village?", "Where is the inn?",
                     "Tell me about the village's history.", "Can you tell me where the healer is?",
                     "How old is this village?", "The sunrise looks bright."]:
            with self.subTest(text=text):
                self.assertFalse(personal_evidence(text).eligible)

    def test_first_person_or_possessive_words_alone_do_not_make_a_fact(self):
        for text in ["I wonder if there is a blacksmith.", "I have a question about the village.",
                     "I was wondering whether a blacksmith lives here.",
                     "I have been wondering where the inn is.",
                     "I'd like to know where the inn is.", "My question is whether a healer lives here.",
                     "I am not sure where the market is.", "I asked about the village's history."]:
            with self.subTest(text=text):
                self.assertFalse(personal_evidence(text).eligible)

    def test_explicit_facts_preferences_relationships_locations_and_events(self):
        for text in ["My name is Mira.", "I prefer tea.", "I do not like coffee.",
                     "My sister's name is Emily.", "I live near the old market.",
                     "I witnessed a fire last winter.", "I won the archery contest.",
                     "Tea is my favorite drink.", "The blacksmith is my brother.",
                     "A healer saved my life last winter.", "An archer taught me a new skill.",
                     "I am from Riverford.",
                     "Actually, I prefer water now."]:
            with self.subTest(text=text):
                assessment = personal_evidence(text)
                self.assertTrue(assessment.eligible)
                self.assertTrue(all(statement in text for statement in assessment.statements))

    def test_conversational_and_question_like_explicit_facts_are_kept(self):
        for text, fact in [
            ("Did I mention that my sister's name is Emily?", "my sister's name is Emily"),
            ("Did I tell you I live near the old market?", "I live near the old market"),
            ("Can you remember that I prefer tea?", "I prefer tea"),
            ("Do you know that I won the archery contest?", "I won the archery contest"),
            ("I prefer tea, remember?", "I prefer tea"),
            ("Can you recommend a shop, since I live near the river?", "I live near the river"),
            ("Can you help my sister Emily?", "my sister Emily"),
            ("What shops are close to my home in Riverford?", "my home in Riverford"),
        ]:
            with self.subTest(text=text):
                assessment = personal_evidence(text)
                self.assertTrue(assessment.eligible)
                self.assertIn(fact, assessment.statements)

    def test_unknown_values_confirmation_questions_and_hypotheticals_are_not_assertions(self):
        for text in ["Where do I live?", "What is my sister's name?", "Is my sister's name Emily?",
                     "Do I prefer tea?", "Do you remember if I prefer tea?",
                     "Did I mention whether I prefer tea?", "If I prefer tea, would you remember?",
                     "It is not true that I prefer tea.", "I never said I live by the river.",
                     "What if I lived near the old market?", "I like tea. Just kidding."]:
            with self.subTest(text=text):
                self.assertFalse(personal_evidence(text).eligible)

    def test_mixed_message_keeps_personal_clause_without_promoting_general_question(self):
        assessment = personal_evidence("Is there a blacksmith? My sister's name is Emily.")
        self.assertEqual(assessment.statements, ("My sister's name is Emily.",))

    def test_uncertainty_in_another_sentence_does_not_erase_a_clear_fact(self):
        text = "I prefer tea. I am not sure if a blacksmith lives here."
        self.assertEqual(personal_evidence(text).statements, ("I prefer tea.",))

    def test_common_name_abbreviation_is_not_truncated(self):
        text = "My sister's name is Dr. Emily Stone."
        self.assertEqual(personal_evidence(text).statements, (text,))


class RetentionPublicationTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.db_path = Path(temporary.name) / "memory.sqlite3"
        init_db(self.db_path)
        init_summary_schema(self.db_path)

    def seed(self, messages):
        for text in messages:
            save_conversation("karan", "Arthur", text, "Acknowledged.", self.db_path)
        for index in range(6):
            save_conversation("karan", "Arthur", f"Weather discussion {index}", "Clear skies.", self.db_path)

    def test_model_labels_cannot_authorize_general_question_and_cannot_drop_clear_fact(self):
        question = "Is there a blacksmith in this village?"
        fact = "Did I mention that my sister's name is Emily?"
        self.seed([question, fact])
        batch = prepare_summary_batch("karan", "Arthur", self.db_path)
        decisions = [{"message_id": source["message_id"],
                      "category": "location" if source["message_id"] == 1 else "ignore"}
                     for source in batch["sources"]]
        saved = publish_summary_batch(batch, decisions, "qwen3:8b", self.db_path)
        self.assertEqual([e["source_message_id"] for e in saved["entries"]], [3])
        self.assertEqual(saved["entries"][0]["statement"], fact)
        self.assertEqual(saved["entries"][0]["category"], "relationship")
        self.assertEqual(prepare_summary_batch("karan", "Arthur", self.db_path)["sources"], [])

    def test_legacy_invalid_row_stays_stored_but_is_flagged_and_excluded_without_writes(self):
        question = "Is there a blacksmith in this village?"
        self.seed([question])
        # Reconstruct a pre-fix, structurally valid row in this disposable DB.
        with closing(sqlite3.connect(self.db_path)) as connection, connection:
            connection.execute("INSERT INTO memory_summary_state VALUES ('karan','Arthur',1,3,'created','updated','qwen3:8b',1)")
            connection.execute("INSERT INTO memory_summary_entries VALUES ('karan','Arthur',1,?,'location',?,1,'created')",
                               (question, hashlib.sha256(question.encode()).hexdigest()))
        before = self.db_path.read_bytes()
        saved = get_summary("karan", "Arthur", self.db_path)
        self.assertEqual(saved["entries"][0]["statement"], question)
        self.assertIsNone(summary_context(saved))
        audit = audit_summary("karan", "Arthur", self.db_path)
        self.assertFalse(audit["storage_changed"])
        self.assertFalse(audit["entries"][0]["eligible_for_personal_context"])
        data = inspect_chat_context("karan", "Arthur", "What do you remember about me?",
                                    self.db_path, include_summary=True)
        self.assertEqual(data["saved_summary"]["entries"][0]["source_message_id"], 1)
        self.assertIsNone(data["summary_context"])
        self.assertFalse(data["summary_retention_review"][0]["eligible_for_personal_context"])
        self.assertEqual(self.db_path.read_bytes(), before)

    def test_read_only_audit_never_creates_a_missing_database(self):
        missing = self.db_path.with_name("missing.sqlite3")
        with self.assertRaises(sqlite3.OperationalError):
            audit_summary("karan", "Arthur", missing)
        self.assertFalse(missing.exists())


if __name__ == "__main__":
    unittest.main()
