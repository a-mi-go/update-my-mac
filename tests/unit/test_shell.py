from update_my_mac import shell


def test_only_web_addresses_are_opened():
    # Anything else here would mean opening a local file or handing the URL to
    # whatever application claims that scheme.
    assert shell.open_in_browser("file:///etc/passwd") is False
    assert shell.open_in_browser("/Applications/Calculator.app") is False
    assert shell.open_in_browser("http://example.com") is False
    assert shell.open_in_browser("") is False
