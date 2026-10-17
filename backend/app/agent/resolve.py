"""Natural-language entity resolution — areas, wells, windows, visuals from DB + text."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any

from sqlalchemy.orm import Session

from app.db import models


WELL_RE = re.compile(r"\b(WELL-\d{4})\b", re.I)
YEAR_RE = re.compile(r"\b(20\d{2})\b")
MONTH_NAME = {
    "jan": 1,
    "january": 1,
    "feb": 2,
    "february": 2,
    "mar": 3,
    "march": 3,
    "apr": 4,
    "april": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "august": 8,
    "sep": 9,
    "sept": 9,
    "september": 9,
    "oct": 10,
    "october": 10,
    "nov": 11,
    "november": 11,
    "dec": 12,
    "december": 12,
}


@dataclass
class ResolvedQuery:
    text: str
    wells: list[str] = field(default_factory=list)
    area_name: str | None = None
    area_id: str | None = None
    team_id: str | None = None
    my_area_only: bool = False
    year: int | None = None
    start: date | None = None
    end: date | None = None
    visual_hint: str | None = None
    since: datetime | None = None


def _normalize(s: str) -> str:
    return re.sub(r"\s+", " ", s.strip().lower())


def resolve_areas(db: Session) -> list[models.Area]:
    return list(db.query(models.Area).all())


def match_area(db: Session, text: str) -> models.Area | None:
    ql = _normalize(text)
    areas = resolve_areas(db)
    # Longest name first to avoid partial clashes
    for area in sorted(areas, key=lambda a: len(a.name), reverse=True):
        if _normalize(area.name) in ql:
            return area
    # Loose: "northeast block 8" style without requiring title case
    m = re.search(
        r"\b((?:north|south|east|west|northeast|northwest|southeast|southwest)\w*)\s+block\s+(\d+)\b",
        ql,
    )
    if m:
        needle = f"{m.group(1)} block {m.group(2)}"
        for area in areas:
            if _normalize(area.name) == needle or needle in _normalize(area.name):
                return area
    return None


def parse_relative_window(text: str, as_of: datetime) -> tuple[date | None, date | None]:
    ql = text.lower()
    end = as_of.date()
    if "last 90 days" in ql or "past 90 days" in ql:
        return end - timedelta(days=90), end
    if "last 4 months" in ql or "past 4 months" in ql:
        # approximate calendar: same day 4 months back
        month = end.month - 4
        year = end.year
        while month <= 0:
            month += 12
            year -= 1
        day = min(end.day, 28)
        return date(year, month, day), end
    if "last 4 years" in ql or "past 4 years" in ql:
        return date(end.year - 4, end.month, end.day), end
    if "last 12 months" in ql or "past 12 months" in ql:
        return date(end.year - 1, end.month, end.day), end
    if "last month" in ql or "over the last month" in ql:
        return end - timedelta(days=30), end
    if "last 13 weeks" in ql:
        return end - timedelta(days=13 * 7), end
    return None, None


def parse_since(text: str, as_of: datetime) -> datetime | None:
    ql = text.lower()
    # "since 1 Nov 2026" / "since November 2026"
    m = re.search(
        r"since\s+(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})",
        text,
        re.I,
    )
    if m:
        day = int(m.group(1))
        mon = MONTH_NAME.get(m.group(2).lower())
        year = int(m.group(3))
        if mon:
            return datetime(year, mon, day, tzinfo=timezone.utc)
    m2 = re.search(r"since\s+([A-Za-z]+)\s+(20\d{2})", text, re.I)
    if m2:
        mon = MONTH_NAME.get(m2.group(1).lower())
        year = int(m2.group(2))
        if mon:
            return datetime(year, mon, 1, tzinfo=timezone.utc)
    m3 = re.search(r"\bin\s+(20\d{2})\b", ql)
    if m3 and ("produced" in ql or "jobs started" in ql or "started in" in ql):
        y = int(m3.group(1))
        return datetime(y, 1, 1, tzinfo=timezone.utc)
    return None


def visual_hint(text: str) -> str | None:
    ql = text.lower()
    if "heatmap" in ql:
        return "heatmap"
    if "stacked bar" in ql or "stacked" in ql and "bar" in ql:
        return "stacked_bar"
    if "bar chart" in ql or "show a bar" in ql:
        return "bar_chart"
    if "line chart" in ql:
        return "line_chart"
    if "status card" in ql:
        return "status_card"
    if re.search(r"\bmap\b", ql) and "heatmap" not in ql:
        return "map"
    if "table" in ql or "list every" in ql or "list them" in ql:
        return "table"
    return None


def resolve_query(
    db: Session,
    text: str,
    *,
    as_of: datetime,
    user_id: str | None = None,
) -> ResolvedQuery:
    wells = [m.group(1).upper() for m in WELL_RE.finditer(text)]
    # de-dupe preserving order
    seen: set[str] = set()
    uniq_wells: list[str] = []
    for w in wells:
        if w not in seen:
            seen.add(w)
            uniq_wells.append(w)

    area = match_area(db, text)
    start, end = parse_relative_window(text, as_of)
    since = parse_since(text, as_of)
    years = [int(y) for y in YEAR_RE.findall(text)]
    year = years[-1] if years else None

    my_area = "my area" in text.lower() or "in my area" in text.lower()
    team_id = None
    if user_id:
        user = db.get(models.User, user_id)
        if user:
            team_id = user.team_id

    if my_area and not area and team_id:
        # Prefer an area owned by the user's team
        cand = (
            db.query(models.Area)
            .filter(models.Area.team_id == team_id)
            .order_by(models.Area.name)
            .first()
        )
        if cand:
            area = cand

    return ResolvedQuery(
        text=text,
        wells=uniq_wells,
        area_name=area.name if area else None,
        area_id=area.area_id if area else None,
        team_id=team_id,
        my_area_only=my_area,
        year=year,
        start=start,
        end=end or as_of.date(),
        visual_hint=visual_hint(text),
        since=since,
    )


def areas_for_team(db: Session, team_id: str) -> list[str]:
    return [a.name for a in db.query(models.Area).filter(models.Area.team_id == team_id).all()]


def table_answer(
    *,
    kind: str,
    summary: str,
    rows: list[dict[str, Any]],
    fields: list[str],
    title: str,
    evidence: list[dict[str, Any]] | None = None,
    citations: list[dict[str, Any]] | None = None,
    conflicts: list[dict[str, Any]] | None = None,
    coverage: dict[str, Any] | None = None,
    discussed_asset_ids: list[str] | None = None,
    reference_label: str | None = None,
    scope: dict[str, Any] | None = None,
    data: dict[str, Any] | None = None,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "kind": kind,
        "summary": summary,
        "rows": rows,
        "data": data,
        "visuals": [{"kind": kind if kind != "short_answer" else "table", "title": title, "dataset_ref": "rows", "fields": fields}]
        if kind != "short_answer" and rows is not None
        else ([] if kind == "short_answer" else [{"kind": kind, "title": title, "dataset_ref": "rows", "fields": fields}]),
        "evidence": evidence or [],
        "citations": citations or [],
        "conflicts": conflicts or [],
        "coverage": coverage or {},
        "discussed_asset_ids": discussed_asset_ids
        or [r.get("asset_id") for r in (rows or []) if r.get("asset_id")],
        "reference_label": reference_label,
        "scope": scope or {},
        "warnings": warnings or [],
    }
