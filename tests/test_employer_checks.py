import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest

import checks


HOME = '''<div class="company-logos">
{% for company_id in site.data.guest_metadata.featured_companies %}
  {% assign company = site.data.guest_metadata.companies[company_id] %}
  <img{% if company.dark_invert %} class="dark"{% endif %}
    src="{{ site.data.guest_metadata.logo_base_url }}{{ company.logo }}" alt="{{ company.name }}">
{% endfor %}
</div>'''


def metadata(featured=("futurewei",), logo="company/futurewei.svg"):
    return {
        "featured_companies": list(featured),
        "companies": {"futurewei": {
            "name": "Futurewei", "aliases": ["Futurewei Technologies"], "logo": logo,
        }},
    }


class EmployerChecksTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        self.posts = self.root / "_posts"
        self.posts.mkdir()

    def post(self, number, employers, guests=None):
        path = self.posts / f"2026-01-01-Episode-{number}.md"
        guests = guests or ["Test Guest"] * len(employers)
        path.write_text("**About the Guests:**\n\n" + "\n\n".join(
            f"[{guest}](https://example.com/{index}) is a programmer.\n\n"
            f"**Employer as of recording:** {employer}"
            for index, (guest, employer) in enumerate(zip(guests, employers))
        ))
        return path

    def report(self):
        (self.root / "_data").mkdir()
        (self.root / "_data" / "guest_metadata.json").write_text(json.dumps(metadata()))
        (self.root / "_layouts").mkdir()
        (self.root / "_layouts" / "home.html").write_text(HOME)
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            checks.report_guest_employers(self.root)
        return output.getvalue()

    def test_lists_unconfirmed_episodes_once_in_episode_order(self):
        self.post(12, ["unconfirmed", "UNCONFIRMED"])
        self.post(2, ["NVIDIA", "unconfirmed"])
        self.post(3, ["Independent", "Retired", "Independent (Romeo Training)"])
        unconfirmed, employers = checks.guest_employer_inventory(self.posts)
        self.assertEqual([entry["episode"] for entry in unconfirmed], [2, 12])
        self.assertEqual(len(unconfirmed[1]["lines"]), 2)
        self.assertEqual(employers, {"NVIDIA": {2}})

    def test_names_the_unconfirmed_guest_and_groups_episode_runs(self):
        for number in [24, 75, 76, 77, 78]:
            self.post(number, ["unconfirmed"], ["Ben Deane"])
        for number in [117, 118, 119, 120, 121]:
            self.post(number, ["unconfirmed"], ["Zach Laine"])
        # A plain-text bio and the second guest in a multi-guest episode work too.
        path = self.post(161, ["unconfirmed"], ["Zach Laine"])
        path.write_text(path.read_text().replace("[Zach Laine](https://example.com/0)", "Zach Laine"))
        self.post(265, ["Independent", "unconfirmed"], ["Kevlin Henney", "Damian Maclennan"])
        text = self.report()
        self.assertIn("Unconfirmed employers in 12 episodes", text)
        self.assertIn("Ben Deane: episodes 24, 75–78", text)
        self.assertIn("Zach Laine: episodes 117–121, 161", text)
        self.assertIn("Damian Maclennan: episode 265", text)
        self.assertNotIn("Kevlin Henney:", text)
        self.assertNotIn("Unknown guest", text)

    def test_reads_multiple_employers_and_linked_company_names(self):
        self.post(4, ["[Company A](https://example.com/a); University B"])
        self.post(5, ["Company A"])
        unconfirmed, employers = checks.guest_employer_inventory(self.posts)
        self.assertFalse(unconfirmed)
        self.assertEqual(employers, {"Company A": {4, 5}, "University B": {4}})

    def test_homepage_loop_covers_featured_company_aliases(self):
        missing = checks.missing_employer_logos({"Futurewei Technologies": {106, 107}}, metadata(), HOME)
        self.assertFalse(missing)

    def test_reports_unknown_companies_with_their_episodes(self):
        missing = checks.missing_employer_logos({"Dyalog": {197, 196}}, metadata(), HOME)
        self.assertEqual(len(missing), 1)
        self.assertEqual(missing[0]["company"], "Dyalog")
        self.assertEqual(missing[0]["episodes"], {196, 197})
        self.assertIn("catalog", missing[0]["reason"])

    def test_catalog_entry_without_featured_logo_is_missing(self):
        missing = checks.missing_employer_logos({"Futurewei": {106}}, metadata(featured=()), HOME)
        self.assertEqual(missing[0]["reason"], "not in featured_companies")

    def test_exclusions_match_aliases_and_leave_new_employers_visible(self):
        missing = checks.missing_employer_logos(
            {"Futurewei Technologies": {106}, "New Company": {20}},
            metadata(featured=()), HOME, logos_not_included={"Futurewei"},
        )
        self.assertEqual([entry["company"] for entry in missing], ["New Company"])

    def test_featured_company_needs_a_logo_and_a_rendered_image(self):
        for settings, home in [
            (metadata(logo=""), HOME),
            (metadata(), "<!--" + HOME + "-->"),
            (metadata(), "{% comment %}" + HOME + "{% endcomment %}"),
            (metadata(), HOME.replace("{{ company.logo }}", "unrelated.svg")),
        ]:
            with self.subTest(settings=settings, home=home):
                self.assertTrue(checks.missing_employer_logos({"Futurewei": {106}}, settings, home))

    def test_logo_reference_outside_image_source_does_not_count(self):
        home = HOME.replace("{{ company.logo }}", "unrelated.svg").replace("{{ company.name }}", "{{ company.logo }}")
        self.assertTrue(checks.missing_employer_logos({"Futurewei": {106}}, metadata(), home))

    def test_literal_homepage_logo_counts_but_commented_logo_does_not(self):
        logo = '<img src="/assets/dyalog.svg" alt="Dyalog">'
        self.assertFalse(checks.missing_employer_logos({"Dyalog": {196}}, metadata(), logo))
        self.assertTrue(checks.missing_employer_logos({"Dyalog": {196}}, metadata(), "<!--" + logo + "-->"))

    def test_reports_metadata_gaps_as_non_blocking_warnings(self):
        self.post(4, ["unconfirmed", "New Company"])
        text = self.report()
        self.assertIn("Test Guest: episode 4", text)
        self.assertIn("New Company: episodes 4", text)
        self.assertIn("⚠️", text)
        self.assertNotIn("❌", text)


if __name__ == "__main__":
    unittest.main()
