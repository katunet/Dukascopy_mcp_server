"""
Dukascopy MCP Server
Dukascopy datafeed からティックデータ・1分足OHLCを取得する
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

from mcp.server import Server
from mcp.server.stdio import stdio_server
from mcp.types import TextContent, Tool

from dukascopy_client import DukascopyClient

CACHE_DIR = Path(os.path.dirname(os.path.abspath(__file__))) / "cache"

app = Server("dukascopy")
client = DukascopyClient(cache_dir=CACHE_DIR)


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
