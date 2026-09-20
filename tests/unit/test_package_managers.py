import pytest

from update_my_mac import package_managers
from update_my_mac.package_managers import CheckFailed
from update_my_mac.shell import CommandResult

NPM_OUTDATED = """{
  "typescript": {"current": "5.4.2", "wanted": "5.4.5", "latest": "5.4.5"},
  "prettier": {"current": "3.2.0", "wanted": "3.3.0", "latest": "3.3.0"}
}"""

# npm exits 1 for this too, which is why the exit code alone can't classify it.
NPM_NETWORK_FAILURE = """{
  "error": {
    "code": "ENOTFOUND",
    "summary": "request to https://registry.npmjs.org/typescript failed"
  }
}"""


class FakeShell:
    """Stands in for the shell module: same two functions, no subprocesses."""

    def __init__(self, installed, result):
        self.installed = installed
        self.result = result
        self.calls = []

    def find_executable(self, command):
        return f"/fake/{command}" if command in self.installed else None

    def run_command(self, args, success_exit_codes=(0,), env=None):
        self.calls.append((args, env))
        return self.result


def manager(key):
    return next(m for m in package_managers.MANAGERS if m.key == key)


def test_npm_json_becomes_one_line_per_package():
    assert package_managers.parse_npm_outdated(NPM_OUTDATED) == [
        "prettier  3.2.0 → 3.3.0",
        "typescript  5.4.2 → 5.4.5",
    ]


def test_empty_json_object_is_up_to_date():
    assert package_managers.parse_pnpm_outdated("{}") == []
    assert package_managers.parse_npm_outdated("") == []


def test_npm_error_payload_is_a_failed_check():
    with pytest.raises(CheckFailed, match="ENOTFOUND|request to"):
        package_managers.parse_npm_outdated(NPM_NETWORK_FAILURE)


def test_unreadable_output_is_a_failed_check():
    with pytest.raises(CheckFailed):
        package_managers.parse_npm_outdated("npm error code ENOTFOUND")


def test_failing_npm_is_reported_as_an_error_not_a_package():
    shell = FakeShell(
        installed=("npm",), result=CommandResult(True, NPM_NETWORK_FAILURE, "")
    )

    report = package_managers.check_for_outdated(manager("npm"), shell)
    assert report.outdated_packages == []
    assert "ENOTFOUND" in report.error_message


def test_stderr_is_never_parsed_as_packages():
    shell = FakeShell(
        installed=("npm",),
        result=CommandResult(True, "{}", "npm warn config global deprecated"),
    )

    report = package_managers.check_for_outdated(manager("npm"), shell)
    assert report.outdated_packages == []
    assert report.error_message == ""


def test_missing_manager_is_skipped():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    assert package_managers.check_for_outdated(manager("mas"), shell) is None


def test_nonzero_exit_is_reported_with_its_stderr():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(False, "", "brew: boom")
    )

    report = package_managers.check_for_outdated(manager("brew"), shell)
    assert report.error_message == "brew: boom"
    assert report.outdated_packages == []


def test_brew_runs_without_an_auto_update():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0", "")
    )

    package_managers.check_for_outdated(manager("brew"), shell)
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"


def test_check_installed_skips_everything_that_is_missing():
    shell = FakeShell(installed=(), result=CommandResult(True, "", ""))
    assert package_managers.check_installed(shell) == []
