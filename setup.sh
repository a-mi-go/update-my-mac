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

usage() {
  echo "usage: ./setup.sh [--name NAME]" >&2
  exit 2
}

name=""
while [ $# -gt 0 ]; do
  case "$1" in
    --name) [ $# -ge 2 ] || usage; name="$2"; shift 2 ;;
    -h|--help) echo "usage: ./setup.sh [--name NAME]"; exit 0 ;;
    *) usage ;;
  esac
done

interactive() { [ -t 0 ] && [ -t 1 ]; }

SHELL_CONFIGS=(
  "$HOME/.zshrc"
  "$HOME/.zprofile"
  "$HOME/.bashrc"
  "$HOME/.bash_profile"
  "$HOME/.profile"
)

# It becomes a file name, so no slashes, spaces or anything a shell reads.
usable_name() { [[ "$1" =~ ^[A-Za-z0-9._-]+$ ]]; }

# Config files defining `alias <name>=`, which would shadow the command.
files_aliasing() {
  local name="${1//./\\.}" file
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

# An alias lives only in the memory of the shell that loaded it, so there is no
# asking the calling shell what it has. What can be told is whether it started
# before its config last changed — then whatever it holds may be out of date.
calling_shell_is_stale() {
  local started newest=0 modified file
  case "$(ps -o comm= -p "$PPID" 2>/dev/null)" in
    *zsh|*bash) ;;
    *) return 1 ;;
  esac
  # C locale, or ps writes "Mo. 21 Sep." on a German system and date can't read it.
  started=$(LC_ALL=C ps -o lstart= -p "$PPID" 2>/dev/null) || return 1
  started=$(LC_ALL=C date -j -f "%a %b %d %T %Y" "$started" +%s 2>/dev/null) || return 1
  for file in "${SHELL_CONFIGS[@]}"; do
    [ -f "$file" ] || continue
    modified=$(stat -f %m "$file" 2>/dev/null) || continue
    [ "$modified" -gt "$newest" ] && newest=$modified
  done
  [ "$started" -lt "$newest" ]
}

# What else the shell would find under this name: a builtin like cd, or another
# program on PATH that a link here would hide, or be hidden by.
already_taken_by() {
  local name="$1" found
  case "$(type -t "$name" 2>/dev/null)" in
    builtin|keyword) echo "a shell builtin" ;;
    file) found=$(command -v "$name")
          [ "$found" = "$bin_dir/$name" ] && return 1
          # Another copy of this same tool, such as a development environment.
          grep -q update_my_mac "$found" 2>/dev/null && return 1
          echo "$found" ;;
    *) return 1 ;;
  esac
}

ask_for_name() {
  read -r -p "What should the command be called? [update] " name
  name="${name:-update}"
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

# --editable so a git pull updates the command, with no reinstall. uv always
# names it `update`; any other name is a symlink to it.
uv tool install --editable .
bin_dir="${UV_TOOL_BIN_DIR:-$HOME/.local/bin}"

if [ -z "$name" ]; then
  if interactive; then
    echo
    ask_for_name
  else
    name="update"
  fi
fi

while true; do
  if ! usable_name "$name"; then
    echo "setup: '$name' is not a usable command name." >&2
    interactive || exit 1
    ask_for_name
    continue
  fi

  if taken=$(already_taken_by "$name"); then
    echo "setup: '$name' is already $taken." >&2
    interactive || exit 1
    ask_for_name
    continue
  fi

  aliased_in=$(files_aliasing "$name")
  [ -z "$aliased_in" ] && break

  echo
  echo "'$name' is already an alias in:"
  while read -r file; do echo "  $file"; done <<< "$aliased_in"
  if ! interactive; then
    echo "It would shadow the command. Remove it, or pick another name with --name."
    break
  fi
  echo "  1) call the command something else"
  echo "  2) comment the alias out"
  echo "  3) leave it — the alias wins in your shell"
  read -r -p "> " choice
  case "$choice" in
    1) ask_for_name ;;
    2) while read -r file; do comment_out_alias "$name" "$file"; done <<< "$aliased_in"
       break ;;
    3) break ;;
    *) echo "Please answer 1, 2 or 3." ;;
  esac
done

if [ "$name" != "update" ]; then
  target="$bin_dir/$name"
  if [ -L "$target" ] && [ "$(readlink "$target")" = "$bin_dir/update" ]; then
    :  # already set up by an earlier run
  elif [ -e "$target" ] || [ -L "$target" ]; then
    echo "setup: $target already exists — not touching it." >&2
    exit 1
  else
    ln -s "$bin_dir/update" "$target"
    echo "  $name -> $bin_dir/update"
  fi
fi

case ":$PATH:" in
  *":$bin_dir:"*) ;;
  *) echo
     echo "Add $bin_dir to your PATH, or run: uv tool update-shell" ;;
esac

if calling_shell_is_stale; then
  echo
  echo "This terminal was opened before your shell config last changed, so it may"
  echo "still hold an old '$name' alias. Run this first, or open a new tab:"
  echo "  alias $name >/dev/null 2>&1 && unalias $name; hash -r"
fi

echo
echo "Done. Try: $name --check"
