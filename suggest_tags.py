#!/usr/bin/env python3
"""Suggest tags for one episode from its public Buzzsprout transcript, without writing files."""

import argparse
from collections import Counter, defaultdict
import json
import os
from pathlib import Path
import re
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from generate_episodes import (
    TRANSCRIPT_URL,
    classify_transcript_speakers,
    guest_catalog,
    guest_tag,
    normalized_person_name,
    parse_transcript,
    read_guest_metadata,
    read_posts,
)
from update_topic_tags import AI_PATTERNS


# These supplement literal matches against every tag in the archive. Entries
# absent from the archive become possible new tags, rather than additions to it.
# Keep aliases specific: incidental words such as "go" and "windows" are common
# in conversation. The output supplies evidence for a person to review.
TOPIC_ALIASES = {
    "C++": r"c\s*\+\s*\+(?:\d{2})?|c\s+plus\s+plus|cpp(?:\d{2})?",
    "C#": r"c\s*#|c\s+sharp",
    "AI": r"a\.?\s*i\.?|artificial intelligence|large language models?|llms?",
    "codex": AI_PATTERNS["codex"].pattern + r"|open\s+ai|chat\s+gpt|g\s+p\s+t",
    "claude": AI_PATTERNS["claude"].pattern,
    "cursor": AI_PATTERNS["cursor"].pattern,
    "Algorithms": r"algorithms?",
    "Parallel Algorithms": r"parallel algorithms?",
    "Graph Algorithms": r"graph (?:algorithms?|theory)|shortest paths?|travel(?:l)?ing salesman",
    "Data Structures": r"data structures?",
    "Conferences": r"(?:programming|developer|c\+\+) conferences?",
    "Concepts": r"c\+\+ concepts?|concepts and constraints|requires clauses?",
    "Programming Languages": r"programming languages?",
    "Array Languages": r"array (?:programming )?languages?",
    "Functional Programming": r"functional programming|functional languages?",
    "Combinators": r"combinators?",
    "Compilers": r"compilers?|compilation",
    "Standard Libraries": r"standard librar(?:y|ies)|stl",
    "Senders & Receivers": r"senders? (?:and|&) receivers?|std::execution",
    "GPU": r"g\s*p\s*u|graphics processing units?",
    "GPUs": r"gpus|g\s*p\s*us|graphics processing units",
    "CUDA": r"cuda|c\s*u\s*d\s*a",
    "BQN": r"bqn|b\s*q\s*n|bee cue en",
    "APL": r"apl|a\s*p\s*l",
    "UI": r"ui|u\s*i|user interfaces?",
    "FP": r"fp|functional programming",
    "LISP": r"lisps?",
    "Microsoft Excel": r"(?:microsoft )?excel",
    "JavaScript": r"java\s*script|ecmascript",
    "Java": r"java(?!\s+script\b)",
    "Pascal": r"pascal(?!\s+(?:p\d|gpus?\b|architecture\b))",
    "Learning": r"learning (?:to|how)|learning programming|programming education",
    "GitHub": r"git\s*hub",
    "CppNorth": r"cpp\s*north|c\+\+\s*north|c plus plus north",
    "CppCon": r"cpp\s*con|c\+\+\s*con|c plus plus con",
    "C++Now": r"cpp\s*now|c\+\+\s*now|c plus plus now",
    "C++ On Sea": r"c(?:\+\+| plus plus) on sea|cpp on sea",
    "C++ Under the Sea": r"c(?:\+\+| plus plus) under the sea|cpp under the sea",
    "Advent of Code": r"advent of code",
    "Point Free": r"point[- ]free",
    "Operating Systems": r"operating systems?",
    "Windows": r"microsoft windows|windows (?:1[01]|xp|vista|os)|wsl(?:\s*2)?|windows subsystem for linux",
    "macOS": r"mac\s*os|os x",
    "Ubuntu": r"ubuntu",
    "LLVM": r"llvm|l\s*l\s*v\s*m",
    "NVIDIA": r"nvidia",
    "Vim": r"n?vim|vi editor",
    "Emacs": r"emacs",
    "VS Code": r"vs\s*code|visual studio code",
    "GitHub Copilot": r"(?:github )?copilot",
    "TypeScript": r"type\s*script",
    "Docker": r"docker",
    "Kubernetes": r"kubernetes|k8s",
    "Large Language Models": r"large language models?|llms?",
    "AI Agents": r"ai agents?|agentic (?:ai|coding|workflows?|systems?|os)|coding agents?",
    "Computer Use": r"computer use|browser automation",
    "High Performance Computing": r"high[- ]performance computing|hpc",
    "Distributed Systems": r"distributed (?:systems?|computing)",
    "Concurrency": r"concurrency|concurrent (?:programming|systems?)|multithreading|multi[- ]threaded",
    "Move Semantics": r"move semantics?|move constructors?|std::move",
    "Memory Management": r"memory management|garbage collect(?:ion|ors?)|memory allocat(?:ion|ors?)",
    "Type Systems": r"type systems?|type inference|dependent types?",
    "Recursion": r"recurs(?:ion|ive)|tail calls?",
    "Testing": r"unit tests?|unit testing|integration tests?|test[- ]driven development",
    "Optimization": r"optimizations?|optimisations?|performance tuning",
    "Version Control": r"version control|git (?:commits?|branches|repositories)",
    "Web Development": r"web development|front[- ]end development|back[- ]end development",
}

# A bare letter cannot reliably identify a language in a speech transcript.
# These tags require explicit language context, even if spelled in uppercase.
AMBIGUOUS_LANGUAGES = {"b", "c", "d", "j", "k", "q", "r", "go", "val", "circle"}
NON_TOPIC_TAGS = {"guest", "guests", "ai generated", "interview", "interviews"}


def tag_key(tag):
    """Preserve significant punctuation: C, C++, and C# are different tags."""
    return " ".join(tag.casefold().split())


def tag_catalog(episodes):
    spellings = defaultdict(Counter)
    counts = Counter()
    for episode in episodes:
        seen = set()
        for tag in episode["tag_values"]:
            key = tag_key(tag)
            spellings[key][tag] += 1
            seen.add(key)
        counts.update(seen)
    names = {
        key: sorted(variants, key=lambda tag: (-variants[tag], tag))[0]
        for key, variants in spellings.items()
    }
    return names, counts


def literal_pattern(tag):
    return re.escape(tag).replace(r"\ ", r"[\s-]+")


def topic_pattern(tag):
    key = tag_key(tag)
    aliases = next((value for name, value in TOPIC_ALIASES.items() if tag_key(name) == key), "")
    if key in AMBIGUOUS_LANGUAGES:
        name = literal_pattern(tag)
        # Do not mistake C++ or C# for C, including after words like "in".
        boundary = r"(?![\w+#]|\s+(?:plus|sharp)\b)" if key == "c" else r"(?![\w+#])"
        aliases = (
            rf"{name}{boundary}\s+(?:programming\s+)?(?:language|compiler|code|programmers?)\b"
            rf"|(?:written|programming|programmed|coding|implemented)\s+in\s+{name}{boundary}"
            rf"|(?:language called|language named)\s+{name}{boundary}"
        )
        if key == "go":
            aliases += r"|golang"
    elif not aliases:
        aliases = literal_pattern(tag)
    return re.compile(r"(?<!\w)(?:" + aliases + r")(?!\w)", re.IGNORECASE)


def timestamp(seconds):
    seconds = int(seconds)
    hours, remainder = divmod(seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def excerpt(text, start, end):
    left, right = max(0, start - 65), min(len(text), end + 100)
    if left:
        space = text.find(" ", left, start)
        if space != -1:
            left = space + 1
    if right < len(text):
        space = text.rfind(" ", end, right)
        if space != -1:
            right = space
    return ("…" if left else "") + text[left:right] + ("…" if right < len(text) else "")


def evidence_for(turn, text, match=None):
    return {
        # The public transcript's turn timestamp, not a claimed word timestamp.
        "timestamp": timestamp(turn["start"]),
        "speaker": turn["speaker"],
        "excerpt": excerpt(text, match.start(), match.end()) if match else excerpt(text, 0, 0),
    }


def topic_suggestion(tag, turns, archive_count, min_mentions):
    pattern = topic_pattern(tag)
    mentions = 0
    turn_count = 0
    evidence = []
    for turn in turns:
        text = " ".join(turn["text"].split())
        matches = list(pattern.finditer(text))
        if not matches:
            continue
        mentions += len(matches)
        turn_count += 1
        if len(evidence) < 2:
            evidence.append(evidence_for(turn, text, matches[0]))
    if mentions < min_mentions:
        return None
    return {
        "tag": tag,
        "kind": "topic",
        "confidence": "high" if mentions >= 5 and turn_count >= 2 else "medium" if mentions >= 2 else "low",
        "mentions": mentions,
        "turns": turn_count,
        "archive_episodes": archive_count,
        "reason": "Matched topic names or aliases in the transcript.",
        "evidence": evidence,
    }


def suggest_tags(episode, turns, episodes, metadata=None, *, min_mentions=2, limit=12, new_limit=5):
    names, counts = tag_catalog(episodes)
    current = {tag_key(tag) for tag in episode["tag_values"]}
    people = guest_catalog(episodes, metadata)
    classifications, _, guests = classify_transcript_speakers(episode, turns, people)
    guest_keys = {
        tag_key(guest_tag(name, names.values()) or name)
        for name, _ in people.values()
    }
    # Include newly discovered speaker names in the exclusion, too. Names of
    # guests come from their labels, never from someone merely mentioning them.
    guest_keys.update(tag_key(guest_tag(name, names.values()) or name) for _, name, _ in guests)
    candidates = []
    for key, tag in names.items():
        if key in NON_TOPIC_TAGS or key in guest_keys:
            continue
        suggestion = topic_suggestion(tag, turns, counts[key], min_mentions)
        if suggestion:
            candidates.append(suggestion)
    for tag in TOPIC_ALIASES:
        key = tag_key(tag)
        if key not in names and key not in guest_keys:
            suggestion = topic_suggestion(tag, turns, 0, min_mentions)
            if suggestion:
                candidates.append(suggestion)

    for _, name, _ in guests:
        tag = guest_tag(name, names.values()) or name
        key = tag_key(tag)
        guest_turns = [
            turn for turn in turns
            if classifications.get(normalized_person_name(turn["speaker"]))
            == (f"guest:{normalized_person_name(name)}", "guest")
        ]
        candidates.append({
            "tag": tag,
            "kind": "guest",
            "confidence": "high",
            "mentions": None,
            "turns": len(guest_turns),
            "archive_episodes": counts[key],
            "reason": f"{name} speaks as a guest in the transcript.",
            "evidence": [evidence_for(turn, " ".join(turn["text"].split())) for turn in guest_turns[:2]],
        })

    guest_topic = names.get("guests") if "guests" in current else names.get("guest", names.get("guests"))
    if guests and guest_topic:
        candidates.append({
            "tag": guest_topic, "kind": "guest", "confidence": "high",
            "mentions": None, "turns": None, "archive_episodes": counts[tag_key(guest_topic)],
            "reason": "The transcript contains guest speakers.",
            "evidence": [],
        })

    candidates.sort(key=lambda item: (
        item["kind"] != "guest", -(item["mentions"] or 0),
        -(item["turns"] or 0), -item["archive_episodes"], tag_key(item["tag"]),
    ))
    existing = [item for item in candidates if tag_key(item["tag"]) not in current and item["archive_episodes"]]
    new = [item for item in candidates if tag_key(item["tag"]) not in current and not item["archive_episodes"]]
    return {
        "episode": episode["number"],
        "title": episode["title"],
        "transcript_url": TRANSCRIPT_URL.format(buzzsprout_id=episode["buzzsprout_id"]),
        "current_tags": list(episode["tag_values"]),
        "existing_suggestions": existing[:limit],
        "new_suggestions": new[:new_limit],
        "matched_current_tags": [item["tag"] for item in candidates if tag_key(item["tag"]) in current],
        "method": "Keyword/alias matches and guest speaker labels; review before adding tags.",
        "timestamp_note": "Evidence timestamps mark the start of the speaker turn.",
    }


def fetch_transcript(episode):
    if not episode["buzzsprout_id"]:
        raise ValueError(f"episode {episode['number']} has no buzzsprout-id")
    request = Request(
        TRANSCRIPT_URL.format(buzzsprout_id=episode["buzzsprout_id"]),
        headers={"User-Agent": "ADSP tag suggestions"},
    )
    try:
        with urlopen(request, timeout=30) as response:
            return response.read().decode(response.headers.get_content_charset() or "utf-8")
    except HTTPError as error:
        if error.code == 404:
            raise ValueError(f"episode {episode['number']} has no published transcript yet") from error
        raise ValueError(f"could not fetch the transcript: HTTP {error.code}; try again or use --transcript-file") from error
    except (URLError, TimeoutError) as error:
        raise ValueError(f"could not fetch the transcript: {error}; try again or use --transcript-file") from error


def color_enabled(mode):
    if mode != "auto":
        return mode == "always"
    return sys.stdout.isatty() and "NO_COLOR" not in os.environ and os.environ.get("TERM") != "dumb"


def print_report(report, *, color="auto"):
    use_color = color_enabled(color)

    def paint(text, style):
        return f"\033[{style}m{text}\033[0m" if use_color else text

    print(f"Episode {report['episode']}: {report['title']}")
    print("Current tags: " + (", ".join(paint(tag, "32") for tag in report["current_tags"]) or "none"))
    print("Read-only suggestions; review before adding. Timestamps mark speaker-turn starts.")
    for title, suggestions in (
        ("Suggested existing tags", report["existing_suggestions"]),
        ("Possible new tags", report["new_suggestions"]),
    ):
        print(f"\n{title}:")
        if not suggestions:
            print("  None above the mention threshold.")
        for item in suggestions:
            detail = f"{item['mentions']} mentions" if item["kind"] == "topic" else item["reason"]
            if item["archive_episodes"]:
                detail += f"; used in {item['archive_episodes']} archive episodes"
            print(f"  {paint(item['tag'], '1;32')} [{item['confidence']}] — {detail}")
            pattern = topic_pattern(item["tag"])
            for evidence in item["evidence"]:
                snippet = evidence["excerpt"]
                if use_color:
                    snippet = pattern.sub(lambda match: paint(match.group(), "32"), snippet)
                speaker = paint(evidence["speaker"], "32") if item["kind"] == "guest" else evidence["speaker"]
                print(f"    {paint(evidence['timestamp'], '36')} {speaker}: {snippet}")
    if report["existing_suggestions"] or report["new_suggestions"]:
        print("\nSuggested additions (YAML/JSON list):")
        print(json.dumps([item["tag"] for group in ("existing_suggestions", "new_suggestions") for item in report[group]], ensure_ascii=False))


def positive_int(value):
    number = int(value)
    if number < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return number


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("episode", type=int, help="episode number, e.g. 306 (not the Buzzsprout ID)")
    parser.add_argument("--json", action="store_true", help="print the full report as JSON")
    parser.add_argument("--color", choices=("auto", "always", "never"), default="auto", help="terminal colors (default: auto; respects NO_COLOR)")
    parser.add_argument("--transcript-file", type=Path, help="read saved Buzzsprout transcript HTML instead of downloading it")
    parser.add_argument("--min-mentions", type=positive_int, default=2, help="minimum topic/alias mentions (default: 2; guests do not need mentions)")
    parser.add_argument("--limit", type=positive_int, default=12, help="maximum existing tag suggestions (default: 12)")
    parser.add_argument("--new-limit", type=positive_int, default=5, help="maximum possible new tags (default: 5)")
    args = parser.parse_args(argv)
    try:
        episodes = read_posts()
        episode = next((item for item in episodes if item["number"] == args.episode), None)
        if episode is None:
            raise ValueError(f"episode {args.episode} does not exist in _posts")
        transcript = args.transcript_file.read_text(encoding="utf-8") if args.transcript_file else fetch_transcript(episode)
        turns, _ = parse_transcript(transcript)
        report = suggest_tags(
            episode, turns, episodes, read_guest_metadata(),
            min_mentions=args.min_mentions, limit=args.limit, new_limit=args.new_limit,
        )
    except (OSError, ValueError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_report(report, color=args.color)
    return 0


if __name__ == "__main__":
    sys.exit(main())
