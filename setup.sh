#!/bin/bash
# One-time setup: make sure uv is there, then install the command.
# Everyday runs go through that command, not through this script.
#
#   ./setup.sh               asks what to call the command (default: update)
#   ./setup.sh --name NAME   no question, installs it as NAME
set -euo pipefail

# Follow symlinks, so this works when linked somewhere convenient.
source="${BASH_SOURCE[0]}"
while [ -L "$source" ]; do
  link_dir="$(cd -P "$(dirname "$source")" && pwd)"
  source="$(readlink "$source")"
  [[ "$source" != /* ]] && source="$link_dir/$source"
done
cd "$(cd -P "$(dirname "$source")" && pwd)"

if ! command -v uv &>/dev/null; then
  if [ ! -t 0 ] || [ ! -t 1 ]; then
    echo "setup: 'uv' is missing and there is no terminal to ask on. See https://astral.sh/uv" >&2
    exit 1
  fi
  if command -v brew &>/dev/null; then
    read -r -p "This needs 'uv' (a Python version/dependency manager). Install it with Homebrew? [y/N] " answer
  else
    read -r -p "This needs 'uv' (a Python version/dependency manager). Download and run the installer from astral.sh? [y/N] " answer
  fi
  if [[ ! "$answer" =~ ^[Yy]$ ]]; then
    echo "Install uv yourself, then run this again: https://astral.sh/uv" >&2
    exit 1
  fi
  if command -v brew &>/dev/null; then
    brew install uv
  else
    curl -LsSf https://astral.sh/uv/install.sh | sh
    PATH="$HOME/.local/bin:$PATH"
  fi
  command -v uv &>/dev/null || { echo "setup: uv still isn't on PATH after installing it." >&2; exit 1; }
fi

# Everything else is easier to get right in Python: choosing the name, dealing
# with whatever in zsh, bash or fish config would hide it, and the install
# itself. It asks every question before it installs anything. The calling
# shell's pid goes along so it can tell whether that terminal is out of date,
# and uv is asked where it puts commands, since XDG_BIN_HOME can move them.
exec uv run --frozen --no-dev --quiet python -m update_my_mac.install_command \
  --project-dir "$PWD" \
  --bin-dir "$(uv tool dir --bin)" \
  --calling-pid "$PPID" \
  "$@"
