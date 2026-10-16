"""What the checks in here turn up, gathered as one run's answer."""

from dataclasses import dataclass, field


@dataclass
class Findings:
    """Everything one run turned up, before anyone decides how to show it."""

    managers_behind: list = field(default_factory=list)
    reports: list = field(default_factory=list)
    untracked: list = field(default_factory=list)
    offered: dict = field(default_factory=dict)
    left_alone: int = 0
    doubled: list = field(default_factory=list)
    apps_behind: list = field(default_factory=list)
    stale: list = field(default_factory=list)
    foreign: list = field(default_factory=list)
    flagged: list = field(default_factory=list)
    mounted: list = field(default_factory=list)
    find_cask: object = None
    any_manager_installed: bool = True
