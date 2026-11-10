import unittest

from silt_relay import Archive, DATA, MODES


class CrateDiggingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.archive = Archive.from_directory(DATA)
        cls.addClassCleanup(cls.archive.close)

    def test_sound_query_finds_an_original_with_a_confirmed_vinyl_reissue(self):
        results = self.archive.dig("liquid electric piano", vinyl_only=True)["matches"]
        self.assertEqual([row["code"] for row in results], ["SR007"])
        match, = results
        self.assertEqual(match["sound"]["id"], "SR007:sound")
        self.assertEqual([source["id"] for source in match["format_sources"]], ["SR007:format", "SR011:format"])

    def test_searches_note_text_even_when_query_has_no_title(self):
        match, = self.archive.dig("muted brass and tape echo", vinyl_only=True)["matches"]
        self.assertEqual(match["code"], "SR003")
        self.assertEqual(match["format_sources"][0]["id"], "SR003:format")
        self.assertFalse(match["comparisons"])

    def test_proposed_vinyl_never_passes_the_confirmed_filter(self):
        matches = self.archive.dig("pitched-down bell")["matches"]
        match = next(row for row in matches if row["code"] == "SR004")
        self.assertEqual([source["id"] for source in match["proposed"]], ["SR004:edition"])
        for mode in MODES:
            result = self.archive.dig("pitched-down bell on vinyl", mode)
            self.assertEqual(result["matches"], [])
            proposal, = result["proposals"]
            self.assertEqual(proposal["sources"][0]["id"], "SR004:edition")

    def test_comparison_matches_either_code_and_cites_both_tracklists(self):
        by_original, = self.archive.editions("SR007")
        by_reissue, = self.archive.editions("sr011")
        self.assertEqual(by_original, by_reissue)
        self.assertEqual(by_original["added"], ["Night Ferry (Quay Dub)"])
        self.assertEqual(by_original["original_only"], [])
        self.assertEqual(by_original["original"]["tracks"]["id"], "SR007:tracks")
        self.assertEqual(by_original["reissue"]["tracks"]["id"], "SR011:tracks")
        self.assertIn("SR007", by_original["relationship"]["text"])

    def test_second_reissue_reports_additions_and_original_only_tracks(self):
        result, = self.archive.editions("SR001")
        self.assertEqual(result["added"], ["Wet Mark (Dubplate Mix)"])
        self.assertEqual(result["original_only"], ["Root Chamber"])
        self.assertEqual(result["reissue"]["tracks"]["id"], "SR021:tracks")

    def test_reissue_and_original_collapse_to_one_sound_match(self):
        for mode in MODES:
            with self.subTest(mode=mode):
                matches = self.archive.dig("electric piano", mode)["matches"]
                self.assertEqual(sum(row["code"] == "SR007" for row in matches), 1)

    def test_unknown_sound_and_unrelated_title_yield_no_keyword_match(self):
        self.assertEqual(self.archive.dig("tuba harmonica")["matches"], [])
        self.assertEqual(self.archive.dig("unknown title")["matches"], [])

    def test_legacy_lookup_does_not_cite_original_for_reissue_question(self):
        result = self.archive.answer("What tracks are on the Silt Thread reissue?")
        self.assertEqual(result["outcome"], "insufficient_evidence")
        self.assertEqual(result["claims"], [])

    def test_named_editions_can_be_compared_without_a_sound_description(self):
        result = self.archive.dig("What changed between Basin Window and Basin Window (2026 Recut)?")
        match, = result["matches"]
        self.assertEqual(match["code"], "SR007")
        self.assertEqual(match["comparisons"][0]["added"], ["Night Ferry (Quay Dub)"])

    def test_sound_match_cannot_satisfy_an_undocumented_format(self):
        result = self.archive.dig("Warbling chords on CD")
        self.assertEqual(result["formats"], ["cd"])
        self.assertEqual(result["matches"], [])

    def test_vinyl_size_is_a_format_constraint(self):
        self.assertEqual(self.archive.dig("electric piano on 10-inch vinyl")["matches"], [])
        match, = self.archive.dig("electric piano on 12-inch vinyl")["matches"]
        self.assertIn("12-inch vinyl", match["formats"])

    def test_reissues_only_excludes_original_only_families(self):
        result = self.archive.dig("Show vinyl reissues only")
        self.assertEqual({row["code"] for row in result["matches"]}, {"SR001", "SR007"})
        self.assertFalse(result["proposals"])

    def test_or_does_not_match_a_fragment_of_an_alternative(self):
        result = self.archive.dig("Find piano or warbling chords on vinyl or cassette.")
        self.assertEqual({row["code"] for row in result["matches"]}, {"SR007", "SR009"})
