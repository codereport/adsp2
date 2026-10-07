# The ADSP Podcast Website Source

The ADSP website is automatically updated when this repo changes.

## Local Development

To host the site locally for development and testing:

### Prerequisites

1. **Install Ruby** (version 3.0 or higher). For example, on Ubuntu:
   ```bash
   sudo apt-get update
   sudo apt-get install -y ruby-full
   ```

2. **Install Bundler** for your user account:
   ```bash
   gem install bundler --user-install
   ```

### Setup and Run

1. **Serve the site locally** (the script installs missing gems into `vendor/bundle`):
   ```bash
   ./serve-local.sh
   ```

2. **Access the site**:
   Open your browser and navigate to `http://localhost:4000`

The site will automatically rebuild when you make changes to the source files,
but it will not refresh the browser automatically. Refresh the page manually to
see the new build. Press `Ctrl+C` to stop the server.

## Updating the Episodes Table

Run the generator after adding or editing an episode post:

```bash
python3 generate_episodes.py
```

This also adds missing guest names from available transcripts to each episode's
front-matter tags, making guest names link to all tagged appearances. It reuses
existing guest tag spellings (for example, `Doug Gregor`), preserves existing
topic tags, and applies the same host, clip, and AI exclusions as the statistics.
`MYSTERY SPEAKER` is included. Run `python3 generate_episodes.py --check` to check
both generated data and guest tags without modifying files.

Run the topic updater and refresh the homepage logo order after editing titles
or show notes:

```bash
python3 update_topic_tags.py
python3 reorder_logos.py
python3 generate_episodes.py
```

The topic updater matches titles and the Show Notes section, including link URLs,
case-insensitively: `codex` for Codex, OpenAI, GPT, or ChatGPT; `claude` for Claude,
Anthropic, Opus, or Sonnet; and `cursor` for Cursor. Existing variants of those
three tags are normalized to lowercase. It also retains the Thrust/CUDA rules:
`thrust::` anywhere in the episode body adds both tags, and a `Thrust` tag adds
`CUDA`. Use `python3 update_topic_tags.py --check` to check without writing.
`update_thrust_cuda_tags.py` remains an alias for the expanded updater.

The Codex, Claude, and Cursor topic logos are stored in `assets/img/`; the homepage
logo script orders them with the language logos by tagged episode count. Logo
links stay on the current site, so previews open their own updated tag archives.
The SVGs come
from [Lobe Icons](https://github.com/lobehub/lobe-icons); their MIT license is
included in `assets/img/ai-logos-LICENSE.txt`.

Every episode post has a numeric `buzzsprout-id` in its front matter. The shared
post template renders its player. The generator checks public transcript pages
across the entire archive and writes `_data/transcripts.json` to show transcript
links only for available transcripts. This also discovers completed transcripts
before Buzzsprout's cached RSS feed updates. Episodes still waiting
for transcription are omitted from conversation statistics until they are ready.

### Generate transcripts for the back catalog

Preview missing transcripts without signing in or changing Buzzsprout:

```bash
python3 generate_transcripts.py --dry-run
```

Use [uv](https://docs.astral.sh/uv/) to install the script's Playwright dependency
automatically. Chromium is already installed on this machine. Start with one episode:

```bash
uv run generate_transcripts.py --episode 257 --limit 1
```

Sign into Buzzsprout in the separate browser window and open any episode's detail
page, the page with **Edit This Episode**. The script detects the admin URL, visits
the selected episode, clicks **Generate Automatic Transcript**, and verifies a
processing or ready status. Then queue the remaining episodes:

```bash
uv run generate_transcripts.py
```

The script skips published transcripts and jobs already queued or processing. It
saves the browser login and progress under `~/.local/state/adsp-transcripts/`
(`$XDG_STATE_HOME/adsp-transcripts/` when set), outside this repository. Runs are
serialized and an interrupted run can resume with the same command. An unexpected
page or confirmation stops the run and saves `last-error.png` there. A click whose
result could not be confirmed stays excluded on restart; use `--retry-uncertain`
only after checking that episode in Buzzsprout.

Track published transcripts and update the website statistics as jobs finish:

```bash
python3 generate_transcripts.py --status
python3 generate_episodes.py
```

The status command uses the feed and the last stats refresh. Run the generator
again to discover jobs that have completed since then.

`--episode` can be repeated to choose episodes; `--limit` bounds a run. Use
`--browser-executable /path/to/chromium` if Chromium is installed elsewhere. On a
machine without Chromium, install Playwright's browser with
`uv run --with playwright playwright install chromium` first.

Run the transcript automation and archive-discovery checks locally:

```bash
uv run --with playwright python -m unittest discover -s tests -v
```

The generator updates episode links, durations, co-hosts, dates, episode colors, and
the collapsible statistics section. Repeated guest profiles and shared conference
tags keep a series the same orange or purple, while episodes tagged `Road Trip` are
green. It copies the title for a new episode once, then preserves that title on
later runs so you can make small Markdown edits such as adding backticks for inline
code. Available transcripts determine the co-host label (`Solo` when Conor is the
only host), guest appearances, and speaker statistics. Speakers whose labels
contain parentheses are treated as inserted audio, and AI hosts are excluded from
guest counts. `MYSTERY SPEAKER` is included as a guest. Guest bios and conference
lists supply profile links and canonical spellings, but a person must speak in the
transcript to count as a guest appearance. Without a transcript, the generator
uses the episode notes; add `cohost: Ben`, `cohost: Bryce`, or `cohost: Solo` to the
front matter when needed. A `Ben Deane` transcript label remains a guest unless the
episode introduction or `cohost: Ben` identifies him as the co-host; the short
`Ben` label identifies a co-host directly.

Guest company and language badges are configured in `_data/guest_metadata.json`.
Add a company to its `companies` catalog, add its key to `featured_companies` to
show it on the homepage, and assign the key and language keys to each guest. Company
logo files live in the `company/` directory of the sibling `codereport/logos`
repository; publish that repository before publishing site metadata that references
a new logo. Each company's `guests` list determines its homepage destination: the
generator links the logo to the most recent episode featuring anyone on that list.
