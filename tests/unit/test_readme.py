"""The planned sources live in the roadmap, so the README must follow it."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_sync():
    spec = importlib.util.spec_from_file_location("sync", REPO_ROOT / "docs" / "sync_readme.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_readme_says_what_the_roadmap_says():
    sync = load_sync()

    assert sync.expected_readme() == sync.README.read_text()


def test_only_the_first_column_is_taken():
    sync = load_sync()
    table = (
        "| Source | Command |\n"
        "| --- | --- |\n"
        "| `softwareupdate` | `softwareupdate --list` |\n"
        "| [Nix](https://github.com/NixOS/nix) | `nix profile list` |\n"
    )

    assert sync.names_in(table) == ["`softwareupdate`", "[Nix](https://github.com/NixOS/nix)"]


def test_the_roadmap_is_always_linked():
    sync = load_sync()

    assert "[roadmap](docs/roadmap.md)" in sync.sentence_for(["Nix"])


def test_the_names_are_separated_by_commas():
    sync = load_sync()

    assert sync.sentence_for(["Nix", "Cargo"]).startswith("Nix, Cargo.")
