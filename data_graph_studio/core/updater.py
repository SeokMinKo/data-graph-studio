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
    """Best-effort current app version.

    Priority:
    1) data_graph_studio._build_version.__version__ (CI-injected; works in PyInstaller)
    2) importlib.metadata.version("data-graph-studio")
    """

    try:
        from data_graph_studio._build_version import __version__ as build_ver

        if build_ver and build_ver != "0.0.0":
            return build_ver
    except Exception:
        pass

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
    sha256_url: str
    sha256_name: str


def _parse_version(v: str) -> Optional[Version]:
    try:
        return Version(v)
    except InvalidVersion:
        return None


def check_github_latest(expected_asset_prefix: str = "DataGraphStudio-Setup-") -> Optional[UpdateInfo]:
    """Check GitHub latest release and find Windows installer + checksum asset.

    Returns UpdateInfo if compatible assets exist, else None.
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

    installer = None
    checksum = None

    for a in assets:
        name = a.get("name", "")
        if installer is None and name.startswith(expected_asset_prefix) and name.endswith(".exe"):
            installer = a
            continue

    if installer is None:
        return None

    # Expect checksum asset: same base name + .sha256
    expected_sha = installer.get("name", "") + ".sha256"
    for a in assets:
        name = a.get("name", "")
        if name == expected_sha or (name.startswith(expected_asset_prefix) and name.endswith(".sha256")):
            checksum = a
            # prefer exact match
            if name == expected_sha:
                break

    if checksum is None:
        return None

    return UpdateInfo(
        latest_version=latest,
        tag=tag,
        html_url=html_url,
        notes=notes,
        asset_url=installer.get("browser_download_url", ""),
        asset_name=installer.get("name", ""),
        sha256_url=checksum.get("browser_download_url", ""),
        sha256_name=checksum.get("name", ""),
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
    with urllib.request.urlopen(url, timeout=60) as resp:
        with open(out_path, "wb") as f:
            f.write(resp.read())
    return out_path


def read_sha256_file(path: str) -> str:
    """Parse a .sha256 file content like: '<hash>  <filename>'"""
    with open(path, "r", encoding="utf-8", errors="ignore") as f:
        line = f.readline().strip()
    if not line:
        return ""
    # split on whitespace, first token is hash
    return line.split()[0].lower()


def sha256sum(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


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
