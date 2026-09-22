# update-my-mac

One command that checks — and optionally applies — software updates from every
package manager on your Mac, plus macOS itself and the apps you installed by
downloading a `.dmg` or `.pkg`.

Those last ones are the interesting case. No package manager tracks them, so
they go stale silently. `update-my-mac` finds them and offers to start tracking
them, so they stop being invisible.

> **Status: in progress.** Checking and applying updates works for mas,
> Homebrew, npm and pnpm. The remaining sources in the table below and the
> untracked-app discovery are still being built; `--background` and
> `--retry-app` are stubs that exit 1.

## Usage

```bash
update                # interactive: find untracked apps, report, offer to apply
update --check        # report only, no prompts to apply
update --background   # unattended (launchd): no prompts, notify if anything is outdated
update --retry-app    # revisit apps you previously chose not to track
```

## What it checks

Whatever you have. Each source is skipped when its command is not installed, so
none of these is a requirement:

| Source | Checked with | |
| --- | --- | --- |
| Mac App Store | `mas` | ✅ |
| Homebrew | `brew` (formulae and casks) | ✅ formulae |
| JavaScript | global `npm`, `pnpm`, `yarn`, `bun` packages | ✅ npm, pnpm |
| macOS | `softwareupdate` | planned |
| MacPorts | `port` | planned |
| Python | `uv tool`, `pipx` | planned |
| Ruby | `gem` | planned |
| Rust | `cargo` | planned |
| Directly downloaded apps | app bundle versions | planned |

## Tracking a downloaded app

An app that came from a `.dmg` belongs to no package manager, so for each one
found you choose how it should be handled:

- **Adopt it into Homebrew Cask**, when `brew` is installed and a cask matches.
  Homebrew then knows about the app and it shows up in ordinary checks.
- **Watch it directly** — compare the installed bundle's version against the
  app's own update feed. Needs no package manager, and it is the only option for
  an app with no cask.
- **Ignore it**, remembered between runs and revisitable with `--retry-app`.

## Installation

```bash
git clone https://github.com/a-mi-go/update-my-mac.git
cd update-my-mac
./setup.sh
```

`setup.sh` runs once. It makes sure [uv](https://astral.sh/uv) is installed —
asking first, then using Homebrew if you have it and the official installer
otherwise — and then installs `update` into `~/.local/bin` with its own isolated
environment. It is installed from the clone, so a `git pull` updates the command
with no reinstall.

macOS is the only requirement; uv brings its own Python.

`setup.sh` asks what to call the command, `update` unless you choose otherwise,
or takes the name up front with `./setup.sh --name mac-update`. A name that
another program or a shell builtin already has is refused.

If zsh, bash or fish already define that name — an alias, a function, or a fish
abbreviation — you choose: keep it and give the command another name, or
disable it. Nothing changes without you picking it, and setup never installs a
command that something in your shell would hide; without a terminal to ask on,
it stops and suggests `--name`. Disabling comments out a one-line definition
(with a timestamped backup) or moves a fish function file aside; a multi-line
function has to be removed by hand, and setup says where it is.

Any name other than `update` is a plain symlink uv doesn't know about, so
`uv tool uninstall update-my-mac` leaves it behind — remove it yourself.

If the terminal you ran it from is older than your shell config and the old
definition is gone from the config, `setup.sh` says so and prints the line that
clears it from that terminal, in zsh/bash or fish syntax as needed.

Scheduled runs get a bare `PATH`, so the tool adds the usual locations itself
(`/opt/homebrew`, `/usr/local`, `/opt/local`, `~/.local/bin`, `~/.cargo/bin` and
pnpm's global bin). If your package managers live somewhere unusual, set
`UPDATE_MY_MAC_PREFIXES` to the prefixes to search — it replaces the list above
rather than adding to it, so include every prefix you need (colon-separated).
The home directories are always searched.

## Development

```bash
uv run pytest
```

Tests come in two layers, both run by CI on macOS and Linux:

- `tests/unit/` — pure logic, no mocking and no subprocesses.
- `tests/integration/` — runs the real CLI against fake package managers that
  sit alone on `PATH`, with an empty `HOME`, so nothing installed on the machine
  takes part.

## License

MIT © a-mi-go
