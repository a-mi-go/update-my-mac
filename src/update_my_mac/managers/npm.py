"""npm's global packages."""

from update_my_mac.managers.manager import PackageManager, parse_json_packages


class Npm(PackageManager):
    key = "npm"
    label = "npm (global)"
    command = "npm"
    outdated_args = ("outdated", "-g", "--json")
    upgrade_args = ("update", "-g")
    # npm exits 1 both when it finds updates and when it fails; only the JSON
    # tells them apart, by carrying an "error" key.
    success_exit_codes = (0, 1)
    self_check_args = ("outdated", "-g", "npm", "--json")
    self_package = "npm"
    self_upgrade_args = ("install", "-g", "npm@latest")

    def parse_outdated(self, stdout):
        return parse_json_packages(stdout)
