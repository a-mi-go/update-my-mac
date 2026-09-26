# Roadmap

What is built, what is next, and the ideas not decided on yet. The reasoning
behind the design is in the commit messages and in the pull requests.

## Works today

- `update --check`: the package managers themselves, then mas, Homebrew
  formulae, global npm and pnpm packages.
- `update`: the managers are offered first and on their own, so that everything
  checked afterwards comes from current tools. Then one menu that takes a number
  or several separated by commas, with the untracked apps as an entry in it.
- Telling which untracked apps update themselves, by reading Sparkle's settings
  out of the app bundle and the user's own preferences.
- Showing where an untracked app came from, matched against Homebrew's list of
  casks by the app's file name, and opening that website.
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

**The remaining package managers.** One registry entry plus a fixture each.
This table is the source for the one in the README, so keep it here:

<!-- planned-sources:start -->
| Source | Command |
| --- | --- |
| `softwareupdate` | `softwareupdate --list` |
| [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) | `brew outdated --cask --greedy` |
| [MacPorts](https://github.com/macports/macports-base) | `port outdated` |
| [Yarn](https://github.com/yarnpkg/yarn) | `yarn global list` |
| [Bun](https://github.com/oven-sh/bun) | not decided |
| [uv](https://github.com/astral-sh/uv) | `uv tool list --outdated` |
| [pipx](https://github.com/pypa/pipx) | `pipx list --json` |
| [RubyGems](https://github.com/rubygems/rubygems) | `gem outdated` |
| [Cargo](https://github.com/rust-lang/cargo) | `cargo install --list` |
| [Nix](https://github.com/NixOS/nix) | `nix profile list` |
<!-- planned-sources:end -->

Three of these need a decision rather than a fixture. Nix, because
`nix profile upgrade` and a flake-based setup behave differently from the other
managers and a Nix user may not want a tool outside Nix touching their profile,
so reporting is the safe part. Yarn, because only Yarn Classic has global
installs at all and Yarn 2 dropped them. And Bun, which has global installs but
no command that reports them as outdated.

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
