"""
アライメントペアから時間帯別（UTC hour 0-23）スプレッドプロファイルを生成する。

出力形式:
{
  "10": {
    "mid_offset_mean": 0.06,    # MT5.mid - Duku.mid の平均
    "mid_offset_std": 0.01,
    "spread_delta_mean": 0.11,  # MT5.spread - Duku.spread の平均
    "spread_delta_std": 0.01,
    "sample_count": 2,
  },
  ...
}
"""
from __future__ import annotations

import statistics
from collections import defaultdict
from datetime import datetime, timezone

from calibration.tick_aligner import AlignedPair, TickAligner


class SpreadProfiler:

    def build(
        self,
        pairs: list[AlignedPair],
        calendar=None,
        news_window_minutes: int = 30,
    ) -> dict[str, dict]:
        """
        pairs:               TickAligner.align() の出力
        calendar:            CalendarLoader インスタンス（None でニュースフィルタなし）
        news_window_minutes: ニュース前後何分を除外するか

        戻り値: hour 文字列キー（"0"〜"23"）の dict
        """
        buckets: dict[int, list[tuple[float, float]]] = defaultdict(list)

        for pair in pairs:
            if calendar is not None:
                ts_ms = TickAligner.parse_mt5_ms(pair.mt5_tick["time_msc"])
                ts = datetime.fromtimestamp(ts_ms / 1000, tz=timezone.utc)
                if calendar.is_news_period(ts, window_minutes=news_window_minutes):
                    continue
            buckets[pair.hour_utc].append((pair.mid_delta, pair.spread_delta))

        profile: dict[str, dict] = {}
        for hour, samples in sorted(buckets.items()):
            mids = [s[0] for s in samples]
            spreads = [s[1] for s in samples]
            profile[str(hour)] = {
                "mid_offset_mean": statistics.mean(mids),
                "mid_offset_std": statistics.stdev(mids) if len(mids) > 1 else 0.0,
                "spread_delta_mean": statistics.mean(spreads),
                "spread_delta_std": statistics.stdev(spreads) if len(spreads) > 1 else 0.0,
                "sample_count": len(samples),
            }

        return profile
