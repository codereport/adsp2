#!/usr/bin/env python3

import os
import re
import json
import html
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, parse_qs
from urllib.request import Request, urlopen

from generate_episodes import TRANSCRIPTS_PATH, canonical_guest_name, guest_people, post_tag_values

ROOT = Path(__file__).resolve().parent
# Employers whose logos are intentionally omitted from the homepage. Remove a
# company here when adding its logo; newly encountered employers still warn.
LOGOS_NOT_INCLUDED = {
    "Collège Lionel-Groulx",
    "Dyalog",
    "Genki Robotics",
    "Gregory Consulting",
    "LADE GmbH",
    "NV Michel Van de Wiele",
    "TurtleSec",
    "Université de Sherbrooke",
    "Vendr",
    "YOW! Conferences",
}
EMPLOYER_FIELD = re.compile(
    r"^\*\*Employer as of recording:\*\*[ \t]*(?P<value>[^\r\n]*)",
    re.MULTILINE | re.IGNORECASE,
)


def company_name_key(name):
    return re.sub(r"[\W_]+", "", name.casefold())


def guest_employer_inventory(posts_dir):
    """Read recording-time employers, including every bio in multi-guest posts."""
    employers = defaultdict(set)
    unconfirmed = []
    for path in posts_dir.glob("*Episode-*.md"):
        number_match = re.search(r"Episode-(\d+)\.md$", path.name)
        if not number_match:
            continue
        number = int(number_match.group(1))
        content = path.read_text(encoding="utf-8")
        uncertain_lines = []
        uncertain_guests = set()
        bio_start = 0
        for match in EMPLOYER_FIELD.finditer(content):
            people = guest_people(content[bio_start:match.start()], "", set())
            guest = canonical_guest_name(people[0][1]) if people else "Unknown guest"
            bio_start = match.end()
            value = re.sub(r"\[([^]]+)\]\([^)]+\)", r"\1", match["value"])
            value = html.unescape(re.sub(r"<[^>]+>", "", value)).strip()
            for employer in value.split(";"):
                employer = employer.strip()
                if company_name_key(employer) in {"", "unconfirmed", "notconfirmed"}:
                    uncertain_lines.append(content.count("\n", 0, match.start()) + 1)
                    uncertain_guests.add(guest)
                    continue
                status = employer.split("(", 1)[0].strip().casefold()
                if status in {"independent", "self-employed", "self employed", "retired"}:
                    continue
                employers[employer].add(number)
        if uncertain_lines:
            unconfirmed.append({
                "episode": number, "path": path, "lines": sorted(set(uncertain_lines)),
                "guests": sorted(uncertain_guests),
            })
    return sorted(unconfirmed, key=lambda item: item["episode"]), dict(employers)


def episode_ranges(episodes):
    ranges = []
    for number in sorted(set(episodes)):
        if ranges and number == ranges[-1][1] + 1:
            ranges[-1][1] = number
        else:
            ranges.append([number, number])
    return ", ".join(str(start) if start == end else f"{start}–{end}" for start, end in ranges)


class HomepageImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.names = set()

    def handle_starttag(self, tag, attributes):
        if tag != "img":
            return
        attributes = dict(attributes)
        name, source = attributes.get("alt", ""), attributes.get("src", "")
        if name and source and "{{" not in name + source:
            self.names.add(company_name_key(name))


def homepage_company_names(metadata, homepage):
    """Resolve the homepage's featured-company loop and any literal logo images."""
    homepage = re.sub(r"<!--.*?-->", "", homepage, flags=re.DOTALL)
    homepage = re.sub(
        r"{%[-]?\s*comment\s*[-]?%}.*?{%[-]?\s*endcomment\s*[-]?%}",
        "", homepage, flags=re.DOTALL,
    )
    images = HomepageImages()
    images.feed(homepage)
    covered = set(images.names)
    loops = re.finditer(
        r"{%[-]?\s*for\s+(?P<key>\w+)\s+in\s+site\.data\.guest_metadata\.featured_companies\s*[-]?%}"
        r"(?P<body>.*?){%[-]?\s*endfor\s*[-]?%}", homepage, re.DOTALL,
    )
    for loop in loops:
        assignment = re.search(
            r"assign\s+(\w+)\s*=\s*site\.data\.guest_metadata\.companies\[\s*"
            + re.escape(loop["key"]) + r"\s*\]", loop["body"],
        )
        if not assignment:
            continue
        logo_reference = re.compile(r"{{\s*" + re.escape(assignment[1]) + r"\.logo\s*}}")
        renders_logo = False
        for tag in re.findall(r"<img\b[^>]*>", loop["body"], re.DOTALL):
            source = re.search(r'''\bsrc\s*=\s*(["'])(.*?)\1''', tag, re.DOTALL)
            if source and logo_reference.search(source[2]):
                renders_logo = True
                break
        if not renders_logo:
            continue
        for key in metadata.get("featured_companies", []):
            company = metadata.get("companies", {}).get(key, {})
            if company.get("logo"):
                covered.update(company_name_key(name) for name in [key, company.get("name", ""), *company.get("aliases", [])])
    return covered


def missing_employer_logos(employers, metadata, homepage, logos_not_included=()):
    companies = metadata.get("companies", {})
    aliases = {}
    for key, company in companies.items():
        for name in [key, company["name"], *company.get("aliases", [])]:
            aliases[company_name_key(name)] = key
    covered = homepage_company_names(metadata, homepage)
    excluded = {company_name_key(name) for name in logos_not_included}
    missing = {}
    for employer, episodes in employers.items():
        normalized = company_name_key(employer)
        key = aliases.get(normalized)
        company = companies.get(key, {})
        names = {normalized}
        if company:
            names.update(company_name_key(name) for name in [key, company["name"], *company.get("aliases", [])])
        if (covered | excluded) & names:
            continue
        if not company:
            reason = "not in the company logo catalog"
        elif not company.get("logo"):
            reason = "no logo configured"
        elif key not in metadata.get("featured_companies", []):
            reason = "not in featured_companies"
        else:
            reason = "logo image not rendered by the home layout"
        identity = key or normalized
        entry = missing.setdefault(identity, {"company": company.get("name", employer), "episodes": set(), "reason": reason})
        entry["episodes"].update(episodes)
    return sorted(missing.values(), key=lambda item: item["company"].casefold())


def report_guest_employers(root):
    unconfirmed, employers = guest_employer_inventory(root / "_posts")
    print("EMPLOYER CHECKS")
    if unconfirmed:
        print(f"⚠️ - Unconfirmed employers in {len(unconfirmed)} episodes")
        episodes_by_guest = defaultdict(set)
        for entry in unconfirmed:
            for guest in entry["guests"]:
                episodes_by_guest[guest].add(entry["episode"])
        for guest, episodes in sorted(episodes_by_guest.items(), key=lambda item: (min(item[1]), item[0])):
            label = "episode" if len(episodes) == 1 else "episodes"
            print(f"  {guest}: {label} {episode_ranges(episodes)}")
    else:
        print("✅ - No unconfirmed employers")

    metadata = json.loads((root / "_data" / "guest_metadata.json").read_text(encoding="utf-8"))
    homepage = (root / "_layouts" / "home.html").read_text(encoding="utf-8")
    missing = missing_employer_logos(employers, metadata, homepage, LOGOS_NOT_INCLUDED)
    print("HOMEPAGE COMPANY LOGO CHECKS")
    if missing:
        print(f"⚠️ - Missing homepage logos for {len(missing)} guest employers")
        for entry in missing:
            episodes = episode_ranges(entry["episodes"])
            print(f"  {entry['company']}: episodes {episodes} ({entry['reason']})")
    else:
        print("✅ - All included guest employers have homepage logos")


def main():
    os.chdir(ROOT)
    # Posts
    print("POST CHECKS")

    # Episode Number in Title
    problem = False
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        num = int(post_name[:-3].split("-")[-1])
        with open("_posts/" + post_name) as post:
            for line in post:
                if "title:" in line and num != 110 and num != 200:
                    if int(line.split()[2][:-1]) != num:
                        problem = True
    print(("❌" if problem else "✅") + " - Episode Number in Title")

    # Episode Number in Link to Website (Text)
    problem = False
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        num = int(post_name[:-3].split("-")[-1])
        with open("_posts/" + post_name) as post:
            idx = 3 if num < 115 else 4
            for line in post:
                if "Link to Episode" in line:
                    if int(line.split()[idx]) != num:
                        problem = True
    print(("❌" if problem else "✅") + " - Episode Number in Link to Website (Text)")

    # Date in Link to Website (Link)
    problem = False
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        date = post_name[:10]
        with open("_posts/" + post_name) as post:
            idx = 3 if num < 115 else 4
            for line in post:
                if "Link to Episode" in line:
                    if "-".join(line.split("/")[3:6]) != date:
                        problem = True
    print(("❌" if problem else "✅") + " - Date in Link to Website (Link)")

    # Date in Release Date
    problem = False
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        date = post_name[:10]
        with open("_posts/" + post_name) as post:
            idx = 3 if num < 115 else 4
            for line in post:
                if "Date Released:" in line:
                    if line.strip().split()[-1] != date:
                        problem = True
    print(("❌" if problem else "✅") + " - Date in Release Date")

    # Discussion Link Issue Number
    problem = False
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        num = int(post_name[:-3].split("-")[-1])
        with open("_posts/" + post_name) as post:
            for line in post:
                if "Discuss this episode" in line:
                    # Ep 115 started with Issue 5 (so subtract 110)
                    actual_num = (
                        num
                        - 110
                        + (num > 116)
                        + (num > 151)
                        + ((num > 181) * 3)
                        + ((num > 184) * 4)
                        + ((num > 260))
                        + ((num > 269))
                        + ((num > 274))
                    )
                    if actual_num != int(line[:-2].split("/")[-1]):
                        print(num, actual_num, int(line[:-2].split("/")[-1]))
                        problem = True
    print(("❌" if problem else "✅") + " - Discussion Link Issue Number")

    # Dates Differ by 7 Days
    problem = False
    dates = []
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        date = post_name[:10]
        dates.append(datetime.strptime(date, "%Y-%m-%d"))
    dates.sort()
    for a, b in zip(dates[:-1], dates[1:]):
        if (b - a).days != 7:
            problem = True
    print(("❌" if problem else "✅") + " - Dates Differ by 7 Days")

    # No Unknown or Placeholder Speaker Tags
    problem = False
    for post_name in sorted(os.listdir("_posts/")):
        if not post_name.endswith(".md"):
            continue
        with open("_posts/" + post_name) as post:
            tags = post_tag_values(post.read())
        placeholder_tags = [
            tag for tag in tags
            if tag.strip().casefold() == "unknown"
            or tag.strip().casefold().startswith("speaker_")
        ]
        if placeholder_tags:
            print(f"  {post_name}: placeholder tag(s) {', '.join(placeholder_tags)}")
            problem = True
    print(("❌" if problem else "✅") + " - No Unknown or Placeholder Speaker Tags")

    # Unique Buzzsprout IDs
    problem = False
    buzzsprout_ids = {}
    transcript_buzzsprout_ids = {}
    try:
        available_transcript_ids = set(json.loads(TRANSCRIPTS_PATH.read_text()))
    except (OSError, ValueError, TypeError) as error:
        print(f"❌ - Could not read generated transcript availability ({error}); run generate_episodes.py")
        available_transcript_ids = set()
    for post_name in sorted(os.listdir("_posts/")):
        if not post_name.endswith(".md"):
            continue
        with open("_posts/" + post_name) as post:
            content = post.read()

        front_matter_match = re.search(r"^buzzsprout-id:\s*(\d+)\s*$", content, re.MULTILINE)
        player_match = re.search(r"buzzsprout-player-(\d+)", content)
        id_match = front_matter_match or player_match
        if not id_match:
            print(f"❌ - Missing Buzzsprout ID: {post_name}")
            problem = True
            continue

        bid = id_match.group(1)
        if bid in buzzsprout_ids:
            if not problem:
                print("❌ - Unique Buzzsprout IDs")
            print(f"  Duplicate buzzsprout-id {bid}: {buzzsprout_ids[bid]} and {post_name}")
            problem = True
        else:
            buzzsprout_ids[bid] = post_name

        if bid in available_transcript_ids:
            transcript_buzzsprout_ids[bid] = post_name
    if not problem:
        print("✅ - Unique Buzzsprout IDs")

    # No Unknown or Placeholder Speakers in Buzzsprout Transcripts
    transcript_cache_path = ".transcript-check-cache"
    transcript_cache_version = "unknown-or-speaker-v2"
    try:
        with open(transcript_cache_path) as cache:
            cache_lines = [line.strip() for line in cache if line.strip()]
    except FileNotFoundError:
        cache_lines = []

    passed_transcript_ids = (
        {line for line in cache_lines[1:] if line.isdigit()}
        if cache_lines[:1] == [f"version:{transcript_cache_version}"]
        else set()
    )

    problem = False
    newly_passed_transcript_ids = set()
    placeholder_label = r"(?P<label>unknown|speaker(?:[ _-]*#?[ _-]*\d+|[ _-]+#)?)"
    placeholder_speaker_patterns = (
        re.compile(
            rf"<cite(?:\s[^>]*)?>\s*{placeholder_label}\s*</cite>",
            re.IGNORECASE,
        ),
        re.compile(
            rf"(?:<!--block-->|<br\s*/?>\s*<br\s*/?>)\s*"
            rf"{placeholder_label}\s*:\s*\d{{1,2}}:\d{{2}}",
            re.IGNORECASE,
        ),
    )

    for bid, post_name in sorted(
        transcript_buzzsprout_ids.items(), key=lambda item: item[0]
    ):
        if not bid or bid in passed_transcript_ids:
            continue

        transcript_url = f"https://www.buzzsprout.com/1501960/{bid}/transcript"
        request = Request(transcript_url, headers={"User-Agent": "ADSP transcript checker"})
        try:
            with urlopen(request, timeout=15) as response:
                charset = response.headers.get_content_charset() or "utf-8"
                transcript = response.read().decode(charset, errors="replace")
        except (HTTPError, URLError, TimeoutError) as error:
            print(f"  {post_name}: could not check {transcript_url} ({error})")
            problem = True
            continue

        placeholder_labels = {
            match.group("label").strip()
            for pattern in placeholder_speaker_patterns
            for match in pattern.finditer(transcript)
        }
        if placeholder_labels:
            labels = ", ".join(sorted(placeholder_labels, key=str.casefold))
            print(
                f"  {post_name}: placeholder speaker label(s) {labels} "
                f"in {transcript_url}"
            )
            problem = True
        else:
            newly_passed_transcript_ids.add(bid)

    if newly_passed_transcript_ids:
        passed_transcript_ids.update(newly_passed_transcript_ids)
        with open(transcript_cache_path, "w") as cache:
            cache.write(f"version:{transcript_cache_version}\n")
            for bid in sorted(passed_transcript_ids, key=int):
                cache.write(f"{bid}\n")

    print(
        ("❌" if problem else "✅")
        + " - No Unknown or Placeholder Speakers in Transcripts"
    )

    # Episodes
    print("EPISODES CHECKS")

    # Number, Title & Link in Episodes.md
    problem_title = False
    problem_date = False
    problem_link_date = False
    problem_link_num = False
    episodes_rows = {}
    episodes_row_pattern = re.compile(
        r"^\|\s*(?P<num>\d+)\s*\|\s*\[(?P<title>.*)\]"
        r"\(https://adspthepodcast\.com/"
        r"(?P<link_date>\d{4}/\d{2}/\d{2})/Episode-(?P<link_num>\d+)\.html\)"
        r"(?:\{:[^}]*\})?\s*\|\s*[^|]*\|\s*[^|]*\|"
        r"\s*(?P<release_date>\d{4}-\d{2}-\d{2})\s*\|"
    )

    with open("pages/episodes.md") as file:
        for line in file:
            match = episodes_row_pattern.match(line)
            if match:
                episodes_rows[int(match.group("num"))] = match.groupdict()

    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        num = int(post_name[:-3].split("-")[-1])
        date = post_name[:10]
        row = episodes_rows.get(num)

        if not row:
            problem_title = True
            problem_date = True
            problem_link_date = True
            problem_link_num = True
            continue

        if not row["title"].strip():
            problem_title = True
        if row["release_date"] != date:
            problem_date = True
        if row["link_date"].replace("/", "-") != date:
            problem_link_date = True
        if int(row["link_num"]) != num:
            problem_link_num = True

    print(("❌" if problem_date else "✅") + " - Episode Date")
    print(("❌" if problem_title else "✅") + " - Episode Title")
    print(("❌" if problem_link_date else "✅") + " - Episode Date in Link")
    print(("❌" if problem_link_num else "✅") + " - Episode Number in Link")

    # Hoogle Translate by-algo-id Links Have Numeric q= Parameter
    print("HOOGLE TRANSLATE CHECKS")
    problem = False
    invalid_links = []
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        with open("_posts/" + post_name) as post:
            for line_num, line in enumerate(post, 1):
                # Find all Hoogle Translate links in the line
                urls = re.findall(r"https://hoogletranslate\.com/[^\s\)]+", line)
                for url in urls:
                    # Parse the URL and query parameters
                    parsed = urlparse(url)
                    params = parse_qs(parsed.query)

                    # Check if type=by-algo-id
                    if "type" in params and "by-algo-id" in params["type"]:
                        # Check if q parameter exists and is numeric
                        if "q" in params:
                            q_value = params["q"][0]
                            if not q_value.isdigit():
                                problem = True
                                invalid_links.append((post_name, line_num, url, q_value))
                        else:
                            problem = True
                            invalid_links.append((post_name, line_num, url, "MISSING"))

    if invalid_links:
        print(f"❌ - Hoogle Translate by-algo-id Links Have Numeric q= Parameter")
        for post_name, line_num, url, q_value in invalid_links:
            print(f"  {post_name}:{line_num} - q={q_value} (should be numeric)")
    else:
        print("✅ - Hoogle Translate by-algo-id Links Have Numeric q= Parameter")

    # Hoogle Translate Link Format (Hoogle Translate first)
    problem = False
    fixed_files = []
    pattern = re.compile(r"\[`([^`]+)` Hoogle Translate\]")
    for post_name in os.listdir("_posts/"):
        if not post_name.endswith(".md"):
            continue
        file_path = "_posts/" + post_name
        with open(file_path) as post:
            content = post.read()

        # Find and fix any instances of "`algorithm` Hoogle Translate"
        matches = pattern.findall(content)
        if matches:
            new_content = content
            for algo in matches:
                old_pattern = f"[`{algo}` Hoogle Translate]"
                new_pattern = f"[Hoogle Translate `{algo}`]"
                new_content = new_content.replace(old_pattern, new_pattern)

            if new_content != content:
                with open(file_path, "w") as post:
                    post.write(new_content)
                fixed_files.append((post_name, len(matches)))
                problem = True

    if fixed_files:
        print(f"🔧 - Fixed Hoogle Translate Link Format (Hoogle Translate now first)")
        for post_name, count in fixed_files:
            print(f"  {post_name} - Fixed {count} link(s)")
    else:
        print("✅ - Hoogle Translate Link Format (Hoogle Translate first)")

    report_guest_employers(ROOT)


if __name__ == "__main__":
    main()
