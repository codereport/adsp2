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
code. If the co-host cannot be inferred from the episode introduction, add
`cohost: Ben` or `cohost: Bryce` to that post's front matter.

Guest company and language badges are configured in `_data/guest_metadata.json`.
Add a company to its `companies` catalog, add its key to `featured_companies` to
show it on the homepage, and assign the key and language keys to each guest. Company
logo files live in the `company/` directory of the sibling `codereport/logos`
repository; publish that repository before publishing site metadata that references
a new logo. Each company's `guests` list determines its homepage destination: the
generator links the logo to the most recent episode featuring anyone on that list.
