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

interactive() { [ -t 0 ] && [ -t 1 ]; }

SHELL_CONFIGS=(
  "$HOME/.zshrc"
  "$HOME/.zprofile"
  "$HOME/.bashrc"
  "$HOME/.bash_profile"
  "$HOME/.profile"
)

# Files defining `alias <name>=`, which would shadow the installed command.
files_aliasing() {
  local name="$1" file
  for file in "${SHELL_CONFIGS[@]}"; do
    if [ -f "$file" ] && grep -qE "^[[:space:]]*alias[[:space:]]+$name=" "$file"; then
      echo "$file"
    fi
  done
}

comment_out_alias() {
  local name="$1" file="$2" suffix
  # Timestamped, so running this twice doesn't replace the first backup. -i with
  # a suffix works the same on BSD and GNU sed.
  suffix=".bak-$(date +%Y%m%d%H%M%S)"
  sed -i"$suffix" -E "s|^([[:space:]]*alias[[:space:]]+$name=)|# \1|" "$file"
  echo "  commented it out in $file (kept a copy as $(basename "$file")$suffix)"
}

if ! command -v uv &>/dev/null; then
  if ! interactive; then
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

# An alias wins over anything on PATH, so an old one quietly shadows the
# command that was just installed.
aliased_in=$(files_aliasing update)
if [ -n "$aliased_in" ]; then
  echo
  echo "An 'update' alias is defined in:"
  while read -r file; do echo "  $file"; done <<< "$aliased_in"
  echo "It would shadow the command just installed."

  if interactive; then
    read -r -p "Comment it out? [y/N] " answer
    if [[ "$answer" =~ ^[Yy]$ ]]; then
      while read -r file; do comment_out_alias update "$file"; done <<< "$aliased_in"
    else
      read -r -p "Install under a different name instead? Name (empty to skip): " other_name
      if [ -n "$other_name" ]; then
        # It becomes a path, so no slashes, spaces or anything the shell reads.
        if [[ ! "$other_name" =~ ^[A-Za-z0-9._-]+$ ]]; then
          echo "setup: '$other_name' is not a usable command name." >&2
          exit 1
        fi
        if [ -e "$bin_dir/$other_name" ] || [ -L "$bin_dir/$other_name" ]; then
          echo "setup: $bin_dir/$other_name already exists — not touching it." >&2
          exit 1
        fi
        ln -s "$bin_dir/update" "$bin_dir/$other_name"
        echo "  $other_name -> $bin_dir/update"
        echo
        echo "Done. Try: $other_name --check"
        exit 0
      fi
    fi
  fi
  echo "Your current shell still has the old alias — run 'unalias update' or open a new tab."
fi

echo
echo "Done. Try: update --check"
