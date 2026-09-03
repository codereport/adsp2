#!/usr/bin/env python3

import argparse
from collections import Counter
import html
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


def episode_url(episode):
    return (
        f"https://adspthepodcast.com/{episode['date'].replace('-', '/')}/"
        f"Episode-{episode['number']}.html"
    )


def total_duration_label(seconds):
    hours, remainder = divmod(seconds, 60 * 60)
    minutes = remainder // 60
    return f"{hours:,}h {minutes:02d}m"


def guest_table_rows(guests, indentation="            "):
    rows = []
    for guest in guests:
        name = html.escape(guest["name"])
        recordings = len(guest["recordings"])
        episodes = len(guest["episodes"])
        total_seconds = guest["total_seconds"]
        total_time = format_duration(total_seconds) if total_seconds is not None else "—"
        if guest["tag_name"]:
            name = (
                f'<a href="/tags/#{html.escape(quote_plus(guest["tag_name"]), quote=True)}">'
                f"{name}</a>"
            )
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


def render_stats(episodes, durations):
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
        '    <span class="episode-stats-summary-hint">Guests, lengths and trends</span>',
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
        '      <p class="episode-stat-note">Recordings are counted by unique recorded date; one recording can become several episodes.</p>',
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

    guest_lines.extend(guest_table_rows(frequent_guests))

    if additional_guests:
        guest_lines.extend(
            [
                "          </tbody>",
                '          <tbody id="additional-guests" hidden>',
            ]
        )
        guest_lines.extend(guest_table_rows(additional_guests))
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
    durations = read_durations(args.feed_file)
    stats = render_stats(episodes, durations)
    table = render_table(episodes, durations, existing_values)
    generated_page = render_page(current_page, stats, table)

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
