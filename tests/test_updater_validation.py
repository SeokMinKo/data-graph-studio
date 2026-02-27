from __future__ import annotations

import hashlib

import pytest

from data_graph_studio.core.updater import (
    UpdatePayloadError,
    download_asset,
    validate_downloaded_update_assets,
)


def _write_bytes(path, content: bytes) -> None:
    path.write_bytes(content)


def _write_sha(path, payload_path, content: bytes) -> None:
    digest = hashlib.sha256(content).hexdigest()
    path.write_text(f"{digest}  {payload_path.name}\n", encoding="utf-8")


def test_validate_downloaded_update_assets_ok(tmp_path) -> None:
    installer = tmp_path / "DataGraphStudio-Setup-1.2.3.exe"
    payload = b"MZ" + b"\x00" * 64
    _write_bytes(installer, payload)

    sha = tmp_path / "DataGraphStudio-Setup-1.2.3.exe.sha256"
    _write_sha(sha, installer, payload)

    validate_downloaded_update_assets(str(installer), str(sha))


def test_validate_downloaded_update_assets_rejects_non_exe_payload(tmp_path) -> None:
    installer = tmp_path / "DataGraphStudio-Setup-1.2.3.exe"
    payload = b"<!DOCTYPE html>offline cache page"
    _write_bytes(installer, payload)

    sha = tmp_path / "DataGraphStudio-Setup-1.2.3.exe.sha256"
    _write_sha(sha, installer, payload)

    with pytest.raises(UpdatePayloadError, match="MZ header missing"):
        validate_downloaded_update_assets(str(installer), str(sha))


def test_validate_downloaded_update_assets_rejects_checksum_mismatch(tmp_path) -> None:
    installer = tmp_path / "DataGraphStudio-Setup-1.2.3.exe"
    payload = b"MZ" + b"\x11" * 16
    _write_bytes(installer, payload)

    sha = tmp_path / "DataGraphStudio-Setup-1.2.3.exe.sha256"
    sha.write_text(f"{'0' * 64}  {installer.name}\n", encoding="utf-8")

    with pytest.raises(UpdatePayloadError, match="Checksum verification failed"):
        validate_downloaded_update_assets(str(installer), str(sha))


def test_validate_downloaded_update_assets_rejects_html_checksum_payload(tmp_path) -> None:
    installer = tmp_path / "DataGraphStudio-Setup-1.2.3.exe"
    payload = b"MZ" + b"\x22" * 32
    _write_bytes(installer, payload)

    sha = tmp_path / "DataGraphStudio-Setup-1.2.3.exe.sha256"
    sha.write_text("<!doctype html>offline cached checksum", encoding="utf-8")

    with pytest.raises(UpdatePayloadError, match="sha256 digest not found"):
        validate_downloaded_update_assets(str(installer), str(sha))


def test_validate_downloaded_update_assets_rejects_checksum_for_other_installer(tmp_path) -> None:
    installer = tmp_path / "DataGraphStudio-Setup-1.2.3.exe"
    payload = b"MZ" + b"\x33" * 48
    _write_bytes(installer, payload)

    sha = tmp_path / "DataGraphStudio-Setup-1.2.3.exe.sha256"
    digest = hashlib.sha256(payload).hexdigest()
    sha.write_text(f"{digest}  other-installer.exe\n", encoding="utf-8")

    with pytest.raises(UpdatePayloadError, match="different installer"):
        validate_downloaded_update_assets(str(installer), str(sha))


def test_download_asset_rejects_non_http_url() -> None:
    with pytest.raises(UpdatePayloadError, match="Invalid download URL"):
        download_asset("file:///tmp/installer.exe", "installer.exe")


def test_download_asset_rejects_unsafe_filename() -> None:
    with pytest.raises(UpdatePayloadError, match="Unsafe asset filename"):
        download_asset("https://example.com/installer.exe", "../installer.exe")
