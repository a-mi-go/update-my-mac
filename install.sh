#!/bin/bash
# Installs from the latest release, without git. Running it again updates.
set -euo pipefail

archive_url="${UPDATE_MY_MAC_ARCHIVE_URL:-https://github.com/a-mi-go/update-my-mac/releases/latest/download/update-my-mac.tar.gz}"
target="${XDG_DATA_HOME:-$HOME/.local/share}/update-my-mac"

if [ -e "$target/.git" ]; then
  echo "install: $target is a git clone. Update it with 'git pull' and run its setup.sh." >&2
  exit 1
fi

mkdir -p "$(dirname "$target")"
# Beside the target, so the swaps below are renames that cannot stop halfway.
work="$(mktemp -d "$target.XXXXXX")"
trap 'rm -rf "$work"' EXIT

curl -fsSL "$archive_url" | tar -xz -C "$work"

if [ -e "$target" ]; then
  mv "$target" "$work/previous"
fi
if ! mv "$work/update-my-mac" "$target"; then
  [ ! -e "$work/previous" ] || mv "$work/previous" "$target"
  exit 1
fi

# exec would skip the trap, and the old install is in there.
rm -rf "$work"
exec "$target/setup.sh" "$@"
