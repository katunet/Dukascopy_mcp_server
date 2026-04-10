# Dukascopy MCP Server

Dukascopy の無料公開データフィードからティックデータ・1分足OHLCを取得する MCP (Model Context Protocol) サーバー。

Claude Code / Claude Desktop から直接呼び出して、FX・CFDのヒストリカルデータを取得・分析できる。

MT5_mcp と組み合わせることで、実ブローカーのティック特性（スプレッド・遅延）を Dukascopy データに重畳した「較正済みティック」を生成できる。

## 機能一覧

### データ取得・キャッシュ（6ツール）

| ツール | 用途 |
|-------|------|
| `get_ticks` | 指定シンボル・日時の1時間分ティックデータをJSON返却（キャッシュなし） |
| `get_candles` | 指定シンボル・日時の1時間分1分足OHLCをJSON返却（キャッシュ優先） |
| `download_ticks` | 期間指定でティックデータをCSVに一括保存 |
| `download_candles` | 期間指定で1分足OHLCをCSVに一括保存 |
| `cache_status` | 保存済みデータの一覧表示（シンボル・期間・サイズ） |
| `clear_cache` | キャッシュ削除（シンボル・期間指定可） |

### キャリブレーションパイプライン（4ツール）

| ツール | 用途 |
|-------|------|
| `calibrate` | MT5ティック ↔ Dukascopyティックを照合し、時間帯別スプレッドプロファイルを生成・保存 |
| `reshape` | 較正モデルを使って Dukascopy ティックをブローカー特性に近似変換 |
| `calibration_status` | 保存済み較正モデル（profile.json）の一覧と概要を確認 |
| `get_reshaped_ticks` | 成形済みティックをJSON取得（アドホック分析・精度確認用） |

## キャリブレーションの仕組み

```
[前提データ準備]
  MT5_mcp: download_ticks_bulk  → WD_Black/MT5_cache/{broker}/{symbol}/ticks/
  Dukascopy: download_ticks     → WD_Black/Dukascopy_mcp/cache/{symbol}/ticks/

[較正モデル生成]
  calibrate(symbol, broker, start, end)
    → TickAligner: 時刻±tolerance_msでMT5↔Dukascopyのティックペアを照合
    → SpreadProfiler: 時間帯(0-23)ごとにスプレッド差・中値オフセットを集計
    → CalibrationModel: profile.json として WD_Black/calibration/{broker}/{symbol}/ に保存
    ※ ForexFactory 高インパクトニュース前後はサンプルから除外可（use_calendar=true）

[ティック成形]
  reshape(symbol, broker, start, end)
    → Reshaper: 較正モデルの時間帯プロファイルを使い Dukascopy のbid/askを補正
    → 出力: WD_Black/reshaped/{broker}/{symbol}/ticks/{date}.csv
```

## ファイル構成

```
Dukascopy_mcp/
  server.py              # MCPサーバー (10ツール定義)
  dukascopy_client.py    # データ取得・パース・キャッシュ管理
  requirements.txt
  calibration/
    model.py             # CalibrationModel (JSON保存/読み込み)
    tick_aligner.py      # TickAligner (MT5↔Dukascopy ミリ秒アライメント)
    spread_profiler.py   # SpreadProfiler (時間帯別プロファイル集計)
    reshaper.py          # Reshaper (較正モデル適用)
    calendar_loader.py   # CalendarLoader (ForexFactory ニュース除外)
  tests/
    test_client.py
    test_server.py
    test_tick_aligner.py
    test_spread_profiler.py
    test_reshaper.py
    test_calendar_loader.py
```

## キャッシュパス（WD_Black SSD 優先）

| 種別 | WD_Black パス | ローカルフォールバック |
|-----|--------------|----------------------|
| Dukascopy ティック/ローソク | `/Volumes/WD_Black/Dukascopy_mcp/cache/` | `./cache/` |
| MT5 ティック（MT5_mcpと共有） | `/Volumes/WD_Black/MT5_cache/` | `./MT5_cache/` |
| 較正モデル | `/Volumes/WD_Black/calibration/` | `./calibration_cache/` |
| 成形済みティック | `/Volumes/WD_Black/reshaped/` | `./reshaped_cache/` |
| ForexFactory カレンダー | `/Volumes/WD_Black/ForexFactory/calendar/` | 使用しない |

WD_Black が接続中であれば自動的にそちらに書き込む。未接続時はローカルにフォールバック。

## 対応シンボル (デフォルトプリセット 16ペア)

**メイン:** XAUUSD

**クロス通貨:** USDJPY, EURUSD, GBPJPY, EURJPY, EURCHF, EURAUD, EURNZD, GBPCAD, GBPCHF, GBPAUD, GBPNZD, NZDCHF, AUDNZD, AUDCAD, CHFJPY

プリセット外の任意シンボルも指定可能。

## セットアップ

```bash
cd Dukascopy_mcp
pip install -r requirements.txt
```

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

## 使い方

### アドホック分析

```
「XAUUSD の 2024-01-15 10:00 UTC のティックデータを見せて」
→ get_ticks(symbol="XAUUSD", date="2024-01-15", hour=10)

「EURUSD の 2024-03-01 15時台の1分足を取得して」
→ get_candles(symbol="EURUSD", date="2024-03-01", hour=15)
```

### バックテスト用データ一括取得

```
「XAUUSD の 2023年1月〜12月のティックをダウンロードして」
→ download_ticks(symbol="XAUUSD", start="2023-01-01", end="2023-12-31")

「今キャッシュにどれくらいデータがある？」
→ cache_status()
```

### キャリブレーション（WiFi接続・WD_Black接続が必要）

```
# 1. Dukascopy ティックをダウンロード
download_ticks(symbol="XAUUSD", start="2025-01-01", end="2025-03-31")

# 2. MT5 ティックをダウンロード（MT5_mcp で実行）
download_ticks_bulk(symbol="XAUUSD", start="2025-01-01", end="2025-03-31", account="ICMarkets")

# 3. 較正モデルを生成
calibrate(symbol="XAUUSD", broker="ICMarkets", start="2025-01-01", end="2025-03-31")

# 4. Dukascopy ティックをブローカー特性に成形
reshape(symbol="XAUUSD", broker="ICMarkets", start="2025-01-01", end="2025-03-31")

# 5. 成形済みティックを確認
get_reshaped_ticks(symbol="XAUUSD", broker="ICMarkets", date="2025-01-15", hour=10)
```

## データソース

- **URL:** `https://datafeed.dukascopy.com/datafeed/`
- **形式:** LZMA圧縮バイナリ (.bi5)
- **認証:** 不要 (無料公開データ)
- **利用可能期間:** 2003-2004年頃〜現在 (通貨ペアにより異なる)

## テスト

```bash
python3 -m pytest tests/ -v
```

## 技術スタック

- Python 3, asyncio
- httpx — 非同期HTTPクライアント
- MCP — Model Context Protocol (stdio)
- lzma, struct — 標準ライブラリ (bi5解凍・バイナリパース)

## ライセンス

MIT
