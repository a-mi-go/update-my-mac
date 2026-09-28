import json
import os
import time

from update_my_mac import cask_index

PUBLISHED = [
    {
        "token": "codex-app",
        "homepage": "https://openai.com/codex",
        "version": "26.9",
        "artifacts": [{"app": ["Codex.app"]}],
    },
    {
        "token": "docker-desktop",
        "homepage": "https://www.docker.com/",
        "version": "4.92.0",
        "artifacts": [{"app": "Docker.app"}, {"binary": ["docker"]}],
    },
    {
        "token": "no-app-at-all",
        "homepage": "https://example.com/",
        "version": "1.0",
        "artifacts": [{"pkg": ["thing.pkg"]}],
    },
]


def index_of(casks=PUBLISHED):
    return cask_index.CaskIndex(cask_index.reduce_to_apps(casks))


def test_an_app_is_found_by_its_bundle_name():
    found = index_of().for_app("/Applications/Codex.app")

    assert found.token == "codex-app"
    assert found.homepage == "https://openai.com/codex"
    assert found.version == "26.9"


def test_a_cask_that_names_one_app_as_a_string():
    # Casks write a single app as a string and several as a list.
    assert index_of().for_app("/Applications/Docker.app").token == "docker-desktop"


def test_an_app_no_cask_ships_is_not_invented():
    assert index_of().for_app("/Applications/TokenEater.app") is None


def test_casks_without_an_app_are_skipped():
    assert len(index_of()) == 2


def test_a_cask_without_a_token_is_ignored():
    assert len(index_of([{"artifacts": [{"app": ["Orphan.app"]}]}])) == 0


def cached(tmp_path, by_app, age_in_seconds=0):
    path = cask_index.cache_path({"XDG_CACHE_HOME": str(tmp_path)})
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(by_app))
    when = time.time() - age_in_seconds
    os.utime(path, (when, when))
    return {"XDG_CACHE_HOME": str(tmp_path)}


def refusing():
    def fetch():
        raise OSError("no network")

    return fetch


def test_a_fresh_cache_is_used_without_fetching(tmp_path):
    env = cached(tmp_path, {"Codex.app": {"token": "codex-app"}})

    index = cask_index.load(env, refusing())
    assert index.for_app("Codex.app").token == "codex-app"


def test_a_stale_cache_is_replaced(tmp_path):
    env = cached(tmp_path, {"Old.app": {"token": "old"}}, age_in_seconds=2 * 24 * 60 * 60)

    index = cask_index.load(env, lambda: {"New.app": {"token": "new"}})
    assert index.for_app("Old.app") is None
    assert index.for_app("New.app").token == "new"


def test_what_was_fetched_is_kept_for_next_time(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    cask_index.load(env, lambda: {"New.app": {"token": "new"}})

    assert cask_index.load(env, refusing()).for_app("New.app").token == "new"


def test_a_stale_cache_beats_no_answer(tmp_path):
    # Offline, an old lookup table is still better than an empty one.
    env = cached(tmp_path, {"Old.app": {"token": "old"}}, age_in_seconds=9 * 24 * 60 * 60)

    assert cask_index.load(env, refusing()).for_app("Old.app").token == "old"


def test_without_a_cache_or_a_network_the_index_is_simply_empty(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}

    assert len(cask_index.load(env, refusing())) == 0


def test_a_damaged_cache_does_not_stop_the_run(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    path = cask_index.cache_path(env)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")

    assert len(cask_index.load(env, lambda: {"New.app": {"token": "new"}})) == 1


def test_the_cache_sits_where_the_xdg_variables_say(tmp_path):
    xdg = cask_index.cache_path({"XDG_CACHE_HOME": str(tmp_path)})
    assert xdg == tmp_path / "update-my-mac" / "casks.json"

    default = cask_index.cache_path({"HOME": str(tmp_path)})
    assert default == tmp_path / ".cache" / "update-my-mac" / "casks.json"


def test_a_name_that_differs_only_in_case_is_not_claimed():
    # Tempting, because a Mac filesystem does not care about case. But the
    # orca cask installs plotly's orca, and the Orca in /Applications here is
    # a different program with the same name.
    index = cask_index.CaskIndex(cask_index.reduce_to_apps([
        {"token": "orca", "version": "1.3.1", "artifacts": [{"app": ["orca.app"]}]},
    ]))

    assert index.for_app("/Applications/Orca.app") is None
    assert index.for_app("/Applications/orca.app").token == "orca"
