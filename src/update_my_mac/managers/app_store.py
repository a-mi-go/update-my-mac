"""The Mac App Store, through mas."""

import re

from update_my_mac.managers.manager import PackageManager, nonblank_lines


class AppStore(PackageManager):
    key = "mas"
    label = "Mac App Store"
    command = "mas"
    outdated_args = ("outdated",)
    upgrade_args = ("upgrade",)
    counted_as = "apps"

    def parse_outdated(self, stdout):
        """Returns what `mas outdated` names: "497799835  Xcode  (14.0 -> 14.1)"."""
        apps = []
        for line in nonblank_lines(stdout):
            match = re.match(r"\d+\s+(.+?)\s+\((.+?)\s*->\s*(.+?)\)", line.strip())
            if match:
                name, current, latest = match.groups()
                apps.append(f"{name}  {current} → {latest}")
            else:
                apps.append(line.strip())
        return apps
