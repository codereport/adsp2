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
