"""calendar_loader のユニットテスト"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from calibration.calendar_loader import CalendarLoader, NewsEvent


@pytest.fixture
def sample_calendar_dir(tmp_path):
    """テスト用のサンプル ForexFactory CSV を作成する"""
    year_dir = tmp_path / "2024"
    year_dir.mkdir()
    csv_path = year_dir / "2024-01-01.csv"
    rows = [
        "2024-01-05,8:30am,USD,High,Nonfarm Payrolls,200K,185K,150K",
        "2024-01-05,10:00am,USD,Low,ISM Manufacturing PMI,48.5,48.0,47.5",
        "2024-01-08,9:00am,EUR,High,ECB Rate Decision,4.50%,4.50%,4.50%",
    ]
    with open(csv_path, "w") as f:
        f.write("date,time,currency,impact,event,actual,forecast,previous\n")
        f.write("\n".join(rows) + "\n")
    return tmp_path


def test_load_events_returns_high_impact(sample_calendar_dir):
    loader = CalendarLoader(sample_calendar_dir)
    events = loader.load_events(start="2024-01-01", end="2024-01-31", impact="High")
    assert len(events) == 2
    assert all(e.impact == "High" for e in events)


def test_load_events_filters_low_impact(sample_calendar_dir):
    loader = CalendarLoader(sample_calendar_dir)
    events = loader.load_events(start="2024-01-01", end="2024-01-31", impact="High")
    assert all(e.event != "ISM Manufacturing PMI" for e in events)


def test_is_news_period_true_within_window(sample_calendar_dir):
    """指標発表の前後 N 分は True を返す"""
    loader = CalendarLoader(sample_calendar_dir)
    loader.load_events(start="2024-01-01", end="2024-01-31", impact="High")
    # NFP: 2024-01-05 08:30 UTC → window_minutes=30 なら 08:00〜09:00 が対象
    ts_in = datetime(2024, 1, 5, 8, 45, 0, tzinfo=timezone.utc)
    assert loader.is_news_period(ts_in, window_minutes=30) is True


def test_is_news_period_false_outside_window(sample_calendar_dir):
    loader = CalendarLoader(sample_calendar_dir)
    loader.load_events(start="2024-01-01", end="2024-01-31", impact="High")
    ts_out = datetime(2024, 1, 5, 12, 0, 0, tzinfo=timezone.utc)
    assert loader.is_news_period(ts_out, window_minutes=30) is False


def test_load_events_date_filter(sample_calendar_dir):
    """期間外のイベントは含まれない"""
    loader = CalendarLoader(sample_calendar_dir)
    events = loader.load_events(start="2024-01-06", end="2024-01-09", impact="High")
    # NFP(1/5) は範囲外, ECB(1/8) は範囲内
    assert len(events) == 1
    assert events[0].event == "ECB Rate Decision"


def test_is_news_period_empty_events():
    """イベントが 0 件のときは常に False"""
    loader = CalendarLoader(Path("/nonexistent"))
    loader._events = []
    ts = datetime(2024, 1, 5, 8, 30, 0, tzinfo=timezone.utc)
    assert loader.is_news_period(ts) is False
