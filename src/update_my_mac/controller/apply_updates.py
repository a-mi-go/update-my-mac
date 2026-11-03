"""Applying updates: the only module that changes the system."""

from dataclasses import dataclass, field
from update_my_mac.view import arrow_menu
from update_my_mac.view import output
from update_my_mac import managers
from update_my_mac.controller import close_apps
from update_my_mac.system.shell import describe_exit
from update_my_mac.view import prompting
from update_my_mac.view import report

CANCEL = "cancel"
UPDATE = "update"
PACKAGES = "packages"


@dataclass
class MenuEntry:
    kind: str
    label: str
    keys: list = field(default_factory=list)
    # What was outdated when the menu was drawn, to compare against afterwards.
    outdated: list = field(default_factory=list)
    left_outdated: frozenset = frozenset()


def build_menu(reports):
    entries = []
    for report in reports:
        if not report.outdated_packages:
            continue
        entries.append(
            MenuEntry(
                PACKAGES,
                f"{report.label} ({len(report.outdated_packages)} {noun_for_outdated(report)})",
                [report.manager],
                outdated=list(report.outdated_packages),
            )
        )

    return entries


def noun_for_outdated(report):
    """Returns the word for the report's outdated lines, singular for one: "package" or "packages"."""
    plural = managers.by_key(report.manager).counted_as
    return plural if len(report.outdated_packages) != 1 else plural[:-1]


def parse_menu_answer(answer, entries):
    """Returns the chosen entries, or CANCEL, or None when the answer made no sense."""
    answer = answer.strip().lower()
    if answer in ("", "q", "c", "cancel", "exit", "0"):
        return CANCEL

    # Every part has to make sense before any of it counts, otherwise
    # "1,garbage" would quietly pass as "everything".
    numbers = []
    for part in answer.split(","):
        part = part.strip()
        if not part.isdigit():
            return None
        numbers.append(int(part))

    nothing = len(entries) + 2
    if nothing in numbers:
        return CANCEL
    if any(not 1 <= number <= len(entries) + 1 for number in numbers):
        return None
    if 1 in numbers:
        return list(entries)

    chosen = []
    for number in numbers:
        entry = entries[number - 2]
        if entry not in chosen:
            chosen.append(entry)
    return chosen or None


def print_menu(entries):
    console = output.console
    console.print("\nWhat should be updated?\n")
    labels = ["update everything!"] + [entry.label for entry in entries] + [
        f"{prompting.WAY_OUT}exit without updating"
    ]
    for number, label in enumerate(labels, start=1):
        output.print_plain("  ", (f"{number})", "cyan"), " ", label)
    console.print("[dim]One number, or several separated by commas.[/]")


def pick_what_to_update(entries):
    """Returns the entries that are ticked when Enter is pressed, or CANCEL."""
    choices = [(entry, entry.label) for entry in entries] + [
        arrow_menu.BLANK_LINE,
        (UPDATE, "⬆ update"),
        None,
        (CANCEL, f"{prompting.WAY_OUT}exit without updating"),
    ]
    picked = arrow_menu.pick_several(
        "What should be updated?",
        choices,
        ends_menu=(CANCEL,),
        confirm=UPDATE,
        checked=entries,
        start_at=UPDATE,
    ) or []
    if CANCEL in picked:
        return CANCEL
    return picked or CANCEL


def run_each_manager(manager_keys, announce, run_one, dotted=False):
    """Runs one step per manager. With `dotted`, each ends in a single dotted line
    instead of starting under a heading of its own."""
    console = output.console
    done, failed = [], []
    for key in manager_keys:
        manager = managers.by_key(key)
        label = f"{announce} {manager.label}"
        if dotted:
            console.print()
            status = report.waiting_spinner(label)
        else:
            console.print(f"\n{label}")
            if manager.asks_for_password:
                console.print("[dim]It may ask for your password.[/]")
            status = report.waiting_spinner(f"waiting for {manager.label}")
        with prompting.warning_before_stopping():
            exit_code = run_one(manager, status)
        how = describe_exit(exit_code) if exit_code != 0 else ""
        if dotted:
            console.print(report.dotted_line(label, how or "done", not how))
        elif how:
            console.print(f"[yellow]{manager.label} {how}[/]")
        if how:
            failed.append((key, how))
        else:
            done.append(key)
    return done, failed


def upgrade_managers(manager_keys):
    return run_each_manager(
        manager_keys, "Upgrading",
        lambda manager, status: manager.upgrade(status),
    )


@dataclass
class UpdateRun:
    """Whether any manager was updated, and which ones failed."""

    failed: list
    ran: bool


NOTHING_UPDATED = UpdateRun([], False)


def update_the_only_manager(reports):
    """Updates the one manager with something outdated without asking. Returns how it went."""
    output.console.print()
    prompting.print_separator()
    return UpdateRun(run_chosen(build_menu(reports)), True)


def has_only_one_manager_to_update(reports):
    """Returns whether exactly one manager has something outdated."""
    return len(build_menu(reports)) == 1


def ask_what_to_update(reports):
    """Asks which managers to update and updates them. Returns how it went."""
    console = output.console
    entries = build_menu(reports)
    if not entries:
        return NOTHING_UPDATED

    console.print()
    prompting.print_separator()

    if arrow_menu.can_be_drawn():
        while True:
            try:
                chosen = pick_what_to_update(entries)
            except KeyboardInterrupt:
                prompting.interrupted(prompting.print_unwrapped)
                continue
            except arrow_menu.Unusable as failure:
                console.print(arrow_menu.unusable_message(failure))
                break  # out of this loop only: the numbered menu below takes over
            prompting.answered()
            return NOTHING_UPDATED if chosen == CANCEL else UpdateRun(run_chosen(chosen), True)

    while True:
        print_menu(entries)
        try:
            answer = prompting.read_answer("> ")
        except EOFError:
            # No more input. Silence is not consent to upgrade.
            console.print("\nNothing updated.")
            prompting.answered()
            return NOTHING_UPDATED

        chosen = parse_menu_answer(answer, entries)
        if chosen is None:
            console.print("[yellow]Didn't catch that.[/]")
            continue
        prompting.answered()
        return NOTHING_UPDATED if chosen == CANCEL else UpdateRun(run_chosen(chosen), True)


def print_what_changed(entries):
    """Returns the managers that could not be asked again."""
    console = output.console
    # Asked again rather than taken from the upgrade's own output: a manager
    # can report success and still leave a package where it was.
    console.print()
    could_not_confirm = []
    for entry in entries:
        manager = managers.by_key(entry.keys[0])
        with report.waiting_spinner(f"asking {manager.label} again what is outdated"):
            again = manager.outdated()
        if again is None or again.error_message:
            output.print_plain(f"{manager.label}: could not check again", style="yellow")
            could_not_confirm.append(manager.key)
            continue

        remaining = again.outdated_packages
        entry.left_outdated = frozenset(report.item_from_package_line(one).name for one in remaining)
        updated = max(0, len(entry.outdated) - len(remaining))
        if not remaining:
            output.print_plain((manager.label, "green"), f": {len(entry.outdated)} updated")
            continue

        output.print_plain(
            (manager.label, "yellow"), f": {updated} of {len(entry.outdated)} updated, still outdated:"
        )
        items = [report.item_from_package_line(package) for package in remaining]
        for item in items:
            if item.name in manager.refused_in_last_upgrade:
                item.comment = "no download started"
        report.print_as_list_or_grid("    ", items)
        if manager.failure_hint:
            output.print_plain(f"    {manager.failure_hint}", style="dim")
    return could_not_confirm


def run_chosen(entries):
    upgraded = [entry for entry in entries if entry.kind == PACKAGES]
    package_keys = [key for entry in upgraded for key in entry.keys]
    closed = close_apps.ask_before_the_update(upgraded)
    _, failed = upgrade_managers(package_keys)
    could_not_confirm = print_what_changed(upgraded)
    _offer_the_app_store(upgraded)
    close_apps.ask_to_start_again(closed)
    return [key for key, _ in failed] + could_not_confirm


def _offer_the_app_store(upgraded):
    """Offers to open the App Store app on the updates mas left outdated."""
    if not any(entry.keys == ["mas"] and entry.left_outdated for entry in upgraded):
        return
    step = prompting.Step()
    step.print_empty_line()
    try:
        wants_to = step.yes_or_no("Open the App Store to update them there?")
    except prompting.Stopped:
        return
    if wants_to and not managers.by_key("mas").open_updates_page():
        step.print_indented("The App Store could not be opened.", style="yellow")
