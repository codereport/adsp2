from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
import shutil
import threading
import unittest

try:
    from playwright.sync_api import sync_playwright
except ImportError:
    sync_playwright = None


ROOT = Path(__file__).resolve().parents[1]


class QuietHandler(SimpleHTTPRequestHandler):
    def log_message(self, *args):
        pass


@unittest.skipUnless(
    sync_playwright and shutil.which("chromium") and (ROOT / "_site/index.html").exists(),
    "requires Playwright, Chromium, and a Jekyll build",
)
class LogoCarouselTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(
            ("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "_site"))
        )
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.origin = f"http://127.0.0.1:{cls.server.server_port}"
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch(
            headless=True, executable_path=shutil.which("chromium")
        )

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join()

    def setUp(self):
        self.context = self.browser.new_context(viewport={"width": 940, "height": 1000})
        self.addCleanup(self.context.close)
        self.page = self.context.new_page()
        self.page.add_init_script("localStorage.setItem('theme', 'light')")
        self.page.route("**/*", self.route)
        self.page.goto(self.origin, wait_until="networkidle")
        self.page.wait_for_function("document.querySelectorAll('.logo-carousel').length === 2")
        self.company = self.page.locator(".logo-carousel").filter(has=self.page.locator(".company-logos"))

    def route(self, route):
        if route.request.url.startswith(self.origin):
            route.continue_()
        elif route.request.url.startswith("https://raw.githubusercontent.com/codereport/logos/"):
            # Keep layout tests independent of the remote image host.
            route.fulfill(content_type="image/svg+xml", body=(
                '<svg xmlns="http://www.w3.org/2000/svg" width="80" height="80">'
                '<rect width="80" height="80" fill="navy"/></svg>'
            ))
        else:
            route.abort()

    def position(self):
        return self.company.locator(".logo-carousel-viewport").evaluate("el => el.scrollLeft")

    def test_overflow_stays_on_one_line_and_fitting_rows_are_static(self):
        for width in (390, 940, 2800):
            with self.subTest(width=width):
                self.page.set_viewport_size({"width": width, "height": 1000})
                self.page.wait_for_timeout(100)
                for row in self.page.locator(".logo-carousel").all():
                    expected = width != 2800
                    self.assertEqual("is-overflowing" in row.get_attribute("class"), expected)
                    self.assertEqual(row.locator(".logo-carousel-toggle").is_visible(), expected)
                    tops = row.locator(".logo-carousel-group").first.locator("a").evaluate_all(
                        "nodes => nodes.map(el => el.getBoundingClientRect().top)"
                    )
                    self.assertLess(max(tops) - min(tops), 1)
                    if not expected:
                        self.assertEqual(row.locator(".logo-carousel-viewport").evaluate("el => el.scrollLeft"), 0)
                        self.assertTrue(row.locator('[aria-hidden="true"].logo-carousel-group').is_hidden())

    def test_motion_pauses_for_hover_focus_and_the_persistent_control(self):
        self.company.scroll_into_view_if_needed()
        self.page.mouse.move(0, 0)
        first = self.position()
        self.page.wait_for_timeout(250)
        self.assertGreater(self.position(), first + 2)

        self.company.hover()
        paused = self.position()
        self.page.wait_for_timeout(200)
        self.assertEqual(self.position(), paused)
        self.page.mouse.move(0, 0)
        self.company.locator(".logo-carousel-group").first.locator("a").last.focus()
        paused = self.position()
        self.page.wait_for_timeout(200)
        self.assertEqual(self.position(), paused)

        button = self.company.locator(".logo-carousel-toggle")
        button.click()
        self.assertEqual(button.get_attribute("aria-pressed"), "true")
        self.page.mouse.move(0, 0)
        button.evaluate("el => el.blur()")
        paused = self.position()
        self.page.wait_for_timeout(200)
        self.assertEqual(self.position(), paused)
        button.click()
        self.assertEqual(button.get_attribute("aria-pressed"), "false")
        first = self.position()
        self.page.wait_for_timeout(250)
        self.assertGreater(self.position(), first + 2)

    def test_reduced_motion_uses_manual_scrolling_and_updates_live(self):
        self.page.emulate_media(reduced_motion="reduce")
        self.company.scroll_into_view_if_needed()
        self.page.mouse.move(0, 0)
        self.page.wait_for_function("document.querySelector('.logo-carousel.is-reduced-motion')")
        self.assertTrue(self.company.locator(".logo-carousel-toggle").is_hidden())
        self.assertTrue(self.company.locator('[aria-hidden="true"].logo-carousel-group').is_hidden())
        self.company.locator(".logo-carousel-viewport").evaluate("el => el.scrollLeft = 100")
        self.page.wait_for_timeout(200)
        self.assertEqual(self.position(), 100)
        self.page.emulate_media(reduced_motion="no-preference")
        self.page.wait_for_timeout(250)
        self.assertGreater(self.position(), 102)

    def test_wraparound_copies_preserve_links_and_switch_themes(self):
        self.company.scroll_into_view_if_needed()
        for row in self.page.locator(".logo-carousel").all():
            original, copy = row.locator(".logo-carousel-group").all()
            self.assertEqual(
                original.locator("a").evaluate_all("nodes => nodes.map(el => el.getAttribute('href'))"),
                copy.locator("a").evaluate_all("nodes => nodes.map(el => el.getAttribute('href'))"),
            )
            self.assertEqual(copy.locator("[id]").count(), 0)
            self.assertTrue(all(value == "-1" for value in copy.locator("a").evaluate_all(
                "nodes => nodes.map(el => el.getAttribute('tabindex'))"
            )))
        self.company.hover()
        self.company.evaluate("""root => {
            const track = root.querySelector('.logo-carousel-track');
            const width = track.firstElementChild.getBoundingClientRect().width;
            root.querySelector('.logo-carousel-viewport').scrollLeft = width + parseFloat(getComputedStyle(track).columnGap) - 4;
        }""")
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(300)
        self.assertLess(self.position(), 20)
        self.page.locator("#theme-toggle").click()
        rust = self.page.locator('img[data-dark-src]')
        self.assertEqual(rust.count(), 2)
        self.assertTrue(all(rust.nth(i).get_attribute("src") == rust.nth(i).get_attribute("data-dark-src") for i in range(2)))

    def test_offscreen_rows_stop_animating(self):
        self.page.set_viewport_size({"width": 940, "height": 400})
        self.company.scroll_into_view_if_needed()
        self.page.mouse.move(0, 0)
        self.page.wait_for_timeout(200)
        self.page.evaluate("window.scrollTo(0, 0)")
        self.page.wait_for_timeout(100)
        paused = self.position()
        self.page.wait_for_timeout(200)
        self.assertEqual(self.position(), paused)


if __name__ == "__main__":
    unittest.main()
