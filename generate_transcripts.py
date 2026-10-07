#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright>=1.50,<2"]
# ///
"""Queue missing Buzzsprout transcripts in a separate, persistent browser."""

import argparse
from collections import Counter
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time
from urllib.parse import urlparse, urlunparse

from generate_episodes import TRANSCRIPTS_PATH, published_transcript_ids, read_feed_root, read_posts


PODCAST_ID = "1501960"
GENERATE_NAME = re.compile(r"^Generate Automatic Transcript$", re.IGNORECASE)
EDIT_NAME = re.compile(r"^Edit This Episode$", re.IGNORECASE)
READY_TEXT = re.compile(
    r"^(?:Transcript (?:is )?Ready|(?:Your )?(?:Automatic )?Transcript "
    r"(?:is |has been )?(?:ready|available|complete(?:d)?))\b", re.IGNORECASE
)
PROCESSING_TEXT = re.compile(
    r"^(?:(?:Your )?(?:Automatic )?Transcript (?:is |has been )?(?:being )?"
    r"(?:generating|generated|processing|processed|queued|pending)|"
    r"(?:We(?:'re| are) )?(?:Generating|Processing|Queuing)(?: (?:your|an|the))?"
    r"(?: automatic)? transcript)\b", re.IGNORECASE
)
SETTLED_STATUSES = {"queued", "processing", "ready"}
UNCERTAIN_STATUSES = {"attempting", "uncertain"}


def default_state_dir():
    base = Path(os.environ.get("XDG_STATE_HOME", Path.home() / ".local/state"))
    return base / "adsp-transcripts"


def feed_episodes(root):
    posts = {episode["buzzsprout_id"]: episode for episode in read_posts()}
    available = published_transcript_ids(root)
    # A recent stats refresh can discover transcripts before the cached RSS feed.
    if TRANSCRIPTS_PATH.exists():
        available.update(json.loads(TRANSCRIPTS_PATH.read_text()))
    episodes = []
    seen = set()
    for item in root.findall("./channel/item"):
        match = re.fullmatch(r"Buzzsprout-(\d+)", item.findtext("guid", ""), re.I)
        if not match:
            raise ValueError("RSS episode has no recognized Buzzsprout GUID")
        episode_id = match.group(1)
        if episode_id in seen:
            raise ValueError(f"Duplicate RSS episode ID: {episode_id}")
        seen.add(episode_id)
        if episode_id not in posts:
            raise ValueError(f"RSS episode {episode_id} has no matching post header")
        episodes.append({
            "number": posts[episode_id]["number"],
            "id": episode_id,
            "title": item.findtext("title", ""),
            "published": episode_id in available,
        })
    return sorted(episodes, key=lambda episode: episode["number"], reverse=True)


def load_state(directory):
    path = directory / "progress.json"
    if not path.exists():
        return {"version": 1, "podcast_id": PODCAST_ID, "episodes": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    if state.get("version") != 1 or state.get("podcast_id") != PODCAST_ID:
        raise ValueError(f"Unrecognized checkpoint: {path}")
    return state


def save_state(directory, state):
    directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = directory / "progress.tmp"
    temporary.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(directory / "progress.json")


def record(directory, state, episode, status):
    state["episodes"][episode["id"]] = {
        "number": episode["number"],
        "status": status,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    save_state(directory, state)


def pending_episodes(episodes, state, retry_uncertain=False):
    excluded = SETTLED_STATUSES | (set() if retry_uncertain else UNCERTAIN_STATUSES)
    return [
        episode for episode in episodes
        if not episode["published"]
        and state["episodes"].get(episode["id"], {}).get("status") not in excluded
    ]


def validate_template(template):
    parsed = urlparse(template)
    if (
        parsed.scheme != "https" or parsed.hostname != "www.buzzsprout.com"
        or parsed.port is not None or parsed.username or parsed.password
        or parsed.query or parsed.fragment
        or template.count("{episode_id}") != 1
        or not re.search(r"(?:^|/)1501960(?:/|$)", parsed.path)
        or "{episode_id}" not in parsed.path.split("/")
    ):
        raise ValueError(
            "The admin URL template must be a www.buzzsprout.com HTTPS URL for "
            "podcast 1501960, with {episode_id} as one path segment and no query."
        )
    return template


def discover_template(url, episode_ids):
    parsed = urlparse(url)
    parts = parsed.path.split("/")
    matching = [
        index for index, part in enumerate(parts)
        if part.split("-", 1)[0] in episode_ids
    ]
    if len(matching) != 1:
        return None
    parts[matching[0]] = "{episode_id}"
    template = urlunparse(parsed._replace(path="/".join(parts), query="", fragment=""))
    try:
        return validate_template(template)
    except ValueError:
        return None


def named_control(page, name):
    return page.get_by_role("link", name=name).or_(page.get_by_role("button", name=name))


def transcript_status(page):
    if page.get_by_text(READY_TEXT).first.is_visible():
        return "ready"
    if page.get_by_text(PROCESSING_TEXT).first.is_visible():
        return "processing"
    return None


def wait_for_admin_page(context, episodes, template, timeout):
    page = context.pages[0] if context.pages else context.new_page()
    destination = template.replace("{episode_id}", episodes[0]["id"]) if template else (
        "https://www.buzzsprout.com/login"
    )
    page.goto(destination, wait_until="domcontentloaded")
    print(
        "Sign into Buzzsprout in the separate Chromium window. "
        "Then open any episode's detail page (the page with Edit This Episode).\n"
        "The script will detect it and continue automatically.", flush=True
    )
    episode_ids = {episode["id"] for episode in episodes}
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for candidate in context.pages:
            if candidate.is_closed():
                continue
            discovered = discover_template(candidate.url, episode_ids)
            if discovered and named_control(candidate, EDIT_NAME).first.is_visible():
                return candidate, discovered
        if not context.pages:
            raise RuntimeError("Browser closed before sign-in completed")
        context.pages[0].wait_for_timeout(500)
    raise RuntimeError("Timed out waiting for sign-in and an episode detail page")


def validate_episode_page(page, episode):
    if urlparse(page.url).hostname != "www.buzzsprout.com":
        raise RuntimeError("Episode page redirected away from Buzzsprout")
    if episode["id"] not in {
        part.split("-", 1)[0] for part in urlparse(page.url).path.split("/")
    }:
        raise RuntimeError("Episode page redirected to another episode or sign-in")
    named_control(page, EDIT_NAME).first.wait_for(state="visible", timeout=30000)
    page.get_by_role(
        "heading", name=episode["title"], exact=True
    ).first.wait_for(state="visible", timeout=30000)


def queue_episode(page, episode, template, directory, state):
    response = page.goto(
        template.replace("{episode_id}", episode["id"]), wait_until="domcontentloaded"
    )
    if response and response.status >= 400:
        raise RuntimeError(f"Episode page returned HTTP {response.status}")
    validate_episode_page(page, episode)
    status = transcript_status(page)
    if status:
        record(directory, state, episode, status)
        return status

    generate = named_control(page, GENERATE_NAME)
    generate.wait_for(state="visible", timeout=15000)
    # Persist before clicking: a crash after dispatch must not silently requeue a job.
    record(directory, state, episode, "attempting")
    rejected_dialogs = []

    def handle_dialog(dialog):
        if (
            re.search(r"transcript", dialog.message, re.I)
            and not re.search(r"delete|charge|cost|pay|purchase|\$", dialog.message, re.I)
            and dialog.type in {"confirm", "alert"}
        ):
            dialog.accept()
        else:
            rejected_dialogs.append(dialog.type)
            dialog.dismiss()

    page.on("dialog", handle_dialog)
    try:
        generate.click()
        deadline = time.monotonic() + 30
        confirmed_dialog = False
        while time.monotonic() < deadline:
            if rejected_dialogs:
                raise RuntimeError("An unexpected confirmation appeared; review the browser")
            status = transcript_status(page)
            if status:
                record(directory, state, episode, "ready" if status == "ready" else "queued")
                return "ready" if status == "ready" else "queued"
            modal = page.get_by_role("dialog")
            if not confirmed_dialog and modal.count() == 1 and modal.is_visible():
                text = modal.inner_text()
                if not re.search(r"transcript", text, re.I) or re.search(
                    r"delete|charge|cost|payment|purchase|\$", text, re.I
                ):
                    raise RuntimeError("An unexpected transcript dialog appeared")
                modal.get_by_role(
                    "button", name=re.compile(
                        r"^(?:Generate(?: Automatic)? Transcript|Generate|Confirm)$", re.I
                    )
                ).click()
                confirmed_dialog = True
            page.wait_for_timeout(250)
        # A disappeared link alone is insufficient evidence of an accepted job.
        page.reload(wait_until="domcontentloaded")
        validate_episode_page(page, episode)
        status = transcript_status(page)
        if status:
            status = "ready" if status == "ready" else "queued"
            record(directory, state, episode, status)
            return status
        raise RuntimeError("Could not verify that transcription started")
    finally:
        page.remove_listener("dialog", handle_dialog)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="list candidates without opening a browser")
    mode.add_argument("--status", action="store_true", help="compare the latest RSS feed with saved progress")
    parser.add_argument("--feed-file", type=Path, help="use a local RSS file")
    parser.add_argument("--state-dir", type=Path, default=default_state_dir())
    parser.add_argument("--episode", type=int, action="append", help="restrict to these episode numbers")
    parser.add_argument("--limit", type=int, help="maximum episodes to visit this run")
    parser.add_argument("--delay", type=float, default=2, help="seconds between episode visits (default: 2)")
    parser.add_argument("--login-timeout", type=int, default=900, help="seconds to allow for manual sign-in")
    parser.add_argument("--admin-url-template", help="optional known admin URL with {episode_id}")
    parser.add_argument("--browser-executable", default=shutil.which("chromium"))
    parser.add_argument("--retry-uncertain", action="store_true", help="revisit jobs whose earlier result was uncertain")
    args = parser.parse_args()
    if args.limit is not None and args.limit < 1 or args.delay < 0 or args.login_timeout < 1:
        parser.error("limit and login timeout must be positive; delay must be non-negative")
    if args.admin_url_template:
        validate_template(args.admin_url_template)
    return args


def main():
    args = parse_args()
    episodes = feed_episodes(read_feed_root(args.feed_file))
    state = load_state(args.state_dir)
    published = sum(episode["published"] for episode in episodes)
    candidates = pending_episodes(episodes, state, args.retry_uncertain)
    outstanding = Counter(
        state["episodes"].get(episode["id"], {}).get("status", "unattempted")
        for episode in episodes if not episode["published"]
    )
    print(f"Available transcripts: {published}/{len(episodes)}; candidates to visit: {len(candidates)}")
    print("Not yet published: " + ", ".join(f"{count} {status}" for status, count in sorted(outstanding.items())))
    if args.episode:
        unknown = set(args.episode) - {episode["number"] for episode in episodes}
        if unknown:
            raise ValueError(f"Episode numbers not in the feed: {sorted(unknown)}")
        candidates = [episode for episode in candidates if episode["number"] in args.episode]
    if args.limit:
        candidates = candidates[:args.limit]
    if args.status:
        return 0
    if args.dry_run:
        for episode in candidates:
            print(f"  Episode {episode['number']}: {episode['id']} — {episode['title']}")
        return 0
    if not candidates:
        print("No jobs to queue. Check --status later; rerun generate_episodes.py when transcripts are published.")
        return 0

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        raise RuntimeError("Playwright is missing. Run: uv run generate_transcripts.py") from None

    args.state_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    args.state_dir.chmod(0o700)
    with (args.state_dir / "run.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("Another transcript run is already using this browser profile") from None
        # Reload after taking the lock so another completed run cannot cause duplicates.
        state = load_state(args.state_dir)
        candidate_ids = {episode["id"] for episode in candidates}
        candidates = [
            episode for episode in pending_episodes(episodes, state, args.retry_uncertain)
            if episode["id"] in candidate_ids
        ]
        if not candidates:
            return 0
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(args.state_dir / "browser"), headless=False,
                executable_path=args.browser_executable, viewport={"width": 1536, "height": 960},
            )
            context.set_default_timeout(30000)
            try:
                page, template = wait_for_admin_page(
                    context, episodes,
                    args.admin_url_template or state.get("admin_url_template"), args.login_timeout,
                )
                state["admin_url_template"] = template
                save_state(args.state_dir, state)
                print(f"Detected admin URL: {template}", flush=True)
                for index, episode in enumerate(candidates, 1):
                    print(f"[{index}/{len(candidates)}] Episode {episode['number']} ({episode['id']})", flush=True)
                    try:
                        status = queue_episode(page, episode, template, args.state_dir, state)
                    except Exception:
                        previous = state["episodes"].get(episode["id"], {}).get("status")
                        status = "uncertain" if previous in UNCERTAIN_STATUSES else "blocked"
                        record(args.state_dir, state, episode, status)
                        if not page.is_closed():
                            try:
                                page.screenshot(path=str(args.state_dir / "last-error.png"), full_page=True)
                            except Exception:
                                pass
                        raise
                    print(f"  {status}", flush=True)
                    if index < len(candidates):
                        page.wait_for_timeout(args.delay * 1000)
            finally:
                context.close()
    print("Run finished. Check --status for publication progress, then run python3 generate_episodes.py.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\nStopped. Saved progress will be used on the next run.", file=sys.stderr)
        sys.exit(130)
    except Exception as error:
        print(f"Transcript run stopped: {error}", file=sys.stderr)
        sys.exit(1)
