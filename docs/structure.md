# Where each thing belongs

## Why this note exists

Several names in this project resist improvement: `ManagerRun`, `behind`,
`_managers_still_behind`, `_check_the_mac`. Each one was rewritten more than
once and none of them ended up saying what it holds.

They resist because one idea is spread across several modules. Whether the
package managers themselves are current is asked in `package_managers`,
offered and performed in `apply_updates`, wrapped in a spinner in `app`, and
counted towards the exit status in `app` again. Four places, so four names for
one thing, and no single name can carry it.

This note says where each kind of thing should live, so the next changes have
somewhere to put it. It describes a target, not a rewrite.

## The layers

View and controller as MVC has them, a folder for the system edge that MVC
has no name for, and `checks/` where the model would be. The name is
deliberate: nine tenths of what would go in a `model/` folder here is code
that runs a subprocess to find something out, and a reader expecting data
classes would be misled.

| Layer | Modules | Rule |
| --- | --- | --- |
| Managers | `managers/` and `managers/homebrew/` | everything specific to the four tools: what they report, and the commands that drive them |
| Checks | `installed_apps`, `app_updaters`, `appcast`, `running_apps`, `duplicate_installations`, `app_decisions`, `versions` | establishes what is on this Mac apart from the tools. Prints nothing, asks nothing |
| View | `report`, `sections`, `prompting`, `keys` | turns findings into text and questions into answers |
| Controller | `app`, `self_update`, `resolve_issues`, `apply_updates`, `track_apps`, `catch_up_casks`, `resolve_duplicates`, `restart_apps` | decides what happens: asks the checks, drives the view, runs the command |
| System | `shell`, `environment` | runs commands, finds executables |

Three reading rules follow. A module in `checks/` that imports `rich` is in
the wrong folder. A controller that holds a rule about apps or packages is in
the wrong folder. And a controller that imports `rich` directly is reaching
past the view instead of through it.

## What the flat layout was doing

**`app.py` is four things at once.** 346 lines, 25 functions, 18 of the 27
modules imported. Only four of the functions are steps anyone calls. Of the
rest:

- twelve wire a walk-through and a bulk action into a `Problem`:
  `_problem`, `_brewing`, `_removal`, `_adoption`, `_app_walkthrough`,
  `_catch_up_walkthrough`, `_duplicate_walkthrough`, `_restart_walkthrough`,
  `_adopt_every_app_we_can`, `_remove_every_shadowed_copy`,
  `_catch_every_app_up`, `_restart_every_app`. That is an adapter layer living
  in the orchestrator. Each action module can offer its own `Problem` instead.
- three hold rules about apps or packages: `_issues`, `_untracked_problem`
  (which decides what is worth sorting out and writes the label for it),
  `_behind_the_recipe`.
- three are lookups with a cache: `_casks`, `_website_and_cask`,
  `_untracked_apps`.

`_exit_code` is the one private function that belongs here: the exit status is
the orchestrator's own output, and a scheduled caller reads nothing else.

**The package manager self-update had no home.** It was spread over the
manager check, the menu that offered it, and the orchestrator that counted the
result. That is the one that produced the unfixable names. It now lives in
`controller/self_update.py`.

**`apply_updates` builds its own menu.** `build_menu`, `print_menu` and
`parse_menu_answer` number and parse a list of options, which is what
`prompting.Step.choose` already does. The numbering convention is written
twice, in `print_menu` and again in `parse_menu_answer`, so adding a row means
editing both.

**Ten of the 27 modules import `rich`.** Two of them are the view
(`report`, `prompting`) and one is the installer, a program of its own. The
other seven are controllers reaching past the view: four import nothing but
`rich.markup.escape` to hand a name to a `Step` that would render it anyway
(`catch_up_casks`, `resolve_duplicates`, `restart_apps`, `track_apps`),
`apply_updates` builds a `Console` because it does not go through `Step` at
all, and `app` and `cli` each hold one for a spinner and for the line printed
on Ctrl-C.

The four `escape` imports are the cheap half: `Step` can escape what it is
given, and then four controllers stop knowing which library draws the screen.

**`adopting` is all three layers in 129 lines.** `compare_to_app`,
`can_adopt`, `would_downgrade` and `can_take_over` judge whether Homebrew
could take an app over, which is the model. `handover_label` and
`homebrew_note` write the text a person reads, which is the view.
`hand_to_homebrew` runs the command, which is the controller. As it stands the
module cannot go in any one folder, and that is the clearest argument for
having folders at all.

**`sections` imported `adopt_apps` and never used it.** A view importing a
controller, for nothing. The line is gone.

## The moves, in order

Six. The first makes the layers visible, the rest put things in them. Move 0
has landed, move 1 is half done, and moves 2 to 5 are open.

**0. The folders.** Four of them, named after the layers, with what is left at
the top:

```
update_my_mac/
    __init__.py
    __main__.py
    cli.py                        the entry point: flags in, dispatch out
    install_command.py            a program of its own
    shell_configs.py              only the installer uses it

    managers/                     the four tools we drive
        __init__.py               the table, what each one reports, and the
                                  commands that drive them
        homebrew/
            __init__.py           empty until move 1 fills it
            casks.py              the downloaded cask list
            behind_the_recipe.py  an app ahead of or behind its recipe
            adopting.py           handing an app over, and whether that works

    checks/                       what is on this Mac, apart from the tools
        __init__.py
        installed_apps.py         every bundle, and who owns it
        app_updaters.py           whether an app looks after itself
        appcast.py                what an app's own update source offers
        running_apps.py           still running an old version
        duplicate_installations.py  the same command from two managers
        app_decisions.py          what the person chose last time
        versions.py               comparing and shortening version strings

    view/
        __init__.py
        report.py                 the run's one report
        sections.py               rows and sections, loudest first
        prompting.py              a question, a menu, an answer
        keys.py                   the arrow keys, where the terminal allows

    controller/
        __init__.py
        app.py                    the order of the steps
        self_update.py            the managers renewing themselves
        resolve_issues.py         the one question before the updates
        apply_updates.py          the upgrade menu and what it runs
        track_apps.py             the walk-through for untracked apps
        catch_up_casks.py         casks Homebrew stopped noticing
        resolve_duplicates.py     dropping the copy PATH never reaches
        restart_apps.py           restarting what still runs old

    system/
        __init__.py
        shell.py                  running a command, finding an executable
        environment.py            the PATH a scheduled run needs
```

Layers at the top, with one exception made on purpose: `managers/` gathers
what is specific to the four tools, because 515 lines of Homebrew knowledge
are spread over four modules today and nothing in their names says so.
`cask_index`, `behind_the_recipe` and `adopt_apps` moved in there as
`casks`, `behind_the_recipe` and `adopting`.

`cli.py` stays at the top because it is the entry point rather than a
controller, and `app.py` goes into `controller/` because it is the one the
others hang off.

The exception costs one thing, and it is worth naming: `adopting.py` keeps
`handover_label` and `homebrew_note`, which write text a person reads. That is
view work sitting in the tool layer. Organising by layer and by subject at the
same time is not possible, and this is the seam. Move 5 can lift those two out
later.

The two paths baked in outside the package, the console script
`update_my_mac.cli:main` in `pyproject.toml` and
`python -m update_my_mac.install_command` in `setup.sh`, both point at modules
that stay at the top, so neither moves.

One placement is a guess rather than a conclusion. `sections.py` sits in the
view, but deciding that a false recorded version is critical while a quiet
feed is not is a judgement about the data. Its `Row` and `Section` shapes and
the order it prints them in are view work. Splitting it is a seventh move, and
this note does not plan it.

The folders go first because every move below then has an address instead of
an argument, and because the later moves would otherwise travel twice.

**1. `self_update.py` owns the managers' own currency.** Half done. The offer
and the doing are there, as `pick_managers` and `update`, and the rule about
who is still behind sits with the manager data as `managers.still_behind`.

What is still in `managers/__init__.py`: `check_self`, `check_homebrew_index`,
`describe_own_version` and `upgrade_self`, and with them the 127 brew-only
lines that belong in `homebrew/`, which is why that folder's `__init__.py` is
empty. The per-manager files for mas, npm and pnpm are two to eleven lines
each and are not worth their own file; their parsers stay in the table's
module.

The `MANAGERS` table stays there either way, because `self_check_args` and
`self_upgrade_args` are columns of it.

**2. Each action module offers its own `Problem`.** The twelve adapter
functions in `app` become one function per action module:
`catch_up_casks.problem(behind)`, `resolve_duplicates.problem(doubled)`,
`restart_apps.problem(stale)`, `track_apps.problem(untracked, ...)`. Then
`_issues` is four calls instead of twelve lambdas, and each module decides for
itself how its walk-through and its bulk action are wired.

`_untracked_problem` moves with it, into `track_apps`, which already holds
`worth_sorting_out`, `known_to_homebrew` and `ready_for_homebrew`. That rule
has no business in the orchestrator.

**3. `prompting` gains the multi-select.** `apply_updates` hands over a list
of options and stops numbering anything. `build_menu` stays, because it is
about managers and packages; `print_menu` and `parse_menu_answer` go.

**4. `package_managers` keeps the questions and loses the commands.**
`upgrade`, `upgrade_self`, `adopt_cask` and `install_cask_over` change the
Mac, so by the table above they do not belong in `checks/`. They move to the
action modules that call them: the first two to `self_update.py` and the
package upgrade, the cask pair to `adopting`.

**5. `adopting` splits three ways.** The four judgements go to `checks/`
beside `behind_the_recipe`, which answers the same kind of question. The two
label writers go to the view. `hand_to_homebrew` stays a controller, together
with the cask commands from move 4.

Afterwards `app.py` holds the four `run_*` modes, two step helpers, a
shortened `_issues` that is four calls, and `_exit_code`. Twenty-five
functions become about nine.

The parked work on `session-wip` waits until these have landed. It touches 73
files. Pouring that onto the current shape would mean moving it twice, and
naming it from a structure we already know we dislike.

## What this note does not say

It does not propose new abstractions, a plugin system, or a protocol between
the layers. Every step above moves existing code to a better address and
deletes what duplicates something else.
