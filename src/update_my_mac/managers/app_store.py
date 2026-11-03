"""The Mac App Store, through mas."""

import re

from update_my_mac.managers.manager import PackageManager, nonblank_lines
from update_my_mac.system import shell

NO_DOWNLOAD = re.compile(r"No downloads initiated for ADAM ID (\d+)")
PROGRESS_NOTICE = re.compile(rb"[^\n]*Update progress cannot be displayed[^\n]*\n?")
UPDATES_PAGE = "macappstore://showUpdatesPage"


class AppStore(PackageManager):
    key = "mas"
    label = "Mac App Store"
    command = "mas"
    outdated_args = ("outdated",)
    upgrade_args = ("upgrade",)
    counted_as = "apps"
    asks_for_password = True
    failure_hint = (
        "An app the App Store refuses to download can be updated in the App Store app instead; "
        "if it refuses there too, it belongs to another Apple Account: sign in with that one."
    )

    def __init__(self):
        self._names_by_id = {}

    def upgrade(self, status=None):
        exit_code = super().upgrade(status)
        ids = NO_DOWNLOAD.findall(shell.output_of_last_streamed_command())
        self.refused_in_last_upgrade = frozenset(self._names_by_id[one] for one in ids if one in self._names_by_id)
        return exit_code

    def rewrite_output_chunk(self, chunk):
        """Returns the output without mas's note that it cannot show progress."""
        return PROGRESS_NOTICE.sub(b"", chunk)

    def open_updates_page(self):
        """Opens the App Store app on its list of updates. Returns whether it worked."""
        executable = shell.find_executable("open")
        return executable is not None and shell.run_command([executable, UPDATES_PAGE]).success

    def parse_outdated(self, stdout):
        apps = []
        for line in nonblank_lines(stdout):
            match = re.match(r"(\d+)\s+(.+?)\s+\((.+?)\s*->\s*(.+?)\)", line.strip())
            if match:
                app_id, name, current, latest = match.groups()
                self._names_by_id[app_id] = name
                apps.append(f"{name}  {current} → {latest}")
            else:
                apps.append(line.strip())
        return apps
