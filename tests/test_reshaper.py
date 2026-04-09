"""reshaper のユニットテスト"""
import csv
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from calibration.model import CalibrationModel
from calibration.reshaper import Reshaper


def make_model(mid_offset_mean: float, spread_delta_mean: float) -> CalibrationModel:
    """hour=10 のみプロファイルを持つ最小モデル"""
    return CalibrationModel(
        broker="TestBroker",
        symbol="XAUUSD",
        mt5_data_range="test",
        total_pairs=10,
        hourly_profiles={
            "10": {
                "mid_offset_mean": mid_offset_mean,
                "mid_offset_std": 0.0,
                "spread_delta_mean": spread_delta_mean,
                "spread_delta_std": 0.0,
                "sample_count": 10,
            }
        },
    )


def test_reshape_adjusts_mid_and_spread():
    """
    Dukascopy: bid=2350.00, ask=2350.30 → duku_spread=0.30, duku_mid=2350.15
    Profile hour=10: mid_offset_mean=0.05, spread_delta_mean=0.15
    reshaped_spread = 0.30 + 0.15 = 0.45
    reshaped_mid    = 2350.15 + 0.05 = 2350.20
    reshaped_bid    = 2350.20 - 0.225 = 2349.975
    reshaped_ask    = 2350.20 + 0.225 = 2350.425
    """
    model = make_model(mid_offset_mean=0.05, spread_delta_mean=0.15)
    tick = {
        "timestamp": "2024-04-09 10:30:00.000",
        "bid": 2350.00, "ask": 2350.30,
        "bid_volume": 0.0, "ask_volume": 0.0,
    }

    result = Reshaper.reshape_tick(tick, model)

    assert result is not None
    assert abs(result["bid"] - 2349.975) < 1e-4
    assert abs(result["ask"] - 2350.425) < 1e-4
    assert result["timestamp"] == tick["timestamp"]


def test_reshape_no_profile_returns_none():
    """対応するプロファイルがない時間帯は None を返す"""
    model = make_model(mid_offset_mean=0.05, spread_delta_mean=0.15)
    tick = {
        "timestamp": "2024-04-09 03:00:00.000",
        "bid": 2350.00, "ask": 2350.30,
        "bid_volume": 0.0, "ask_volume": 0.0,
    }
    result = Reshaper.reshape_tick(tick, model)
    assert result is None


def test_reshape_ticks_skips_none(tmp_path):
    """reshape_ticks はプロファイルなし時間帯のティックをスキップし CSV を出力する"""
    model = make_model(mid_offset_mean=0.05, spread_delta_mean=0.15)
    ticks = [
        {"timestamp": "2024-04-09 10:00:00.000", "bid": 2350.00, "ask": 2350.30,
         "bid_volume": 0.0, "ask_volume": 0.0},
        {"timestamp": "2024-04-09 03:00:00.000", "bid": 2350.00, "ask": 2350.30,
         "bid_volume": 0.0, "ask_volume": 0.0},
    ]
    out_path = tmp_path / "out.csv"
    count = Reshaper.reshape_ticks(ticks, model, out_path)
    assert count == 1

    rows = list(csv.DictReader(open(out_path)))
    assert len(rows) == 1
    assert rows[0]["timestamp"] == "2024-04-09 10:00:00.000"


def test_reshape_zero_spread_delta():
    """spread_delta_mean=0 のとき spread はそのまま、mid_offset のみ適用"""
    model = make_model(mid_offset_mean=0.10, spread_delta_mean=0.0)
    tick = {
        "timestamp": "2024-04-09 10:00:00.000",
        "bid": 2350.00, "ask": 2350.40,  # spread=0.40, mid=2350.20
        "bid_volume": 1.0, "ask_volume": 1.0,
    }
    result = Reshaper.reshape_tick(tick, model)
    # reshaped_mid = 2350.20 + 0.10 = 2350.30
    # reshaped_spread = 0.40
    # bid = 2350.30 - 0.20 = 2350.10
    # ask = 2350.30 + 0.20 = 2350.50
    assert abs(result["bid"] - 2350.10) < 1e-4
    assert abs(result["ask"] - 2350.50) < 1e-4


def test_reshape_ticks_all_written(tmp_path):
    """全ティックがプロファイル対象時間帯なら全件書き込まれる"""
    model = make_model(mid_offset_mean=0.0, spread_delta_mean=0.0)
    ticks = [
        {"timestamp": f"2024-04-09 10:{i:02d}:00.000", "bid": 2350.0, "ask": 2350.3,
         "bid_volume": 0.0, "ask_volume": 0.0}
        for i in range(5)
    ]
    out_path = tmp_path / "out.csv"
    count = Reshaper.reshape_ticks(ticks, model, out_path)
    assert count == 5
