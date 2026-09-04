#!/usr/bin/env python3

import argparse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
import html
import json
import re
import statistics
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.parse import quote_plus
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "_posts"
EPISODES_PAGE = ROOT / "pages" / "episodes.md"
GUEST_METADATA_PATH = ROOT / "_data" / "guest_metadata.json"
COMPANY_EPISODES_PATH = ROOT / "_data" / "company_latest_episodes.json"
FEED_URL = "https://feeds.buzzsprout.com/1501960.rss"
TRANSCRIPT_URL = "https://www.buzzsprout.com/1501960/{buzzsprout_id}/transcript"
TRANSCRIPT_START_EPISODE = 264
GENERATED_START = "<!-- BEGIN GENERATED EPISODES -->"
GENERATED_END = "<!-- END GENERATED EPISODES -->"
ITUNES_DURATION = "{http://www.itunes.com/dtds/podcast-1.0.dtd}duration"
GENERIC_EVENT_TAGS = {
    "conference",
    "conferences",
    "guest",
    "guests",
    "interview",
    "interviews",
}
MAX_EVENT_SERIES_TAG_USES = 12
GUEST_TAG_ALIASES = {
    "douglas gregor": "doug gregor",
    "robert leahy": "rob leahy",
}

POST_NAME_PATTERN = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})-Episode-(?P<number>\d+)\.md$"
)
EXISTING_ROW_PATTERN = re.compile(
    r"^\|\s*(?P<number>\d+)\s*\|\s*\[(?P<title>.*)\]"
    r"\(https://adspthepodcast\.com/[^)]*/Episode-\d+\.html\)"
    r"(?:\{:[^}]*\})?\s*\|(?P<rest>.*)$"
)
TRANSCRIPT_TURN_PATTERN = re.compile(
    r"<cite(?:\s[^>]*)?>(?P<speaker>.*?)</cite>\s*"
    r"<time(?:\s[^>]*)?>(?P<timestamp>.*?)</time>\s*"
    r"<p(?:\s[^>]*)?>(?P<body>.*?)</p>",
    re.IGNORECASE | re.DOTALL,
)
LEGACY_TRANSCRIPT_TURN_PATTERN = re.compile(
    r"(?:^|\n{2,})(?P<speaker>[^:\n]{1,80}):\s*"
    r"(?P<timestamp>\d{1,2}:\d{2}(?::\d{2})?)\s*\n",
)
HOST_NAMES = {
    "ben": "Ben",
    "bryce": "Bryce",
    "conor": "Conor",
    "connor": "Conor",
}
HOST_SPEAKER_COLORS = {
    "host:conor": "#8b1f2d",
    "host:bryce": "#337ab7",
    "host:ben": "#c4752e",
}
OTHER_SPEAKER_COLORS = (
    "#6f4aa8",
    "#2a8f70",
    "#b24f83",
    "#8a7334",
    "#477a9e",
)


def parse_args():
    parser = argparse.ArgumentParser(description="Generate the episodes table.")
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit with an error instead of updating an out-of-date table",
    )
    parser.add_argument(
        "--feed-file",
        type=Path,
        help="read a local Buzzsprout RSS file instead of downloading the feed",
    )
    return parser.parse_args()


def front_matter_value(post, key):
    match = re.search(rf"^{re.escape(key)}:\s*(.*)$", post, re.MULTILINE)
    if not match:
        return ""

    value = match.group(1).strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        value = value[1:-1]
    return value


def buzzsprout_id_from_post(post):
    front_matter_id = front_matter_value(post, "buzzsprout-id")
    if front_matter_id:
        return front_matter_id

    player_match = re.search(r"buzzsprout-player-(\d+)", post)
    return player_match.group(1) if player_match else ""


def title_from_post(post, episode_number):
    title = front_matter_value(post, "title")
    return re.sub(
        rf"^Episode\s+{episode_number}\s*:\s*", "", title, flags=re.IGNORECASE
    ).replace("|", r"\|")


def post_tag_values(post):
    tags = front_matter_value(post, "tags").strip("[]")
    return tuple(
        tag.strip().strip("\"'")
        for tag in tags.split(",")
        if tag.strip()
    )


def guest_tag(name, tag_values):
    normalized_name = name.casefold()
    normalized_tag = GUEST_TAG_ALIASES.get(normalized_name, normalized_name)
    return next(
        (tag for tag in tag_values if tag.casefold() == normalized_tag),
        "",
    )


def about_guest_section(post):
    match = re.search(
        r"^(?:\*\*About the Guests?:\*\*|### About the Guests?)\s*\n"
        r"(?P<body>.*?)(?=^(?:###\s|\*\*[^*\n]+:\*\*)|\Z)",
        post,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def guests_interviewed_section(post):
    match = re.search(
        r"^### Guests Interviewed\s*\n(?P<body>.*?)(?=^###\s|\Z)",
        post,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def is_guest_episode(tags, about_guest, interviewed_guests):
    return bool(
        {"guest", "guests"} & set(tags)
        or about_guest
        or interviewed_guests
    )


def guest_identity(about_guest, tags):
    if about_guest:
        profile_urls = re.findall(
            r"^(?:For\s+)?(?:\*\*)?\[[^]]+\]\(([^)]+)\)(?:\*\*)?",
            about_guest,
            re.MULTILINE,
        )
        if profile_urls:
            return ("profiles",) + tuple(
                sorted(url.rstrip("/").casefold() for url in profile_urls)
            )

        # Some guest bios, such as Zach Laine's, start with plain text rather
        # than a profile link. The first paragraph is still stable across a run.
        first_paragraph = re.split(r"\n\s*\n", about_guest, maxsplit=1)[0]
        return ("bio", re.sub(r"\s+", " ", first_paragraph).casefold())

    # Conference roundups often omit bios and are grouped separately below.
    return ("tags",) + tuple(
        sorted(tag for tag in tags if tag not in {"guest", "guests"})
    )


def guest_people(about_guest, interviewed_guests, tags):
    people = {}

    def add_person(name, profile_url=""):
        name = name.strip()
        if not name or name.casefold() in {"he", "she", "they"}:
            return

        if profile_url:
            longer_tag_names = [
                tag
                for tag in tags
                if re.search(rf"\b{re.escape(name.casefold())}\b", tag)
                and len(tag) > len(name)
            ]
            if longer_tag_names:
                name = max(longer_tag_names, key=len).title()
            key = f"profile:{profile_url.rstrip('/').casefold()}"
        else:
            normalized_name = re.sub(r"[^\w]+", " ", name.casefold()).strip()
            key = f"name:{normalized_name}"

        previous = people.get(key)
        if not previous or len(name) > len(previous[0]):
            people[key] = (name, profile_url)

    for paragraph in re.split(r"\n\s*\n", about_guest):
        paragraph = paragraph.strip()
        if not paragraph:
            continue

        linked_name = re.match(
            r"^(?:For\s+)?(?:\*\*)?\[([^]]+)\]\(([^)]+)\)(?:\*\*)?",
            paragraph,
        )
        if linked_name:
            name, profile_url = linked_name.groups()
        else:
            plain_name = re.match(
                r"^(?:For\s+)?(?:\*\*)?([A-ZÀ-ÖØ-Þ][^.!?\n*]{1,60}?)"
                r"(?:\*\*)?\s+"
                r"(?:is|has|was|works|joined)\b",
                paragraph,
            )
            if not plain_name:
                continue
            name = plain_name.group(1).strip()
            name_words = name.split()
            if (
                len(name_words) < 2
                or len(name_words) > 5
                or any(character.isdigit() or character == "," for character in name)
                or any(not word[0].isupper() for word in name_words)
            ):
                continue
            profile_url = ""

        add_person(name, profile_url)

    for line in interviewed_guests.splitlines():
        list_item = re.match(
            r"^\s*[*-]\s+(?:\[([^]]+)\]\(([^)]+)\)(?:\s+\([^)]*\))?|(.+?))\s*$",
            line,
        )
        if not list_item:
            continue
        linked_name, profile_url, plain_name = list_item.groups()
        add_person(linked_name or plain_name, profile_url or "")

    return tuple(
        (key, name, profile_url)
        for key, (name, profile_url) in people.items()
    )


def recorded_date_from_post(post):
    match = re.search(
        r"^\*\*Date Recorded:\*\*\s*(\d{4}-\d{2}-\d{2})\b",
        post,
        re.MULTILINE,
    )
    return match.group(1) if match else ""


def cohost_from_post(post):
    override = front_matter_value(post, "cohost")
    if override.casefold() in {"ben", "bryce"}:
        return override.title()

    introduction = next(
        (
            line
            for line in post.splitlines()
            if line.lstrip().startswith("<br>In this episode")
        ),
        "",
    )
    bryce_pair = re.search(
        r"\b(?:Conor\s+(?:and|&)\s+Bryce|Bryce\s+(?:and|&)\s+Conor)\b",
        introduction,
        re.IGNORECASE,
    )
    ben_pair = re.search(
        r"\b(?:Conor\s+(?:and|&)\s+Ben|Ben\s+(?:and|&)\s+Conor)\b",
        introduction,
        re.IGNORECASE,
    )

    if bryce_pair or ("Bryce" in introduction and not ben_pair):
        return "Bryce"
    if ben_pair or re.search(r"\bConor gets Ben(?:'s|’s)\b", introduction):
        return "Ben"
    return ""


def read_posts():
    episodes = []
    for path in POSTS_DIR.glob("*Episode-*.md"):
        match = POST_NAME_PATTERN.fullmatch(path.name)
        if not match:
            continue

        post = path.read_text(encoding="utf-8")
        number = int(match.group("number"))
        title = title_from_post(post, number)
        tag_values = post_tag_values(post)
        tags = tuple(tag.casefold() for tag in tag_values)
        about_guest = about_guest_section(post)
        interviewed_guests = guests_interviewed_section(post)
        guest = is_guest_episode(tags, about_guest, interviewed_guests)
        introduction = next(
            (
                line
                for line in post.splitlines()
                if line.lstrip().startswith("<br>In this episode")
            ),
            "",
        )
        episodes.append(
            {
                "number": number,
                "date": match.group("date"),
                "title": title,
                "tags": tags,
                "tag_values": tag_values,
                "guest": guest,
                "guest_identity": guest_identity(about_guest, tags),
                "guest_people": guest_people(
                    about_guest, interviewed_guests, tags
                ),
                "recorded_date": recorded_date_from_post(post),
                "event": guest
                and bool(
                    {"conference", "conferences", "interview", "interviews"}
                    & set(tags)
                    or "record live from" in introduction.casefold()
                    or re.search(r"[\U0001F1E6-\U0001F1FF]{2}", title)
                ),
                "trip": "road trip" in tags,
                "cohost": cohost_from_post(post),
                "buzzsprout_id": buzzsprout_id_from_post(post),
            }
        )

    return sorted(episodes, key=lambda episode: episode["number"])


def parse_duration(value):
    if value.isdigit():
        return int(value)

    parts = value.split(":")
    if not parts or not all(part.isdigit() for part in parts):
        raise ValueError(f"invalid duration: {value!r}")

    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def read_durations(feed_file=None):
    if feed_file:
        feed = feed_file.read_bytes()
    else:
        request = Request(FEED_URL, headers={"User-Agent": "ADSP episode generator"})
        with urlopen(request, timeout=30) as response:
            feed = response.read()

    durations = {}
    root = ET.fromstring(feed)
    for item in root.findall("./channel/item"):
        title = item.findtext("title", default="")
        match = re.match(r"Episode\s+(\d+)\s*:", title, re.IGNORECASE)
        duration = item.findtext(ITUNES_DURATION)
        if match and duration:
            durations[int(match.group(1))] = parse_duration(duration.strip())
    return durations


def parse_timestamp(value):
    parts = value.strip().split(":")
    if not parts or not all(part.isdigit() for part in parts):
        raise ValueError(f"invalid transcript timestamp: {value!r}")

    seconds = 0
    for part in parts:
        seconds = seconds * 60 + int(part)
    return seconds


def plain_text(value):
    without_comments = re.sub(r"<!--.*?-->", "", value, flags=re.DOTALL)
    without_tags = re.sub(r"<[^>]+>", "", without_comments)
    return html.unescape(without_tags).strip()


def count_words(value):
    return len(re.findall(r"\b[\w]+(?:[’'-][\w]+)*\b", value, re.UNICODE))


def parse_transcript(transcript):
    turns = []
    for match in TRANSCRIPT_TURN_PATTERN.finditer(transcript):
        body = match.group("body")
        word_times = [
            float(value)
            for value in re.findall(r'data-t=["\']([0-9]+(?:\.[0-9]+)?)["\']', body)
        ]
        text = plain_text(body)
        if word_times:
            speech_seconds = max(0.4, word_times[-1] - word_times[0] + 0.35)
            final_word_time = word_times[-1] + 0.35
        else:
            speech_seconds = max(0.4, len(text.split()) / 2.5)
            final_word_time = None
        turns.append(
            {
                "speaker": plain_text(match.group("speaker")),
                "start": parse_timestamp(plain_text(match.group("timestamp"))),
                "speech_seconds": speech_seconds,
                "final_word_time": final_word_time,
                "text": text,
                "word_count": len(word_times) if word_times else count_words(text),
            }
        )

    if turns:
        transcript_end = max(
            turn["final_word_time"]
            if turn["final_word_time"] is not None
            else turn["start"] + turn["speech_seconds"]
            for turn in turns
        )
        return turns, transcript_end

    # Some Buzzsprout transcripts use one paragraph with speaker/timestamp
    # markers separated by <br> elements rather than semantic cite/time tags.
    expanded = re.sub(r"<br\s*/?>", "\n", transcript, flags=re.IGNORECASE)
    expanded = plain_text(expanded)
    matches = list(LEGACY_TRANSCRIPT_TURN_PATTERN.finditer(expanded))
    for index, match in enumerate(matches):
        body_start = match.end()
        body_end = matches[index + 1].start() if index + 1 < len(matches) else len(expanded)
        text = expanded[body_start:body_end].strip()
        start = parse_timestamp(match.group("timestamp"))
        next_start = (
            parse_timestamp(matches[index + 1].group("timestamp"))
            if index + 1 < len(matches)
            else None
        )
        estimated_speech = max(0.4, len(text.split()) / 2.5)
        if next_start is not None:
            estimated_speech = min(estimated_speech, max(0.4, next_start - start))
        turns.append(
            {
                "speaker": match.group("speaker").strip(),
                "start": start,
                "speech_seconds": estimated_speech,
                "final_word_time": None,
                "text": text,
                "word_count": count_words(text),
            }
        )

    if not turns:
        raise ValueError("transcript contains no recognizable speaker turns")
    return turns, turns[-1]["start"] + turns[-1]["speech_seconds"]


def normalized_person_name(value):
    return re.sub(r"[^\w]+", " ", value.casefold()).strip()


def guest_speaker_key(episode, normalized_speaker):
    speaker_words = set(normalized_speaker.split())
    if not speaker_words:
        return ""

    for _, guest_name, _ in episode["guest_people"]:
        normalized_guest = normalized_person_name(guest_name)
        guest_words = set(normalized_guest.split())
        if (
            normalized_speaker == normalized_guest
            or (
                len(speaker_words) >= 2
                and speaker_words.issubset(guest_words)
            )
            or (
                len(guest_words) >= 2
                and guest_words.issubset(speaker_words)
            )
        ):
            return f"guest:{normalized_guest}"
    return ""


def classify_transcript_speakers(episode, turns):
    normalized_speakers = {
        normalized_person_name(turn["speaker"])
        for turn in turns
    }
    inferred_cohost_label = ""
    normalized_cohost = episode["cohost"].casefold()
    placeholder_speakers = {
        speaker for speaker in normalized_speakers if speaker.startswith("speaker_")
    }
    if (
        normalized_cohost
        and normalized_cohost not in normalized_speakers
        and len(placeholder_speakers) == 1
    ):
        inferred_cohost_label = next(iter(placeholder_speakers))

    classifications = {}
    for speaker in normalized_speakers:
        first_name = speaker.split(maxsplit=1)[0] if speaker else ""
        host = HOST_NAMES.get(speaker) or HOST_NAMES.get(first_name)
        if host and (host == "Conor" or host == episode["cohost"]):
            classifications[speaker] = (f"host:{host.casefold()}", "host")
            continue
        if speaker == inferred_cohost_label:
            classifications[speaker] = (f"host:{normalized_cohost}", "host")
            continue
        guest_key = guest_speaker_key(episode, speaker) if episode["guest"] else ""
        if guest_key:
            classifications[speaker] = (guest_key, "guest")

    return classifications


def transcript_indices(episode, transcript):
    turns, _ = parse_transcript(transcript)
    classifications = classify_transcript_speakers(episode, turns)
    turn_word_counts = [turn["word_count"] for turn in turns if turn["word_count"]]
    guest_word_counts = Counter()
    speaker_word_counts = Counter()
    speaker_names = {}

    for turn in turns:
        speaker = normalized_person_name(turn["speaker"])
        classification = classifications.get(speaker)
        if classification:
            speaker_key, role = classification
        else:
            speaker_key, role = f"person:{speaker}", "person"
        speaker_word_counts[speaker_key] += turn["word_count"]
        speaker_names.setdefault(speaker_key, turn["speaker"].strip())
        if role == "guest":
            guest_word_counts[speaker_key] += turn["word_count"]

    baf = (
        statistics.pstdev(turn_word_counts)
        if not episode["guest"] and turn_word_counts
        else None
    )
    return {
        "baf": baf,
        "guest_word_counts": dict(guest_word_counts),
        "speaker_word_counts": dict(speaker_word_counts),
        "speaker_names": speaker_names,
    }


def read_transcript_indices(episodes):
    transcript_episodes = [
        episode
        for episode in episodes
        if episode["number"] >= TRANSCRIPT_START_EPISODE
        and episode["buzzsprout_id"]
    ]

    def fetch(episode):
        url = TRANSCRIPT_URL.format(buzzsprout_id=episode["buzzsprout_id"])
        request = Request(url, headers={"User-Agent": "ADSP episode generator"})
        with urlopen(request, timeout=30) as response:
            charset = response.headers.get_content_charset() or "utf-8"
            transcript = response.read().decode(charset, errors="replace")
        return episode["number"], transcript_indices(episode, transcript)

    indices = {}
    failures = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        future_episodes = {
            executor.submit(fetch, episode): episode for episode in transcript_episodes
        }
        for future in as_completed(future_episodes):
            episode = future_episodes[future]
            try:
                number, metrics = future.result()
                indices[number] = metrics
            except Exception as error:
                failures.append(f"Episode {episode['number']}: {error}")

    if failures:
        raise RuntimeError(
            "could not read transcripts:\n  " + "\n  ".join(sorted(failures))
        )
    return indices


def existing_table_values(page):
    values = {}
    for line in page.splitlines():
        match = EXISTING_ROW_PATTERN.match(line)
        if not match:
            continue

        fields = [field.strip() for field in match.group("rest").split("|")]
        values[int(match.group("number"))] = {
            "title": match.group("title"),
            "duration": fields[0] if len(fields) >= 4 else "",
        }
    return values


def format_duration(seconds):
    minutes = seconds // 60
    if minutes < 60:
        return str(minutes)
    return f"{minutes // 60}:{minutes % 60:02d}"


def assign_episode_colors(episodes):
    color_index = -1
    previous_was_guest = False
    previous_episode = None
    colors = ("guest-orange", "guest-purple")
    tag_counts = Counter(tag for episode in episodes for tag in episode["tags"])
    recording_colors = {}

    for episode in episodes:
        if episode["trip"]:
            episode["color_class"] = "trip-green"
            previous_was_guest = False
            previous_episode = episode
            continue

        if episode["guest"]:
            recording_key = (
                episode["guest_identity"],
                episode["recorded_date"],
            )
            continued_recording = bool(
                episode["recorded_date"] and recording_key in recording_colors
            )
            same_guest = bool(
                previous_was_guest
                and episode["guest_identity"] == previous_episode["guest_identity"]
            )
            shared_event_tags = set()
            if previous_was_guest and episode["event"] and previous_episode["event"]:
                shared_event_tags = (
                    set(episode["tags"])
                    & set(previous_episode["tags"])
                    - GENERIC_EVENT_TAGS
                )
                shared_event_tags = {
                    tag
                    for tag in shared_event_tags
                    if tag_counts[tag] <= MAX_EVENT_SERIES_TAG_USES
                }

            if continued_recording:
                episode["color_class"] = recording_colors[recording_key]
                color_index = colors.index(episode["color_class"])
            elif not same_guest and not shared_event_tags:
                color_index = (color_index + 1) % len(colors)
                episode["color_class"] = colors[color_index]
            else:
                episode["color_class"] = colors[color_index]

            if episode["recorded_date"]:
                recording_colors.setdefault(recording_key, episode["color_class"])
        else:
            episode["color_class"] = ""
        previous_was_guest = episode["guest"]
        previous_episode = episode


def episode_url(episode):
    return f"https://adspthepodcast.com{episode_path(episode)}"


def episode_path(episode):
    return (
        f"/{episode['date'].replace('-', '/')}/"
        f"Episode-{episode['number']}.html"
    )


def total_duration_label(seconds):
    hours, remainder = divmod(seconds, 60 * 60)
    minutes = remainder // 60
    return f"{hours:,}h {minutes:02d}m"


def read_guest_metadata():
    metadata = json.loads(GUEST_METADATA_PATH.read_text(encoding="utf-8"))
    companies = metadata.get("companies", {})
    languages = metadata.get("languages", {})
    unknown_featured = set(metadata.get("featured_companies", [])) - set(companies)
    if unknown_featured:
        raise ValueError(
            "unknown featured companies in guest metadata: "
            + ", ".join(sorted(unknown_featured))
        )
    for name, details in metadata.get("guests", {}).items():
        company = details.get("company")
        if company and company not in companies:
            raise ValueError(f"unknown company {company!r} for guest {name!r}")
        unknown_languages = set(details.get("languages", [])) - set(languages)
        if unknown_languages:
            raise ValueError(
                f"unknown languages for guest {name!r}: "
                + ", ".join(sorted(unknown_languages))
            )
    known_guests = {
        normalized_person_name(name) for name in metadata.get("guests", {})
    }
    for company_key, company in companies.items():
        unknown_guests = {
            name
            for name in company.get("guests", [])
            if normalized_person_name(name) not in known_guests
        }
        if unknown_guests:
            raise ValueError(
                f"unknown guests for company {company_key!r}: "
                + ", ".join(sorted(unknown_guests))
            )
    metadata["guests_by_name"] = {
        normalized_person_name(name): details
        for name, details in metadata.get("guests", {}).items()
    }
    return metadata


def guest_badges(name, guest_metadata):
    guest = guest_metadata["guests_by_name"].get(normalized_person_name(name), {})
    logo_base_url = guest_metadata.get("logo_base_url", "").rstrip("/") + "/"
    badges = []

    company_key = guest.get("company")
    company = guest_metadata.get("companies", {}).get(company_key, {})
    if company:
        company_name = company["name"]
        latest_episode = guest_metadata["company_latest_episodes"][company_key]
        company_description = (
            f"Company: {company_name}. Latest guest episode: "
            f"{latest_episode['guest']}, Episode {latest_episode['episode']}"
        )
        badges.append(
            '<a class="guest-affiliation-badge guest-company-badge" '
            f'href="{html.escape(latest_episode["url"], quote=True)}" '
            f'title="{html.escape(company_description, quote=True)}" '
            f'aria-label="{html.escape(company_description, quote=True)}">'
            f'<img src="{html.escape(logo_base_url + company["logo"], quote=True)}" alt="">'
            "</a>"
        )

    for language_key in guest.get("languages", []):
        language = guest_metadata.get("languages", {}).get(language_key, {})
        if not language:
            continue
        language_name = language["name"]
        badges.append(
            '<a class="guest-affiliation-badge guest-language-badge" '
            f'href="/tags/#{html.escape(language["tag"], quote=True)}" '
            f'title="Language: {html.escape(language_name, quote=True)}" '
            f'aria-label="Language: {html.escape(language_name, quote=True)}">'
            f'<img src="{html.escape(logo_base_url + language["logo"], quote=True)}" alt="">'
            "</a>"
        )

    if not badges:
        return ""
    return '<span class="guest-affiliation-badges">' + "".join(badges) + "</span>"


def guest_name_html(name, tag_name, guest_metadata):
    rendered_name = html.escape(name)
    if tag_name:
        rendered_name = (
            f'<a href="/tags/#{html.escape(quote_plus(tag_name), quote=True)}">'
            f"{rendered_name}</a>"
        )
    return (
        '<span class="guest-identity">'
        f'<span class="guest-display-name">{rendered_name}</span>'
        f"{guest_badges(name, guest_metadata)}"
        "</span>"
    )


def guest_table_rows(guests, guest_metadata, indentation="            "):
    rows = []
    for guest in guests:
        name = guest_name_html(guest["name"], guest["tag_name"], guest_metadata)
        recordings = len(guest["recordings"])
        episodes = len(guest["episodes"])
        total_seconds = guest["total_seconds"]
        total_time = format_duration(total_seconds) if total_seconds is not None else "—"
        rows.append(
            f'{indentation}<tr data-guest="{html.escape(guest["name"].casefold(), quote=True)}" '
            f'data-recordings="{recordings}" data-episodes="{episodes}" '
            f'data-total-time="{total_seconds if total_seconds is not None else ""}">'
            f"<td>{name}</td>"
            f"<td>{recordings}</td>"
            f"<td>{episodes}</td>"
            f"<td>{total_time}</td>"
            "</tr>"
        )
    return rows


def cohost_class(cohost):
    return f"cohost-{cohost.casefold()}" if cohost else "cohost-unknown"


def latest_company_episodes(episodes, guest_metadata):
    latest_by_guest = {}
    for episode in episodes:
        for _, guest_name, _ in episode["guest_people"]:
            guest_key = normalized_person_name(guest_name)
            previous = latest_by_guest.get(guest_key)
            if previous is None or (episode["date"], episode["number"]) > (
                previous["date"],
                previous["number"],
            ):
                latest_by_guest[guest_key] = episode

    result = {}
    companies = guest_metadata["companies"]
    for company_key in guest_metadata["featured_companies"]:
        candidates = []
        for guest_name in companies[company_key].get("guests", []):
            episode = latest_by_guest.get(normalized_person_name(guest_name))
            if episode:
                candidates.append((episode["date"], episode["number"], guest_name, episode))

        if not candidates:
            raise ValueError(
                f"no episode found for a configured guest from {companies[company_key]['name']}"
            )

        _, _, guest_name, episode = max(candidates)
        result[company_key] = {
            "episode": episode["number"],
            "guest": guest_name,
            "title": episode["title"].replace(r"\|", "|"),
            "url": episode_path(episode),
        }

    return result


def render_conversation_stats(episodes, transcript_stats, guest_metadata):
    episode_by_number = {episode["number"]: episode for episode in episodes}
    transcript_entries = [
        (episode_by_number[number], metrics)
        for number, metrics in sorted(transcript_stats.items())
        if number in episode_by_number
    ]
    if not transcript_entries:
        return []

    baf_entries = [
        (episode, metrics)
        for episode, metrics in transcript_entries
        if not episode["guest"] and metrics["baf"] is not None
    ]
    guest_episode_entries = [
        (episode, metrics)
        for episode, metrics in transcript_entries
        if episode["guest"] and metrics["guest_word_counts"]
    ]
    baf_values = [metrics["baf"] for _, metrics in baf_entries]
    median_baf = statistics.median(baf_values) if baf_values else None
    median_baf_label = f"{median_baf:.1f}" if median_baf is not None else "—"
    max_baf = max(baf_values, default=0)
    baf_description = "; ".join(
        f'Episode {episode["number"]}: {metrics["baf"]:.1f}, {episode["cohost"] or "no co-host"}'
        for episode, metrics in baf_entries
    )

    guest_appearances = []
    for episode, metrics in guest_episode_entries:
        people_by_name = {
            normalized_person_name(name): name
            for _, name, _ in episode["guest_people"]
        }
        for speaker_key, words in metrics["guest_word_counts"].items():
            normalized_name = speaker_key.removeprefix("guest:")
            name = people_by_name.get(normalized_name, normalized_name.title())
            guest_appearances.append(
                {
                    "episode": episode,
                    "name": name,
                    "words": words,
                    "tag_name": guest_tag(name, episode["tag_values"]),
                }
            )

    guest_appearances.sort(
        key=lambda appearance: (
            appearance["episode"]["number"],
            appearance["name"].casefold(),
        )
    )
    median_guest_words = (
        statistics.median(
            appearance["words"] for appearance in guest_appearances
        )
        if guest_appearances
        else None
    )
    median_guest_words_label = (
        f"{median_guest_words:,.0f}"
        if median_guest_words is not None
        else "—"
    )

    speaker_episode_rows = []
    for episode, metrics in transcript_entries:
        people_by_name = {
            normalized_person_name(name): name
            for _, name, _ in episode["guest_people"]
        }

        def speaker_sort_key(speaker_key):
            if speaker_key == "host:conor":
                return 0, speaker_key
            if speaker_key == f'host:{episode["cohost"].casefold()}':
                return 1, speaker_key
            if speaker_key.startswith("guest:"):
                return 2, speaker_key
            return 3, speaker_key

        participants = []
        other_color_index = 0
        for speaker_key, words in sorted(
            metrics["speaker_word_counts"].items(),
            key=lambda item: speaker_sort_key(item[0]),
        ):
            if not words:
                continue
            tag_name = ""
            if speaker_key.startswith("host:"):
                name = speaker_key.removeprefix("host:").title()
            elif speaker_key.startswith("guest:"):
                normalized_name = speaker_key.removeprefix("guest:")
                name = people_by_name.get(
                    normalized_name,
                    metrics["speaker_names"].get(speaker_key, normalized_name.title()),
                )
                tag_name = guest_tag(name, episode["tag_values"])
            else:
                name = metrics["speaker_names"].get(
                    speaker_key,
                    speaker_key.removeprefix("person:").title(),
                )
                placeholder = re.fullmatch(
                    r"speaker[_ ]0*(\d+)", name, re.IGNORECASE
                )
                if placeholder:
                    name = f"Speaker {int(placeholder.group(1))}"

            color = HOST_SPEAKER_COLORS.get(speaker_key)
            if not color:
                color = OTHER_SPEAKER_COLORS[
                    other_color_index % len(OTHER_SPEAKER_COLORS)
                ]
                other_color_index += 1
            participants.append(
                {
                    "name": name,
                    "tag_name": tag_name,
                    "words": words,
                    "color": color,
                }
            )

        total_words = sum(participant["words"] for participant in participants)
        if total_words:
            speaker_episode_rows.append(
                {
                    "episode": episode,
                    "participants": participants,
                    "total_words": total_words,
                }
            )

    lines = [
        '    <section class="conversation-dynamics" aria-labelledby="conversation-dynamics">',
        '      <h2 id="conversation-dynamics">Conversation dynamics</h2>',
        '      <p class="episode-stat-note">Based on timestamped transcripts from '
        f'Episode {transcript_entries[0][0]["number"]} onward.</p>',
        '      <div class="conversation-index-overview">',
        '        <div class="conversation-index-card">',
        f'          <strong>{median_baf_label}</strong>',
        '          <span>median BAF</span>',
        f'          <small>{len(baf_entries)} non-guest episodes</small>',
        '        </div>',
        '        <div class="conversation-index-card">',
        f'          <strong>{median_guest_words_label}</strong>',
        '          <span>median words / guest</span>',
        f'          <small>{len(guest_appearances)} appearances · {len(guest_episode_entries)} episodes</small>',
        '        </div>',
        '        <div class="conversation-index-card">',
        f'          <strong>{len(transcript_entries)}</strong>',
        '          <span>transcripts measured</span>',
        f'          <small>Episodes {transcript_entries[0][0]["number"]}–{transcript_entries[-1][0]["number"]}</small>',
        '        </div>',
        '      </div>',
        '      <div class="conversation-index-definitions">',
        '        <p><strong>BAF (back-and-forth index)</strong> is calculated only for episodes without a guest. It is the population standard deviation of the number of words in each speaking turn. Lower means more consistently sized back-and-forth turns; higher means turn lengths vary more.</p>',
        '        <p><strong>Speaker word counts</strong> measure every identified person in every available transcript. The guest metric is calculated only for guest episodes, with each guest appearance measured separately.</p>',
        '      </div>',
        '      <section class="conversation-chart-panel" aria-labelledby="baf-over-time">',
        '        <h3 id="baf-over-time">BAF over time</h3>',
        '        <div class="conversation-chart-scroll">',
        f'          <div class="baf-chart" role="img" aria-label="BAF index by non-guest episode. {html.escape(baf_description, quote=True)}" style="--baf-columns: {len(baf_entries)}">',
    ]

    for index, (episode, metrics) in enumerate(baf_entries):
        height = 0 if not max_baf else 92 * metrics["baf"] / max_baf
        show_label = index % 5 == 0 or index == len(baf_entries) - 1
        episode_label = str(episode["number"]) if show_label else ""
        description = (
            f'Episode {episode["number"]}: BAF {metrics["baf"]:.1f}; '
            f'{episode["cohost"] or "no co-host"}'
        )
        lines.extend(
            [
                f'            <div class="baf-column" title="{html.escape(description, quote=True)}">',
                '              <span class="baf-bar-area">',
                f'                <span class="baf-bar {cohost_class(episode["cohost"])}" style="--bar-height: {height:.1f}%"></span>',
                '              </span>',
                f'              <span class="baf-episode-label">{episode_label}</span>',
                '            </div>',
            ]
        )

    lines.extend(
        [
            '          </div>',
            '        </div>',
            '        <div class="conversation-chart-legend" aria-label="Chart legend">',
            '          <span><i class="cohost-swatch cohost-bryce"></i>Bryce</span>',
            '          <span><i class="cohost-swatch cohost-ben"></i>Ben</span>',
            '        </div>',
            '      </section>',
        ]
    )

    speaker_lines = [
        '        <details class="conversation-chart-panel speaker-word-panel speaker-word-details" aria-labelledby="speaker-word-counts">',
        '          <summary><span id="speaker-word-counts">Words spoken by person</span></summary>',
        '          <p class="episode-stat-note">Each bar represents all identified words in one episode; exact counts appear alongside it.</p>',
        '          <div class="speaker-word-chart">',
    ]

    for row in speaker_episode_rows:
        episode = row["episode"]
        participant_description = "; ".join(
            f'{participant["name"]}: {participant["words"]:,} words'
            for participant in row["participants"]
        )
        speaker_lines.extend(
            [
                f'            <div class="speaker-word-row" title="{html.escape(episode["title"], quote=True)}">',
                f'              <a class="speaker-word-episode" href="{html.escape(episode_url(episode), quote=True)}" aria-label="Episode {episode["number"]}">{episode["number"]}</a>',
                f'              <span class="speaker-word-track" role="img" aria-label="Episode {episode["number"]}. {html.escape(participant_description, quote=True)}">',
            ]
        )
        for participant in row["participants"]:
            percentage = 100 * participant["words"] / row["total_words"]
            description = (
                f'{participant["name"]}: {participant["words"]:,} words '
                f'({percentage:.1f}%)'
            )
            speaker_lines.append(
                '                <span class="speaker-word-segment" '
                f'style="--speaker-width: {percentage:.2f}%; --speaker-color: {participant["color"]}" '
                f'title="{html.escape(description, quote=True)}"></span>'
            )
        speaker_lines.extend(
            [
                '              </span>',
                '              <span class="speaker-word-values">',
            ]
        )
        for participant in row["participants"]:
            name = guest_name_html(
                participant["name"], participant["tag_name"], guest_metadata
            )
            speaker_lines.append(
                '                <span class="speaker-word-person">'
                f'<i style="--speaker-color: {participant["color"]}"></i>'
                f'<span>{name}</span><strong>{participant["words"]:,}</strong></span>'
            )
        speaker_lines.extend(
            [
                '              </span>',
                '            </div>',
            ]
        )

    speaker_lines.extend(
        [
            '          </div>',
            '        </details>',
        ]
    )

    lines.extend(
        [
            '      <div class="conversation-detail-grid">',
            '        <section class="conversation-chart-panel cohost-index-panel" aria-labelledby="indices-by-cohost">',
            '          <h3 id="indices-by-cohost">By co-host</h3>',
            '          <div class="cohost-index-list">',
        ]
    )

    for cohost in ("Conor", "Bryce", "Ben"):
        if cohost == "Conor":
            cohost_baf_entries = [metrics for _, metrics in baf_entries]
            cohost_guest_words = [
                words
                for _, metrics in guest_episode_entries
                for words in metrics["guest_word_counts"].values()
            ]
        else:
            cohost_baf_entries = [
                metrics
                for episode, metrics in baf_entries
                if episode["cohost"] == cohost
            ]
            cohost_guest_words = [
                words
                for episode, metrics in guest_episode_entries
                if episode["cohost"] == cohost
                for words in metrics["guest_word_counts"].values()
            ]
        cohost_baf = (
            statistics.median(metrics["baf"] for metrics in cohost_baf_entries)
            if cohost_baf_entries
            else None
        )
        cohost_average_guest_words = (
            statistics.mean(cohost_guest_words)
            if cohost_guest_words
            else None
        )
        baf_label = f"{cohost_baf:.1f}" if cohost_baf is not None else "—"
        guest_words_label = (
            f"{cohost_average_guest_words:,.0f}"
            if cohost_average_guest_words is not None
            else "—"
        )
        transcript_label = (
            "non-guest transcript"
            if len(cohost_baf_entries) == 1
            else "non-guest transcripts"
        )
        guest_label = (
            "guest appearance" if len(cohost_guest_words) == 1 else "guest appearances"
        )
        lines.extend(
            [
                f'            <article class="cohost-index-card {cohost_class(cohost)}">',
                f'              <h4><i class="cohost-swatch {cohost_class(cohost)}"></i>{cohost}</h4>',
                f'              <p>{len(cohost_baf_entries)} {transcript_label}</p>',
                '              <dl>',
                f'                <div><dt>Median BAF</dt><dd>{baf_label}</dd></div>',
                f'                <div><dt>Guest words / appearance</dt><dd>{guest_words_label}</dd></div>',
                '              </dl>',
                f'              <small>{len(cohost_guest_words)} {guest_label}</small>',
                '            </article>',
            ]
        )

    lines.extend(
        [
            '          </div>',
            '        </section>',
        ]
    )
    lines.extend(speaker_lines)
    lines.extend(['      </div>', '    </section>'])
    return lines


def render_stats(episodes, durations, transcript_stats, guest_metadata):
    duration_entries = [
        (episode, durations[episode["number"]])
        for episode in episodes
        if episode["number"] in durations
    ]
    duration_values = [seconds for _, seconds in duration_entries]
    total_seconds = sum(duration_values)
    median_seconds = int(statistics.median(duration_values))
    longest_episode, longest_seconds = max(
        duration_entries, key=lambda entry: entry[1]
    )
    shortest_episode, shortest_seconds = min(
        duration_entries, key=lambda entry: entry[1]
    )

    guest_stats = {}
    guest_aliases = {}
    for episode in episodes:
        for key, name, profile_url in episode["guest_people"]:
            normalized_name = re.sub(r"[^\w]+", " ", name.casefold()).strip()
            aliases = (f"name:{normalized_name}", key)
            canonical_key = next(
                (guest_aliases[alias] for alias in aliases if alias in guest_aliases),
                aliases[0],
            )
            guest = guest_stats.setdefault(
                canonical_key,
                {
                    "name": name,
                    "profile_url": profile_url,
                    "episodes": set(),
                    "recordings": set(),
                    "tag_names": set(),
                },
            )
            for alias in aliases:
                guest_aliases[alias] = canonical_key
            if len(name) > len(guest["name"]):
                guest["name"] = name
            guest["episodes"].add(episode["number"])
            guest["recordings"].add(
                episode["recorded_date"] or f"episode-{episode['number']}"
            )
            tag_name = guest_tag(name, episode["tag_values"])
            if tag_name:
                guest["tag_names"].add(tag_name)

    for guest in guest_stats.values():
        guest_durations = [
            durations[number]
            for number in guest["episodes"]
            if number in durations
        ]
        guest["total_seconds"] = sum(guest_durations) if guest_durations else None
        guest["tag_name"] = min(guest["tag_names"], key=str.casefold, default="")

    all_guests = sorted(
        guest_stats.values(),
        key=lambda guest: (
            -len(guest["episodes"]),
            -len(guest["recordings"]),
            guest["name"].casefold(),
        ),
    )
    frequent_guests = all_guests[:10]
    additional_guests = all_guests[10:]

    histogram_buckets = [
        ("<20", 0, 20),
        ("20–29", 20, 30),
        ("30–39", 30, 40),
        ("40–49", 40, 50),
        ("50–59", 50, 60),
        ("60+", 60, None),
    ]
    histogram = []
    for label, start, end in histogram_buckets:
        count = sum(
            1
            for seconds in duration_values
            if seconds >= start * 60 and (end is None or seconds < end * 60)
        )
        histogram.append((label, count))
    max_bucket = max(count for _, count in histogram)
    histogram_description = "; ".join(
        f"{label} minutes: {count} episodes" for label, count in histogram
    )

    episodes_by_year = {}
    for episode in episodes:
        year = episode["date"][:4]
        totals = episodes_by_year.setdefault(year, {"all": 0, "guest": 0})
        totals["all"] += 1
        totals["guest"] += int(episode["guest"])

    guest_episode_count = sum(episode["guest"] for episode in episodes)
    guest_percentage = 100 * guest_episode_count / len(episodes)
    lines = [
        '<details class="episode-stats">',
        "  <summary>",
        '    <span class="episode-stats-summary-title">Explore episode stats</span>',
        '    <span class="episode-stats-summary-hint">Guests, lengths, conversation and trends</span>',
        "  </summary>",
        '  <div class="episode-stats-content">',
        '    <section aria-labelledby="stats-at-a-glance">',
        '      <h2 id="stats-at-a-glance">At a glance</h2>',
        '      <div class="episode-stat-cards">',
        '        <div class="episode-stat-card">',
        f'          <strong>{len(episodes):,}</strong><span>episodes listed</span>',
        "        </div>",
        '        <div class="episode-stat-card">',
        f'          <strong>{total_duration_label(total_seconds)}</strong><span>total listening time</span>',
        "        </div>",
        '        <div class="episode-stat-card">',
        f'          <strong>{format_duration(median_seconds)}</strong><span>median minutes</span>',
        "        </div>",
        '        <div class="episode-stat-card">',
        f'          <strong>{guest_percentage:.0f}%</strong><span>guest episodes</span>',
        "        </div>",
        "      </div>",
        '      <p class="episode-stat-highlight">',
        "        Longest episode:",
        f'<a href="{html.escape(episode_url(longest_episode), quote=True)}">',
        f'Episode {longest_episode["number"]}: {html.escape(longest_episode["title"].replace(r"\|", "|"))}</a>',
        f' ({format_duration(longest_seconds)})',
        "      </p>",
        '      <p class="episode-stat-highlight">',
        "        Shortest episode:",
        f'<a href="{html.escape(episode_url(shortest_episode), quote=True)}">',
        f'Episode {shortest_episode["number"]}: {html.escape(shortest_episode["title"].replace(r"\|", "|"))}</a>',
        f' ({format_duration(shortest_seconds)})',
        "      </p>",
        "    </section>",
    ]

    guest_lines = [
        '    <section aria-labelledby="frequent-guests">',
        '      <h2 id="frequent-guests">Most frequent guests</h2>',
        '      <p class="episode-stat-note">Recordings are counted by unique recorded date; one recording can become several episodes. Logo badges link to company sites and language episode tags.</p>',
        '      <div class="episode-stats-table-wrapper">',
        '        <table class="frequent-guests-table">',
        "          <thead>",
        "            <tr>",
        '              <th><button type="button" class="guest-sort" data-sort-key="guest" data-sort-type="text">Guest</button></th>',
        '              <th><button type="button" class="guest-sort" data-sort-key="recordings" data-sort-type="number">Recordings</button></th>',
        '              <th><button type="button" class="guest-sort" data-sort-key="episodes" data-sort-type="number">Episodes</button></th>',
        '              <th><button type="button" class="guest-sort" data-sort-key="total-time" data-sort-type="number">Total Time</button></th>',
        "            </tr>",
        "          </thead>",
        "          <tbody>",
    ]

    guest_lines.extend(guest_table_rows(frequent_guests, guest_metadata))

    if additional_guests:
        guest_lines.extend(
            [
                "          </tbody>",
                '          <tbody id="additional-guests" hidden>',
            ]
        )
        guest_lines.extend(guest_table_rows(additional_guests, guest_metadata))
        guest_lines.extend(
            [
                "          </tbody>",
            ]
        )
    else:
        guest_lines.append("          </tbody>")

    guest_lines.extend(
        [
            "        </table>",
            "      </div>",
        ]
    )

    if additional_guests:
        guest_lines.append(
            '      <button type="button" class="more-guests-toggle" '
            'aria-expanded="false" aria-controls="additional-guests" '
            f'data-show-label="Show {len(additional_guests)} more guests" '
            'data-hide-label="Show fewer guests">'
            f'Show {len(additional_guests)} more guests</button>'
        )

    guest_lines.append("    </section>")

    lines.extend(
        [
            '    <div class="episode-chart-grid">',
            '      <section aria-labelledby="episode-lengths">',
            '        <h2 id="episode-lengths">Episode lengths</h2>',
            '        <p class="episode-stat-note">Number of episodes in each duration range.</p>',
            f'        <div class="episode-histogram" role="img" aria-label="{html.escape(histogram_description, quote=True)}">',
        ]
    )

    for label, count in histogram:
        height = 0 if not max_bucket else round(85 * count / max_bucket)
        lines.extend(
            [
                '          <div class="episode-histogram-column">',
                '            <div class="episode-histogram-bar-area">',
                f"              <span>{count}</span>",
                f'              <span class="episode-histogram-bar" style="--bar-height: {height}%"></span>',
                "            </div>",
                f"            <span>{html.escape(label)}</span>",
                "          </div>",
            ]
        )

    lines.extend(
        [
            "        </div>",
            "      </section>",
            '      <section aria-labelledby="guest-episodes-over-time">',
            '        <h2 id="guest-episodes-over-time">Guest episodes over time</h2>',
            '        <p class="episode-stat-note">Share of releases featuring at least one guest.</p>',
            '        <div class="guest-share-chart">',
        ]
    )

    for year, totals in sorted(episodes_by_year.items()):
        percentage = 100 * totals["guest"] / totals["all"]
        lines.extend(
            [
                f'          <div class="guest-share-row" aria-label="{year}: {totals["guest"]} of {totals["all"]} episodes, {percentage:.1f} percent">',
                f"            <span>{year}</span>",
                '            <span class="guest-share-track">',
                f'              <span class="guest-share-fill" style="width: {percentage:.1f}%"></span>',
                "            </span>",
                f"            <strong>{percentage:.0f}%</strong>",
                "          </div>",
            ]
        )

    lines.extend(
        [
            "        </div>",
            "      </section>",
            "    </div>",
        ]
    )
    lines.extend(guest_lines)
    lines.extend(render_conversation_stats(episodes, transcript_stats, guest_metadata))
    lines.extend(["  </div>", "</details>"])
    return "\n".join(lines)


def render_table(episodes, durations, existing_values):
    assign_episode_colors(episodes)
    lines = [
        '<div class="episodes-table-wrapper" markdown="1">',
        "",
        '| <button type="button" class="episodes-sort" data-sort-key="number">#</button> | Title | <button type="button" class="episodes-sort" data-sort-key="duration">Duration</button> | Co-host | Release Date |',
        "| :-: | :---- | :------: | :-----: | :----------: |",
    ]

    for episode in reversed(episodes):
        number = episode["number"]
        previous = existing_values.get(number, {})
        title = previous.get("title") or episode["title"]
        duration = (
            format_duration(durations[number])
            if number in durations
            else previous.get("duration") or "—"
        )
        cohost = episode["cohost"] or "—"
        url = episode_url(episode)
        classes = ".episode-title"
        if episode["color_class"]:
            classes += f" .{episode['color_class']}"

        lines.append(
            f"| {number} | [{title}]({url}){{: {classes} }} | "
            f"{duration} | {cohost} | {episode['date']} |"
        )

    lines.extend(["{: .episodes-table }", "", "</div>"])
    return "\n".join(lines)


def render_page(current_page, stats, table):
    generated = "\n".join(
        [
            GENERATED_START,
            "<!-- Existing title text is preserved when generate_episodes.py runs. -->",
            stats,
            table,
            GENERATED_END,
        ]
    )

    if GENERATED_START in current_page and GENERATED_END in current_page:
        pattern = re.compile(
            rf"{re.escape(GENERATED_START)}.*?{re.escape(GENERATED_END)}",
            re.DOTALL,
        )
        return pattern.sub(generated, current_page)

    table_start = re.search(r"^\|\s*#\s*\|", current_page, re.MULTILINE)
    if not table_start:
        raise ValueError(f"could not find the episodes table in {EPISODES_PAGE}")
    return current_page[: table_start.start()] + generated + "\n"


def main():
    args = parse_args()
    current_page = EPISODES_PAGE.read_text(encoding="utf-8")
    existing_values = existing_table_values(current_page)
    episodes = read_posts()
    guest_metadata = read_guest_metadata()
    company_episodes = latest_company_episodes(episodes, guest_metadata)
    guest_metadata["company_latest_episodes"] = company_episodes
    durations = read_durations(args.feed_file)
    transcript_stats = read_transcript_indices(episodes)
    stats = render_stats(episodes, durations, transcript_stats, guest_metadata)
    table = render_table(episodes, durations, existing_values)
    generated_page = render_page(current_page, stats, table)
    generated_company_episodes = (
        json.dumps(company_episodes, ensure_ascii=False, indent=2) + "\n"
    )
    current_company_episodes = (
        COMPANY_EPISODES_PATH.read_text(encoding="utf-8")
        if COMPANY_EPISODES_PATH.exists()
        else ""
    )
    page_changed = generated_page != current_page
    company_episodes_changed = generated_company_episodes != current_company_episodes

    if not page_changed and not company_episodes_changed:
        print("✅ - Episodes table and company links are up to date")
        return 0

    if args.check:
        print(
            "❌ - Generated episode data is out of date; "
            "run python3 generate_episodes.py"
        )
        return 1

    if page_changed:
        EPISODES_PAGE.write_text(generated_page, encoding="utf-8")
        print(f"🔧 - Generated {len(episodes)} rows in {EPISODES_PAGE.relative_to(ROOT)}")
    if company_episodes_changed:
        COMPANY_EPISODES_PATH.write_text(generated_company_episodes, encoding="utf-8")
        print(
            "🔧 - Generated latest company appearances in "
            f"{COMPANY_EPISODES_PATH.relative_to(ROOT)}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
