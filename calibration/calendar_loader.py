"""
ForexFactory カレンダー CSV の読み込みと指標発表期間フィルタリング

ディレクトリ構造:
    {calendar_dir}/{YYYY}/{YYYY-MM-DD}.csv

CSV フォーマット:
    date,time,currency,impact,event,actual,forecast,previous
    2024-01-05,8:30am,USD,High,Nonfarm Payrolls,...
"""
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


@dataclass
class NewsEvent:
    dt: datetime       # UTC
    currency: str
    impact: str
    event: str


class CalendarLoader:
    """
    /Volumes/WD_Black/ForexFactory/calendar/ 配下の週次 CSV を読む。

    注: ForexFactory の時刻は "8:30am" 形式。UTC として扱う。
    実際のズレは window_minutes で吸収する設計。
    """

    def __init__(self, calendar_dir: str | Path):
        self._dir = Path(calendar_dir)
        self._events: list[NewsEvent] = []

    def load_events(
        self,
        start: str,
        end: str,
        impact: str = "High",
    ) -> list[NewsEvent]:
        """
        start〜end の期間（YYYY-MM-DD）で指定 impact レベルのイベントを読み込む。
        返値と同時に内部リスト self._events も上書きする。
        """
        start_date = datetime.strptime(start, "%Y-%m-%d").date()
        end_date = datetime.strptime(end, "%Y-%m-%d").date()

        events: list[NewsEvent] = []
        if not self._dir.exists():
            self._events = events
            return events

        for year_dir in sorted(self._dir.iterdir()):
            if not year_dir.is_dir():
                continue
            for csv_path in sorted(year_dir.glob("*.csv")):
                for row in self._read_csv(csv_path):
                    if row.get("impact") != impact:
                        continue
                    dt = self._parse_datetime(row.get("date", ""), row.get("time", ""))
                    if dt is None:
                        continue
                    if start_date <= dt.date() <= end_date:
                        events.append(NewsEvent(
                            dt=dt,
                            currency=row.get("currency", ""),
                            impact=row.get("impact", ""),
                            event=row.get("event", ""),
                        ))

        self._events = events
        return events

    def is_news_period(self, ts: datetime, window_minutes: int = 30) -> bool:
        """ts が任意のニュースイベントの ±window_minutes 以内なら True"""
        if not self._events:
            return False
        # tzinfo を統一
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        half = timedelta(minutes=window_minutes)
        for ev in self._events:
            if abs(ts - ev.dt) <= half:
                return True
        return False

    # ------------------------------------------------------------------
    # 内部ヘルパー
    # ------------------------------------------------------------------

    @staticmethod
    def _read_csv(path: Path) -> list[dict]:
        with open(path, newline="", encoding="utf-8") as f:
            return list(csv.DictReader(f))

    @staticmethod
    def _parse_datetime(date_str: str, time_str: str) -> datetime | None:
        """'2024-01-05', '8:30am' → UTC datetime"""
        date_str = date_str.strip()
        time_str = time_str.strip()
        if not date_str or not time_str:
            return None
        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %I:%M%p")
            return dt.replace(tzinfo=timezone.utc)
        except ValueError:
            return None
