from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_episodes as generator


def post(number=0, tags="[C++, CUDA]", body="<br>In this episode, Conor and Bryce chat.\n"):
    return (
        "---\nlayout: post\n"
        f'title: "Episode {number}: Test"\n'
        f"tags: {tags}\nbuzzsprout-id: {number + 100}\n---\n\n{body}"
    )


class GuestTagTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.posts = self.root / "_posts"
        self.posts.mkdir()
        self.patch_posts = patch.object(generator, "POSTS_DIR", self.posts)
        self.patch_posts.start()
        self.addCleanup(self.patch_posts.stop)

    def write_post(self, number=0, **kwargs):
        path = self.posts / f"2026-01-01-Episode-{number}.md"
        path.write_text(post(number, **kwargs))
        return path

    def test_guest_tags_preserve_topics_body_and_front_matter(self):
        path = self.write_post(body="tags: [A body example]\nKeep the show notes.\n")
        episodes = generator.read_posts()
        metrics = generator.transcript_indices(episodes[0], "".join(
            f"<cite>{name}</cite><time>0:00</time><p>Some words.</p>"
            for name in ("Conor", "Bryce", "Shima", "Ramona", "Sean Parent (Clip)", "AI Host 1", "MYSTERY SPEAKER")
        ))
        original = path.read_text()
        updates = generator.guest_tag_updates(episodes, {0: metrics})
        self.assertEqual(path.read_text(), original)
        self.assertEqual(generator.post_tag_values(updates[path]), ("C++", "CUDA", "Shima", "Ramona", "MYSTERY SPEAKER"))
        self.assertEqual(updates[path].split("---", 2)[2], original.split("---", 2)[2])
        self.assertEqual(updates[path].splitlines()[1:3], original.splitlines()[1:3])

    def test_existing_alias_is_reused_across_episodes_without_duplicates(self):
        self.write_post(0, tags="[Guest, Doug Gregor]")
        second = self.write_post(1)
        episodes = generator.read_posts()
        stats = {n: {"guest_people": (("name:douglas gregor", "Douglas Gregor", ""),)} for n in (0, 1)}
        updates = generator.guest_tag_updates(episodes, stats)
        self.assertEqual(list(updates), [second])
        self.assertIn("Doug Gregor", generator.post_tag_values(updates[second]))
        self.assertNotIn("Douglas Gregor", generator.post_tag_values(updates[second]))
        self.assertFalse(generator.guest_tag_updates(generator.read_posts(updates), stats))

    def test_guest_tag_alias_and_capitalization_are_not_duplicated(self):
        self.write_post(tags="[Guest, Rob Leahy, koen poppe]")
        episodes = generator.read_posts()
        stats = {0: {"guest_people": (("name:robert leahy", "Robert Leahy", ""), ("name:koen poppe", "Koen Poppe", ""))}}
        self.assertFalse(generator.guest_tag_updates(episodes, stats))

    def test_notes_without_a_transcript_do_not_add_guest_tags(self):
        self.write_post(body="**About the Guest:**\n\n[Shima](https://example.com) is a guest.\n")
        self.assertFalse(generator.guest_tag_updates(generator.read_posts(), {}))

    def test_punctuation_and_unicode_round_trip_as_yaml_strings(self):
        names = ("Jonathan O'Connor", 'Guest, with "quotes"', "Andor Pénzes", "Name: with colon")
        original = post(tags="['C++', CUDA]")
        updated = generator.add_post_tags(original, names)
        self.assertEqual(generator.post_tag_values(updated), ("C++", "CUDA") + names)

    def test_empty_or_missing_tag_line_and_comments(self):
        for original in (post(tags="[]"), post().replace("tags: [C++, CUDA]\n", "")):
            with self.subTest(original=original):
                updated = generator.add_post_tags(original, ("Shima",))
                self.assertEqual(generator.post_tag_values(updated), ("Shima",))
        original = post(tags="[C++, CUDA] # Keep this comment")
        updated = generator.add_post_tags(original, ("Shima",))
        self.assertIn('# Keep this comment\n', updated)
        self.assertEqual(generator.post_tag_values(updated), ("C++", "CUDA", "Shima"))

    def test_unsupported_tag_format_is_rejected_without_writing(self):
        path = self.write_post(tags="\n  - C++")
        original = path.read_text()
        stats = {0: {"guest_people": (("name:shima", "Shima", ""),)}}
        with self.assertRaisesRegex(ValueError, "inline YAML list"):
            generator.guest_tag_updates(generator.read_posts(), stats)
        self.assertEqual(path.read_text(), original)

    def test_check_mode_detects_missing_tags_without_modifying_files(self):
        path = self.write_post()
        original = path.read_text()
        page = self.root / "episodes.md"
        page.write_text(generator.GENERATED_START + "\n" + generator.GENERATED_END + "\n")
        company_path = self.root / "companies.json"
        transcripts_path = self.root / "transcripts.json"
        metadata = {"guests": {}, "guests_by_name": {}, "companies": {}, "languages": {}, "featured_companies": []}
        metrics = generator.transcript_indices(generator.read_posts()[0], '<cite>Conor</cite><time>0:00</time><p>Hello.</p><cite>Shima</cite><time>0:01</time><p>Hello.</p>')
        with (
            patch.object(generator, "EPISODES_PAGE", page),
            patch.object(generator, "COMPANY_EPISODES_PATH", company_path),
            patch.object(generator, "TRANSCRIPTS_PATH", transcripts_path),
            patch.object(generator, "read_guest_metadata", return_value=metadata),
            patch.object(generator, "read_feed_root", return_value=None),
            patch.object(generator, "read_durations", return_value={0: 1200}),
            patch.object(generator, "read_transcript_indices", return_value={0: metrics}),
            patch("sys.argv", ["generate_episodes.py", "--check"]),
            redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(generator.main(), 1)
        self.assertEqual(path.read_text(), original)
        self.assertEqual(page.read_text(), generator.GENERATED_START + "\n" + generator.GENERATED_END + "\n")
        self.assertFalse(company_path.exists())
        self.assertFalse(transcripts_path.exists())


if __name__ == "__main__":
    unittest.main()
