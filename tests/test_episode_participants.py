import re
import unittest

import generate_episodes as generator


def episode(number=0, cohost="", guests=()):
    return {
        "number": number,
        "date": "2026-01-01",
        "title": f"Test episode {number}",
        "cohost": cohost,
        "guest": bool(guests),
        "guest_people": tuple((f"name:{name.casefold()}", name, "") for name in guests),
        "guest_identity": ("notes",),
        "recorded_date": "2025-12-01",
        "tags": (),
        "tag_values": (),
        "event": False,
        "trip": False,
    }


def transcript(*labels):
    return "".join(
        f"<cite>{label}</cite><time>0:{index:02}</time><p>Some spoken words.</p>"
        for index, label in enumerate(labels)
    )


class EmployerMetadataTests(unittest.TestCase):
    def test_employer_fields_do_not_hide_later_guest_bios(self):
        post = """[Link to Episode 24 on Website](https://example.com/episode)

**About the Guests:**

[Ben Deane](https://example.com/ben) is a programmer.

**Employer as of recording:** Intel

[Tristan Brindle](https://example.com/tristan) is a freelance programmer.

**Employer as of recording:** Independent

### Show Notes

**Date Recorded:** 2023-05-16
"""
        body = generator.about_guest_section(post)
        people = generator.guest_people(body, "", ("ben deane", "tristan brindle"))
        self.assertEqual([name for _, name, _ in people], ["Ben Deane", "Tristan Brindle"])
        self.assertNotIn("Employer as of recording", body)
        self.assertNotIn("Date Recorded", body)

    def test_employer_changes_do_not_change_recording_identity(self):
        post = "**About the Guest:**\n\n[Sean Parent](https://example.com/sean) is a programmer.\n\n"
        before = generator.about_guest_section(post)
        after = generator.about_guest_section(post + "**Employer as of recording:** Adobe\n")
        self.assertEqual(generator.guest_identity(before, ()), generator.guest_identity(after, ()))

    def test_employers_stay_associated_with_their_guest_in_multi_guest_bios(self):
        post = """[Link to Episode 24 on Website](https://example.com/episode)

**About the Guests:**

For [Ben Deane](https://example.com/ben), C++ pays the bills.

His bio continues in a second paragraph.

**Employer as of recording:** Quantlab

Zach Laine has been using C++ for years.

**Employer as of recording:** [Cadence](https://example.com/cadence); University
"""
        self.assertEqual(generator.guest_employers_from_post(post), {
            generator.normalized_person_name("Ben Deane"): ("Quantlab",),
            generator.normalized_person_name("Zach Laine"): ("Cadence", "University"),
        })

    def test_employer_bio_uses_the_full_name_from_guest_tags(self):
        post = """---
tags: [Guest, Marco Franzreb Salgado]
---

**About the Guest:**

[Marco](https://example.com/marco) is a software engineer.

**Employer as of recording:** NVIDIA
"""
        self.assertEqual(generator.guest_employers_from_post(post), {
            generator.normalized_person_name("Marco Franzreb Salgado"): ("NVIDIA",),
        })

    def test_company_logos_link_to_recordings_from_that_employer(self):
        episodes = []
        for number, guest, employer in [
            (78, "Ben Deane", "Quantlab"),
            (131, "Ben Deane", "Intel"),
            (161, "Zach Laine", "Cadence Design Systems"),
            (311, "Zach Laine", "LSEG"),
        ]:
            item = episode(number, guests=(guest,))
            item["guest_employers"] = {generator.normalized_person_name(guest): (employer,)}
            episodes.append(item)
        metadata = {
            "featured_companies": ["quantlab", "cadence", "lseg", "legacy"],
            "companies": {
                "quantlab": {"name": "Quantlab", "guests": ["Ben Deane"]},
                "cadence": {"name": "Cadence", "aliases": ["Cadence Design Systems"], "guests": ["Zach Laine"]},
                "lseg": {"name": "LSEG", "guests": ["Zach Laine"]},
                "legacy": {"name": "Legacy affiliation", "guests": ["Ben Deane"]},
            },
        }
        result = generator.latest_company_episodes(episodes, metadata)
        self.assertEqual({key: value["episode"] for key, value in result.items()}, {
            "quantlab": 78, "cadence": 161, "lseg": 311, "legacy": 131,
        })


class EpisodeParticipantTests(unittest.TestCase):
    def test_transcript_finds_cohost_missing_from_notes(self):
        post = episode()
        metrics = generator.transcript_indices(post, transcript("Conor", "Bryce"))
        generator.apply_transcript_participants([post], {0: metrics})
        self.assertEqual(post["cohost"], "Bryce")
        self.assertFalse(post["guest"])
        self.assertEqual(metrics["speaker_word_counts"], {"host:conor": 3, "host:bryce": 3})

    def test_outro_and_clips_do_not_make_a_solo_episode_cohosted(self):
        metrics = generator.transcript_indices(
            episode(cohost="Bryce"), transcript("Conor", "Bryce (Outro)", "Sean Parent (Clip)")
        )
        self.assertEqual(metrics["cohost"], "Solo")
        self.assertEqual(metrics["baf"], 0)
        self.assertFalse(metrics["guest_people"])
        self.assertIn("person:bryce outro", metrics["speaker_word_counts"])

    def test_guests_come_from_speakers_and_count_once_per_episode(self):
        post = episode(guests=("Sean Parent", "Kate Gregory"))
        metrics = generator.transcript_indices(
            post, transcript("Conor", "Sean Parent", "Sean Parent", "Koen Poppe", "Kate Gregory (Clip)")
        )
        generator.apply_transcript_participants([post], {0: metrics})
        self.assertEqual([name for _, name, _ in post["guest_people"]], ["Sean Parent", "Koen Poppe"])
        self.assertEqual(metrics["guest_word_counts"], {"guest:sean parent": 6, "guest:koen poppe": 3})
        self.assertIsNone(metrics["baf"])

    def test_ben_deane_guest_and_cohost_roles_remain_distinct(self):
        guest_metrics = generator.transcript_indices(
            episode(cohost="Bryce", guests=("Ben Deane",)), transcript("Conor", "Bryce", "Ben Deane")
        )
        self.assertIn("guest:ben deane", guest_metrics["guest_word_counts"])
        self.assertEqual(guest_metrics["cohost"], "Bryce")
        for label in ("Ben", "Ben Deane"):
            with self.subTest(label=label):
                metrics = generator.transcript_indices(
                    episode(cohost="Ben"), transcript("Conor", label, "Kate Gregory")
                )
                self.assertEqual(metrics["cohost"], "Ben")
                self.assertIn("host:ben", metrics["speaker_word_counts"])
                self.assertNotIn("guest:ben deane", metrics["guest_word_counts"])

    def test_host_names_are_matched_precisely(self):
        metrics = generator.transcript_indices(
            episode(), transcript("Conor Hoekstra", "Bryce's Mom", "Ben Other")
        )
        self.assertEqual(metrics["cohost"], "Solo")
        self.assertEqual(set(metrics["guest_word_counts"]), {"guest:bryce s mom", "guest:ben other"})

    def test_ai_excluded_but_mystery_guest_included(self):
        metrics = generator.transcript_indices(
            episode(), transcript("Conor", "AI Host 1", "AI Host 2", "MYSTERY SPEAKER")
        )
        self.assertEqual(metrics["guest_word_counts"], {"guest:mystery speaker": 3})
        self.assertEqual([name for _, name, _ in metrics["guest_people"]], ["MYSTERY SPEAKER"])
        self.assertIn("person:ai host 1", metrics["speaker_word_counts"])

    def test_spelling_variants_merge_and_keep_profile_links(self):
        people = generator.guest_catalog([{
            "guest_people": (
                ("profile:tristan", "Tristan Brindle", "https://example.com/tristan"),
                ("profile:doug", "Douglas Gregor", "https://example.com/doug"),
            )
        }])
        metrics = generator.transcript_indices(
            episode(), transcript("Conor", "Trinstan Brindle", "Tristan Brindle", "Doug Gregor"), people
        )
        self.assertEqual(metrics["guest_word_counts"], {"guest:tristan brindle": 6, "guest:douglas gregor": 3})
        self.assertEqual(len(metrics["guest_people"]), 2)
        self.assertEqual(metrics["guest_people"][0][2], "https://example.com/tristan")

    def test_parenthesized_guest_never_merges_with_actual_guest(self):
        metrics = generator.transcript_indices(
            episode(guests=("Tristan Brindle",)),
            transcript("Conor", "Trinstan Brindle", "Tristan Brindle (Video)"),
        )
        self.assertEqual(metrics["guest_word_counts"], {"guest:tristan brindle": 3})

    def test_both_cohosts_are_not_counted_as_guests(self):
        metrics = generator.transcript_indices(episode(), transcript("Conor", "Bryce", "Ben"))
        self.assertEqual(metrics["cohost"], "Bryce & Ben")
        self.assertFalse(metrics["guest_people"])
        self.assertEqual(generator.cohost_names(metrics["cohost"]), ("Bryce", "Ben"))

    def test_missing_transcript_keeps_notes_and_explicit_solo_override(self):
        post = episode(cohost="Bryce", guests=("Sean Parent",))
        generator.apply_transcript_participants([post], {})
        self.assertEqual(post["cohost"], "Bryce")
        self.assertTrue(post["guest"])
        self.assertEqual(generator.cohost_from_post("cohost: Solo\n<br>In this episode, Conor and Bryce"), "Solo")


class GuestStatsTests(unittest.TestCase):
    def render_rows(self, episodes, durations, metrics):
        stats = generator.render_stats(
            episodes, durations, metrics, {"guests_by_name": {}}
        )
        return {
            name: row for name, row in re.findall(
                r'<tr data-guest="([^"]+)"(.*?)</tr>', stats
            )
        }

    def test_talking_time_uses_each_guests_share_of_all_words(self):
        post = episode(guests=("Sean Parent", "Kate Gregory"))
        metrics = generator.transcript_indices(
            post, transcript("Conor", "Sean Parent", "Sean Parent", "Kate Gregory")
        )
        rows = self.render_rows([post], {0: 3600}, {0: metrics})
        self.assertIn('data-talking-time="1800.0"', rows["sean parent"])
        self.assertIn("<td>0h30m</td>", rows["sean parent"])
        self.assertIn('data-talking-time="900.0"', rows["kate gregory"])

    def test_talking_time_weights_each_episode_before_summing(self):
        posts = [episode(number=n, guests=("Sean Parent",)) for n in (0, 1)]
        metrics = {
            0: generator.transcript_indices(posts[0], transcript("Conor", "Sean Parent")),
            1: generator.transcript_indices(posts[1], transcript("Conor", "Bryce", "Sean Parent")),
        }
        row = self.render_rows(posts, {0: 3600, 1: 1800}, metrics)["sean parent"]
        self.assertIn('data-talking-time="2400.0"', row)
        self.assertIn('data-recordings="1" data-episodes="2"', row)
        self.assertIn("<td>0h40m</td>", row)

    def test_missing_transcripts_durations_and_empty_word_counts_are_unavailable(self):
        post = episode(guests=("Sean Parent",))
        other = episode(number=1)
        metrics = generator.transcript_indices(post, transcript("Conor", "Sean Parent"))
        empty = dict(metrics, guest_word_counts={"guest:sean parent": 0}, speaker_word_counts={})
        for durations, transcript_stats in (
            ({0: 3600, 1: 1800}, {}),
            ({1: 1800}, {0: metrics}),
            ({0: 3600, 1: 1800}, {0: empty}),
        ):
            with self.subTest(durations=durations, transcript_stats=transcript_stats):
                row = self.render_rows([post, other], durations, transcript_stats)["sean parent"]
                self.assertIn('data-talking-time=""', row)
                self.assertIn("<td>—</td>", row)

    def test_missing_transcript_does_not_add_full_episode_duration(self):
        posts = [episode(number=n, guests=("Sean Parent",)) for n in (0, 1)]
        metrics = {0: generator.transcript_indices(posts[0], transcript("Conor", "Sean Parent"))}
        row = self.render_rows(posts, {0: 3600, 1: 7200}, metrics)["sean parent"]
        self.assertIn('data-talking-time="1800.0"', row)

    def test_ranks_continue_into_collapsed_guests(self):
        post = episode(guests=tuple(f"Guest {n:02}" for n in range(12)))
        rows = list(self.render_rows([post], {0: 3600}, {}).values())
        self.assertEqual(len(rows), 12)
        for rank, row in enumerate(rows, start=1):
            self.assertIn(f'<td class="guest-rank">{rank}</td>', row)


if __name__ == "__main__":
    unittest.main()
