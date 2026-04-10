# Dukascopy MCP — タスク管理

最終更新: 2026-04-10

---

## 現状サマリー

| フェーズ | 内容 | 状態 |
|---------|------|------|
| 1 | 基本データ取得 (get/download ticks・candles, cache管理) | **完了** |
| 2 | キャリブレーションパイプライン実装 | **完了** |
| 3 | 実データによる精度検証 | **未着手**（WiFi・WD_Black環境が必要） |
| 4 | バックテストスクリプトとの統合 | **未着手** |

---

## Phase 3: 実データ検証（WiFi + WD_Black 接続環境で実施）

### 手順

```
Step 1: データ収集（1〜2時間）
  download_ticks(XAUUSD, 2025-01-01, 2025-03-31)         # Dukascopy側
  download_ticks_bulk(XAUUSD, 2025-01-01, 2025-03-31,    # MT5側
                      account="ICMarkets")

Step 2: 較正モデル生成
  calibrate(XAUUSD, ICMarkets, 2025-01-01, 2025-03-31)
  → profile.json に時間帯別プロファイルが保存されることを確認

Step 3: 成形
  reshape(XAUUSD, ICMarkets, 2025-01-01, 2025-03-31)

Step 4: 精度確認
  - 較正に使っていない期間（例: 2025-04-01〜）で get_reshaped_ticks を取得
  - MT5_mcp の get_ticks で同日同時刻のMT5実ティックを取得
  - スプレッド・中値の差を比較 → 平均誤差・最大誤差を記録
```

### 精度評価基準（暫定）

| 指標 | 目標 |
|------|------|
| スプレッド平均誤差 | ±1 pip 以内 |
| 中値オフセット平均誤差 | ±0.5 pip 以内 |
| ニュース時間帯の除外率 | profile.json の sample_count で確認 |

---

## Phase 4: バックテスト統合

### 4-1. AUDCAD への接続

- AUDCAD の `zone_hunter_backtest_v2.py` がティックデータを使えるようにする
- 入力フォーマット: `WD_Black/reshaped/ICMarkets/AUDCAD/ticks/{date}.csv`
- 現状バックテストは `backtest/` 内で独自ダウンロードしている可能性 → 統合要否を確認

### 4-2. Brakeout/MorningScalp への接続

- MorningScalp Phase 3 (EntryEA) のティックシミュレーション用データソースとして利用
- スプレッド成形済みデータをそのままスプレッドメーターデータの代替として使えるか検討

---

## 追加機能候補（優先度順）

| # | 機能 | 概要 | 優先度 |
|---|------|------|--------|
| A | `get_reshaped_candles` | reshaped ticks を1分足OHLCに集約して返すツール | 中 |
| B | ForexFactory自動DL | `calendar_loader.py` にカレンダーCSVの自動ダウンロード機能を追加 | 低 |
| C | TitanFX対応 | MT5_mcp に TitanFX 口座を追加後、同ブローカーの較正モデルも生成 | 低 |
| D | 複数シンボル一括較正 | symbol のリストを受け取って一括 calibrate する `calibrate_bulk` ツール | 低 |

---

## 環境メモ

- **キャリブレーション実行条件**: WiFi接続 + WD_Black SSD 接続（`/Volumes/WD_Black` マウント）
- **対象ブローカー**: ICMarkets（MT5_mcp の `ICMarkets` 口座）
- **MT5_mcp との連携**: `download_ticks_bulk` の `broker` パラメータを `ICMarkets` で統一すること
  - WD_Black パス: `MT5_cache/ICMarkets/XAUUSD/ticks/`
