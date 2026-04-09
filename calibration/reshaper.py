"""
CalibrationModel を使って Dukascopy ティックを成形し CSV に出力する。

補正ロジック:
  duku_mid    = (duku.bid + duku.ask) / 2
  duku_spread = duku.ask - duku.bid
  reshaped_spread = duku_spread + profile.spread_delta_mean
  reshaped_mid    = duku_mid    + profile.mid_offset_mean
  reshaped_bid    = reshaped_mid - reshaped_spread / 2
  reshaped_ask    = reshaped_mid + reshaped_spread / 2

プロファイルがない時間帯のティックは除外する。
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path

from calibration.model import CalibrationModel


_CSV_FIELDS = ["timestamp", "bid", "ask", "bid_volume", "ask_volume"]


class Reshaper:

    @staticmethod
    def reshape_tick(tick: dict, model: CalibrationModel) -> dict | None:
        """
        tick:    {"timestamp": "YYYY-MM-DD HH:MM:SS.mmm", "bid": float, "ask": float, ...}
        戻り値:  成形済み tick dict。プロファイルなし時間帯なら None。
        """
        ts_str = tick["timestamp"]
        # "YYYY-MM-DD HH:MM:SS.mmm" の先頭 19 文字で時間を取得
        try:
            hour = int(ts_str[11:13])
        except (ValueError, IndexError):
            return None

        profile = model.get_profile(hour)
        if profile is None:
            return None

        duku_bid = float(tick["bid"])
        duku_ask = float(tick["ask"])
        duku_mid = (duku_bid + duku_ask) / 2
        duku_spread = duku_ask - duku_bid

        reshaped_spread = duku_spread + profile["spread_delta_mean"]
        reshaped_mid = duku_mid + profile["mid_offset_mean"]
        half = reshaped_spread / 2

        return {
            "timestamp": ts_str,
            "bid": round(reshaped_mid - half, 5),
            "ask": round(reshaped_mid + half, 5),
            "bid_volume": float(tick.get("bid_volume", 0.0)),
            "ask_volume": float(tick.get("ask_volume", 0.0)),
        }

    @staticmethod
    def reshape_ticks(
        ticks: list[dict],
        model: CalibrationModel,
        out_path: str | Path,
    ) -> int:
        """
        ticks を成形して CSV に保存する。プロファイルなし時間帯はスキップ。
        戻り値: 書き込んだティック数
        """
        out_path = Path(out_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with open(out_path, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=_CSV_FIELDS)
            writer.writeheader()
            for tick in ticks:
                reshaped = Reshaper.reshape_tick(tick, model)
                if reshaped is None:
                    continue
                writer.writerow(reshaped)
                count += 1
        return count
