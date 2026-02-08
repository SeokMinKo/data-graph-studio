from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional

from packaging.version import Version, InvalidVersion


REPO = "SeokMinKo/data-graph-studio"
GITHUB_API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"


def get_current_version() -> str:
    """Best-effort current app version."""
    try:
        from importlib.metadata import version

        return version("data-graph-studio")
    except Exception:
        return "0.0.0"


@dataclass
class UpdateInfo:
    latest_version: str
    tag: str
    html_url: str
    notes: str
    asset_url: str
    asset_name: str


def _parse_version(v: str) -> Optional[Version]:
    try:
        return Version(v)
    except InvalidVersion:
        return None


def check_github_latest(expected_asset_prefix: str = "DataGraphStudio-Setup-") -> Optional[UpdateInfo]:
    """Check GitHub latest release and find a Windows installer asset.

    Returns UpdateInfo if a compatible asset exists, else None.
    """

    req = urllib.request.Request(
        GITHUB_API_LATEST,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "DataGraphStudio-Updater",
        },
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode("utf-8"))

    tag = data.get("tag_name", "")
    html_url = data.get("html_url", "")
    notes = data.get("body", "") or ""

    latest = tag.lstrip("v")
    assets = data.get("assets", []) or []

    asset = None
    for a in assets:
        name = a.get("name", "")
        if name.startswith(expected_asset_prefix) and name.endswith(".exe"):
            asset = a
            break

    if not asset:
        return None

    return UpdateInfo(
        latest_version=latest,
        tag=tag,
        html_url=html_url,
        notes=notes,
        asset_url=asset.get("browser_download_url", ""),
        asset_name=asset.get("name", ""),
    )


def is_update_available(current_version: str, latest_version: str) -> bool:
    cur = _parse_version(current_version)
    lat = _parse_version(latest_version)
    if not cur or not lat:
        return False
    return lat > cur


def download_asset(url: str, filename: str) -> str:
    """Download asset to temp dir and return full path."""
    tmp_dir = tempfile.mkdtemp(prefix="dgs-update-")
    out_path = os.path.join(tmp_dir, filename)
    urllib.request.urlretrieve(url, out_path)
    return out_path


def run_windows_installer(installer_path: str, silent: bool = True) -> None:
    """Run installer and exit current app.

    Note: truly seamless background updates on Windows are complex.
    This uses an installer-based flow (Inno Setup compatible).
    """

    if sys.platform != "win32":
        return

    args = [installer_path]
    if silent:
        args += ["/VERYSILENT", "/NORESTART"]

    # Launch installer detached
    subprocess.Popen(args, close_fds=True)
