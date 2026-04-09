"""
較正モデルの保存・読み込み。

JSON ファイル形式:
{
  "broker": "ICMarkets",
  "symbol": "XAUUSD",
  "created_at": "2026-04-09T00:00:00+00:00",
  "mt5_data_range": "2025-04-09 ~ 2026-04-09",
  "total_pairs": 500000,
  "hourly_profiles": {
    "0":  {"mid_offset_mean": ..., "mid_offset_std": ...,
           "spread_delta_mean": ..., "spread_delta_std": ..., "sample_count": ...},
    ...
    "23": {...}
  }
}
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path


class CalibrationModel:

    def __init__(
        self,
        broker: str,
        symbol: str,
        mt5_data_range: str,
        total_pairs: int,
        hourly_profiles: dict[str, dict],
    ):
        self.broker = broker
        self.symbol = symbol
        self.mt5_data_range = mt5_data_range
        self.total_pairs = total_pairs
        self.hourly_profiles = hourly_profiles
        self.created_at = datetime.now(tz=timezone.utc).isoformat()

    def get_profile(self, hour_utc: int) -> dict | None:
        """hour_utc (0-23) のプロファイルを返す。なければ None。"""
        return self.hourly_profiles.get(str(hour_utc))

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self._to_dict(), f, indent=2, ensure_ascii=False)
        return path

    @classmethod
    def load(cls, path: str | Path) -> "CalibrationModel":
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        obj = cls(
            broker=data["broker"],
            symbol=data["symbol"],
            mt5_data_range=data["mt5_data_range"],
            total_pairs=data["total_pairs"],
            hourly_profiles=data["hourly_profiles"],
        )
        obj.created_at = data.get("created_at", "")
        return obj

    @classmethod
    def model_path(cls, cache_root: Path, broker: str, symbol: str) -> Path:
        return cache_root / broker / symbol.upper() / "profile.json"

    def _to_dict(self) -> dict:
        return {
            "broker": self.broker,
            "symbol": self.symbol,
            "created_at": self.created_at,
            "mt5_data_range": self.mt5_data_range,
            "total_pairs": self.total_pairs,
            "hourly_profiles": self.hourly_profiles,
        }
