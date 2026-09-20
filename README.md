# update-my-mac

One command that checks — and optionally applies — software updates from every
package manager on your Mac, plus macOS itself and the apps you installed by
downloading a `.dmg` or `.pkg`.

Those last ones are the interesting case. No package manager tracks them, so
they go stale silently. `update-my-mac` finds them and offers to start tracking
them, so they stop being invisible.

> **Status: in progress.** `--check` works for mas, Homebrew, npm and pnpm.
> The remaining sources in the table below, the untracked-app discovery and
> applying updates are still being built; `--background` and `--retry-app` are
> stubs that exit 1.

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
ln -s "$PWD/update-my-mac/update" ~/.local/bin/update
```

`update` is a small bash launcher, not the Python program itself. It builds a
`PATH` containing the tools being queried, makes sure [uv](https://astral.sh/uv)
is installed — asking first, then using Homebrew if you have it and the official
installer otherwise — and hands off to `uv run`. From there uv resolves a
compatible Python, creates the project environment and installs dependencies on
its own, so there is no Python setup to do by hand.

macOS is the only requirement.

## Development

```bash
uv run pytest
```

Tests come in two layers, both run by CI on macOS and Linux:

- `tests/unit/` — pure logic, no mocking and no subprocesses.
- `tests/integration/` — runs the real CLI against fake package managers that
  sit alone on `PATH`, plus the launcher under launchd's environment.

## License

MIT © a-mi-go
