import json

import pytest


def with_a_cask_cache(home):
    """Writes an empty cask list, so a run reads it instead of fetching 10MB."""
    cache = home / ".cache" / "update-my-mac"
    cache.mkdir(parents=True, exist_ok=True)
    (cache / "casks.json").write_text(json.dumps({}))
    return home


@pytest.fixture(scope="session")
def empty_home(tmp_path_factory):
    """A home with nothing in it, so nothing installed here takes part."""
    return with_a_cask_cache(tmp_path_factory.mktemp("empty-home"))
