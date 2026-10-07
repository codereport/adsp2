from contextlib import redirect_stdout
import io
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import generate_episodes as generator
import reorder_logos
import update_topic_tags as updater


def post(title="Test", notes="", tags="[AI, C++, 'Jonathan O''Connor']", extra=""):
    return (
        f'---\nlayout: post\ntitle: "Episode 1: {title}"\ntags: {tags}\n'
        "buzzsprout-id: 100\n---\n\n"
        + extra + "\n### Show Notes\n" + notes + "\n### Intro Song Info\nA song.\n"
    )


class TopicTagTests(unittest.TestCase):
    def test_each_requested_keyword_matches_case_insensitively(self):
        for tag, words in {
            "codex": ("Codex", "OpenAI", "GPT", "GPT-4o", "GPT5", "ChatGPT", "GPTDuck"),
            "claude": ("Claude", "Anthropic", "Opus", "Sonnet"),
            "cursor": ("Cursor",),
        }.items():
            for word in words:
                with self.subTest(tag=tag, word=word):
                    self.assertIn(tag, updater.topic_tags(post(title=word.swapcase())))
                    self.assertIn(tag, updater.topic_tags(post(notes=word.swapcase())))

    def test_urls_and_nested_show_notes_are_matched(self):
        original = post(notes='#### Links\n* [Docs](https://platform.openai.com/docs)\n* [Editor](https://cursor.com/)\n* [Models](https://anthropic.com/sonnet)')
        self.assertEqual(updater.topic_tags(original), ["codex", "claude", "cursor"])

    def test_other_sections_and_existing_tags_do_not_trigger_matches(self):
        original = post(
            extra='A biography mentioning OpenAI, Claude, and Cursor.\n',
            tags='[AI, codex, claude, cursor]',
        ).replace('A song.', 'A song mentioning GPT, Opus, and Cursor.')
        self.assertEqual(updater.topic_tags(original), [])

    def test_unrelated_substrings_do_not_trigger_matches(self):
        self.assertEqual(updater.topic_tags(post(title='Corpus, sonnets, and cursory precodex examples')), [])

    def test_legacy_thrust_rules_still_apply(self):
        self.assertEqual(updater.topic_tags(post(extra='thrust::transform in the introduction')), ["Thrust", "CUDA"])
        self.assertEqual(updater.topic_tags(post(tags='[Thrust]')), ["CUDA"])
        updated = updater.updated_post(post(tags='[Thrust, CUDA]', notes='GPT'))
        self.assertEqual(generator.post_tag_values(updated), ("Thrust", "CUDA", "codex"))

    def test_guest_tags_front_matter_and_body_are_preserved(self):
        original = post(notes='Codex, Claude, Cursor')
        updated = updater.updated_post(original)
        self.assertEqual(generator.post_tag_values(updated), ("AI", "C++", "Jonathan O'Connor", "codex", "claude", "cursor"))
        self.assertEqual(original.split('---', 2)[2], updated.split('---', 2)[2])
        self.assertEqual([line for line in original.splitlines() if not line.startswith('tags:')],
                         [line for line in updated.splitlines() if not line.startswith('tags:')])
        self.assertEqual(updater.updated_post(updated), updated)

    def test_ai_tag_case_is_normalized_and_duplicates_are_removed(self):
        original = post(tags='[Claude, claude, Codex, Cursor, "Jonathan O\'Connor", CUDA]')
        updated = updater.updated_post(original)
        self.assertEqual(generator.post_tag_values(updated), ("claude", "codex", "cursor", "Jonathan O'Connor", "CUDA"))
        self.assertEqual(updater.updated_post(updated), updated)

    def test_missing_tags_and_show_notes_are_supported(self):
        original = post(title='Opus and GPT').replace("tags: [AI, C++, 'Jonathan O''Connor']\n", '').replace('### Show Notes', '### Other Section')
        self.assertEqual(generator.post_tag_values(updater.updated_post(original)), ("codex", "claude"))

    def test_check_mode_does_not_write_and_normal_run_is_repeatable(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            path = folder / '2026-01-01-Episode-1.md'
            path.write_text(post(title='Codex'))
            original = path.read_text()
            with patch.object(updater, 'POSTS_DIR', folder), redirect_stdout(io.StringIO()):
                with patch('sys.argv', ['update_topic_tags.py', '--check']):
                    self.assertEqual(updater.main(), 1)
                self.assertEqual(path.read_text(), original)
                with patch('sys.argv', ['update_topic_tags.py']):
                    self.assertEqual(updater.main(), 0)
                updated = path.read_text()
                with patch('sys.argv', ['update_topic_tags.py', '--check']):
                    self.assertEqual(updater.main(), 0)
                self.assertEqual(path.read_text(), updated)

    def test_logo_counter_reads_quoted_tags_once_per_episode(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            (folder/'2026-01-01-Episode-1.md').write_text(post(tags='["codex", "codex", "claude", CUDA, "Guest, with comma"]'))
            with patch.object(reorder_logos, 'POSTS_DIR', folder):
                counts = reorder_logos.count_tags_in_posts()
            self.assertEqual(dict(counts), {"codex": 1, "claude": 1, "CUDA": 1})

    def test_logo_links_use_the_current_site(self):
        for name in ('codex', 'claude', 'cursor', 'C++'):
            with self.subTest(name=name):
                markup = reorder_logos.generate_logo_html(name, reorder_logos.TECHNOLOGIES[name])
                self.assertIn("href=\"{{ '/tags/' | relative_url }}#", markup)
                self.assertNotIn('https://adspthepodcast.com', markup)

    def test_gpt_titles_in_the_archive_all_have_codex_tags(self):
        episodes = {episode['number']: episode for episode in generator.read_posts()}
        for number in (114, 122, 127, 291, 295):
            with self.subTest(number=number):
                self.assertIn('codex', episodes[number]['tag_values'])


if __name__ == '__main__':
    unittest.main()
