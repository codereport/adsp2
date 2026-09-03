#!/usr/bin/env python3

import argparse
from collections import Counter
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parent
POSTS_DIR = ROOT / "_posts"
EPISODES_PAGE = ROOT / "pages" / "episodes.md"
FEED_URL = "https://feeds.buzzsprout.com/1501960.rss"
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

POST_NAME_PATTERN = re.compile(
    r"(?P<date>\d{4}-\d{2}-\d{2})-Episode-(?P<number>\d+)\.md$"
)
EXISTING_ROW_PATTERN = re.compile(
    r"^\|\s*(?P<number>\d+)\s*\|\s*\[(?P<title>.*)\]"
    r"\(https://adspthepodcast\.com/[^)]*/Episode-\d+\.html\)"
    r"(?:\{:[^}]*\})?\s*\|(?P<rest>.*)$"
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


def title_from_post(post, episode_number):
    title = front_matter_value(post, "title")
    return re.sub(
        rf"^Episode\s+{episode_number}\s*:\s*", "", title, flags=re.IGNORECASE
    ).replace("|", r"\|")


def post_tags(post):
    tags = front_matter_value(post, "tags").strip("[]")
    return tuple(
        tag.strip().strip("\"'").casefold()
        for tag in tags.split(",")
        if tag.strip()
    )


def about_guest_section(post):
    match = re.search(
        r"^(?:\*\*About the Guests?:\*\*|### About the Guests?)\s*\n"
        r"(?P<body>.*?)(?=^(?:###\s|\*\*[^*\n]+:\*\*)|\Z)",
        post,
        re.MULTILINE | re.DOTALL,
    )
    return match.group("body").strip() if match else ""


def is_guest_episode(tags, about_guest):
    return bool(
        {"guest", "guests"} & set(tags)
        or about_guest
    )


def guest_identity(about_guest, tags):
    if about_guest:
        profile_urls = re.findall(
            r"^(?:For\s+)?\[[^]]+\]\(([^)]+)\)", about_guest, re.MULTILINE
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
        tags = post_tags(post)
        about_guest = about_guest_section(post)
        guest = is_guest_episode(tags, about_guest)
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
                "guest": guest,
                "guest_identity": guest_identity(about_guest, tags),
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


def render_table(episodes, durations, existing_values):
    assign_episode_colors(episodes)
    lines = [
        '<div class="episodes-table-wrapper" markdown="1">',
        "",
        "| # | Title | Duration | Co-host | Release Date |",
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
        url = (
            f"https://adspthepodcast.com/{episode['date'].replace('-', '/')}/"
            f"Episode-{number}.html"
        )
        classes = ".episode-title"
        if episode["color_class"]:
            classes += f" .{episode['color_class']}"

        lines.append(
            f"| {number} | [{title}]({url}){{: {classes} }} | "
            f"{duration} | {cohost} | {episode['date']} |"
        )

    lines.extend(["{: .episodes-table }", "", "</div>"])
    return "\n".join(lines)


def render_page(current_page, table):
    generated = "\n".join(
        [
            GENERATED_START,
            "<!-- Existing title text is preserved when generate_episodes.py runs. -->",
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
    durations = read_durations(args.feed_file)
    table = render_table(episodes, durations, existing_values)
    generated_page = render_page(current_page, table)

    if generated_page == current_page:
        print("✅ - Episodes table is up to date")
        return 0

    if args.check:
        print("❌ - Episodes table is out of date; run python3 generate_episodes.py")
        return 1

    EPISODES_PAGE.write_text(generated_page, encoding="utf-8")
    print(f"🔧 - Generated {len(episodes)} rows in {EPISODES_PAGE.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
