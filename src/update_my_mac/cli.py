"""Command line entry point. Flags in, dispatch out — no logic here."""

import argparse

from update_my_mac import __version__, app


def build_argument_parser():
    parser = argparse.ArgumentParser(
        prog="update",
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


def main(argv=None):
    args = build_argument_parser().parse_args(argv)

    if args.check:
        return app.run_check_mode()

    if args.background:
        mode = "--background"
    elif args.retry_app:
        mode = "--retry-app"
    else:
        mode = "interactive"

    # Exit non-zero so a scaffold run can't be mistaken for "nothing to update".
    print(f"update-my-mac: {mode} mode is not implemented yet.")
    return 1
