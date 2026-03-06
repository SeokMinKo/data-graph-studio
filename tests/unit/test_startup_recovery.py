import main


def test_module_not_found_dev_recovery_guide():
    exc = ModuleNotFoundError("No module named 'pandas'")
    setattr(exc, "name", "pandas")

    steps = main._startup_recovery_guide(exc, is_frozen=False, platform_name="linux")

    assert any("누락 모듈: pandas" in step for step in steps)
    assert any("pip install -r requirements.txt" in step for step in steps)


def test_windows_frozen_dll_recovery_guide():
    exc = ImportError(
        "DLL load failed while importing PySide6: 지정된 모듈을 찾을 수 없습니다"
    )

    steps = main._startup_recovery_guide(exc, is_frozen=True, platform_name="win32")

    assert any("Repair/재설치" in step for step in steps)
    assert any("Visual C++ 2015-2022" in step for step in steps)


def test_name_error_recovery_guide():
    steps = main._startup_recovery_guide(
        NameError("name 'foo' is not defined"), is_frozen=False, platform_name="linux"
    )

    assert any("NameError" in step for step in steps)
    assert any("~/.dgs/crash.log" in step for step in steps)


def test_format_startup_failure_contains_recovery_header():
    msg = main._format_startup_failure(
        "IMPORT ERROR", ModuleNotFoundError("No module named 'x'")
    )

    assert "IMPORT ERROR" in msg
    assert "Recovery Guide:" in msg


def test_file_not_found_recovery_guide_windows_frozen():
    steps = main._startup_recovery_guide(
        FileNotFoundError("resources/icons/dgs.ico"),
        is_frozen=True,
        platform_name="win32",
    )

    assert any("setup-log.txt" in step for step in steps)
    assert any("resources" in step for step in steps)
    assert any("Repair" in step for step in steps)
