"""Tool catalogue the model may call. Numbers come from these functions, not the model."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Any, Callable

from sqlalchemy.orm import Session

from app.agent.resolve import resolve_query
from app.analytics import queries
from app.analytics.rca import wells_needing_rca
from app.capabilities import analytics_ext, coverage, equipment, ops, regulator
from app.compliance.assess import assess_containment_breaches, assess_well_compliance
from app.db import models
from app.feedback.service import apply_feedback, preview_feedback, record_assertion

CORRECTION_FIELDS = {"wellhead_temp_c", "ambient_temp_c", "spill_est_volume_bbl"}
NOTE_KINDS = {"shared_note", "pump_replaced", "equipment_replaced"}


@dataclass
class ToolContext:
    db: Session
    text: str
    user_id: str
    conversation_id: uuid.UUID
    as_of: datetime


def _str(description: str) -> dict[str, str]:
    return {"type": "string", "description": description}


def _int(description: str) -> dict[str, str]:
    return {"type": "integer", "description": description}


def _fn(name: str, description: str, properties: dict, required: list[str] | None = None) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": properties,
                "required": required or [],
                "additionalProperties": False,
            },
        },
    }


def _date(value: str) -> date:
    return date.fromisoformat(str(value)[:10])


def _dt(value: str) -> datetime:
    raw = str(value).replace("Z", "+00:00")
    if len(raw) == 10:
        raw = f"{raw}T00:00:00+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _resolve(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    resolved = resolve_query(ctx.db, ctx.text, as_of=ctx.as_of, user_id=ctx.user_id)
    return {
        "wells": resolved.wells,
        "area_name": resolved.area_name,
        "area_id": resolved.area_id,
        "team_id": resolved.team_id,
        "my_area_only": resolved.my_area_only,
        "year": resolved.year,
        "start": resolved.start.isoformat() if resolved.start else None,
        "end": resolved.end.isoformat() if resolved.end else None,
        "visual_hint": resolved.visual_hint,
        "as_of": ctx.as_of.date().isoformat(),
    }


def _list_areas(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    areas = ctx.db.query(models.Area).order_by(models.Area.name).all()
    return {
        "areas": [
            {"area_id": a.area_id, "name": a.name, "team_id": a.team_id} for a in areas
        ]
    }


def _well(ctx: ToolContext, asset_id: str, **_: Any) -> dict[str, Any]:
    return queries.get_well_summary(ctx.db, asset_id.strip().upper(), ctx.as_of)


def _non_producing(ctx: ToolContext, area_name: str, **_: Any) -> dict[str, Any]:
    return queries.non_producing_in_area(ctx.db, area_name, ctx.as_of)


def _downtime(ctx: ToolContext, area_name: str, start: str, end: str, limit: int = 10, **_: Any) -> dict[str, Any]:
    return queries.analyze_downtime_by_area(
        ctx.db,
        area_name=area_name,
        start=_date(start),
        end_inclusive=_date(end),
        limit=int(limit),
    )


def _temps(ctx: ToolContext, asset_id: str, start: str, end: str, **_: Any) -> dict[str, Any]:
    return queries.temperature_series(ctx.db, asset_id.strip().upper(), _date(start), _date(end))


def _spills(ctx: ToolContext, asset_id: str, start: str | None = None, end: str | None = None, **_: Any) -> dict[str, Any]:
    return queries.spill_history(
        ctx.db,
        asset_id.strip().upper(),
        _date(start) if start else None,
        _date(end) if end else None,
    )


def _spill_map(ctx: ToolContext, area_name: str, start: str, end: str, **_: Any) -> dict[str, Any]:
    return queries.spill_map(ctx.db, area_name, _date(start), _date(end))


def _heatmap(ctx: ToolContext, year: int, **_: Any) -> dict[str, Any]:
    return queries.spill_heatmap(ctx.db, int(year))


def _repairs(ctx: ToolContext, asset_ids: list[str], start: str, end: str, **_: Any) -> dict[str, Any]:
    ids = [str(a).strip().upper() for a in asset_ids]
    return queries.repair_costs(ctx.db, ids, _date(start), _date(end))


def _year_downtime(ctx: ToolContext, asset_id: str, year: int, **_: Any) -> dict[str, Any]:
    return queries.downtime_for_asset_year(ctx.db, asset_id.strip().upper(), int(year))


def _compliance(ctx: ToolContext, asset_id: str, lookback_days: int = 365, **_: Any) -> dict[str, Any]:
    return assess_well_compliance(ctx.db, asset_id.strip().upper(), ctx.as_of, int(lookback_days))


def _containment(ctx: ToolContext, area_name: str, start: str, end: str, **_: Any) -> dict[str, Any]:
    return assess_containment_breaches(
        ctx.db,
        area_name=area_name,
        start=_dt(start),
        end=_dt(end),
    )


def _rca(ctx: ToolContext, area_name: str, equipment_kind: str, **_: Any) -> dict[str, Any]:
    return wells_needing_rca(
        ctx.db,
        area_name=area_name,
        equipment_kind=equipment_kind,
        as_of=ctx.as_of,
    )


def _hotter(ctx: ToolContext, lookback_days: int = 90, **_: Any) -> dict[str, Any]:
    return analytics_ext.hotter_regions(ctx.db, as_of=ctx.as_of, lookback_days=int(lookback_days))


def _waits(ctx: ToolContext, year: int, **_: Any) -> dict[str, Any]:
    return analytics_ext.wait_reasons_by_area(ctx.db, year=int(year), as_of=ctx.as_of)


def _risk(ctx: ToolContext, lookback_days: int = 30, top_n: int = 10, **_: Any) -> dict[str, Any]:
    return analytics_ext.repair_risk_rank(
        ctx.db,
        as_of=ctx.as_of,
        lookback_days=int(lookback_days),
        top_n=int(top_n),
    )


def _gas(ctx: ToolContext, since: str, **_: Any) -> dict[str, Any]:
    return ops.gas_odor_compliance(ctx.db, since=_dt(since), as_of=ctx.as_of)


def _bypasses(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    return ops.temporary_bypasses(ctx.db, as_of=ctx.as_of)


def _status(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    return ops.status_disagreements(ctx.db, as_of=ctx.as_of)


def _letter(ctx: ToolContext, **_: Any) -> dict[str, Any]:
    return regulator.letter_spill_compliance(ctx.db, as_of=ctx.as_of)


def _pumps(ctx: ToolContext, area_names: list[str] | None = None, **_: Any) -> dict[str, Any]:
    return equipment.recalled_pumps_still_in_ground(
        ctx.db,
        as_of=ctx.as_of,
        area_names=area_names or None,
    )


def _missing(ctx: ToolContext, measurement: str, year: int | None = None, **_: Any) -> dict[str, Any]:
    if measurement == "reservoir_pressure":
        return coverage.answer_missing_pressure(ctx.db, ctx.as_of)
    if measurement == "oil_volume":
        return coverage.answer_missing_production_volume(ctx.db, year, ctx.as_of)
    return {"error": "unknown_measurement", "measurement": measurement, "recoverable": True}


def _note(
    ctx: ToolContext,
    text: str,
    asset_id: str | None = None,
    kind: str = "shared_note",
    confirmation_state: str = "active",
    **_: Any,
) -> dict[str, Any]:
    note_kind = kind if kind in NOTE_KINDS else "shared_note"
    state = confirmation_state if confirmation_state in {"active", "unconfirmed"} else "active"
    row = record_assertion(
        ctx.db,
        kind=note_kind,
        author_user_id=ctx.user_id,
        text=text,
        asset_id=asset_id.strip().upper() if asset_id else None,
        confirmation_state=state,
    )
    return {"assertion_id": str(row.id), "kind": row.kind, "state": row.confirmation_state}


def _correct(
    ctx: ToolContext,
    inspection_id: str,
    field: str,
    new_value: str,
    reason: str,
    unit: str | None = None,
    **_: Any,
) -> dict[str, Any]:
    if field not in CORRECTION_FIELDS:
        return {
            "error": "field_not_correctable",
            "allowed": sorted(CORRECTION_FIELDS),
            "recoverable": True,
        }
    preview = preview_feedback(
        ctx.db,
        kind="correction",
        author_user_id=ctx.user_id,
        target_id=inspection_id,
        field=field,
        new_value=str(new_value),
        reason=reason,
        unit=unit,
    )
    applied = apply_feedback(ctx.db, preview=preview, author_user_id=ctx.user_id)
    return {**preview, **applied}


HANDLERS: dict[str, Callable[..., dict[str, Any]]] = {
    "resolve_question": _resolve,
    "list_areas": _list_areas,
    "get_well_summary": _well,
    "non_producing_in_area": _non_producing,
    "analyze_downtime": _downtime,
    "temperature_series": _temps,
    "spill_history": _spills,
    "spill_map": _spill_map,
    "spill_heatmap": _heatmap,
    "repair_costs": _repairs,
    "downtime_for_year": _year_downtime,
    "assess_well_compliance": _compliance,
    "assess_containment": _containment,
    "wells_needing_rca": _rca,
    "hotter_regions": _hotter,
    "wait_reasons_by_area": _waits,
    "repair_risk_rank": _risk,
    "gas_odor_compliance": _gas,
    "temporary_bypasses": _bypasses,
    "status_disagreements": _status,
    "letter_spill_compliance": _letter,
    "recalled_pumps": _pumps,
    "report_missing_measurement": _missing,
    "record_shared_note": _note,
    "apply_inspection_correction": _correct,
}

TOOL_SPECS: list[dict] = [
    _fn("resolve_question", "Resolve wells, area, team, and dates mentioned in the user question. Call this first.", {}),
    _fn("list_areas", "List areas loaded in this dataset.", {}),
    _fn("get_well_summary", "Latest effective status, temperatures, notes, and conflicts for one well.", {"asset_id": _str("WELL-####")}, ["asset_id"]),
    _fn("non_producing_in_area", "Wells in an area that are not producing at the analysis clock.", {"area_name": _str("Area name")}, ["area_name"]),
    _fn(
        "analyze_downtime",
        "Downtime days (7 × non-producing inspections) for wells in an area between two dates.",
        {
            "area_name": _str("Area name"),
            "start": _str("YYYY-MM-DD inclusive"),
            "end": _str("YYYY-MM-DD inclusive"),
            "limit": _int("How many wells to return, default 10"),
        },
        ["area_name", "start", "end"],
    ),
    _fn(
        "temperature_series",
        "Wellhead and ambient temperature points for a line chart.",
        {"asset_id": _str("WELL-####"), "start": _str("YYYY-MM-DD"), "end": _str("YYYY-MM-DD")},
        ["asset_id", "start", "end"],
    ),
    _fn(
        "spill_history",
        "Spill events for one well. Volumes are effective (corrections applied).",
        {"asset_id": _str("WELL-####"), "start": _str("YYYY-MM-DD optional"), "end": _str("YYYY-MM-DD optional")},
        ["asset_id"],
    ),
    _fn(
        "spill_map",
        "Spill pins in an area for a map.",
        {"area_name": _str("Area name"), "start": _str("YYYY-MM-DD"), "end": _str("YYYY-MM-DD")},
        ["area_name", "start", "end"],
    ),
    _fn("spill_heatmap", "Spill counts by area and month for one calendar year.", {"year": _int("Calendar year")}, ["year"]),
    _fn(
        "repair_costs",
        "Maintenance cost rows for specific wells in a date window.",
        {
            "asset_ids": {"type": "array", "items": {"type": "string"}, "description": "WELL-#### ids"},
            "start": _str("YYYY-MM-DD"),
            "end": _str("YYYY-MM-DD"),
        },
        ["asset_ids", "start", "end"],
    ),
    _fn("downtime_for_year", "Downtime days for one well in a calendar year.", {"asset_id": _str("WELL-####"), "year": _int("Year")}, ["asset_id", "year"]),
    _fn("assess_well_compliance", "Compliance obligations for one well.", {"asset_id": _str("WELL-####"), "lookback_days": _int("Days, default 365")}, ["asset_id"]),
    _fn(
        "assess_containment",
        "Containment-hour breaches in an area.",
        {"area_name": _str("Area name"), "start": _str("YYYY-MM-DD"), "end": _str("YYYY-MM-DD")},
        ["area_name", "start", "end"],
    ),
    _fn(
        "wells_needing_rca",
        "Wells whose corrective maintenance count meets the root-cause threshold.",
        {"area_name": _str("Area name"), "equipment_kind": _str("pump, wellhead, or other equipment kind")},
        ["area_name", "equipment_kind"],
    ),
    _fn("hotter_regions", "Mean and median ΔT by area.", {"lookback_days": _int("Default 90")}, []),
    _fn("wait_reasons_by_area", "Why repairs waited, grouped by area, for a year.", {"year": _int("Year")}, ["year"]),
    _fn("repair_risk_rank", "Wells with anomaly notes and no later corrective repair.", {"lookback_days": _int("Default 30"), "top_n": _int("Default 10")}, []),
    _fn("gas_odor_compliance", "Gas-odor notes versus the response deadline.", {"since": _str("YYYY-MM-DD")}, ["since"]),
    _fn("temporary_bypasses", "Open temporary bypasses versus MOC approval and expiry.", {}),
    _fn("status_disagreements", "Inspection status versus newer shut-in or restart notes.", {}),
    _fn("letter_spill_compliance", "Regulator-letter spills and whether soil samples went to the lab.", {}),
    _fn(
        "recalled_pumps",
        "Pumps whose latest installed lot is on the supplier recall list.",
        {"area_names": {"type": "array", "items": {"type": "string"}, "description": "Optional area filter"}},
        [],
    ),
    _fn(
        "report_missing_measurement",
        "Call this and stop when the question needs reservoir pressure or oil volume. Those measurements are not in the dataset.",
        {
            "measurement": {"type": "string", "enum": ["reservoir_pressure", "oil_volume"]},
            "year": _int("Optional year for an oil-volume question"),
        },
        ["measurement"],
    ),
    _fn(
        "record_shared_note",
        "Save a shared note or equipment replacement. Author is the signed-in user. Use confirmation_state=unconfirmed for second-hand claims.",
        {
            "text": _str("What the operator said"),
            "asset_id": _str("WELL-#### if the note is about one well"),
            "kind": {"type": "string", "enum": sorted(NOTE_KINDS)},
            "confirmation_state": {"type": "string", "enum": ["active", "unconfirmed"]},
        },
        ["text"],
    ),
    _fn(
        "apply_inspection_correction",
        "Formally correct one inspection field. Original value is read on the server. Raw data is kept.",
        {
            "inspection_id": _str("Inspection id from a tool result"),
            "field": {"type": "string", "enum": sorted(CORRECTION_FIELDS)},
            "new_value": _str("Replacement value"),
            "reason": _str("Why the reading is being corrected"),
            "unit": _str("Optional unit, such as C or bbl"),
        },
        ["inspection_id", "field", "new_value", "reason"],
    ),
    _fn(
        "submit_answer",
        "Finish the turn. Summary numbers must appear in tool results. Rows and charts are copied from result_handle, not from this call.",
        {
            "summary": _str("Operator-facing answer. Cite only figures the tools returned."),
            "kind": {
                "type": "string",
                "enum": [
                    "short_answer",
                    "status_card",
                    "table",
                    "bar_chart",
                    "line_chart",
                    "map",
                    "heatmap",
                    "stacked_bar",
                ],
            },
            "result_handle": _str("Handle from a tool result, such as r1. Required for any visual that shows rows."),
            "title": _str("Chart or table title"),
            "fields": {"type": "array", "items": {"type": "string"}, "description": "Column keys present on the tool rows"},
            "warnings": {"type": "array", "items": {"type": "string"}},
        },
        ["summary", "kind"],
    ),
]


def openai_tools() -> list[dict]:
    return TOOL_SPECS


def execute_tool(name: str, arguments: dict[str, Any], ctx: ToolContext) -> dict[str, Any]:
    handler = HANDLERS.get(name)
    if handler is None:
        return {"error": "unknown_tool", "name": name, "recoverable": True}
    try:
        result = handler(ctx, **(arguments or {}))
    except TypeError as exc:
        ctx.db.rollback()
        return {"error": "bad_arguments", "message": str(exc)[:400], "recoverable": True}
    except Exception as exc:  # noqa: BLE001 — tool errors go back to the model, not a fake answer
        ctx.db.rollback()
        return {"error": type(exc).__name__, "message": str(exc)[:400], "recoverable": True}
    if not isinstance(result, dict):
        return {"value": result}
    return result
