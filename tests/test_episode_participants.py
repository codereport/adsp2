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


if __name__ == "__main__":
    unittest.main()
