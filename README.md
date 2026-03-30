# Dukascopy MCP Server

Dukascopy の無料公開データフィードからティックデータ・1分足OHLCを取得する MCP (Model Context Protocol) サーバー。

Claude Code / Claude Desktop から直接呼び出して、FX・CFDのヒストリカルデータを取得・分析できる。

## 機能

| ツール | 用途 | 説明 |
|-------|------|------|
| `get_ticks` | リアルタイム分析 | 指定シンボル・日時の1時間分ティックデータをJSON返却 |
| `get_candles` | リアルタイム分析 | 指定シンボル・日時の1時間分1分足OHLCをJSON返却 |
| `download_ticks` | バックテスト | 期間指定でティックデータをCSVに一括保存 |
| `download_candles` | バックテスト | 期間指定で1分足OHLCをCSVに一括保存 |
| `cache_status` | キャッシュ管理 | 保存済みデータの一覧表示 (シンボル・期間・サイズ) |
| `clear_cache` | キャッシュ管理 | キャッシュ削除 (シンボル・期間指定可) |

## 対応シンボル (デフォルトプリセット 16ペア)

**メイン:** XAUUSD

**クロス通貨:** USDJPY, EURUSD, GBPJPY, EURJPY, EURCHF, EURAUD, EURNZD, GBPCAD, GBPCHF, GBPAUD, GBPNZD, NZDCHF, AUDNZD, AUDCAD, CHFJPY

プリセット外の任意シンボルも指定可能。

## セットアップ

### 1. 依存パッケージのインストール

```bash
cd Dukascopy_mcp
pip install -r requirements.txt
```

### 2. MCP設定に登録

**Claude Code** (`.mcp.json`):

```json
{
  "mcpServers": {
    "dukascopy": {
      "command": "python3",
      "args": ["server.py"],
      "cwd": "/path/to/Dukascopy_mcp"
    }
  }
}
```

**Claude Desktop** (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "dukascopy": {
      "command": "python3",
      "args": ["/path/to/Dukascopy_mcp/server.py"]
    }
  }
}
```

## 使い方

### EA考察・アドホック分析

```
「XAUUSD の 2024-01-15 10:00 UTC のティックデータを見せて」
→ get_ticks(symbol="XAUUSD", date="2024-01-15", hour=10)
```

```
「EURUSD の 2024-03-01 15時台の1分足を取得して」
→ get_candles(symbol="EURUSD", date="2024-03-01", hour=15)
```

### バックテスト用データ取得

```
「XAUUSD の 2023年1月〜12月の1分足データをダウンロードして」
→ download_candles(symbol="XAUUSD", start="2023-01-01", end="2023-12-31")
→ CSV保存先: cache/XAUUSD/candles/2023-01-01.csv ~ 2023-12-31.csv
```

### キャッシュ管理

```
「今キャッシュにどれくらいデータがある？」
→ cache_status()

「XAUUSDのキャッシュだけ消して」
→ clear_cache(symbol="XAUUSD")
```

## データソース

- **URL:** `https://datafeed.dukascopy.com/datafeed/`
- **形式:** LZMA圧縮バイナリ (.bi5)
- **認証:** 不要 (無料公開データ)
- **利用可能期間:** 2003-2004年頃〜現在 (通貨ペアにより異なる)

## CSV出力フォーマット

**ティック:**
```csv
timestamp,bid,ask,bid_volume,ask_volume
2024-01-15 10:00:00.113,2054.925,2055.235,0.0,0.0
```

**1分足:**
```csv
timestamp,open,high,low,close,volume
2024-01-15 10:00:00,2054.93,2055.10,2054.80,2055.05,150.5
```

## ファイル構成

```
Dukascopy_mcp/
  server.py              # MCPサーバー (6ツール定義)
  dukascopy_client.py    # データ取得・パース・キャッシュ管理
  requirements.txt       # pip依存関係
  .gitignore
  cache/                 # ティック・1分足CSVの一時保存先 (git管理外)
  tests/
    test_client.py       # クライアントテスト (27件)
    test_server.py       # サーバーテスト (5件)
```

## テスト

```bash
python3 -m pytest tests/ -v
```

## 技術スタック

- Python 3, asyncio
- [httpx](https://www.python-httpx.org/) — 非同期HTTPクライアント
- [MCP](https://modelcontextprotocol.io/) — Model Context Protocol (stdio)
- lzma, struct — 標準ライブラリ (bi5解凍・バイナリパース)

## ライセンス

MIT
