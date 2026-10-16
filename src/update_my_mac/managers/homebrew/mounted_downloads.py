"""Disk images of Homebrew's downloads that are still attached.

A cask upgrade that stopped halfway leaves its download mounted, and every
later attempt to attach the same file fails with "Resource busy".
"""

import plistlib
from dataclasses import dataclass
from pathlib import Path

from update_my_mac.managers.homebrew import brew
from update_my_mac.system import shell


@dataclass
class MountedImage:
    path: Path
    device: str


def find():
    """Returns the disk images from Homebrew's download folder that are attached."""
    executable = shell.find_executable("hdiutil")
    cache = brew.download_cache()
    if executable is None or cache is None:
        return []

    result = shell.run_command([executable, "info", "-plist"], (0,))
    if not result.success:
        return []
    try:
        images = plistlib.loads(result.stdout.encode()).get("images", [])
    except (plistlib.InvalidFileException, ValueError):
        return []

    downloads = Path(cache) / "downloads"
    found = []
    for image in images:
        path = Path(image.get("image-path", ""))
        entries = image.get("system-entities") or [{}]
        device = entries[0].get("dev-entry")
        if device and path.is_relative_to(downloads):
            found.append(MountedImage(path, device))
    return found
