import unittest

from reply_safety import evidence_statements, safe_memory_reply


class ReplySafetyTests(unittest.TestCase):
    def test_exact_first_person_copy_is_attributed_without_changing_the_fact(self):
        statement = "I study astronomy."
        self.assertEqual(safe_memory_reply(statement, "What do I study?", [statement]),
                         'You previously said: “I study astronomy.”')

    def test_copy_of_current_user_statement_is_also_attributed(self):
        self.assertEqual(safe_memory_reply("I study astronomy.", "I study astronomy.", []),
                         'You previously said: “I study astronomy.”')

    def test_exact_copy_with_player_as_object_is_attributed(self):
        statement = "A ranger taught me tracking."
        self.assertEqual(safe_memory_reply(statement, "What happened to me?", [statement]),
                         'You previously said: “A ranger taught me tracking.”')

    def test_legitimate_npc_first_person_is_not_rewritten(self):
        self.assertEqual(safe_memory_reply("I patrol the gate.", "Hello", ["I study astronomy."]),
                         "I patrol the gate.")

    def test_unseen_values_are_quoted_instead_of_explained(self):
        claims = ["My favorite color is amber.", "My favorite color is violet."]
        answer = safe_memory_reply("Perhaps you enjoy both colors.", "What is my favorite color?", claims)
        for claim in claims:
            self.assertIn(claim, answer)
        self.assertIn("I'm not sure which is current", answer)
        self.assertNotIn("Perhaps", answer)

    def test_distinct_topics_and_unrelated_questions_do_not_trigger_conflict(self):
        claims = ["My favorite color is amber.", "My home is near the river."]
        self.assertEqual(safe_memory_reply("Your favorite color is amber.", "What is my favorite color?", claims),
                         "Your favorite color is amber.")
        claims.append("My favorite color is violet.")
        self.assertEqual(safe_memory_reply("It is sunny.", "How is the weather?", claims), "It is sunny.")

    def test_explicit_correction_can_supersede_older_simple_claims(self):
        claims = ["My favorite color is amber.", "My favorite color is violet.",
                  "Correction: my favorite color is green."]
        self.assertEqual(safe_memory_reply("Your favorite color is green.", "What is my favorite color?", claims),
                         "Your favorite color is green.")

    def test_plain_actually_correction_in_current_turn_does_not_trigger_old_conflict(self):
        claims = ["My favorite color is amber.", "My favorite color is violet."]
        self.assertEqual(safe_memory_reply("Noted.", "Actually my favorite color is blue.", claims), "Noted.")

    def test_question_is_not_mistaken_for_a_statement(self):
        self.assertEqual(safe_memory_reply("I don't know.", "My home is near the river?", ["My home is by the lake."]),
                         "I don't know.")

    def test_evidence_excludes_assistants_and_orders_older_sources(self):
        statements = evidence_statements(
            [{"role": "assistant", "content": "My favorite color is green."},
             {"role": "user", "content": "Correction: my favorite color is blue."}],
            [{"message_id": 1, "content": "My favorite color is amber."}],
            {"entries": [{"source_message_ids": [3], "statement": "My favorite color is violet."}]},
        )
        self.assertEqual(statements, ["My favorite color is amber.", "My favorite color is violet.",
                                      "Correction: my favorite color is blue."])

    def test_personal_overview_does_not_repeat_model_speaker_error_or_general_questions(self):
        reply = "I also recall asking about the village's history and the presence of a blacksmith."
        statements = ["Is there a blacksmith in this village?", "Tell me about the village's history.",
                      "My favorite color is amber.", "Did I mention that my sister's name is Mira?"]
        answer = safe_memory_reply(reply, "What do you remember about me?", statements)
        self.assertTrue(answer.startswith("Here are some things you've told me:"))
        self.assertIn("My favorite color is amber.", answer)
        self.assertIn("my sister's name is Mira", answer)
        self.assertNotIn("blacksmith", answer)
        self.assertNotIn("I also recall asking", answer)

    def test_personal_overview_with_only_questions_acknowledges_missing_facts(self):
        answer = safe_memory_reply("I asked about the market.", "What do you know about me?",
                                   ["Where is the market?", "Can you help me find an inn?"])
        self.assertEqual(answer, "I don't have that information in the available context.")

    def test_personal_overview_is_bounded_deduplicated_and_keeps_negation(self):
        statements = ["I do not like coffee."] * 3 + [f"My personal token is token{index}." for index in range(20)]
        answer = safe_memory_reply("A guess.", "Tell me what you know about me.", statements)
        self.assertEqual(answer.count("I do not like coffee."), 1)
        self.assertLessEqual(len(answer), 1400)
        self.assertLessEqual(answer.count("“"), 5)


if __name__ == "__main__":
    unittest.main()
