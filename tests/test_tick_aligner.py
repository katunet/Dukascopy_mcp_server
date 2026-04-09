"""tick_aligner のユニットテスト"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from calibration.tick_aligner import TickAligner, AlignedPair


def mt5_tick(time_msc_iso: str, bid: float, ask: float) -> dict:
    return {"time_msc": time_msc_iso, "bid": bid, "ask": ask}


def duku_tick(timestamp: str, bid: float, ask: float) -> dict:
    return {"timestamp": timestamp, "bid": bid, "ask": ask}


def test_exact_match_returns_pair():
    mt5 = [mt5_tick("2024-04-09T10:00:00.100000+00:00", 2350.10, 2350.40)]
    duku = [duku_tick("2024-04-09 10:00:00.100", 2350.05, 2350.35)]
    pairs = TickAligner.align(mt5, duku, tolerance_ms=1000)
    assert len(pairs) == 1
    assert pairs[0].gap_ms == 0


def test_within_tolerance_returns_pair():
    mt5 = [mt5_tick("2024-04-09T10:00:00.100000+00:00", 2350.10, 2350.40)]
    duku = [duku_tick("2024-04-09 10:00:00.600", 2350.05, 2350.35)]  # +500ms
    pairs = TickAligner.align(mt5, duku, tolerance_ms=1000)
    assert len(pairs) == 1
    assert pairs[0].gap_ms == 500


def test_outside_tolerance_returns_empty():
    mt5 = [mt5_tick("2024-04-09T10:00:00.100000+00:00", 2350.10, 2350.40)]
    duku = [duku_tick("2024-04-09 10:00:02.500", 2350.05, 2350.35)]  # +2400ms
    pairs = TickAligner.align(mt5, duku, tolerance_ms=1000)
    assert len(pairs) == 0


def test_mid_delta_calculation():
    """mid_delta = MT5.mid - Duku.mid"""
    # MT5 mid = (2350.10 + 2350.40) / 2 = 2350.25
    # Duku mid = (2350.05 + 2350.35) / 2 = 2350.20
    # mid_delta = 0.05
    mt5 = [mt5_tick("2024-04-09T10:00:00.000000+00:00", 2350.10, 2350.40)]
    duku = [duku_tick("2024-04-09 10:00:00.000", 2350.05, 2350.35)]
    pairs = TickAligner.align(mt5, duku)
    assert abs(pairs[0].mid_delta - 0.05) < 1e-9


def test_spread_delta_calculation():
    """spread_delta = MT5.spread - Duku.spread"""
    # MT5 spread = 0.30, Duku spread = 0.30 → delta = 0.0
    mt5 = [mt5_tick("2024-04-09T10:00:00.000000+00:00", 2350.10, 2350.40)]
    duku = [duku_tick("2024-04-09 10:00:00.000", 2350.05, 2350.35)]
    pairs = TickAligner.align(mt5, duku)
    assert abs(pairs[0].spread_delta) < 1e-9


def test_multiple_duku_nearest_neighbor():
    """MT5 ティックが複数の Duku 候補の中で最近傍を選ぶ"""
    mt5 = [mt5_tick("2024-04-09T10:00:00.500000+00:00", 2350.10, 2350.40)]
    duku = [
        duku_tick("2024-04-09 10:00:00.000", 2350.05, 2350.35),  # gap=500ms
        duku_tick("2024-04-09 10:00:00.400", 2350.06, 2350.36),  # gap=100ms ← 最近傍
        duku_tick("2024-04-09 10:00:01.000", 2350.07, 2350.37),  # gap=500ms
    ]
    pairs = TickAligner.align(mt5, duku)
    assert len(pairs) == 1
    assert pairs[0].gap_ms == 100


def test_hour_utc_set_correctly():
    """hour_utc フィールドが MT5 タイムスタンプの UTC 時を反映する"""
    mt5 = [mt5_tick("2024-04-09T14:30:00.000000+00:00", 2350.0, 2350.3)]
    duku = [duku_tick("2024-04-09 14:30:00.000", 2350.0, 2350.3)]
    pairs = TickAligner.align(mt5, duku)
    assert pairs[0].hour_utc == 14


def test_empty_inputs_return_empty():
    assert TickAligner.align([], []) == []
    assert TickAligner.align([mt5_tick("2024-04-09T10:00:00.000000+00:00", 1.0, 1.1)], []) == []
