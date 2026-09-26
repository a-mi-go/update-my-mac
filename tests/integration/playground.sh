#!/bin/bash
# A run against the fake package managers next to this script, so you can click
# through the menus without touching anything on your Mac. Everything it writes
# goes into a throwaway directory.
#
#   tests/integration/playground.sh
#   tests/integration/playground.sh --check
set -eu

here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/../.." && pwd)
playground=$(mktemp -d)
mkdir -p "$playground/home"

# The real managers must not be on PATH, so the interpreter is named outright
# rather than looked up through uv.
PATH="$here/mocks:/usr/bin:/bin" \
MOCK_FIXTURES="$here/fixtures/outdated" \
MOCK_STATE="$playground/state" \
HOME="$playground/home" \
UPDATE_MY_MAC_PREFIXES="" \
UPDATE_MY_MAC_APP_DIRS="" \
  "$repo/.venv/bin/python3" -m update_my_mac "$@"
