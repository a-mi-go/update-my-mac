# Setup and configuration

What `setup.sh` does beyond installing, and the one setting the tool has.

## Choosing the command name

The command is called `update` unless you choose otherwise, either at the
question setup asks or up front with `--name`. A name another program or a
shell builtin already answers to is refused. Every question comes before
anything is installed, so stopping partway leaves the machine as it was.

Running setup again recognises the earlier install from what is in uv's bin
directory and offers to keep the name it has. Without a terminal to ask on, it
keeps that name rather than falling back to `update`.

Any name other than `update` is a symlink to it. uv doesn't know about that
symlink, so `uv tool uninstall update-my-mac` leaves it behind for you to
remove.

## When your shell already defines that name

An alias, a function or a fish abbreviation wins over anything on `PATH`, so it
would hide the installed command. Setup finds such definitions in zsh, bash and
fish configuration and offers two ways out: keep the definition and call the
command something else, or disable the definition. Nothing changes without you
picking one, and setup never installs a command your shell would hide. Without
a terminal to ask on, it stops and suggests `--name`.

Disabling comments out a one-line definition, keeping a timestamped backup of
the file, or moves a fish function file aside. A function spanning several lines
has to be removed by hand, and setup says where it is.

## A terminal that still holds an old definition

A definition lives in the memory of the shell that loaded it, so a terminal
opened earlier keeps an alias that the configuration no longer has. Reloading
the configuration does not remove it, because sourcing a file adds what is in it
and deletes nothing.

When the terminal you ran setup from is older than your shell configuration, and
the definition is gone from that configuration, setup says so and prints the
line that clears it from that terminal, in zsh, bash or fish syntax as needed.
Opening a new tab works as well.

## Where your decisions are kept

Choosing to leave an app alone is written to
`~/.local/state/update-my-mac/apps.json`, or under `XDG_STATE_HOME` when you
have that set. It is a small JSON file you can read, copy to another machine or
delete; deleting it means every app is offered again.

Nothing else is stored, and a run that only checks never writes it. If the file
cannot be written, the run says so and carries on rather than stopping.

## Where the tool looks for package managers

A scheduled run starts with a bare `PATH`, so the tool adds the usual locations
itself: `/opt/homebrew`, `/usr/local`, `/opt/local`, `~/.local/bin`,
`~/.cargo/bin` and pnpm's global bin directory. They are appended, so anything
already on your `PATH` still wins.

If your package managers live somewhere unusual, set `UPDATE_MY_MAC_PREFIXES`
to the prefixes to search, colon-separated. It replaces the list of prefixes
above rather than adding to it, so include every prefix you need. The home
directories are always searched.
