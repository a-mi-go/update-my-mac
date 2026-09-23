"""The logo is generated, so the file in the repository has to match its script."""

import importlib.util
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def load_generator():
    spec = importlib.util.spec_from_file_location("logo", REPO_ROOT / "docs" / "logo.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_checked_in_logo_is_what_the_script_draws():
    logo = load_generator()
    drawn = logo.build("#2f6feb", "#1b4fc4", "#1b4fc4")

    assert drawn == (REPO_ROOT / "docs" / "logo.svg").read_text()
