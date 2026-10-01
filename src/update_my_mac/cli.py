"""Command line entry point. Flags in, dispatch out, no logic here."""

import argparse

from update_my_mac import __version__, app, environment

from rich.console import Console


def build_argument_parser(prog=None):
    parser = argparse.ArgumentParser(
        prog=prog,
        description="Check and apply macOS updates across every source you use.",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"update-my-mac {__version__}",
    )

    modes = parser.add_mutually_exclusive_group()
    modes.add_argument(
        "--check",
        action="store_true",
        help="report what is outdated; never offer to apply",
    )
    modes.add_argument(
        "--background",
        action="store_true",
        help="unattended mode for scheduled runs: no prompts, notify only",
    )
    modes.add_argument(
        "--retry-app",
        action="store_true",
        help="revisit apps you previously chose not to track",
    )
    return parser


def main(argv=None, prog=None):
    # prog is None for the installed command, so the help names whatever it
    # was invoked as, including a second name chosen during setup.
    args = build_argument_parser(prog).parse_args(argv)
    environment.prepare()

    try:
        return _run(args)
    except KeyboardInterrupt:
        # Ctrl-C ends the run wherever it arrives. Nothing below catches it,
        # so a question, a walk-through and a download all stop the same way.
        Console(highlight=False).print(
            "\n[yellow]Stopped.[/] Whatever had already run has run, "
            "nothing new was started."
        )
        return 130


def _run(args):
    if args.check:
        return app.run_check_mode()

    if args.retry_app:
        return app.run_retry_app_mode()

    if args.background:
        mode = "--background"
    else:
        return app.run_interactive_mode()

    # Exit non-zero so a stub run can't be mistaken for "nothing to update".
    print(f"update-my-mac: {mode} mode is not implemented yet.")
    return 1
