from update_my_mac import package_managers
from update_my_mac.shell import CommandResult

NPM_OUTPUT = """Package  Current  Wanted  Latest  Location
typescript  5.4.2  5.4.5  5.4.5  global
prettier  3.2.0  3.3.0  3.3.0  global"""

PNPM_OUTPUT = """┌────────────────┬─────────┬────────┐
│ Package        │ Current │ Latest │
├────────────────┼─────────┼────────┤
│ eslint         │ 9.0.0   │ 9.12.0 │
└────────────────┴─────────┴────────┘"""


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


def test_npm_header_is_dropped():
    assert package_managers.parse_npm_outdated(NPM_OUTPUT) == [
        "typescript  5.4.2  5.4.5  5.4.5  global",
        "prettier  3.2.0  3.3.0  3.3.0  global",
    ]


def test_pnpm_keeps_only_the_package_rows():
    lines = package_managers.parse_pnpm_outdated(PNPM_OUTPUT)
    assert len(lines) == 1
    assert lines[0].startswith("eslint")


def test_pnpm_up_to_date_is_empty():
    assert package_managers.parse_pnpm_outdated("Everything up-to-date") == []


def test_missing_manager_is_skipped():
    shell = FakeShell(installed=(), result=CommandResult(True, ""))
    assert package_managers.check_for_outdated(manager("mas"), shell) is None


def test_failed_check_is_reported_not_raised():
    shell = FakeShell(installed=("brew",), result=CommandResult(False, "brew: boom"))

    report = package_managers.check_for_outdated(manager("brew"), shell)
    assert report.error_message == "brew: boom"
    assert report.outdated_packages == []


def test_brew_runs_without_an_auto_update():
    shell = FakeShell(
        installed=("brew",), result=CommandResult(True, "git (2.48.1) < 2.49.0")
    )

    package_managers.check_for_outdated(manager("brew"), shell)
    _, env = shell.calls[0]
    assert env["HOMEBREW_NO_AUTO_UPDATE"] == "1"


def test_check_installed_skips_everything_that_is_missing():
    shell = FakeShell(installed=(), result=CommandResult(True, ""))
    assert package_managers.check_installed(shell) == []
