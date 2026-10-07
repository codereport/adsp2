import copy
from pathlib import Path
import re
import shutil
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError
import xml.etree.ElementTree as ET

import generate_episodes as generator
import generate_transcripts as automation


TEMPLATE = "https://www.buzzsprout.com/admin/1501960/episodes/{episode_id}"
EPISODE = {"number": 257, "id": "18065465", "title": "Episode 257: Test", "published": False}


def feed(items):
    return ET.fromstring(
        '<rss xmlns:podcast="https://podcastindex.org/namespace/1.0"><channel>'
        + "".join(
            f'<item><guid>Buzzsprout-{episode_id}</guid>'
            + ('<podcast:transcript url="https://example.com/transcript"/>' if available else "")
            + "</item>"
            for episode_id, available in items
        ) + "</channel></rss>"
    )


class TranscriptDiscoveryTests(unittest.TestCase):
    def test_generator_discovers_older_transcripts_despite_stale_feed_and_skips_missing(self):
        episodes = [{"number": 0, "buzzsprout_id": "10"}, {"number": 300, "buzzsprout_id": "20"}]
        root = feed([("10", False), ("20", False)])
        response = unittest.mock.MagicMock()
        response.__enter__.return_value = response
        response.headers.get_content_charset.return_value = "utf-8"
        response.read.return_value = b"older transcript"
        def fetch_page(request, timeout):
            if request.full_url.endswith("/20/transcript"):
                raise HTTPError(request.full_url, 404, "not ready", {}, None)
            return response

        with patch.object(generator, "urlopen", side_effect=fetch_page) as fetch, patch.object(
            generator, "transcript_indices", return_value={"baf": 3}
        ):
            self.assertEqual(generator.read_transcript_indices(episodes, root), {0: {"baf": 3}})
        self.assertEqual(fetch.call_count, 2)

    def test_advertised_transcript_failures_are_not_silently_ignored(self):
        with patch.object(generator, "urlopen", side_effect=HTTPError("url", 500, "failure", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "Episode 0"):
                generator.read_transcript_indices([{"number": 0, "buzzsprout_id": "10"}], feed([("10", True)]))

    def test_advertised_404_is_an_error(self):
        with patch.object(generator, "urlopen", side_effect=HTTPError("url", 404, "missing", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "Episode 0"):
                generator.read_transcript_indices([{"number": 0, "buzzsprout_id": "10"}], feed([("10", True)]))

    def test_unadvertised_server_failure_is_an_error(self):
        with patch.object(generator, "urlopen", side_effect=HTTPError("url", 500, "failure", {}, None)):
            with self.assertRaisesRegex(RuntimeError, "Episode 0"):
                generator.read_transcript_indices([{"number": 0, "buzzsprout_id": "10"}], feed([("10", False)]))

    def test_resume_skips_published_queued_and_uncertain_jobs(self):
        episodes = [dict(EPISODE, id=str(i), published=i == 1) for i in range(1, 6)]
        state = {"episodes": {"2": {"status": "queued"}, "3": {"status": "attempting"}, "4": {"status": "blocked"}}}
        self.assertEqual([e["id"] for e in automation.pending_episodes(episodes, state)], ["4", "5"])
        self.assertEqual([e["id"] for e in automation.pending_episodes(episodes, state, True)], ["3", "4", "5"])

    def test_admin_url_discovery_and_host_restrictions(self):
        url = TEMPLATE.replace("{episode_id}", EPISODE["id"]) + "?ignored=1"
        self.assertEqual(automation.discover_template(url, {EPISODE["id"]}), TEMPLATE)
        slug_url = TEMPLATE.replace("{episode_id}", EPISODE["id"] + "-episode-257-test")
        self.assertEqual(automation.discover_template(slug_url, {EPISODE["id"]}), TEMPLATE)
        for invalid in (
            TEMPLATE.replace("https:", "http:"), TEMPLATE.replace("www.buzzsprout.com", "example.com"),
            TEMPLATE.replace("1501960", "9999"), TEMPLATE + "?token=secret",
            TEMPLATE.replace("{episode_id}", "{episode_id}-slug"),
        ):
            with self.subTest(url=invalid), self.assertRaises(ValueError):
                automation.validate_template(invalid)

    def test_repository_posts_have_unique_explicit_ids_and_no_duplicate_embeds(self):
        ids = []
        for post in generator.POSTS_DIR.glob("*Episode-*.md"):
            content = post.read_text()
            episode_id = generator.front_matter_value(content, "buzzsprout-id")
            self.assertTrue(episode_id.isdigit(), post.name)
            self.assertNotRegex(content, r"<div\s+id=[\"']buzzsprout-", post.name)
            ids.append(episode_id)
        self.assertEqual(len(ids), len(set(ids)))


try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


@unittest.skipUnless(sync_playwright and shutil.which("chromium"), "requires Playwright and Chromium")
class BrowserAutomationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(headless=True, executable_path=shutil.which("chromium"))

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self):
        self.context = self.browser.new_context()
        self.page = self.context.new_page()
        self.directory = tempfile.TemporaryDirectory()
        self.state = {"version": 1, "podcast_id": automation.PODCAST_ID, "episodes": {}}

    def tearDown(self):
        self.context.close()
        self.directory.cleanup()

    def route(self, content, status=200):
        html = '<h1>Episode 257: Test</h1><a href="#edit">Edit This Episode</a>' + content
        self.page.route("**/*", lambda route: route.fulfill(status=status, content_type="text/html", body=html))

    def run_episode(self):
        return automation.queue_episode(self.page, EPISODE, TEMPLATE, Path(self.directory.name), self.state)

    def test_ready_and_processing_transcripts_are_skipped(self):
        for label, expected in (("Transcript is Ready", "ready"), ("Transcript is Processing", "processing")):
            with self.subTest(label=label):
                self.page.unroute("**/*")
                self.route(f'<p>{label}</p><button onclick="throw Error()">Generate Automatic Transcript</button>')
                self.assertEqual(self.run_episode(), expected)
                self.assertEqual(self.state["episodes"][EPISODE["id"]]["status"], expected)

    def test_queued_job_is_verified_and_checkpointed(self):
        self.route('''<p id="status"></p><a href="#" onclick="
            document.querySelector('#status').textContent='Transcript is Processing';
            this.remove(); return false">Generate Automatic Transcript</a>''')
        self.assertEqual(self.run_episode(), "queued")
        saved = automation.load_state(Path(self.directory.name))
        self.assertEqual(saved["episodes"][EPISODE["id"]]["status"], "queued")
        self.assertEqual(automation.pending_episodes([EPISODE], saved), [])

    def test_native_transcript_confirmation(self):
        self.route('''<p id="status"></p><button onclick="
            if(confirm('Generate automatic transcript?'))
              document.querySelector('#status').textContent='Transcript is Processing';
            ">Generate Automatic Transcript</button>''')
        self.assertEqual(self.run_episode(), "queued")

    def test_html_transcript_confirmation(self):
        self.route('''<p id="status"></p><button onclick="document.querySelector('dialog').showModal()">
            Generate Automatic Transcript</button><dialog><p>Generate a transcript?</p>
            <button onclick="document.querySelector('dialog').close();
            document.querySelector('#status').textContent='Transcript is Processing'">Generate</button></dialog>''')
        self.assertEqual(self.run_episode(), "queued")

    def test_unexpected_confirmation_stops_with_uncertain_checkpoint(self):
        self.route('''<button onclick="confirm('Delete this episode?')">Generate Automatic Transcript</button>''')
        with self.assertRaisesRegex(RuntimeError, "unexpected confirmation"):
            self.run_episode()
        self.assertEqual(self.state["episodes"][EPISODE["id"]]["status"], "attempting")
        self.assertEqual(automation.pending_episodes([EPISODE], self.state), [])

    def test_rate_limit_stops_before_clicking(self):
        self.route('<button>Generate Automatic Transcript</button>', status=429)
        with self.assertRaisesRegex(RuntimeError, "HTTP 429"):
            self.run_episode()
        self.assertEqual(self.state["episodes"], {})

    def test_redirect_to_login_cannot_click_another_page(self):
        self.page.route("**/*", lambda route: route.fulfill(
            status=302, headers={"location": "https://www.buzzsprout.com/login"}
        ) if "/episodes/" in route.request.url else route.fulfill(
            status=200, body='<button>Generate Automatic Transcript</button>'
        ))
        with self.assertRaisesRegex(RuntimeError, "another episode or sign-in"):
            self.run_episode()
        self.assertEqual(self.state["episodes"], {})

    def test_episode_page_with_title_slug_is_accepted(self):
        html = '<h1>Episode 257: Test</h1><a href="#edit">Edit This Episode</a><p>Transcript is Ready</p>'
        self.page.route("**/*", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        self.assertEqual(automation.queue_episode(
            self.page, EPISODE, TEMPLATE + "-episode-257-test", Path(self.directory.name), self.state
        ), "ready")

    def test_episode_title_with_slashes_and_ampersand_is_accepted(self):
        episode = dict(EPISODE, title="Episode 257: C++20/23/26/29 & More")
        self.page.route("**/*", lambda route: route.fulfill(
            status=200, content_type="text/html",
            body='<h1>Episode 257: C++20/23/26/29 &amp; More</h1>'
            '<a href="#edit">Edit This Episode</a><p>Transcript is Ready</p>'
        ))
        self.assertEqual(automation.queue_episode(
            self.page, episode, TEMPLATE, Path(self.directory.name), self.state
        ), "ready")


if __name__ == "__main__":
    unittest.main()
