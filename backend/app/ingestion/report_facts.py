from __future__ import annotations

import re
from decimal import Decimal
from typing import Any


_CONTAINED = re.compile(
    r"contained\s+(?:about\s+)?(\d+(?:\.\d+)?)\s+hours?",
    re.IGNORECASE,
)
_REPORTED = re.compile(
    r"(?:reported|filed)\s+(\d+)\s+hours?\s+after",
    re.IGNORECASE,
)
_PARTS = re.compile(
    r"\*\*Parts installed:\*\*\s*(.+?)(?:\n|$)",
    re.IGNORECASE,
)
_LOT = re.compile(r"(LOT-[\w-]+)", re.IGNORECASE)
_SERIAL = re.compile(r"(?:serial|SN)[\s:-]*(SN-[\w-]+|[\w-]{4,})", re.IGNORECASE)
_H2S = re.compile(
    r"(?:highest(?:\s+reading)?|H2S(?:\s+reading)?)\s*(?:of\s*)?(\d+(?:\.\d+)?)\s*ppm",
    re.IGNORECASE,
)
_SOIL_LAB = "Soil samples sent to the lab"


def extract_facts_from_report(
    body: str,
    *,
    asset_id: str,
    maintenance_id: str,
    inspection_id: str | None,
    report_path: str,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for match in _CONTAINED.finditer(body):
        hours = Decimal(match.group(1))
        approx = "about" in match.group(0).lower()
        facts.append(
            {
                "fact_type": "containment_hours",
                "value_numeric": hours,
                "value_text": match.group(0),
                "unit": "hours",
                "approximate": approx,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": match.group(0),
                "extraction_version": "v1",
                "validation_status": "extracted",
            }
        )
    for match in _REPORTED.finditer(body):
        hours = Decimal(match.group(1))
        facts.append(
            {
                "fact_type": "reported_hours",
                "value_numeric": hours,
                "value_text": match.group(0),
                "unit": "hours",
                "approximate": False,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": match.group(0),
                "extraction_version": "v1",
                "validation_status": "extracted",
            }
        )
    if "Action required" in body or "root-cause" in body.lower() or "root cause analysis" in body.lower():
        facts.append(
            {
                "fact_type": "rca_action_required",
                "value_numeric": None,
                "value_text": "Action required",
                "unit": None,
                "approximate": False,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": "RCA/action language present in report",
                "extraction_version": "v1",
                "validation_status": "extracted",
            }
        )
    parts_m = _PARTS.search(body)
    if parts_m:
        line = parts_m.group(1).strip()
        lot_m = _LOT.search(line)
        serial_m = _SERIAL.search(line)
        facts.append(
            {
                "fact_type": "parts_installed",
                "value_numeric": None,
                "value_text": line,
                "unit": None,
                "approximate": False,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": line,
                "extraction_version": "v2",
                "validation_status": "extracted",
            }
        )
        if lot_m:
            facts.append(
                {
                    "fact_type": "pump_lot",
                    "value_numeric": None,
                    "value_text": lot_m.group(1).upper(),
                    "unit": None,
                    "approximate": False,
                    "asset_id": asset_id,
                    "inspection_id": inspection_id,
                    "maintenance_id": maintenance_id,
                    "report_path": report_path,
                    "supporting_text": line,
                    "extraction_version": "v2",
                    "validation_status": "extracted",
                }
            )
        if serial_m:
            facts.append(
                {
                    "fact_type": "pump_serial",
                    "value_numeric": None,
                    "value_text": serial_m.group(1),
                    "unit": None,
                    "approximate": False,
                    "asset_id": asset_id,
                    "inspection_id": inspection_id,
                    "maintenance_id": maintenance_id,
                    "report_path": report_path,
                    "supporting_text": line,
                    "extraction_version": "v2",
                    "validation_status": "extracted",
                }
            )
    for match in _H2S.finditer(body):
        facts.append(
            {
                "fact_type": "h2s_ppm",
                "value_numeric": Decimal(match.group(1)),
                "value_text": match.group(0),
                "unit": "ppm",
                "approximate": False,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": match.group(0),
                "extraction_version": "v2",
                "validation_status": "extracted",
            }
        )
    if _SOIL_LAB in body:
        facts.append(
            {
                "fact_type": "soil_samples_lab",
                "value_numeric": None,
                "value_text": _SOIL_LAB,
                "unit": None,
                "approximate": False,
                "asset_id": asset_id,
                "inspection_id": inspection_id,
                "maintenance_id": maintenance_id,
                "report_path": report_path,
                "supporting_text": _SOIL_LAB,
                "extraction_version": "v2",
                "validation_status": "extracted",
            }
        )
    return facts
