"""spread_profiler のユニットテスト"""
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from calibration.tick_aligner import AlignedPair
from calibration.spread_profiler import SpreadProfiler


def make_pair(hour: int, mid_delta: float, spread_delta: float) -> AlignedPair:
    dummy = {"time_msc": f"2024-04-09T{hour:02d}:00:00.000000+00:00", "bid": 0.0, "ask": 0.0}
    return AlignedPair(
        mt5_tick=dummy,
        duku_tick=dummy,
        gap_ms=0,
        mid_delta=mid_delta,
        spread_delta=spread_delta,
        hour_utc=hour,
    )


def test_profile_mean_per_hour():
    pairs = [
        make_pair(10, mid_delta=0.05, spread_delta=0.10),
        make_pair(10, mid_delta=0.07, spread_delta=0.12),
        make_pair(14, mid_delta=0.02, spread_delta=0.05),
    ]
    profiler = SpreadProfiler()
    profile = profiler.build(pairs)

    assert "10" in profile
    assert abs(profile["10"]["mid_offset_mean"] - 0.06) < 1e-9
    assert abs(profile["10"]["spread_delta_mean"] - 0.11) < 1e-9
    assert profile["10"]["sample_count"] == 2

    assert "14" in profile
    assert profile["14"]["sample_count"] == 1


def test_news_pairs_excluded():
    """CalendarLoader で is_news_period=True のペアは除外される"""
    from calibration.calendar_loader import CalendarLoader

    calendar_mock = MagicMock(spec=CalendarLoader)

    def fake_is_news(ts, window_minutes=30):
        return ts.hour == 10

    calendar_mock.is_news_period.side_effect = fake_is_news

    pairs = [
        make_pair(10, mid_delta=0.05, spread_delta=0.10),  # 除外
        make_pair(14, mid_delta=0.02, spread_delta=0.05),  # 残る
    ]
    profiler = SpreadProfiler()
    profile = profiler.build(pairs, calendar=calendar_mock, news_window_minutes=30)

    assert "10" not in profile
    assert "14" in profile


def test_empty_pairs_returns_empty():
    profiler = SpreadProfiler()
    profile = profiler.build([])
    assert profile == {}


def test_all_24_hours_present_if_data_exists():
    pairs = [make_pair(h, 0.01, 0.02) for h in range(24)]
    profiler = SpreadProfiler()
    profile = profiler.build(pairs)
    for h in range(24):
        assert str(h) in profile


def test_single_sample_std_is_zero():
    """サンプル 1 件のときは std=0.0"""
    pairs = [make_pair(5, mid_delta=0.03, spread_delta=0.08)]
    profiler = SpreadProfiler()
    profile = profiler.build(pairs)
    assert profile["5"]["mid_offset_std"] == 0.0
    assert profile["5"]["spread_delta_std"] == 0.0
