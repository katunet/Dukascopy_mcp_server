"""
Dukascopy datafeed クライアント
bi5 (LZMA圧縮バイナリ) のダウンロード・パース・CSV保存を担当する
"""

from __future__ import annotations

import asyncio
import csv
import lzma
import os
import struct
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

BASE_URL = "https://datafeed.dukascopy.com/datafeed"

# WD_Black SSD が接続中ならそこを使い、未接続ならローカルにフォールバック
_WD_BLACK_CACHE = Path("/Volumes/WD_Black/Dukascopy_mcp/cache")
_LOCAL_CACHE = Path(__file__).resolve().parent / "cache"


def resolve_cache_dir() -> Path:
    """キャッシュディレクトリを解決する。

    WD_Black SSD が /Volumes/WD_Black にマウントされていればそのパスを返す。
    未接続の場合はスクリプト隣の cache/ をフォールバックとして返す。
    """
    if _WD_BLACK_CACHE.parent.parent.exists():  # /Volumes/WD_Black/ が存在する
        _WD_BLACK_CACHE.mkdir(parents=True, exist_ok=True)
        return _WD_BLACK_CACHE
    return _LOCAL_CACHE
TICK_RECORD_SIZE = 20
CANDLE_RECORD_SIZE = 24
MAX_CONCURRENT = 5
REQUEST_DELAY = 0.2

POINT_VALUES: dict[str, float] = {
    "XAUUSD": 1e3,
    "USDJPY": 1e3,
    "GBPJPY": 1e3,
    "EURJPY": 1e3,
    "CHFJPY": 1e3,
    "EURUSD": 1e5,
    "EURCHF": 1e5,
    "EURAUD": 1e5,
    "EURNZD": 1e5,
    "GBPCAD": 1e5,
    "GBPCHF": 1e5,
    "GBPAUD": 1e5,
    "GBPNZD": 1e5,
    "NZDCHF": 1e5,
    "AUDNZD": 1e5,
    "AUDCAD": 1e5,
}

DEFAULT_POINT_VALUE = 1e5


class DukascopyClient:
    TIMEOUT = 30.0
    USER_AGENT = "dukascopy-mcp/1.0"

    def __init__(self, cache_dir: str | Path = "cache"):
        self._cache_dir = Path(cache_dir)
        self._http = httpx.AsyncClient(
            timeout=self.TIMEOUT,
            headers={"User-Agent": self.USER_AGENT},
        )

    @staticmethod
    def get_point_value(symbol: str) -> float:
        return POINT_VALUES.get(symbol.upper(), DEFAULT_POINT_VALUE)

    @staticmethod
    def build_tick_url(symbol: str, year: int, month: int, day: int, hour: int) -> str:
        return f"{BASE_URL}/{symbol.upper()}/{year}/{month - 1:02d}/{day:02d}/{hour:02d}h_ticks.bi5"

    @staticmethod
    def build_candle_url(symbol: str, year: int, month: int, day: int) -> str:
        return f"{BASE_URL}/{symbol.upper()}/{year}/{month - 1:02d}/{day:02d}/BID_candles_min_1.bi5"

    @staticmethod
    def parse_ticks(data: bytes, hour_start: datetime, symbol: str) -> list[dict[str, Any]]:
        if not data:
            return []
        point_value = DukascopyClient.get_point_value(symbol)
        ticks = []
        for i in range(0, len(data), TICK_RECORD_SIZE):
            chunk = data[i:i + TICK_RECORD_SIZE]
            if len(chunk) < TICK_RECORD_SIZE:
                break
            time_offset, ask_raw, bid_raw, ask_vol, bid_vol = struct.unpack(">IIIff", chunk)
            ts = hour_start + timedelta(milliseconds=time_offset)
            ticks.append({
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S.") + f"{ts.microsecond // 1000:03d}",
                "bid": round(bid_raw / point_value, 5),
                "ask": round(ask_raw / point_value, 5),
                "bid_volume": round(bid_vol, 2),
                "ask_volume": round(ask_vol, 2),
            })
        return ticks

    @staticmethod
    def parse_candles(data: bytes, day_start: datetime, symbol: str) -> list[dict[str, Any]]:
        if not data:
            return []
        point_value = DukascopyClient.get_point_value(symbol)
        candles = []
        for i in range(0, len(data), CANDLE_RECORD_SIZE):
            chunk = data[i:i + CANDLE_RECORD_SIZE]
            if len(chunk) < CANDLE_RECORD_SIZE:
                break
            time_offset, open_raw, close_raw, low_raw, high_raw, volume = struct.unpack(">IIIIIf", chunk)
            ts = day_start + timedelta(seconds=time_offset)
            candles.append({
                "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
                "open": round(open_raw / point_value, 5),
                "high": round(high_raw / point_value, 5),
                "low": round(low_raw / point_value, 5),
                "close": round(close_raw / point_value, 5),
                "volume": round(volume, 2),
            })
        return candles

    @staticmethod
    def decompress_bi5(data: bytes) -> bytes:
        if not data:
            return b""
        try:
            return lzma.decompress(data)
        except (lzma.LZMAError, EOFError):
            return b""

    async def _fetch_bi5(self, url: str) -> bytes:
        try:
            resp = await self._http.get(url)
            if resp.status_code == 404:
                return b""
            resp.raise_for_status()
            return resp.content
        except httpx.HTTPStatusError:
            return b""
        except httpx.RequestError:
            return b""

    async def fetch_hour_ticks(self, symbol: str, year: int, month: int, day: int, hour: int) -> list[dict[str, Any]]:
        url = self.build_tick_url(symbol, year, month, day, hour)
        compressed = await self._fetch_bi5(url)
        raw = self.decompress_bi5(compressed)
        hour_start = datetime(year, month, day, hour, 0, 0, tzinfo=timezone.utc)
        return self.parse_ticks(raw, hour_start, symbol)

    async def fetch_day_candles(self, symbol: str, year: int, month: int, day: int) -> list[dict[str, Any]]:
        url = self.build_candle_url(symbol, year, month, day)
        compressed = await self._fetch_bi5(url)
        raw = self.decompress_bi5(compressed)
        day_start = datetime(year, month, day, 0, 0, 0, tzinfo=timezone.utc)
        return self.parse_candles(raw, day_start, symbol)

    def _read_candles_csv(self, symbol: str, date_str: str) -> list[dict[str, Any]] | None:
        """キャッシュCSVから1分足を読む。ファイルが存在しなければ None を返す。"""
        path = self._cache_dir / symbol.upper() / "candles" / f"{date_str}.csv"
        if not path.exists():
            return None
        candles: list[dict[str, Any]] = []
        with open(path, newline="") as f:
            for row in csv.DictReader(f):
                candles.append({
                    "timestamp": row["timestamp"],
                    "open":   float(row["open"]),
                    "high":   float(row["high"]),
                    "low":    float(row["low"]),
                    "close":  float(row["close"]),
                    "volume": float(row["volume"]),
                })
        return candles

    async def fetch_day_candles_cached(self, symbol: str, year: int, month: int, day: int) -> list[dict[str, Any]]:
        """キャッシュ優先でH1日分の1分足を取得する。

        キャッシュ（WD_Black または ローカル）にCSVがあればそこから読み込む。
        なければDukascopyから取得しキャッシュに保存する。
        """
        date_str = f"{year:04d}-{month:02d}-{day:02d}"
        cached = self._read_candles_csv(symbol, date_str)
        if cached is not None:
            return cached
        candles = await self.fetch_day_candles(symbol, year, month, day)
        if candles:
            self.write_candles_csv(symbol, date_str, candles)
        return candles

    # --- Task 6: CSV保存 + 一括ダウンロード ---

    def write_ticks_csv(self, symbol: str, date_str: str, ticks: list[dict]) -> Path:
        dir_path = self._cache_dir / symbol.upper() / "ticks"
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{date_str}.csv"
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "bid", "ask", "bid_volume", "ask_volume"])
            for t in ticks:
                writer.writerow([t["timestamp"], t["bid"], t["ask"], t["bid_volume"], t["ask_volume"]])
        return file_path

    def write_candles_csv(self, symbol: str, date_str: str, candles: list[dict]) -> Path:
        dir_path = self._cache_dir / symbol.upper() / "candles"
        dir_path.mkdir(parents=True, exist_ok=True)
        file_path = dir_path / f"{date_str}.csv"
        with open(file_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
            for c in candles:
                writer.writerow([c["timestamp"], c["open"], c["high"], c["low"], c["close"], c["volume"]])
        return file_path

    async def download_ticks(self, symbol: str, start: str, end: str) -> dict[str, Any]:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        total_ticks = 0
        days = 0
        current = start_date
        sem = asyncio.Semaphore(MAX_CONCURRENT)

        while current <= end_date:
            day_ticks = []
            for hour in range(24):
                async with sem:
                    ticks = await self.fetch_hour_ticks(
                        symbol, current.year, current.month, current.day, hour
                    )
                    day_ticks.extend(ticks)
                    await asyncio.sleep(REQUEST_DELAY)
            if day_ticks:
                self.write_ticks_csv(symbol, current.isoformat(), day_ticks)
                total_ticks += len(day_ticks)
                days += 1
            current += timedelta(days=1)

        cache_path = self._cache_dir / symbol.upper() / "ticks"
        size_mb = sum(f.stat().st_size for f in cache_path.glob("*.csv")) / (1024 * 1024) if cache_path.exists() else 0
        return {
            "path": str(cache_path),
            "days": days,
            "total_ticks": total_ticks,
            "size_mb": round(size_mb, 2),
        }

    async def download_candles(self, symbol: str, start: str, end: str) -> dict[str, Any]:
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()
        total_candles = 0
        days = 0
        current = start_date

        while current <= end_date:
            candles = await self.fetch_day_candles(
                symbol, current.year, current.month, current.day
            )
            if candles:
                self.write_candles_csv(symbol, current.isoformat(), candles)
                total_candles += len(candles)
                days += 1
            current += timedelta(days=1)
            await asyncio.sleep(REQUEST_DELAY)

        cache_path = self._cache_dir / symbol.upper() / "candles"
        size_mb = sum(f.stat().st_size for f in cache_path.glob("*.csv")) / (1024 * 1024) if cache_path.exists() else 0
        return {
            "path": str(cache_path),
            "days": days,
            "total_candles": total_candles,
            "size_mb": round(size_mb, 2),
        }

    # --- Task 7: キャッシュ管理 ---

    def cache_status(self, symbol: str | None = None) -> list[dict[str, Any]]:
        results = []
        if not self._cache_dir.exists():
            return results
        symbol_dirs = [self._cache_dir / symbol.upper()] if symbol else sorted(self._cache_dir.iterdir())
        for sym_dir in symbol_dirs:
            if not sym_dir.is_dir():
                continue
            sym_name = sym_dir.name
            for type_name in ["ticks", "candles"]:
                type_dir = sym_dir / type_name
                if not type_dir.exists():
                    continue
                csv_files = sorted(type_dir.glob("*.csv"))
                if not csv_files:
                    continue
                dates = [f.stem for f in csv_files]
                size_bytes = sum(f.stat().st_size for f in csv_files)
                results.append({
                    "symbol": sym_name,
                    "type": type_name,
                    "date_range": f"{dates[0]} ~ {dates[-1]}",
                    "file_count": len(csv_files),
                    "size_mb": round(size_bytes / (1024 * 1024), 2),
                })
        return results

    def clear_cache(self, symbol: str | None = None, start: str | None = None, end: str | None = None) -> dict[str, Any]:
        deleted = 0
        freed = 0
        if not self._cache_dir.exists():
            return {"deleted_files": 0, "freed_mb": 0.0}

        symbol_dirs = [self._cache_dir / symbol.upper()] if symbol else list(self._cache_dir.iterdir())
        for sym_dir in symbol_dirs:
            if not sym_dir.is_dir():
                continue
            for type_dir in sym_dir.iterdir():
                if not type_dir.is_dir():
                    continue
                for csv_file in type_dir.glob("*.csv"):
                    if start and end:
                        file_date = csv_file.stem
                        if file_date < start or file_date > end:
                            continue
                    freed += csv_file.stat().st_size
                    csv_file.unlink()
                    deleted += 1
                if type_dir.exists() and not any(type_dir.iterdir()):
                    type_dir.rmdir()
            if sym_dir.exists() and not any(sym_dir.iterdir()):
                sym_dir.rmdir()

        return {"deleted_files": deleted, "freed_mb": round(freed / (1024 * 1024), 2)}

    async def close(self) -> None:
        await self._http.aclose()
