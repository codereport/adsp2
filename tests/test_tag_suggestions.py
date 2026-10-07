from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

import generate_episodes as generator
import suggest_tags as suggester


def episode(number=1, tags=(), cohost="Bryce", guest_people=()):
    return {
        "number": number, "title": "Test episode", "tag_values": tags,
        "buzzsprout_id": str(100 + number), "cohost": cohost,
        "guest_people": guest_people,
    }


def turn(text, speaker="Conor", start=0):
    return {"text": text, "speaker": speaker, "start": start}


def tags(report, group="existing_suggestions"):
    return {item["tag"] for item in report[group]}


class TagSuggestionTests(unittest.TestCase):
    def suggest(self, turns, current=(), archive=(), metadata=None, **kwargs):
        selected = episode(tags=current)
        return suggester.suggest_tags(
            selected, turns, [selected, episode(2, archive)], metadata, **kwargs,
        )

    def test_archive_spelling_and_significant_punctuation_are_preserved(self):
        names, counts = suggester.tag_catalog([
            episode(tags=("Algorithms", "C", "C++", "C#")),
            episode(2, ("Algorithms", "algorithms", "c++")),
        ])
        self.assertEqual(names["algorithms"], "Algorithms")
        self.assertEqual(counts["algorithms"], 2)
        self.assertEqual(set(names), {"algorithms", "c", "c++", "c#"})

    def test_spoken_language_names_and_versions_do_not_trigger_c(self):
        report = self.suggest([
            turn("Written in C++20. Programming in C plus plus. Written in C plus plus. Coding in C sharp. C# is different."),
        ], archive=("C", "C++", "C#"))
        self.assertEqual(tags(report), {"C++", "C#"})

    def test_ordinary_go_and_single_letters_need_language_context(self):
        archive = ("Go", "C", "D", "J", "K", "Q", "R", "Val", "Circle")
        ordinary = "Go home, go away. Plan B. C? D? J? K? Q? R? Val was walking in a circle."
        self.assertFalse(tags(self.suggest([turn(ordinary)] * 2, archive=archive)))
        report = self.suggest([turn("Written in Go. Programming in Go. The C language and the C compiler.")], archive=archive)
        self.assertEqual(tags(report), {"Go", "C"})

    def test_c_plus_plus_asr_standard_numbers_are_not_c_evidence(self):
        report = self.suggest([turn("C17 std reduce and C23 ranges, with C17 std accumulate.")], archive=("C",))
        self.assertFalse(tags(report))

    def test_ai_aliases_and_transcript_whitespace(self):
        report = self.suggest([
            turn("ChatGPT 5.6 and GPT-5.5, Open\n AI, and Chat\n GPT. Claude Opus and Anthropic Sonnet. Cursor and cursor."),
        ], archive=("codex", "claude", "cursor"))
        self.assertEqual(tags(report), {"codex", "claude", "cursor"})
        codex = next(item for item in report["existing_suggestions"] if item["tag"] == "codex")
        self.assertEqual(codex["mentions"], 4)

    def test_false_ai_substrings_do_not_match(self):
        report = self.suggest([turn("Corpus, sonnets, a cursory precodex example, and agpt." * 2)], archive=("codex", "claude", "cursor"))
        self.assertFalse(tags(report))

    def test_alias_context_distinguishes_windows_pascal_and_java(self):
        report = self.suggest([
            turn("There are windows in the room; windows everywhere. Pascal P620 GPU and Pascal GPU. Java Script and Java script."),
        ], archive=("Pascal", "Java", "JavaScript"))
        self.assertEqual(tags(report), {"JavaScript"})
        self.assertNotIn("Windows", tags(report, "new_suggestions"))
        report = self.suggest([turn("Windows 11 and WSL2. The Pascal language and Pascal code.")], archive=("Pascal",))
        self.assertIn("Pascal", tags(report))
        self.assertIn("Windows", tags(report, "new_suggestions"))

    def test_current_tags_are_not_proposed_again(self):
        report = self.suggest([turn("GPT GPT and Python Python.")], current=("Codex", "PYTHON"), archive=("codex", "Python"))
        self.assertFalse(tags(report))
        self.assertEqual(set(report["matched_current_tags"]), {"Codex", "PYTHON"})

    def test_mentions_and_evidence_are_attributed_to_turn_starts(self):
        report = self.suggest([
            turn("We use Python here.", start=73),
            turn("Python runs this script. Python is helpful.", speaker="Bryce", start=3700),
        ], archive=("Python",))
        item = report["existing_suggestions"][0]
        self.assertEqual(item["mentions"], 3)
        self.assertEqual(item["turns"], 2)
        self.assertEqual([entry["timestamp"] for entry in item["evidence"]], ["01:13", "1:01:40"])
        self.assertEqual(item["evidence"][1]["speaker"], "Bryce")
        self.assertIn("Python", item["evidence"][0]["excerpt"])

    def test_mention_threshold_and_separate_new_tag_limits(self):
        turns = [turn("Rust. Python Python Python. Computer use and browser automation. LLVM LLVM LLVM.")]
        report = self.suggest(turns, archive=("Python", "Rust"), limit=1, new_limit=1)
        self.assertEqual(tags(report), {"Python"})
        self.assertEqual(tags(report, "new_suggestions"), {"LLVM"})
        report = self.suggest(turns, archive=("Python", "Rust"), min_mentions=1)
        self.assertIn("Rust", tags(report))
        self.assertIn("Computer Use", tags(report, "new_suggestions"))

    def test_existing_topic_takes_precedence_over_a_new_candidate(self):
        report = self.suggest([turn("Unit tests and unit testing.")], archive=("testing",))
        self.assertEqual(tags(report), {"testing"})
        self.assertNotIn("Testing", tags(report, "new_suggestions"))

    def test_guest_names_require_speakers_and_reuse_aliases(self):
        metadata = {"guests": {"Douglas Gregor": {}, "Sean Parent": {}}}
        report = self.suggest([
            turn("Sean Parent and Sean Parent are mentioned here."),
            turn("I work on compilers.", speaker="Douglas Gregor"),
            turn("I work on algorithms.", speaker="Sean Parent (Clip)"),
            turn("Hello.", speaker="AI Host 1"),
            turn("Hello.", speaker="MYSTERY SPEAKER"),
        ], archive=("Guest", "Doug Gregor", "Sean Parent", "AI Host 1"), metadata=metadata)
        self.assertEqual(tags(report), {"Guest", "Doug Gregor"})
        self.assertEqual(tags(report, "new_suggestions"), {"MYSTERY SPEAKER"})
        guest = next(item for item in report["existing_suggestions"] if item["tag"] == "Doug Gregor")
        self.assertEqual(guest["confidence"], "high")
        self.assertEqual(guest["turns"], 1)

    def test_ben_cohost_is_not_suggested_as_a_guest(self):
        selected = episode(cohost="Ben")
        turns = [turn("Hello", speaker="Ben Deane"), turn("Hello", speaker="Conor")]
        report = suggester.suggest_tags(selected, turns, [selected, episode(2, ("Ben Deane", "Guest"))], {"guests": {"Ben Deane": {}}})
        self.assertFalse(tags(report))
        selected["cohost"] = "Bryce"
        report = suggester.suggest_tags(selected, turns, [selected, episode(2, ("Ben Deane", "Guest"))], {"guests": {"Ben Deane": {}}})
        self.assertEqual(tags(report), {"Ben Deane", "Guest"})

    def test_existing_guests_tag_does_not_add_singular_guest(self):
        report = self.suggest(
            [turn("Hello", speaker="Shima")],
            current=("Guests", "Shima"), archive=("Guest",),
        )
        self.assertFalse(tags(report))
        self.assertFalse(tags(report, "new_suggestions"))

    def test_offline_cli_prints_json_without_fetching_or_writing(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            posts = root / "_posts"
            posts.mkdir()
            path = posts / "2026-01-01-Episode-1.md"
            content = '---\nlayout: post\ntitle: "Episode 1: Test"\ntags: [Python]\nbuzzsprout-id: 101\n---\nKeep these notes.\n'
            path.write_text(content)
            transcript = root / "transcript.html"
            html = '<cite>Conor</cite><time>1:23</time><p>Computer use and browser automation.</p>'
            transcript.write_text(html)
            output = io.StringIO()
            with (
                patch.object(generator, "POSTS_DIR", posts),
                patch.object(suggester, "read_guest_metadata", return_value={}),
                patch.object(suggester, "fetch_transcript") as fetch,
                redirect_stdout(output),
            ):
                self.assertEqual(suggester.main(["1", "--transcript-file", str(transcript), "--json"]), 0)
            fetch.assert_not_called()
            report = json.loads(output.getvalue())
            self.assertEqual(report["episode"], 1)
            self.assertEqual(tags(report, "new_suggestions"), {"Computer Use"})
            self.assertEqual(path.read_text(), content)
            self.assertEqual(transcript.read_text(), html)
            self.assertEqual(set(root.iterdir()), {posts, transcript})

    def test_unknown_episode_fails_before_a_network_request(self):
        error = io.StringIO()
        with patch.object(suggester, "read_posts", return_value=[episode()]), patch.object(suggester, "fetch_transcript") as fetch, redirect_stderr(error):
            self.assertEqual(suggester.main(["999"]), 1)
        fetch.assert_not_called()
        self.assertIn("episode 999 does not exist", error.getvalue())

    def test_missing_transcript_and_server_errors_are_actionable(self):
        for code, message in ((404, "no published transcript"), (502, "try again or use --transcript-file")):
            with self.subTest(code=code), patch.object(suggester, "urlopen", side_effect=HTTPError("https://example.com", code, "error", None, None)):
                with self.assertRaisesRegex(ValueError, message):
                    suggester.fetch_transcript(episode())


if __name__ == "__main__":
    unittest.main()
