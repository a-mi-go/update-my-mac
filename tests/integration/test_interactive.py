"""A bare `update`: check, report, then offer to upgrade.

The fakes record what they were asked to do, so these tests can assert that an
upgrade really was — or really wasn't — run.
"""

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).parent
MOCKS = HERE / "mocks"
FIXTURES = HERE / "fixtures"


def run_interactively(answer, scenario="outdated", log=None):
    env = {
        "PATH": f"{MOCKS}:/usr/bin:/bin",
        "MOCK_FIXTURES": str(FIXTURES / scenario),
        "HOME": str(Path.home()),
        "TERM": "dumb",
    }
    if log is not None:
        env["MOCK_LOG"] = str(log)

    return subprocess.run(
        [sys.executable, "-m", "update_my_mac"],
        env=env,
        input=answer,
        capture_output=True,
        text=True,
        timeout=120,
    )


def logged(log):
    return log.read_text().splitlines() if log.exists() else []


def test_everything_upgrades_each_outdated_manager(tmp_path):
    log = tmp_path / "calls.log"
    result = run_interactively("1\n", log=log)

    assert result.returncode == 0, result.stderr
    assert "What should be upgraded?" in result.stdout
    assert "mas upgrade" in logged(log)
    assert "brew upgrade" in logged(log)
    assert "npm update -g" in logged(log)
    assert "pnpm update -g" in logged(log)


def test_choosing_one_manager_leaves_the_others_alone(tmp_path):
    log = tmp_path / "calls.log"
    run_interactively("3\n", log=log)

    upgrades = [line for line in logged(log) if "outdated" not in line]
    assert upgrades == ["brew upgrade"]


def test_cancelling_upgrades_nothing(tmp_path):
    log = tmp_path / "calls.log"
    result = run_interactively("0\n", log=log)

    assert result.returncode == 0
    assert [line for line in logged(log) if "outdated" not in line] == []


def test_nothing_outdated_means_no_menu(tmp_path):
    log = tmp_path / "calls.log"
    result = run_interactively("1\n", scenario="clean", log=log)

    assert "What should be upgraded?" not in result.stdout
    assert "Everything is up to date" in result.stdout
    assert [line for line in logged(log) if "outdated" not in line] == []
