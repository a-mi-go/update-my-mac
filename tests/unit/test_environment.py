from update_my_mac.system import environment

LAUNCHD_PATH = "/usr/bin:/bin:/usr/sbin:/sbin"


def everything_exists(_directory):
    return True


def only(*wanted):
    return lambda directory: directory in wanted


def test_a_launchd_path_gains_the_manager_locations():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert "/opt/homebrew/bin" in result
    assert "/Users/x/.local/bin" in result
    assert "/Users/x/.cargo/bin" in result
    assert result[:4] == LAUNCHD_PATH.split(":")


def test_pnpm_needs_its_own_global_bin_directory():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert "/Users/x/Library/pnpm/bin" in result


def test_a_configured_pnpm_home_wins():
    env = {"HOME": "/Users/x", "PNPM_HOME": "/elsewhere/pnpm", "PATH": LAUNCHD_PATH}
    result = environment.path_with_managers(env, everything_exists)

    assert "/elsewhere/pnpm/bin" in result
    assert "/Users/x/Library/pnpm" not in result


def test_directories_that_do_not_exist_are_left_out():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH}
    result = environment.path_with_managers(env, only("/opt/homebrew/bin"))

    assert result == f"{LAUNCHD_PATH}:/opt/homebrew/bin"


def test_what_is_already_there_is_not_added_twice():
    env = {"HOME": "/Users/x", "PATH": f"/opt/homebrew/bin:{LAUNCHD_PATH}"}
    result = environment.path_with_managers(env, everything_exists)

    assert result.count("/opt/homebrew/bin") == 1


def test_what_the_caller_chose_wins_over_what_we_guess():
    # An explicit PATH entry beats a directory we went looking for.
    env = {"HOME": "/Users/x", "PATH": "/my/tools"}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert result[0] == "/my/tools"


def test_personal_locations_come_before_system_ones():
    # A pnpm or uv the user installed should win over an older one in a prefix.
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert result.index("/Users/x/.local/bin") < result.index("/opt/homebrew/bin")


def test_prepare_rewrites_the_path_in_place():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH}
    environment.prepare(env)

    assert env["PATH"].startswith(LAUNCHD_PATH)


def test_prefixes_can_be_pointed_somewhere_else():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH, "UPDATE_MY_MAC_PREFIXES": "/nix/var/profile"}
    result = environment.path_with_managers(env, everything_exists)

    assert "/nix/var/profile/bin" in result
    assert "/opt/homebrew/bin" not in result


def test_an_empty_override_looks_in_no_prefixes():
    env = {"HOME": "/Users/x", "PATH": LAUNCHD_PATH, "UPDATE_MY_MAC_PREFIXES": ""}
    result = environment.path_with_managers(env, everything_exists)

    assert "/opt/homebrew/bin" not in result
    assert "/Users/x/.local/bin" in result


def test_a_missing_home_adds_nothing_relative():
    # env -i, or a launchd job with no EnvironmentVariables.
    env = {"PATH": "/usr/bin", "HOME": ""}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert all(entry.startswith("/") for entry in result)


def test_a_pnpm_home_inside_a_prefix_is_not_added_twice():
    env = {"HOME": "/Users/x", "PNPM_HOME": "/usr/local", "PATH": "/usr/bin"}
    result = environment.path_with_managers(env, everything_exists).split(":")

    assert result.count("/usr/local/bin") == 1
