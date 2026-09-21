import pytest


@pytest.fixture(scope="session")
def empty_home(tmp_path_factory):
    """A home with nothing in it, so nothing installed here takes part."""
    return tmp_path_factory.mktemp("empty-home")
