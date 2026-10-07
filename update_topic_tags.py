#!/usr/bin/env python3
"""Add AI tool and Thrust/CUDA topic tags to episode posts."""

import argparse
from collections import Counter
import json
import re
import sys

from generate_episodes import POSTS_DIR, add_post_tags, front_matter_value, post_tag_values


AI_PATTERNS = {
    "codex": re.compile(r"\b(?:codex|openai)\b|\b(?:chat)?gpt\w*", re.IGNORECASE),
    "claude": re.compile(r"\b(?:claude|anthropic|opus|sonnet)\b", re.IGNORECASE),
    "cursor": re.compile(r"\bcursor\b", re.IGNORECASE),
}
FRONT_MATTER = re.compile(
    r"\A---[ \t]*\r?\n(?P<header>.*?)^---[ \t]*(?:\r?\n|\Z)(?P<body>.*)\Z",
    re.MULTILINE | re.DOTALL,
)


def show_notes(body):
    heading = re.search(r"^(#{1,6})[ \t]+Show Notes[ \t]*\r?$", body, re.MULTILINE | re.IGNORECASE)
    if heading is None:
        return ""
    remaining = body[heading.end():]
    next_section = re.search(rf"^#{{1,{len(heading.group(1))}}}[ \t]+", remaining, re.MULTILINE)
    return remaining[:next_section.start()] if next_section else remaining


def topic_tags(post):
    match = FRONT_MATTER.fullmatch(post)
    if match is None:
        raise ValueError("post has no complete YAML front matter")
    header, body = match.group("header", "body")
    title = front_matter_value(header, "title")
    searchable = title + "\n" + show_notes(body)
    tags = [tag for tag, pattern in AI_PATTERNS.items() if pattern.search(searchable)]
    if "thrust::" in body:
        tags.extend(("Thrust", "CUDA"))
    elif any(tag.casefold() == "thrust" for tag in post_tag_values(post)):
        tags.append("CUDA")
    return tags


def updated_post(post):
    current = list(post_tag_values(post))
    normalized = []
    for tag in current:
        if tag.casefold() in AI_PATTERNS:
            tag = tag.casefold()
            if tag in normalized:
                continue
        normalized.append(tag)
    additions = []
    for tag in topic_tags(post):
        if not any(existing.casefold() == tag.casefold() for existing in normalized):
            normalized.append(tag)
            additions.append(tag)

    if current == normalized:
        return post
    if current == normalized[:len(current)]:
        return add_post_tags(post, additions)

    # Canonicalize the three AI tag spellings while retaining every other tag.
    match = FRONT_MATTER.fullmatch(post)
    header = match.group("header")
    tag_line = re.compile(r"^(tags:[ \t]*)\[.*\]([ \t]*(?:#.*)?)(\r?\n|$)", re.MULTILINE)
    header, changed = tag_line.subn(
        lambda found: found.group(1) + json.dumps(normalized, ensure_ascii=False)
        + found.group(2) + found.group(3), header, count=1,
    )
    if not changed:
        raise ValueError("expected tags to be an inline YAML list")
    return post[:match.start("header")] + header + post[match.end("header"):]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="check tags without changing files")
    args = parser.parse_args()
    updates = {}
    counts = Counter()
    for path in sorted(POSTS_DIR.glob("*Episode-*.md")):
        original = path.read_text(encoding="utf-8")
        try:
            updated = updated_post(original)
        except ValueError as error:
            raise ValueError(f"{path.name}: {error}") from error
        if updated != original:
            updates[path] = updated
        counts.update(set(post_tag_values(updated)))

    if args.check:
        status = f"need updates in {len(updates)} posts" if updates else "are up to date"
        print(f"{'❌' if updates else '✅'} - Topic tags {status}")
    else:
        for path, content in updates.items():
            path.write_text(content, encoding="utf-8")
        print(f"🔧 - Updated topic tags in {len(updates)} episode posts")
    print("AI topic totals: " + ", ".join(f"{tag}: {counts[tag]}" for tag in AI_PATTERNS))
    return int(args.check and bool(updates))


if __name__ == "__main__":
    sys.exit(main())
