import lzma
import os
import struct
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dukascopy_client import DukascopyClient


# --- Task 2: シンボル定義とpoint値マッピング ---

class TestPointValue:
    def test_xauusd_point_value(self):
        assert DukascopyClient.get_point_value("XAUUSD") == 1e3

    def test_jpy_pair_point_value(self):
        assert DukascopyClient.get_point_value("USDJPY") == 1e3
        assert DukascopyClient.get_point_value("GBPJPY") == 1e3
        assert DukascopyClient.get_point_value("EURJPY") == 1e3
        assert DukascopyClient.get_point_value("CHFJPY") == 1e3

    def test_standard_pair_point_value(self):
        assert DukascopyClient.get_point_value("EURUSD") == 1e5
        assert DukascopyClient.get_point_value("EURCHF") == 1e5
        assert DukascopyClient.get_point_value("GBPCAD") == 1e5

    def test_unknown_symbol_defaults_to_1e5(self):
        assert DukascopyClient.get_point_value("SOMETHINGELSE") == 1e5

    def test_case_insensitive(self):
        assert DukascopyClient.get_point_value("xauusd") == 1e3


# --- Task 3: URL構築とティックバイナリパース ---

class TestUrlBuilding:
    def test_tick_url_january(self):
        url = DukascopyClient.build_tick_url("XAUUSD", 2024, 1, 15, 10)
        assert url == "https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/00/15/10h_ticks.bi5"

    def test_tick_url_december(self):
        url = DukascopyClient.build_tick_url("EURUSD", 2024, 12, 1, 0)
        assert url == "https://datafeed.dukascopy.com/datafeed/EURUSD/2024/11/01/00h_ticks.bi5"

    def test_candle_url(self):
        url = DukascopyClient.build_candle_url("XAUUSD", 2024, 1, 15)
        assert url == "https://datafeed.dukascopy.com/datafeed/XAUUSD/2024/00/15/BID_candles_min_1.bi5"


class TestTickParsing:
    def test_parse_single_tick(self):
        raw = struct.pack(">IIIff", 500, 2028950, 2028450, 1.5, 2.0)
        hour_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ticks = DukascopyClient.parse_ticks(raw, hour_start, "XAUUSD")
        assert len(ticks) == 1
        tick = ticks[0]
        assert tick["timestamp"] == "2024-01-15 10:00:00.500"
        assert tick["ask"] == pytest.approx(2028.95, abs=0.01)
        assert tick["bid"] == pytest.approx(2028.45, abs=0.01)
        assert tick["ask_volume"] == pytest.approx(1.5)
        assert tick["bid_volume"] == pytest.approx(2.0)

    def test_parse_empty_data(self):
        hour_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ticks = DukascopyClient.parse_ticks(b"", hour_start, "XAUUSD")
        assert ticks == []

    def test_parse_eurusd_tick(self):
        raw = struct.pack(">IIIff", 0, 108550, 108500, 1.0, 1.0)
        hour_start = datetime(2024, 1, 15, 10, 0, 0, tzinfo=timezone.utc)
        ticks = DukascopyClient.parse_ticks(raw, hour_start, "EURUSD")
        assert ticks[0]["ask"] == pytest.approx(1.08550, abs=0.00001)
        assert ticks[0]["bid"] == pytest.approx(1.08500, abs=0.00001)


# --- Task 4: 1分足パースとbi5解凍 ---

class TestCandleParsing:
    def test_parse_single_candle(self):
        raw = struct.pack(">IIIIIf", 3600, 2028450, 2028950, 2028300, 2029100, 150.5)
        day_start = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        candles = DukascopyClient.parse_candles(raw, day_start, "XAUUSD")
        assert len(candles) == 1
        c = candles[0]
        assert c["timestamp"] == "2024-01-15 01:00:00"
        assert c["open"] == pytest.approx(2028.45, abs=0.01)
        assert c["close"] == pytest.approx(2028.95, abs=0.01)
        assert c["low"] == pytest.approx(2028.30, abs=0.01)
        assert c["high"] == pytest.approx(2029.10, abs=0.01)
        assert c["volume"] == pytest.approx(150.5)

    def test_parse_empty_candle_data(self):
        day_start = datetime(2024, 1, 15, 0, 0, 0, tzinfo=timezone.utc)
        candles = DukascopyClient.parse_candles(b"", day_start, "XAUUSD")
        assert candles == []


class TestBi5Decompress:
    def test_decompress_valid_lzma(self):
        original = struct.pack(">IIIff", 500, 2028950, 2028450, 1.5, 2.0)
        compressed = lzma.compress(original)
        result = DukascopyClient.decompress_bi5(compressed)
        assert result == original

    def test_decompress_empty(self):
        result = DukascopyClient.decompress_bi5(b"")
        assert result == b""

    def test_decompress_invalid_returns_empty(self):
        result = DukascopyClient.decompress_bi5(b"not valid lzma data")
        assert result == b""


# --- Task 5: HTTP取得 (fetch_hour_ticks / fetch_day_candles) ---

class TestFetchTicks:
    @pytest.mark.asyncio
    async def test_fetch_hour_ticks_success(self):
        client = DukascopyClient()
        try:
            ticks = await client.fetch_hour_ticks("EURUSD", 2024, 1, 15, 10)
            assert isinstance(ticks, list)
            assert len(ticks) > 0
            tick = ticks[0]
            assert "timestamp" in tick
            assert "bid" in tick
            assert "ask" in tick
            assert tick["bid"] > 0
            assert tick["ask"] > 0
        finally:
            await client.close()

    @pytest.mark.asyncio
    async def test_fetch_hour_ticks_weekend_returns_empty(self):
        client = DukascopyClient()
        try:
            ticks = await client.fetch_hour_ticks("EURUSD", 2024, 1, 13, 10)
            assert ticks == []
        finally:
            await client.close()


class TestFetchCandles:
    @pytest.mark.asyncio
    async def test_fetch_day_candles_success(self):
        client = DukascopyClient()
        try:
            candles = await client.fetch_day_candles("EURUSD", 2024, 1, 15)
            assert isinstance(candles, list)
            assert len(candles) > 0
            c = candles[0]
            assert "timestamp" in c
            assert "open" in c
            assert "high" in c
            assert "low" in c
            assert "close" in c
            assert "volume" in c
        finally:
            await client.close()


# --- Task 6: CSV保存 ---

class TestCsvOperations:
    def test_write_ticks_csv(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        ticks = [
            {"timestamp": "2024-01-15 10:00:00.500", "bid": 2028.45, "ask": 2028.95, "bid_volume": 1.5, "ask_volume": 2.0},
            {"timestamp": "2024-01-15 10:00:01.200", "bid": 2028.50, "ask": 2029.00, "bid_volume": 1.0, "ask_volume": 1.5},
        ]
        path = client.write_ticks_csv("XAUUSD", "2024-01-15", ticks)
        assert path.exists()
        assert path == tmp_path / "XAUUSD" / "ticks" / "2024-01-15.csv"
        lines = path.read_text().strip().split("\n")
        assert lines[0] == "timestamp,bid,ask,bid_volume,ask_volume"
        assert len(lines) == 3

    def test_write_candles_csv(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        candles = [
            {"timestamp": "2024-01-15 01:00:00", "open": 2028.45, "high": 2029.10, "low": 2028.30, "close": 2028.90, "volume": 150.5},
        ]
        path = client.write_candles_csv("XAUUSD", "2024-01-15", candles)
        assert path.exists()
        assert path == tmp_path / "XAUUSD" / "candles" / "2024-01-15.csv"
        lines = path.read_text().strip().split("\n")
        assert lines[0] == "timestamp,open,high,low,close,volume"
        assert len(lines) == 2


# --- Task 7: キャッシュ管理 ---

class TestCacheManagement:
    def test_cache_status_empty(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        status = client.cache_status()
        assert status == []

    def test_cache_status_with_data(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        ticks_dir = tmp_path / "XAUUSD" / "ticks"
        ticks_dir.mkdir(parents=True)
        (ticks_dir / "2024-01-15.csv").write_text("timestamp,bid,ask,bid_volume,ask_volume\n")
        (ticks_dir / "2024-01-16.csv").write_text("timestamp,bid,ask,bid_volume,ask_volume\n")
        candles_dir = tmp_path / "XAUUSD" / "candles"
        candles_dir.mkdir(parents=True)
        (candles_dir / "2024-01-15.csv").write_text("timestamp,open,high,low,close,volume\n")

        status = client.cache_status()
        assert len(status) == 2
        ticks_entry = [s for s in status if s["type"] == "ticks"][0]
        assert ticks_entry["symbol"] == "XAUUSD"
        assert ticks_entry["file_count"] == 2
        assert ticks_entry["date_range"] == "2024-01-15 ~ 2024-01-16"

    def test_cache_status_filter_by_symbol(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        (tmp_path / "XAUUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "XAUUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")
        (tmp_path / "EURUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "EURUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")

        status = client.cache_status(symbol="XAUUSD")
        assert len(status) == 1
        assert status[0]["symbol"] == "XAUUSD"

    def test_clear_cache_all(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        (tmp_path / "XAUUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "XAUUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")
        (tmp_path / "EURUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "EURUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")

        result = client.clear_cache()
        assert result["deleted_files"] == 2
        assert client.cache_status() == []

    def test_clear_cache_by_symbol(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        (tmp_path / "XAUUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "XAUUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")
        (tmp_path / "EURUSD" / "ticks").mkdir(parents=True)
        (tmp_path / "EURUSD" / "ticks" / "2024-01-15.csv").write_text("h\n")

        result = client.clear_cache(symbol="XAUUSD")
        assert result["deleted_files"] == 1
        status = client.cache_status()
        assert len(status) == 1
        assert status[0]["symbol"] == "EURUSD"

    def test_clear_cache_by_date_range(self, tmp_path):
        client = DukascopyClient(cache_dir=tmp_path)
        ticks_dir = tmp_path / "XAUUSD" / "ticks"
        ticks_dir.mkdir(parents=True)
        (ticks_dir / "2024-01-15.csv").write_text("h\n")
        (ticks_dir / "2024-01-16.csv").write_text("h\n")
        (ticks_dir / "2024-01-17.csv").write_text("h\n")

        result = client.clear_cache(symbol="XAUUSD", start="2024-01-15", end="2024-01-16")
        assert result["deleted_files"] == 2
        remaining = client.cache_status(symbol="XAUUSD")
        assert remaining[0]["file_count"] == 1
