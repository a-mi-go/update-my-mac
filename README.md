<p align="center">
  <img src="docs/logo.svg" width="128" alt="update-my-mac logo" />
</p>

<p align="center">
  One command for every update on your Mac.
</p>

<p align="center"><img alt="Platform" src="https://img.shields.io/badge/platform-macOS-blue" />&nbsp;<img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue" />&nbsp;<img alt="License" src="https://img.shields.io/badge/license-MIT-green" />&nbsp;<a href="https://github.com/a-mi-go/update-my-mac/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/a-mi-go/update-my-mac/actions/workflows/ci.yml/badge.svg" /></a></p>

---

update-my-mac checks for software updates from every package manager on your
Mac, plus macOS itself and the apps you installed by downloading a `.dmg` or
`.pkg`, and applies them when you ask it to.

Apps installed from a `.dmg` belong to no package manager, which is what makes
them go stale unnoticed. Those are listed separately, and an interactive run
offers to leave an app alone so it stops being listed. Adopting one into
Homebrew Cask or watching its update feed is the next thing being built.

## Usage

```bash
update                # report what is outdated, then offer to apply
update --check        # report only, no prompts to apply
update --background   # planned: unattended run for launchd, notify only
update --retry-app    # list an app again that you chose to leave alone
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
| Directly downloaded apps | app bundle versions | ✅ listed |

## Installation

```bash
git clone https://github.com/a-mi-go/update-my-mac.git
cd update-my-mac
./setup.sh
```

macOS is the only requirement; uv brings its own Python. Setup asks what to
call the command, or takes the name up front with `./setup.sh --name mac-update`.

## Updating

```bash
git pull
```

The command runs from the clone, so there is nothing to reinstall.

## Development

```bash
uv run pytest
```

Tests come in two layers, both run by CI on macOS and Linux:

- `tests/unit/`: pure logic, no mocking and no subprocesses.
- `tests/integration/`: runs the real CLI against fake package managers that
  sit alone on `PATH`, with an empty `HOME`, so nothing installed on the machine
  takes part.

## More

- [docs/setup.md](docs/setup.md): choosing the command name, what setup does
  about an alias that would hide it, and where the tool looks for package
  managers.
- [docs/roadmap.md](docs/roadmap.md): what is built, what is next, and the open
  questions.

## License

MIT © a-mi-go
