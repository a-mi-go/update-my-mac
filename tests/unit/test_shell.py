from update_my_mac.system import shell


def test_only_web_addresses_are_opened():
    # Anything else here would mean opening a local file or handing the URL to
    # whatever application claims that scheme.
    assert shell.open_in_browser("file:///etc/passwd") is False
    assert shell.open_in_browser("/Applications/Calculator.app") is False
    assert shell.open_in_browser("http://example.com") is False
    assert shell.open_in_browser("") is False


def test_a_command_that_cannot_start_has_no_exit_code():
    # -1 would read as SIGHUP, which is a command that ran and was killed.
    assert shell.stream_command(["/nonexistent/program"]) is None


def test_a_command_that_never_ran_is_not_described_by_a_number():
    assert shell.describe_exit(None) == "could not be run"
    assert shell.describe_exit(2) == "exited with 2"
