"""pnpm's global packages."""

from update_my_mac.managers.manager import PackageManager, parse_json_packages


class Pnpm(PackageManager):
    key = "pnpm"
    label = "pnpm (global)"
    command = "pnpm"
    outdated_args = ("outdated", "-g", "--json")
    upgrade_args = ("update", "-g")
    success_exit_codes = (0, 1)
    self_check_args = ("outdated", "-g", "pnpm", "--json")
    self_package = "pnpm"
    self_upgrade_args = ("self-update",)

    def parse_outdated(self, stdout):
        return parse_json_packages(stdout)
