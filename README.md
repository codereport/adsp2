# The ADSP Podcast Website Source

The ADSP website is automatically updated when this repo changes.

## Local Development

To host the site locally for development and testing:

### Prerequisites

1. **Install Ruby** (version 3.0 or higher):
   ```bash
   sudo apt-get update
   sudo apt-get install -y ruby-full
   ```

2. **Install Bundler**:
   ```bash
   sudo gem install bundler
   ```

### Setup and Run

1. **Install dependencies**:
   ```bash
   sudo bundle install
   ```

2. **Serve the site locally**:
   ```bash
   ./serve-local.sh
   ```

3. **Access the site**:
   Open your browser and navigate to `http://localhost:4000`

The site will automatically rebuild when you make changes to the source files,
but it will not refresh the browser automatically. Refresh the page manually to
see the new build. Press `Ctrl+C` to stop the server.

## Updating the Episodes Table

Run the generator after adding or editing an episode post:

```bash
python3 generate_episodes.py
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
