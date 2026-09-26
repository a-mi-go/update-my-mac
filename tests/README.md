<p align="center">
  <img src="docs/logo.svg" width="128" alt="update-my-mac logo" />
</p>

<p align="center">
  Check and update all apps and packages of your Mac with one single tool.
</p>

<p align="center"><img alt="Platform" src="https://img.shields.io/badge/platform-macOS-blue" />&nbsp;<img alt="Python" src="https://img.shields.io/badge/python-3.10%2B-blue" />&nbsp;<img alt="License" src="https://img.shields.io/badge/license-MIT-green" />&nbsp;<a href="https://github.com/a-mi-go/update-my-mac/actions/workflows/ci.yml"><img alt="CI" src="https://github.com/a-mi-go/update-my-mac/actions/workflows/ci.yml/badge.svg" /></a></p>

<p align="center">
  <a href="https://buymeacoffee.com/a.mi.go">
    <img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" height="42" alt="Buy Me a Coffee" />
  </a>
</p>

---

> **Warning**
> Upgrading everything at once can break things. A new version of a package can
> pull in a change you were not ready for, and no upgrade asks whether your work
> still builds afterwards. This tool never upgrades without asking first, but
> what happens after you say yes is up to the package managers. Use it at your
> own risk.

update-my-mac is an interactive tool that checks your App Store, manually installed / untracked apps, apps and packages installed with various package managers,  and updates everything or what you tell it to.

## Usage

```bash
update
```

It reports, then asks. You pick which managers to upgrade and whether an app
should be left alone. Nothing runs before you answer, and upgrades run in your
terminal, so a password prompt from `brew` or `mas` works as usual.

```bash
update --check        # report only, no questions, for scripts and cron jobs
update --retry-app    # list an app again that you chose to leave alone
update --background   # planned: unattended run for launchd, notify only
```

`--check` exits non-zero only when a check could not run, not when something is
out of date.

## What it checks today

Each source is skipped when its command is not installed. None of them is a
requirement.

| Source | Checked with | Notes |
| --- | --- | --- |
| [mas](https://github.com/mas-cli/mas) | `mas outdated` | Mac App Store apps. Upgrades with `mas upgrade`. |
| [Homebrew](https://github.com/Homebrew/brew) | `brew outdated` | Formulae. Runs with `HOMEBREW_NO_AUTO_UPDATE=1`, so a scheduled check does not pull a new index first. Upgrades with `brew upgrade`. |
| [npm](https://github.com/npm/cli) | `npm outdated -g --json` | Global packages. JSON because npm exits 1 both when it finds updates and when it fails. Upgrades with `npm update -g`. |
| [pnpm](https://github.com/pnpm/pnpm) | `pnpm outdated -g --json` | Global packages. Upgrades with `pnpm update -g`. |
| Installed apps | `Info.plist` in `/Applications` and `~/Applications` | Apps from a `.dmg` or `.pkg` belong to no manager, so they are listed, not upgraded. You can tell the tool to leave one alone. |

## What is planned

| Source | Checked with | Notes |
| --- | --- | --- |
| `softwareupdate` | `softwareupdate --list` | Ships with macOS. Report always, install only when asked. |
| [Homebrew Cask](https://github.com/Homebrew/homebrew-cask) | `brew outdated --cask --greedy` | `brew outdated` compares what Homebrew recorded at install time, not the app on disk, and skips casks marked `auto_updates`. |
| [MacPorts](https://github.com/macports/macports-base) | `port outdated` | Upgrades with `port upgrade outdated`. |
| [Yarn](https://github.com/yarnpkg/yarn) | `yarn global list` | Only Yarn Classic has global installs. Yarn 2 and later dropped them, so there may be nothing to check there. |
| [Bun](https://github.com/oven-sh/bun) | not decided | Bun has global installs but no command that reports them as outdated. |
| [uv](https://github.com/astral-sh/uv) | `uv tool list --outdated` | Command line tools installed with `uv tool`. |
| [pipx](https://github.com/pypa/pipx) | `pipx list --json` | Python applications. |
| [RubyGems](https://github.com/rubygems/rubygems) | `gem outdated` | Installed gems. |
| [Cargo](https://github.com/rust-lang/cargo) | `cargo install --list` | Binaries installed from crates.io. |
| [Nix](https://github.com/NixOS/nix) | `nix profile list` | Reporting first. A Nix user may not want a tool outside Nix changing their profile. |

## Installation

```bash
git clone https://github.com/a-mi-go/update-my-mac.git
cd update-my-mac
./setup.sh
```

macOS is the only requirement, uv brings its own Python. Setup asks what to call
the command, or takes the name up front with `./setup.sh --name mac-update`.

## Updating

```bash
git pull
```

The command runs from the clone, so there is nothing to reinstall.

## Development

```bash
uv run pytest
```

Two layers, both run by CI on macOS and Linux. `tests/unit/` is pure logic with
no mocking and no subprocesses. `tests/integration/` runs the real CLI against
fake package managers that sit alone on `PATH`, with an empty `HOME`, so nothing
installed on the machine takes part.

## More

- [docs/setup.md](docs/setup.md): the command name, what setup does about an
  alias that would hide it, where your decisions about apps are kept.
- [docs/roadmap.md](docs/roadmap.md): what is next and what is still undecided.

## License

MIT © a-mi-go
