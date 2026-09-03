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
   bundle exec jekyll serve --host 0.0.0.0 --port 4000
   ```

3. **Access the site**:
   Open your browser and navigate to `http://localhost:4000`

The site will automatically rebuild when you make changes to the source files. Press `Ctrl+C` to stop the server.

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
