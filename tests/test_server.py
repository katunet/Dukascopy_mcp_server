import pytest
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from server import TOOLS, app


class TestServerTools:
    def test_tool_count(self):
        assert len(TOOLS) == 6

    def test_tool_names(self):
        names = {t.name for t in TOOLS}
        assert names == {
            "get_ticks",
            "get_candles",
            "download_ticks",
            "download_candles",
            "cache_status",
            "clear_cache",
        }

    def test_get_ticks_schema_requires_symbol_date_hour(self):
        tool = next(t for t in TOOLS if t.name == "get_ticks")
        assert tool.inputSchema["required"] == ["symbol", "date", "hour"]

    def test_cache_status_has_no_required(self):
        tool = next(t for t in TOOLS if t.name == "cache_status")
        assert tool.inputSchema["required"] == []

    def test_server_name(self):
        assert app.name == "dukascopy"
