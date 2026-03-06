from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from dataclasses import dataclass
from typing import Optional


class UpdatePayloadError(RuntimeError):
    """Raised when downloaded update artifacts are invalid or unsafe to launch."""


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


def check_github_latest(
    expected_asset_prefix: str = "DataGraphStudio-Setup-",
) -> Optional[UpdateInfo]:
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
        if (
            installer is None
            and name.startswith(expected_asset_prefix)
            and name.endswith(".exe")
        ):
            installer = a
            continue

    if installer is None:
        return None

    # Expect checksum asset: same base name + .sha256
    expected_sha = installer.get("name", "") + ".sha256"
    for a in assets:
        name = a.get("name", "")
        if name == expected_sha or (
            name.startswith(expected_asset_prefix) and name.endswith(".sha256")
        ):
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
    if not url.startswith(("http://", "https://")):
        raise UpdatePayloadError(f"Invalid download URL: {url!r}")
    if not filename or any(sep in filename for sep in ("/", "\\")):
        raise UpdatePayloadError(f"Unsafe asset filename: {filename!r}")

    tmp_dir = tempfile.mkdtemp(prefix="dgs-update-")
    out_path = os.path.join(tmp_dir, filename)
    urllib.request.urlretrieve(url, out_path)
    return out_path


def read_sha256_file(path: str) -> tuple[str, str]:
    """Parse a .sha256 line like: '<hash>  <filename>'.

    Returns (hash, filename). filename may be empty if it is not present.
    """
    with open(path, "r", encoding="utf-8-sig", errors="ignore") as f:
        line = f.readline().strip()
    if not line:
        return "", ""

    parts = line.split()
    digest = parts[0].lower() if parts else ""
    filename = parts[-1].strip() if len(parts) >= 2 else ""
    return digest, filename


def sha256sum(path: str) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


def validate_downloaded_update_assets(installer_path: str, sha_path: str) -> None:
    """Validate downloaded installer/checksum artifacts before launch.

    Raises UpdatePayloadError with a user-facing message when validation fails.
    """

    if not os.path.isfile(installer_path):
        raise UpdatePayloadError(f"Installer file not found: {installer_path}")
    if not os.path.isfile(sha_path):
        raise UpdatePayloadError(f"Checksum file not found: {sha_path}")

    if os.path.getsize(installer_path) <= 0:
        raise UpdatePayloadError("Downloaded installer is empty (0 bytes).")

    # Basic PE signature guard for corrupted/offline-cached HTML payloads.
    with open(installer_path, "rb") as f:
        mz = f.read(2)
    if mz != b"MZ":
        raise UpdatePayloadError(
            "Downloaded installer is not a valid Windows executable (MZ header missing)."
        )

    expected, checksum_target = read_sha256_file(sha_path)
    if not expected:
        raise UpdatePayloadError("Checksum file is empty or malformed.")

    if len(expected) != 64 or any(c not in "0123456789abcdef" for c in expected):
        raise UpdatePayloadError(
            "Checksum file format is invalid (sha256 digest not found)."
        )

    expected_name = os.path.basename(installer_path)
    if checksum_target and os.path.basename(checksum_target) != expected_name:
        raise UpdatePayloadError(
            "Checksum file points to a different installer. "
            f"Expected: {expected_name} / Found: {checksum_target}"
        )

    actual = sha256sum(installer_path)
    if expected != actual:
        raise UpdatePayloadError(
            f"Checksum verification failed. Expected: {expected} / Actual: {actual}"
        )


def _validate_installer_path_for_launch(installer_path: str) -> None:
    if not installer_path:
        raise UpdatePayloadError("Installer path is empty.")

    if not installer_path.lower().endswith(".exe"):
        raise UpdatePayloadError(
            f"Installer path must be an .exe file: {installer_path}"
        )

    if not os.path.isfile(installer_path):
        raise UpdatePayloadError(f"Installer file not found: {installer_path}")

    with open(installer_path, "rb") as f:
        if f.read(2) != b"MZ":
            raise UpdatePayloadError(
                "Installer file is not a valid Windows executable (MZ header missing)."
            )


def run_windows_installer(installer_path: str, silent: bool = True) -> None:
    """Run installer and exit current app.

    Note: truly seamless background updates on Windows are complex.
    This uses an installer-based flow (Inno Setup compatible).
    """

    if sys.platform != "win32":
        return

    _validate_installer_path_for_launch(installer_path)

    args = [installer_path]
    if silent:
        args += ["/VERYSILENT", "/NORESTART"]

    # Launch installer detached
    subprocess.Popen(args, close_fds=True)
