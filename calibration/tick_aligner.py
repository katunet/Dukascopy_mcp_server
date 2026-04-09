"""
MT5 ティックと Dukascopy ティックをタイムスタンプでアライメントする。

入力タイムスタンプ形式:
  MT5:       time_msc フィールド — ISO 8601 文字列 "YYYY-MM-DDTHH:MM:SS.ffffff+00:00"
  Dukascopy: timestamp フィールド — "YYYY-MM-DD HH:MM:SS.mmm"

アルゴリズム:
  MT5 ティック毎に Dukascopy 側で bisect による最近傍探索 O(N log M)。
  tolerance_ms 以内に収まるペアのみ返す。
"""
from __future__ import annotations

import bisect
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class AlignedPair:
    mt5_tick: dict
    duku_tick: dict
    gap_ms: int          # |MT5.time_msc - Duku.timestamp| ミリ秒
    mid_delta: float     # MT5.mid - Duku.mid
    spread_delta: float  # MT5.spread - Duku.spread
    hour_utc: int        # 0-23


class TickAligner:

    @staticmethod
    def parse_mt5_ms(time_msc_str: str) -> int:
        """ISO 8601 文字列 → epoch ミリ秒"""
        dt = datetime.fromisoformat(time_msc_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def parse_duku_ms(timestamp_str: str) -> int:
        """'YYYY-MM-DD HH:MM:SS.mmm' → epoch ミリ秒

        Dukascopy の timestamp は小数点以下 3 桁（ミリ秒）。
        strptime の %f は 6 桁として扱うため、3 桁のときはゼロ埋め。
        """
        # 小数点以下が 3 桁の場合は 6 桁に補完
        parts = timestamp_str.strip().split(".")
        if len(parts) == 2 and len(parts[1]) == 3:
            timestamp_str = parts[0] + "." + parts[1] + "000"
        dt = datetime.strptime(timestamp_str, "%Y-%m-%d %H:%M:%S.%f")
        dt = dt.replace(tzinfo=timezone.utc)
        return int(dt.timestamp() * 1000)

    @staticmethod
    def align(
        mt5_ticks: list[dict],
        duku_ticks: list[dict],
        tolerance_ms: int = 1000,
    ) -> list[AlignedPair]:
        """
        mt5_ticks:  [{"time_msc": ISO_str, "bid": float, "ask": float, ...}]
        duku_ticks: [{"timestamp": str, "bid": float, "ask": float, ...}]

        両リストはソート済みを前提とする（未ソートでも動くが O(N log M) の保証なし）。
        """
        if not mt5_ticks or not duku_ticks:
            return []

        duku_ms_list = [
            TickAligner.parse_duku_ms(t["timestamp"]) for t in duku_ticks
        ]

        pairs: list[AlignedPair] = []

        for mt5 in mt5_ticks:
            mt5_ms = TickAligner.parse_mt5_ms(mt5["time_msc"])
            idx = bisect.bisect_left(duku_ms_list, mt5_ms)

            candidates: list[tuple[int, int]] = []  # (gap_ms, list_idx)
            if idx < len(duku_ticks):
                candidates.append((abs(duku_ms_list[idx] - mt5_ms), idx))
            if idx > 0:
                candidates.append((abs(duku_ms_list[idx - 1] - mt5_ms), idx - 1))

            if not candidates:
                continue

            gap_ms, best_idx = min(candidates)
            if gap_ms > tolerance_ms:
                continue

            duku = duku_ticks[best_idx]
            mt5_bid = float(mt5["bid"])
            mt5_ask = float(mt5["ask"])
            duku_bid = float(duku["bid"])
            duku_ask = float(duku["ask"])

            mt5_mid = (mt5_bid + mt5_ask) / 2
            duku_mid = (duku_bid + duku_ask) / 2
            mt5_spread = mt5_ask - mt5_bid
            duku_spread = duku_ask - duku_bid

            hour_utc = datetime.fromtimestamp(mt5_ms / 1000, tz=timezone.utc).hour

            pairs.append(AlignedPair(
                mt5_tick=mt5,
                duku_tick=duku,
                gap_ms=gap_ms,
                mid_delta=mt5_mid - duku_mid,
                spread_delta=mt5_spread - duku_spread,
                hour_utc=hour_utc,
            ))

        return pairs
