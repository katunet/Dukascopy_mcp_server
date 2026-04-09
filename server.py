"""
Dukascopy MCP Server
Dukascopy datafeed からティックデータ・1分足OHLCを取得する
"""

from __future__ import annotations

import asyncio
import csv
import json
import os
from datetime import datetime, timedelta
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from dukascopy_client import DukascopyClient, resolve_cache_dir
from calibration.calendar_loader import CalendarLoader
from calibration.tick_aligner import TickAligner
from calibration.spread_profiler import SpreadProfiler
from calibration.model import CalibrationModel
from calibration.reshaper import Reshaper

CACHE_DIR = resolve_cache_dir()

app = Server("dukascopy")
client = DukascopyClient(cache_dir=CACHE_DIR)

# ---------------------------------------------------------------------------
# WD_Black パス解決
# ---------------------------------------------------------------------------
_WD_CALIBRATION = Path("/Volumes/WD_Black/calibration")
_WD_RESHAPED    = Path("/Volumes/WD_Black/reshaped")
_WD_MT5         = Path("/Volumes/WD_Black/MT5_cache")
_FF_CALENDAR    = Path("/Volumes/WD_Black/ForexFactory/calendar")

_LOCAL_CALIBRATION = Path(__file__).resolve().parent / "calibration_cache"
_LOCAL_RESHAPED    = Path(__file__).resolve().parent / "reshaped_cache"
_LOCAL_MT5         = Path(__file__).resolve().parent / "MT5_cache"


def _resolve(wd_path: Path, local_path: Path) -> Path:
    """WD_Black がマウントされていればそちらを、なければローカルを返す"""
    if wd_path.parent.exists():
        wd_path.mkdir(parents=True, exist_ok=True)
        return wd_path
    local_path.mkdir(parents=True, exist_ok=True)
    return local_path


def _json_text(data) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps(data, indent=2, ensure_ascii=False))]


def _error_text(msg: str) -> list[TextContent]:
    return [TextContent(type="text", text=json.dumps({"error": msg}, ensure_ascii=False))]


TOOLS = [
    Tool(
        name="get_ticks",
        description="指定シンボル・日時の1時間分ティックデータを取得（リアルタイム返却）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "date": {"type": "string", "description": "日付 (YYYY-MM-DD)"},
                "hour": {"type": "integer", "description": "時間 (0-23, UTC)"},
            },
            "required": ["symbol", "date", "hour"],
        },
    ),
    Tool(
        name="get_candles",
        description="指定シンボル・日時の1時間分1分足OHLCを取得（リアルタイム返却）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "date": {"type": "string", "description": "日付 (YYYY-MM-DD)"},
                "hour": {"type": "integer", "description": "時間 (0-23, UTC)"},
            },
            "required": ["symbol", "date", "hour"],
        },
    ),
    Tool(
        name="download_ticks",
        description="指定期間のティックデータをCSVでキャッシュに一括保存（バックテスト用）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "start": {"type": "string", "description": "開始日 (YYYY-MM-DD)"},
                "end": {"type": "string", "description": "終了日 (YYYY-MM-DD)"},
            },
            "required": ["symbol", "start", "end"],
        },
    ),
    Tool(
        name="download_candles",
        description="指定期間の1分足OHLCをCSVでキャッシュに一括保存（バックテスト用）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "start": {"type": "string", "description": "開始日 (YYYY-MM-DD)"},
                "end": {"type": "string", "description": "終了日 (YYYY-MM-DD)"},
            },
            "required": ["symbol", "start", "end"],
        },
    ),
    Tool(
        name="cache_status",
        description="キャッシュ済みデータの一覧（シンボル・種別・期間・サイズ）を確認",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア（省略で全件）"},
            },
            "required": [],
        },
    ),
    Tool(
        name="clear_cache",
        description="キャッシュデータを削除（シンボル・期間指定可、省略で全消し）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア（省略で全削除）"},
                "start": {"type": "string", "description": "開始日（期間指定削除用）"},
                "end": {"type": "string", "description": "終了日（期間指定削除用）"},
            },
            "required": [],
        },
    ),
    Tool(
        name="calibrate",
        description=(
            "MT5キャッシュとDukascopyキャッシュを照合し、時間帯別スプレッドプロファイルを生成して保存する。"
            "実行前に MT5_mcp の download_ticks_bulk と Dukascopy の download_ticks が完了している必要がある。"
        ),
        inputSchema={
            "type": "object",
            "properties": {
                "symbol":   {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "broker":   {"type": "string", "description": "ブローカー名 (例: ICMarkets)"},
                "start":    {"type": "string", "description": "照合開始日 YYYY-MM-DD"},
                "end":      {"type": "string", "description": "照合終了日 YYYY-MM-DD"},
                "tolerance_ms":        {"type": "integer", "description": "アライメント許容差ミリ秒 (省略時 1000)"},
                "news_window_minutes": {"type": "integer", "description": "ニュース除外ウィンドウ分 (省略時 30)"},
                "use_calendar":        {"type": "boolean", "description": "ForexFactory カレンダーを使うか (省略時 true)"},
            },
            "required": ["symbol", "broker", "start", "end"],
        },
    ),
    Tool(
        name="reshape",
        description="較正モデルを使って Dukascopy の過去ティックデータを成形し WD_Black に保存する",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "broker": {"type": "string", "description": "ブローカー名 (例: ICMarkets)"},
                "start":  {"type": "string", "description": "成形開始日 YYYY-MM-DD"},
                "end":    {"type": "string", "description": "成形終了日 YYYY-MM-DD"},
            },
            "required": ["symbol", "broker", "start", "end"],
        },
    ),
    Tool(
        name="calibration_status",
        description="保存済み較正モデル（profile.json）の一覧と概要を確認する",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア（省略で全件）"},
                "broker": {"type": "string", "description": "ブローカー名（省略で全件）"},
            },
            "required": [],
        },
    ),
    Tool(
        name="get_reshaped_ticks",
        description="成形済みティックを JSON で取得（アドホック分析・バックテスト確認用）",
        inputSchema={
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "通貨ペア (例: XAUUSD)"},
                "broker": {"type": "string", "description": "ブローカー名 (例: ICMarkets)"},
                "date":   {"type": "string", "description": "日付 YYYY-MM-DD"},
                "hour":   {"type": "integer", "description": "時間帯フィルタ 0-23（省略で全時間）"},
            },
            "required": ["symbol", "broker", "date"],
        },
    ),
]


@app.list_tools()
async def list_tools() -> list[Tool]:
    return TOOLS


@app.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    try:
        if name == "get_ticks":
            date_parts = arguments["date"].split("-")
            year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
            ticks = await client.fetch_hour_ticks(
                arguments["symbol"], year, month, day, arguments["hour"]
            )
            return _json_text({"count": len(ticks), "ticks": ticks})

        elif name == "get_candles":
            date_parts = arguments["date"].split("-")
            year, month, day = int(date_parts[0]), int(date_parts[1]), int(date_parts[2])
            candles = await client.fetch_day_candles(
                arguments["symbol"], year, month, day
            )
            hour = arguments["hour"]
            hour_prefix = f"{date_parts[0]}-{date_parts[1]}-{date_parts[2]} {hour:02d}:"
            filtered = [c for c in candles if c["timestamp"].startswith(hour_prefix)]
            return _json_text({"count": len(filtered), "candles": filtered})

        elif name == "download_ticks":
            result = await client.download_ticks(
                arguments["symbol"], arguments["start"], arguments["end"]
            )
            return _json_text(result)

        elif name == "download_candles":
            result = await client.download_candles(
                arguments["symbol"], arguments["start"], arguments["end"]
            )
            return _json_text(result)

        elif name == "cache_status":
            status = client.cache_status(symbol=arguments.get("symbol"))
            return _json_text(status)

        elif name == "clear_cache":
            result = client.clear_cache(
                symbol=arguments.get("symbol"),
                start=arguments.get("start"),
                end=arguments.get("end"),
            )
            return _json_text(result)

        elif name == "calibrate":
            symbol = arguments["symbol"].upper()
            broker = arguments["broker"]
            start  = arguments["start"]
            end    = arguments["end"]
            tolerance_ms = int(arguments.get("tolerance_ms", 1000))
            news_window  = int(arguments.get("news_window_minutes", 30))
            use_calendar = bool(arguments.get("use_calendar", True))

            mt5_dir = _resolve(_WD_MT5, _LOCAL_MT5) / broker / symbol / "ticks"
            if not mt5_dir.exists():
                return _error_text(f"MT5キャッシュなし: {mt5_dir} — 先に download_ticks_bulk を実行してください")

            # ForexFactory カレンダー読み込み
            calendar = None
            if use_calendar and _FF_CALENDAR.exists():
                calendar = CalendarLoader(_FF_CALENDAR)
                calendar.load_events(start=start, end=end, impact="High")

            # 日単位でアライメント → 全ペアを集約
            from datetime import date as _date
            all_pairs = []
            current = _date.fromisoformat(start)
            end_d   = _date.fromisoformat(end)
            while current <= end_d:
                date_str = current.isoformat()
                mt5_csv  = mt5_dir / f"{date_str}.csv"
                duku_csv = client._cache_dir / symbol / "ticks" / f"{date_str}.csv"
                if mt5_csv.exists() and duku_csv.exists():
                    mt5_ticks = list(csv.DictReader(open(mt5_csv)))
                    for t in mt5_ticks:
                        t["bid"] = float(t["bid"]); t["ask"] = float(t["ask"])
                    duku_ticks = list(csv.DictReader(open(duku_csv)))
                    for t in duku_ticks:
                        t["bid"] = float(t["bid"]); t["ask"] = float(t["ask"])
                    pairs = TickAligner.align(mt5_ticks, duku_ticks, tolerance_ms=tolerance_ms)
                    all_pairs.extend(pairs)
                current += timedelta(days=1)

            if not all_pairs:
                return _error_text(
                    "アライメントペアが 0 件。"
                    "MT5 と Dukascopy 両方のティックキャッシュが同一期間に存在するか確認してください。"
                )

            profiler = SpreadProfiler()
            profile_dict = profiler.build(all_pairs, calendar=calendar, news_window_minutes=news_window)
            model = CalibrationModel(
                broker=broker,
                symbol=symbol,
                mt5_data_range=f"{start} ~ {end}",
                total_pairs=len(all_pairs),
                hourly_profiles=profile_dict,
            )
            calib_root = _resolve(_WD_CALIBRATION, _LOCAL_CALIBRATION)
            save_path  = CalibrationModel.model_path(calib_root, broker, symbol)
            model.save(save_path)
            return _json_text({
                "saved_to": str(save_path),
                "total_pairs": len(all_pairs),
                "hours_covered": sorted(int(h) for h in profile_dict),
                "sample_counts": {h: v["sample_count"] for h, v in profile_dict.items()},
            })

        elif name == "reshape":
            symbol = arguments["symbol"].upper()
            broker = arguments["broker"]
            start  = arguments["start"]
            end    = arguments["end"]

            calib_root = _resolve(_WD_CALIBRATION, _LOCAL_CALIBRATION)
            model_path = CalibrationModel.model_path(calib_root, broker, symbol)
            if not model_path.exists():
                return _error_text(f"較正モデルなし: {model_path} — 先に calibrate を実行してください")
            model = CalibrationModel.load(model_path)

            reshaped_root = _resolve(_WD_RESHAPED, _LOCAL_RESHAPED)
            from datetime import date as _date
            total_written = 0
            days = 0
            current = _date.fromisoformat(start)
            end_d   = _date.fromisoformat(end)
            while current <= end_d:
                date_str = current.isoformat()
                duku_csv = client._cache_dir / symbol / "ticks" / f"{date_str}.csv"
                if duku_csv.exists():
                    ticks = list(csv.DictReader(open(duku_csv)))
                    for t in ticks:
                        t["bid"]        = float(t["bid"])
                        t["ask"]        = float(t["ask"])
                        t["bid_volume"] = float(t.get("bid_volume", 0.0))
                        t["ask_volume"] = float(t.get("ask_volume", 0.0))
                    out_path = reshaped_root / broker / symbol / "ticks" / f"{date_str}.csv"
                    n = Reshaper.reshape_ticks(ticks, model, out_path)
                    total_written += n
                    days += 1
                current += timedelta(days=1)

            ticks_dir = reshaped_root / broker / symbol / "ticks"
            size_mb = (
                sum(f.stat().st_size for f in ticks_dir.glob("*.csv")) / (1024 ** 2)
                if ticks_dir.exists() else 0.0
            )
            return _json_text({
                "path": str(ticks_dir),
                "days": days,
                "total_ticks": total_written,
                "size_mb": round(size_mb, 2),
            })

        elif name == "calibration_status":
            calib_root = _resolve(_WD_CALIBRATION, _LOCAL_CALIBRATION)
            results = []
            if calib_root.exists():
                for broker_dir in sorted(calib_root.iterdir()):
                    if not broker_dir.is_dir():
                        continue
                    broker_filter = arguments.get("broker")
                    if broker_filter and broker_dir.name != broker_filter:
                        continue
                    for sym_dir in sorted(broker_dir.iterdir()):
                        if not sym_dir.is_dir():
                            continue
                        sym_filter = arguments.get("symbol")
                        if sym_filter and sym_dir.name != sym_filter.upper():
                            continue
                        profile_path = sym_dir / "profile.json"
                        if not profile_path.exists():
                            continue
                        m = CalibrationModel.load(profile_path)
                        results.append({
                            "broker": m.broker,
                            "symbol": m.symbol,
                            "created_at": m.created_at,
                            "mt5_data_range": m.mt5_data_range,
                            "total_pairs": m.total_pairs,
                            "hours_covered": sorted(int(h) for h in m.hourly_profiles),
                        })
            return _json_text(results)

        elif name == "get_reshaped_ticks":
            symbol = arguments["symbol"].upper()
            broker = arguments["broker"]
            date_str = arguments["date"]
            hour_filter = arguments.get("hour")

            reshaped_root = _resolve(_WD_RESHAPED, _LOCAL_RESHAPED)
            csv_path = reshaped_root / broker / symbol / "ticks" / f"{date_str}.csv"
            if not csv_path.exists():
                return _error_text(f"成形済みデータなし: {csv_path} — reshape を先に実行してください")

            ticks = list(csv.DictReader(open(csv_path)))
            if hour_filter is not None:
                prefix = f"{date_str} {int(hour_filter):02d}:"
                ticks = [t for t in ticks if t["timestamp"].startswith(prefix)]
            for t in ticks:
                t["bid"]        = float(t["bid"])
                t["ask"]        = float(t["ask"])
                t["bid_volume"] = float(t["bid_volume"])
                t["ask_volume"] = float(t["ask_volume"])
            return _json_text({"count": len(ticks), "ticks": ticks})

        else:
            return _error_text(f"不明なツール: {name}")

    except ValueError as e:
        return _error_text(str(e))
    except Exception as e:
        return _error_text(f"予期しないエラー: {str(e)}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await app.run(read_stream, write_stream, app.create_initialization_options())


if __name__ == "__main__":
    asyncio.run(main())
