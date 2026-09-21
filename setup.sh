#!/bin/bash
# One-time setup: make sure uv is there, then install `update` as a command.
# Everyday runs go through that command, not through this script.
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

# --editable so a git pull updates the command, with no reinstall.
uv tool install --editable .

bin_dir="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"
case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo
     echo "Add $bin_dir to your PATH, or run: uv tool update-shell" ;;
esac

echo
echo "Done. Try: update --check"
