from pathlib import Path
import unittest

from silt_relay import Archive, DATA


class ArchiveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = Archive.from_directory(DATA)
        cls.addClassCleanup(cls.archive.close)

    def test_answer_is_exact_source_text(self):
        result = self.archive.answer("When did SR004 come out?")
        self.assertEqual(result["outcome"], "answered")
        claim, = result["claims"]
        self.assertEqual(claim["source_id"], "SR004:date")
        self.assertEqual(claim["text"], self.archive.passages[claim["source_id"]].text)
        self.assertIn(claim["source_id"], {row["id"] for row in result["retrieved"]})

    def test_partial_answer_does_not_turn_a_proposal_into_a_shipment(self):
        result = self.archive.answer("When did Glass Current come out, and did the vinyl ship?")
        self.assertEqual(result["outcome"], "partially_answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:date"])
        self.assertTrue(result["unanswered"])

    def test_unrecognised_second_title_does_not_inherit_first_release(self):
        result = self.archive.answer("When did SR004 come out, and who made Sunken Semaphore?")
        self.assertEqual(result["outcome"], "partially_answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:date"])

    def test_followup_track_list_inherits_the_single_named_release(self):
        question = "When did Glass Current come out, and what is the track list?"
        result = self.archive.answer(question)
        self.assertEqual(result["outcome"], "answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:date", "SR004:tracks"])
        self.assertFalse(result["unanswered"])

    def test_track_list_for_unknown_release_does_not_inherit_context(self):
        question = "When did Glass Current come out, and what is the track list for Sunken Semaphore?"
        result = self.archive.answer(question)
        self.assertEqual(result["outcome"], "partially_answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:date"])

    def test_followup_pronoun_can_inherit_single_release(self):
        result = self.archive.answer("When did SR004 come out, and what format was it?")
        self.assertEqual(result["outcome"], "answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:date", "SR004:format"])

    def test_same_base_title_requires_clarification(self):
        result = self.archive.answer("When was Basin Window released?")
        self.assertEqual(result["outcome"], "needs_clarification")
        self.assertEqual([row["code"] for row in result["choices"]], ["SR007", "SR011"])
        self.assertFalse(result["claims"])

    def test_unknown_fact_and_unknown_title_abstain(self):
        for question in ("How many copies did SR004 sell?", "When did Sunken Semaphore come out?"):
            with self.subTest(question=question):
                result = self.archive.answer(question)
                self.assertEqual(result["outcome"], "insufficient_evidence")
                self.assertFalse(result["claims"])

    def test_plural_tracklists_can_span_two_releases(self):
        result = self.archive.answer("What are the tracklists for SR006 and SR017?")
        self.assertEqual(result["outcome"], "answered")
        self.assertEqual({claim["source_id"] for claim in result["claims"]}, {"SR006:tracks", "SR017:tracks"})

    def test_digital_release_date_does_not_answer_vinyl_date(self):
        result = self.archive.answer("When did Glass Current come out on vinyl?")
        self.assertEqual(result["outcome"], "insufficient_evidence")
        self.assertFalse(result["claims"])

    def test_date_for_narrower_scope_is_withheld(self):
        questions = (
            "When was the Glass Current vinyl released?",
            "When was the Glass Current 12-inch released?",
            "When was Glass Current released in the US?",
            "When did Shear Line from Glass Current come out?",
        )
        for question in questions:
            with self.subTest(question=question):
                result = self.archive.answer(question)
                self.assertEqual(result["outcome"], "insufficient_evidence")
                self.assertFalse(result["claims"])

    def test_mixed_code_and_title_are_both_resolved(self):
        result = self.archive.answer("Compare the formats of SR003 and After the Gauge.")
        self.assertEqual({claim["source_id"] for claim in result["claims"]}, {"SR003:format", "SR009:format"})

    def test_unknown_comparison_target_is_withheld(self):
        result = self.archive.answer("Compare the tracklists for SR004 and Sunken Semaphore.")
        self.assertEqual(result["outcome"], "partially_answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR004:tracks"])

    def test_fields_attach_to_their_own_releases(self):
        for question in (
            "Compare the date of SR004 with the tracklist of SR005.",
            "When did Glass Current come out? What tracks were on Glass Currents?",
        ):
            with self.subTest(question=question):
                result = self.archive.answer(question)
                self.assertEqual(result["outcome"], "answered")
                self.assertEqual({claim["source_id"] for claim in result["claims"]}, {"SR004:date", "SR005:tracks"})

    def test_catalogue_number_can_disambiguate_a_title(self):
        result = self.archive.answer("When was Basin Window released (SR007)?")
        self.assertEqual(result["outcome"], "answered")
        self.assertEqual([claim["source_id"] for claim in result["claims"]], ["SR007:date"])

    def test_two_exact_codes_can_be_answered_together(self):
        result = self.archive.answer("Compare the formats of SR003 and SR009.")
        self.assertEqual(result["outcome"], "answered")
        self.assertEqual({claim["source_id"] for claim in result["claims"]}, {"SR003:format", "SR009:format"})

    def test_similar_title_does_not_attach_wrong_record(self):
        result = self.archive.answer("Who made Glass Currents?")
        self.assertEqual(result["claims"][0]["source_id"], "SR005:credits")

    def test_fts_input_is_literal_and_bounded(self):
        self.assertEqual(self.archive.search('"\"* OR :)', "bm25"), [])
        with self.assertRaises(ValueError):
            self.archive.answer("a" * 401)

    def test_semantic_retrieval_is_independent_of_fts(self):
        hits = self.archive.search("horns and echoes", "semantic")
        self.assertTrue(hits)
        self.assertTrue(all(hit["semantic_rank"] is not None and hit["bm25_rank"] is None for hit in hits))

    def test_every_release_has_a_unique_code(self):
        self.assertEqual(len(self.archive.releases), 21)
        self.assertEqual(len(self.archive.releases), len({p.code for p in self.archive.passages.values()}))
        self.assertTrue(Path(DATA, "releases.json").exists())


if __name__ == "__main__":
    unittest.main()
