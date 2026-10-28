# update-my-mac

- The repository is public. Nothing in code, comments, tests or commit messages names one machine, its
  installed apps, local paths or a person.
- `docs/findings.md`, `docs/structure.md` and `docs/decisions.md` are local notes, ignored by git. Never
  mention or link them.
- Tests run with `uv run pytest`. `tests/unit/` starts no subprocesses; fakes go through the shared module
  objects, not through parameters that exist only for tests.
