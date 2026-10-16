import json
import os
import time

from fake_run import use_environment, swap

from update_my_mac.managers.homebrew import casks

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


def index_of(published=PUBLISHED):
    return casks.CaskIndex(casks.reduce_to_apps(published))


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


def test_a_cask_that_installs_a_package_is_kept_under_its_own_name():
    # Google Drive and Foxit ship installers and name no app, so nothing on
    # disk points at them. The token is the only handle left.
    found = index_of().for_app("/Applications/no app at all.app")

    assert found.token == "no-app-at-all"
    assert found.installs_a_package


def test_an_app_cask_is_not_marked_as_an_installer():
    assert not index_of().for_app("/Applications/Codex.app").installs_a_package


def test_a_package_cask_is_not_matched_against_an_app_it_does_not_name():
    assert index_of().for_app("/Applications/Something Else.app") is None


def test_a_cask_without_a_token_is_ignored():
    assert len(index_of([{"artifacts": [{"app": ["Orphan.app"]}]}])) == 0


def cached(tmp_path, by_app, age_in_seconds=0):
    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    path = casks.cache_path()
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

    use_environment(env)
    swap(casks, "download", refusing())
    index = casks.load()
    assert index.for_app("Codex.app").token == "codex-app"


def test_a_stale_cache_is_replaced(tmp_path):
    env = cached(tmp_path, {"Old.app": {"token": "old"}}, age_in_seconds=2 * 24 * 60 * 60)

    use_environment(env)
    swap(casks, "download", lambda: {"New.app": {"token": "new"}})
    index = casks.load()
    assert index.for_app("Old.app") is None
    assert index.for_app("New.app").token == "new"


def test_what_was_fetched_is_kept_for_next_time(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    swap(casks, "download", lambda: {"New.app": {"token": "new"}})
    casks.load()

    swap(casks, "download", refusing())
    assert casks.load().for_app("New.app").token == "new"


def test_a_stale_cache_beats_no_answer(tmp_path):
    # Offline, an old lookup table is still better than an empty one.
    env = cached(tmp_path, {"Old.app": {"token": "old"}}, age_in_seconds=9 * 24 * 60 * 60)

    use_environment(env)
    swap(casks, "download", refusing())
    assert casks.load().for_app("Old.app").token == "old"


def test_without_a_cache_or_a_network_the_index_is_simply_empty(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}

    use_environment(env)
    swap(casks, "download", refusing())
    assert len(casks.load()) == 0


def test_a_damaged_cache_does_not_stop_the_run(tmp_path):
    env = {"XDG_CACHE_HOME": str(tmp_path)}
    use_environment(env)
    path = casks.cache_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{ not json")

    swap(casks, "download", lambda: {"New.app": {"token": "new"}})
    assert len(casks.load()) == 1


def test_the_cache_sits_where_the_xdg_variables_say(tmp_path):
    use_environment({"XDG_CACHE_HOME": str(tmp_path)})
    xdg = casks.cache_path()
    assert xdg == tmp_path / "update-my-mac" / "casks.json"

    use_environment({"HOME": str(tmp_path)})
    default = casks.cache_path()
    assert default == tmp_path / ".cache" / "update-my-mac" / "casks.json"


def test_a_name_that_differs_only_in_case_is_not_claimed():
    # Tempting, because a Mac filesystem does not care about case. But the
    # orca cask installs plotly's orca, and the Orca in /Applications here is
    # a different program with the same name.
    index = casks.CaskIndex(casks.reduce_to_apps([
        {"token": "orca", "version": "1.3.1", "artifacts": [{"app": ["orca.app"]}]},
    ]))

    assert index.for_app("/Applications/Orca.app") is None
    assert index.for_app("/Applications/orca.app").token == "orca"
