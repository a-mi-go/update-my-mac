"""Write the planned sources into the README, from the roadmap's table.

Markdown has no include, so the list would otherwise be kept in two places and
would drift. The roadmap holds the table with the commands, the README gets the
names alone and a link to the rest:

    uv run python docs/sync_readme.py

A test fails when the two have come apart, so nobody has to remember.
"""

import pathlib
import re
import sys

REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent
ROADMAP = REPO_ROOT / "docs" / "roadmap.md"
README = REPO_ROOT / "README.md"
START = "<!-- planned-sources:start -->"
END = "<!-- planned-sources:end -->"


def table_from(text):
    found = re.search(f"{re.escape(START)}\n(.*?){re.escape(END)}", text, re.S)
    if found is None:
        raise SystemExit(f"no {START} block found in the roadmap")
    return found.group(1)


def names_in(table):
    """The first column of every row, minus the header and the divider."""
    names = []
    for line in table.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        first = line.strip("|").split("|")[0].strip()
        if not first or first == "Source" or set(first) <= set("- :"):
            continue
        names.append(first)
    return names


def sentence_for(names):
    listed = ", ".join(names)
    return (
        f"{listed}.\n\n"
        "The commands and the open questions behind each of these are in the "
        "[roadmap](docs/roadmap.md).\n"
    )


def readme_with(block):
    return re.sub(
        f"{re.escape(START)}\n.*?{re.escape(END)}",
        f"{START}\n{block}{END}",
        README.read_text(),
        flags=re.S,
    )


def expected_readme():
    return readme_with(sentence_for(names_in(table_from(ROADMAP.read_text()))))


def main():
    wanted = expected_readme()
    if wanted == README.read_text():
        print("README is already in step with the roadmap")
        return 0

    README.write_text(wanted)
    print("README updated from the roadmap")
    return 0


if __name__ == "__main__":
    sys.exit(main())
