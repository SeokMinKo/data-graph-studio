"""Tests for Converter Options — FtraceParser option defs + ConverterOptionsPanel."""

import pytest
import polars as pl

from data_graph_studio.parsers.ftrace_parser import FtraceParser


# ── FtraceParser option definitions ──────────────────────────────────


class TestFtraceParserOptionDefs:
    def test_get_option_defs_blocklayer(self):
        defs = FtraceParser.get_option_defs("blocklayer")
        assert isinstance(defs, list)
        assert len(defs) > 0
        keys = [d["key"] for d in defs]
        assert "busy_queue_depth" in keys
        assert "idle_queue_depth" in keys
        assert "window_sec" in keys
        assert "latency_percentiles" in keys
        assert "drain_target_depth" in keys

    def test_get_option_defs_sched_empty(self):
        defs = FtraceParser.get_option_defs("sched")
        assert defs == []

    def test_get_option_defs_unknown_empty(self):
        defs = FtraceParser.get_option_defs("nonexistent")
        assert defs == []

    def test_get_default_options_blocklayer(self):
        defaults = FtraceParser.get_default_options("blocklayer")
        assert isinstance(defaults, dict)
        assert defaults["busy_queue_depth"] == 32
        assert defaults["idle_queue_depth"] == 4
        assert defaults["window_sec"] == 1.0
        assert defaults["latency_percentiles"] == "50,90,99"
        assert defaults["drain_target_depth"] == 0

    def test_get_default_options_unknown_empty(self):
        defaults = FtraceParser.get_default_options("unknown")
        assert defaults == {}

    def test_option_def_structure(self):
        """Each option def should have required fields."""
        for defs in FtraceParser._converter_option_defs.values():
            for d in defs:
                assert "key" in d
                assert "type" in d
                assert "default" in d
                assert "label" in d
                assert "description" in d
                assert d["type"] in ("int", "float", "str")


# ── Converter with options (no crash) ────────────────────────────────


class TestConverterWithOptions:
    @pytest.fixture
    def sample_ftrace_text(self, tmp_path):
        content = (
            "# tracer: nop\n"
            "#\n"
            " kworker/0:1-123 [000] .... 1000.000000: block_rq_insert: 8,0 W 4096 () 100 + 8 [kworker]\n"
            " kworker/0:1-123 [000] .... 1000.000100: block_rq_issue: 8,0 W 4096 () 100 + 8 [kworker]\n"
            " kworker/0:1-123 [000] .... 1000.001000: block_rq_complete: 8,0 W () 100 + 8 [0]\n"
        )
        p = tmp_path / "trace.txt"
        p.write_text(content)
        return str(p)

    def test_blocklayer_with_custom_options(self, sample_ftrace_text):
        """Converter should not crash when given custom options."""
        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        settings["converter_options"] = {
            "busy_queue_depth": 16,
            "idle_queue_depth": 2,
            "window_sec": 0.5,
        }
        df = parser.parse(sample_ftrace_text, settings)
        assert isinstance(df, pl.DataFrame)
        assert len(df) >= 1

    def test_blocklayer_with_default_options(self, sample_ftrace_text):
        """Converter works fine with default options dict."""
        parser = FtraceParser()
        settings = parser.default_settings()
        settings["converter"] = "blocklayer"
        settings["converter_options"] = FtraceParser.get_default_options("blocklayer")
        df = parser.parse(sample_ftrace_text, settings)
        assert isinstance(df, pl.DataFrame)
        assert len(df) >= 1


# ── ConverterOptionsPanel (Qt widget tests) ──────────────────────────


@pytest.fixture
def qapp():
    """Create QApplication if not running; skip if display unavailable."""
    try:
        from PySide6.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            app = QApplication([])
        return app
    except Exception:
        pytest.skip("Qt display not available")


class TestConverterOptionsPanel:
    def test_create_panel(self, qapp):
        from data_graph_studio.ui.panels.converter_options_panel import (
            ConverterOptionsPanel,
        )

        panel = ConverterOptionsPanel()
        assert panel is not None

    def test_set_converter_blocklayer(self, qapp):
        from data_graph_studio.ui.panels.converter_options_panel import (
            ConverterOptionsPanel,
        )

        panel = ConverterOptionsPanel()
        panel.set_converter("blocklayer")
        opts = panel.get_options()
        assert "busy_queue_depth" in opts
        assert opts["busy_queue_depth"] == 32

    def test_set_converter_empty(self, qapp):
        from data_graph_studio.ui.panels.converter_options_panel import (
            ConverterOptionsPanel,
        )

        panel = ConverterOptionsPanel()
        panel.set_converter("sched")
        opts = panel.get_options()
        assert opts == {}

    def test_reset_defaults(self, qapp):
        from data_graph_studio.ui.panels.converter_options_panel import (
            ConverterOptionsPanel,
        )

        panel = ConverterOptionsPanel()
        panel.set_converter("blocklayer")
        # Change a value
        panel._widgets["busy_queue_depth"].setValue(999)
        assert panel.get_options()["busy_queue_depth"] == 999
        # Reset
        panel._reset_defaults()
        assert panel.get_options()["busy_queue_depth"] == 32

    def test_options_changed_signal(self, qapp, qtbot):
        from data_graph_studio.ui.panels.converter_options_panel import (
            ConverterOptionsPanel,
        )

        panel = ConverterOptionsPanel()
        panel.set_converter("blocklayer")

        with qtbot.waitSignal(panel.options_changed, timeout=1000):
            panel._widgets["busy_queue_depth"].setValue(64)
            # Trigger debounce timer immediately
            panel._debounce_timer.setInterval(0)
            panel._debounce_timer.start()
