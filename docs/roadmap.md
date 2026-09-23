# Roadmap

What is built, what is next, and the ideas not decided on yet. The reasoning
behind the design is in the commit messages and in the pull requests.

## Works today

- `update --check`: mas, Homebrew formulae, global npm and pnpm packages.
- `update`: the same check, then a menu to upgrade one manager or all of them.
- `setup.sh`: installs the command under a name you choose, and deals with an
  alias, function or fish abbreviation of that name in zsh, bash or fish.
- Listing apps in `/Applications` that neither the App Store, nor Homebrew, nor
  macOS itself accounts for, and remembering which of them to leave alone.
- `update --retry-app`: list an app again that was left alone.

## Next

**Untracked apps (D7).** Finding them, leaving them alone and revisiting that
are done. What is left are the two ways to actually track one:

- **Adopt it into Homebrew Cask**, when `brew` is installed and a cask matches.
  Homebrew then knows about the app and it shows up in ordinary checks.
- **Watch it directly**: compare the installed bundle's version against the
  app's own update feed. Needs no package manager, and it is the only option for
  an app with no cask.

Both become another decision in the same file, next to "leave it alone".

**The remaining package managers.** One registry entry plus a fixture each:

| Source | Command |
| --- | --- |
| macOS | `softwareupdate` (report always, apply only when asked) |
| MacPorts | `port` |
| JavaScript | `yarn`, `bun` |
| Python | `uv tool`, `pipx` |
| Ruby | `gem` |
| Rust | `cargo` |
| Nix | `nix profile` |

Nix needs a decision of its own: `nix profile upgrade` and a flake-based setup
behave differently from the other managers, and a Nix user may not want a tool
outside Nix changing their profile. Reporting what is outdated is the safe part.

**Stale casks (D2).** `brew outdated` compares the version Homebrew recorded at
install time, not the app on disk, and skips casks marked `auto_updates` unless
asked greedily. On the machine this was written on, roughly 15 apps were behind
while Homebrew reported nothing. The check has to compare the app bundle's own
version against the cask's, which also needs a way to mark casks whose version
scheme has nothing to do with the app's.

**Install scripts (D8).** npm 11 and pnpm 10 skip a package's install scripts
unless it is allow-listed, which can leave a package quietly broken. Ask about
each package once, remember the answer, and pass only approved packages to
`--allow-scripts`. Never in `--background`, where nobody can be asked.

**`--background`.** Unattended run for a scheduled job: no prompts, a macOS
notification when something is outdated, and an example launchd agent.

## Later

- `--dry-run` for `setup.sh`: show the name and config changes it would make.
- Check that the files setup is about to change are writable before installing,
  so nothing can fail halfway.
- A troubleshooting section in the README: why a name was refused, what the
  stale-terminal warning means, why `source ~/.zshrc` does not remove an alias.
- Release: tag a version, make the repository public, add the release and
  Homebrew badges that only work once it is.

## Open questions

- **Do `npm update -g` and `pnpm update -g` cross major versions?** They move to
  the highest version the semver range allows, which may be less than the
  `latest` the check reports. If they do not, a package would stay listed as
  outdated after a successful upgrade, and the commands should become
  `install -g <package>@latest`. Needs testing with a pinned old major.
- **Apps with no update feed at all**, such as one installed from a `.dmg` with
  no Sparkle feed and no cask. The version on disk is readable, but there is
  nothing to compare it against. A source per app, such as a GitHub releases
  page, would have to be recorded somewhere.
- **uv tool install ignores `uv.lock`**, so the installed command may resolve a
  different rich version than the tests ran against. CI installs the tool the
  way a user does, which catches the breakage but does not prevent it.
