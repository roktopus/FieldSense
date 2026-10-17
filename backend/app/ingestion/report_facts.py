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
    return facts
