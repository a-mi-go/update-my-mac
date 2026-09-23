import json

from update_my_mac import app_decisions


def decisions_in(tmp_path):
    return app_decisions.AppDecisions(tmp_path / "apps.json")


def test_nothing_is_ignored_before_anything_was_decided(tmp_path):
    decisions = decisions_in(tmp_path)

    assert decisions.ignored_names() == []
    assert not decisions.is_ignored("TokenEater")


def test_a_decision_survives_a_restart(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2")
    decisions.save()

    assert decisions_in(tmp_path).is_ignored("TokenEater")


def test_what_was_decided_and_when_is_written_down(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2", now=0)
    decisions.save()

    stored = json.loads((tmp_path / "apps.json").read_text())
    assert stored["version"] == 1
    assert stored["apps"]["TokenEater"]["decision"] == "ignore"
    assert stored["apps"]["TokenEater"]["version"] == "5.12.2"
    assert stored["apps"]["TokenEater"]["decided"].startswith("19")


def test_forgetting_brings_an_app_back(tmp_path):
    decisions = decisions_in(tmp_path)
    decisions.ignore("TokenEater", "5.12.2")
    decisions.forget("TokenEater")
    decisions.save()

    assert decisions_in(tmp_path).ignored_names() == []


def test_a_file_written_by_a_newer_version_is_not_acted_on(tmp_path):
    (tmp_path / "apps.json").write_text(
        json.dumps({"version": 99, "apps": {"TokenEater": {"decision": "ignore"}}})
    )

    assert decisions_in(tmp_path).ignored_names() == []


def test_a_damaged_file_does_not_stop_the_run(tmp_path):
    (tmp_path / "apps.json").write_text("{ this is not json")

    assert decisions_in(tmp_path).ignored_names() == []


def test_the_directory_is_created_when_needed(tmp_path):
    decisions = app_decisions.AppDecisions(tmp_path / "state" / "update-my-mac" / "apps.json")
    decisions.ignore("TokenEater", "5.12.2")
    decisions.save()

    assert (tmp_path / "state" / "update-my-mac" / "apps.json").exists()


def test_the_file_sits_where_the_xdg_variables_say(tmp_path):
    xdg = app_decisions.state_path({"XDG_STATE_HOME": str(tmp_path)})
    assert xdg == tmp_path / "update-my-mac" / "apps.json"

    default = app_decisions.state_path({"HOME": str(tmp_path)})
    assert default == tmp_path / ".local" / "state" / "update-my-mac" / "apps.json"


def test_an_interrupted_write_leaves_the_old_file_intact(tmp_path, monkeypatch):
    decisions = decisions_in(tmp_path)
    decisions.ignore("First", "1.0")
    decisions.save()

    decisions.ignore("Second", "2.0")
    monkeypatch.setattr(
        type(tmp_path / "x"), "replace", lambda *_: (_ for _ in ()).throw(OSError("full disk"))
    )
    try:
        decisions.save()
    except OSError:
        pass

    assert decisions_in(tmp_path).ignored_names() == ["First"]
