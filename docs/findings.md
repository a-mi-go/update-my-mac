# What the run found, and who turns it into a report

## Why this note exists

`docs/structure.md` left one placement open and said so: "One placement is a
guess rather than a conclusion. `sections.py` sits in the view, but deciding
that a false recorded version is critical while a quiet feed is not is a
judgement about the data."

Measuring it turned up more than a guess. The run's central data type lives in
the view, two of its fields are there only so that whoever reads them can do
arithmetic, and one answer is worked out in three places by two different
rules, which already contradict each other on screen. Half of `report.py` is
unreachable, which is how the rules drifted apart unnoticed.

This note says where the seam between a finding and its report belongs. It
describes a target, not a rewrite.

## What the measurements say

**`Findings` is the run's own data, and it is defined in the view.** Eleven
fields, one per check. `controller/app.py:260` builds it, fills it field by
field as each check answers, and hands it to `view/report.py:87`. The only
place it is defined is `view/sections.py:61`.

**Two of its eleven fields are not findings.** `offered` holds what every app's
update feed answered, `find_cask` is a lookup function the controller injects.
Neither is a result anyone reports. They are sources, handed on so that
whoever gets them can work out what is on offer for an app, and three places
do: `view/sections.py`, `view/report.py`, and the walk-through, which takes
both as arguments at `controller/track_apps.py:21` and `:25` by way of
`controller/app.py:68`.

**The view asks the checks nine times.** `sections.py` imports
`checks/app_updaters`, `checks/appcast` and `checks/versions`, and calls into
them at nine places. `appcast.answer_for` four times, two of those for the same
app in one comprehension: `_feeds_gone_quiet` at lines 139 and 141 asks once to
decide whether the row belongs and once to fill it in.

**Every other check already hands over a finished answer.** An app behind its
recipe arrives with `version_change()` and `false_version_recorded` on it, from
`managers/homebrew/behind_the_recipe.py`. A doubly installed command arrives
with `describe()`, a stale one with `comment()`. The view reads a field and
lays it out. Untracked apps are the one path that breaks the pattern, and the
disagreement below sits on it.

**The same answer is worked out three times, by two different rules.** Whether
a recipe offers something newer than the app on disk is decided at
`sections._updates_available:270`, at `report._version_column:207` and at
`track_apps.worth_sorting_out:59`. As they stood:

```python
# sections.py
if cask and not versions.any_version_matches(app.versions_named(), cask.version):
    if versions.is_newer(cask.version, than=app.version):

# report.py, and track_apps.py before the fix below
if cask and versions.is_newer(cask.version, than=app.version):
return cask is not None and versions.is_newer(cask.version, than=app.version)
```

`sections` holds back when one of the versions the app names for itself already
matches the recipe. The other two did not.

Which of the rules is right was never open. `versions_named()` returns
`[version, build]`, and the comment on that field in
`checks/installed_apps.py:26` says what it is for: "Sometimes the only version
a Homebrew recipe matches." The `report.py` copy is on the dead path below, but
the `track_apps` one was live, so an app whose recipe matched its build rather
than its short version was printed as current in the report and offered as
worth sorting out in the menu underneath it, in the same run.

That one is fixed, in the same branch as this note: `worth_sorting_out` now
asks `adopting.compare_to_app(app, cask) == adopting.NEWER`, which already
accounted for the build and was imported in that module anyway. The
disagreement on screen is gone. What remains is the shape that produced it,
three callers each working the answer out for themselves, and that is what
moves 0 and 2 are for.

**Half of `report.py` has no caller in the program.** Nine of its functions,
151 of its 300 function lines: `print_manager_updates`,
`print_still_running_old`, `print_behind_the_recipe`,
`print_duplicate_installations`, `print_foreign_owners`,
`print_untracked_apps`, `_print_group`, `_version_column` and
`_say_which_feeds_went_quiet`. They are the path from before `sections`
existed, one printing function per section, replaced by
`report.print_report(findings)` walking `sections.of(findings)`. Fifteen of the
40 tests in `tests/unit/test_report.py` call them, which is the only reason
they are still here, and it is why nobody saw the two rules drift apart.

## The moves, in order

Moves 0 and 1 have landed, moves 2 and 3 are open.

**0. Delete what nothing calls. Landed.** The nine functions and the fifteen
tests went: `report.py` from 381 to 207 lines, the suite from 586 to 571 tests.
Fourteen of the fifteen asserted wording the live path does not use any more,
and the fifteenth is the chown command noted below. It took the second of the
three copies of the version question out, leaving one asker in the view and one
in the walk-through for move 2 to join up.

The deletion left one real loss, and it is a decision rather than a tidy-up.
`print_foreign_owners` printed a command you could paste:

```
sudo chown -R $(id -un) "/Applications/Firefox.app" "/Applications/Disk Drill.app"
```

The live report says only `chown it to yourself first`, once per row. Carrying
the command over is not a one-liner: a `Row` note holds a short phrase in a
folding column, so a long path would wrap and break the paste, and a `Section`
note is a dim right-aligned line on the heading. Either each row carries its
own command, or `Section` gains a trailing line below its rows.

The triage that preceded it was worth the time, and nothing had to be rehomed.
`tests/unit/test_sections.py` already made fourteen of the fifteen claims about
the live path: the four untracked groups, switched off against nobody
answered, a quiet feed listed once, a failed check, the managers that had
nothing to say, and an empty section printing nothing.
`any_manager_installed` turned out to be covered at `report.py:119` with its
own test, and markup in a name and version is covered through
`print_outdated_summary`, which is live. The deleted tests asserted the old
vocabulary, "Not tracked by any package manager", "Possibly don't update at
all", "These update themselves", which the live sections stopped using.

**1. `Findings` leaves the view. Landed.** It sits in `checks/__init__.py`,
not in a `checks/findings.py` as this note first proposed. The layer table in
`docs/structure.md` says `checks/` "establishes what is on this Mac apart from
the tools. Prints nothing, asks nothing", and a dataclass with one field per
check prints nothing and asks nothing. The file was empty, so the type became
the package's own shape, the way `managers/__init__.py` holds the registry,
rather than a module of fifteen lines holding one class.

The move paid for itself at one line: `controller/app.py` imported
`view/sections.py` for nothing but `Findings`, so that import is gone and no
controller reaches into the view any more except through `report`, `prompting`
and `keys`.

One trap worth recording. `app.py` uses the name `findings` for a local
variable thirty-two times, so importing the module would shadow it. The class
is imported by name instead.

**2. The checks answer, everyone else lays out.** `offered` and `find_cask`
stop being handed around. An untracked app arrives knowing what is on offer
for it and what watches it, the way an app behind its recipe already arrives
knowing its `version_change()`. Then `sections.py` stops importing `appcast`
and `versions`, the nine calls into the checks become field reads, and
`_updates_available`, `_what_is_known_about` and `_untracked_not_already_listed`
move to whichever check computes them.

This is the move that makes the disagreement impossible rather than merely
fixed, and that is the reason to make it. `worth_sorting_out` reads the same
field as the report instead of asking the same question in its own words, so
there is no second rule to keep in step with the first.

Which check that is, is the decision this move makes, and this note does not
settle it. `checks/app_updaters.py` already answers what watches an app and
already groups them with `group_by_status`, which argues for extending it. But
it knows nothing about casks today, and teaching it would tie a check to the
Homebrew package. The alternative is a check of its own for the question "what
would update this app, and to what".

**3. What stays is the view.** `Row`, `Section`, the three levels, `of()` with
its builders, `count_findings` and `clean_managers`. Choosing that a false
recorded version is critical while a quiet feed is not, and that Homebrew is
printed before npm, is editorial work, and editorial work belongs in the view.
`docs/structure.md` called this placement a guess. It is not: the judgement
about loudness is a view judgement. What was wrong was the arithmetic
underneath it, which moves 1 and 2 take out.

## What this note does not say

It does not propose a template language, a formatter abstraction, or a protocol
between the checks and the view. Move 0 deletes, move 1 moves a dataclass, and
move 2 moves three functions to the side of the seam that has the data.
