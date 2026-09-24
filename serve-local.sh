#!/usr/bin/env bash

set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v ruby >/dev/null 2>&1; then
  echo "Ruby is required to serve this site. See README.md for setup instructions." >&2
  exit 1
fi

if ! command -v bundle >/dev/null 2>&1; then
  user_gem_bin="$(ruby -r rubygems -e 'print Gem.user_dir')/bin"
  if [[ -x "$user_gem_bin/bundle" ]]; then
    export PATH="$user_gem_bin:$PATH"
  fi
fi

if ! command -v bundle >/dev/null 2>&1; then
  echo "Bundler is required to serve this site. Install it with 'gem install bundler --user-install'." >&2
  exit 1
fi

bundle config set --local path vendor/bundle
bundle check || bundle install

exec bundle exec jekyll serve \
  --host 127.0.0.1 \
  --port 4000 \
  "$@"
