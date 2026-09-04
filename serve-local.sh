#!/usr/bin/env bash

set -eo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if [[ ! -s "$HOME/.rvm/scripts/rvm" ]]; then
  echo "RVM was not found at $HOME/.rvm/scripts/rvm" >&2
  exit 1
fi

# Load RVM explicitly so Homebrew Ruby cannot be mixed with RVM gems.
rvm_silence_path_mismatch_check_flag=1
source "$HOME/.rvm/scripts/rvm"
rvm use 3.1.0
hash -r
set -u

bundle check || bundle install

exec bundle exec jekyll serve \
  --host 127.0.0.1 \
  --port 4000 \
  "$@"
