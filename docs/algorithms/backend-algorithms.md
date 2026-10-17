# Backend Algorithms — How FieldSense Decides

This is the story of an answer: from a plain-English question to numbers you can audit. No magic WELL-IDs. No memorized barrel totals. The same machinery that passes the sample brief has to survive a sealed 600-well field with a new “today.”

## 1. Time is a first-class input

Every run carries an analysis clock (`as_of`). For the sample profile that is **16 Oct 2026**; for the final test profile it is **15 Jan 2027**. Relative windows (“last 90 days”, “last 4 months”, “in 2026”) are computed from that clock — never from the wall clock on the laptop.

Inclusive calendar ends become exclusive next-day midnights when we query. That sounds pedantic until a spill on “16 Oct” disappears because someone used `< end` with the wrong timezone.

```
question + X-Analysis-Clock  →  parse_as_of()  →  capability tools
```

## 2. Effective readings beat raw JSONL

Inspections lie. Crews correct them. The **effective inspection** layer is the spine of production and spill logic:

1. Start with the raw `wellhead_temp_c` / `spill_est_volume_bbl`.
2. Apply active `Correction` rows (chat feedback **and** imported `data_correction` notes).
3. Apply formal `correction` notes that exclude false-positive spills (“not crude”, rainwater, shadows).
4. Classify production: ΔT = wellhead − ambient vs well-type threshold.

| Well type | Threshold (producing if ΔT ≥) |
|---|---|
| T200 | 15 °C |
| T350 | 20 °C |
| T500 (ESP) | 25 °C |

Thresholds live in `DomainRule` / `THRESHOLDS_C`, seeded from manuals — not sprinkled through the router as string literals.

Downtime is deliberately boring: **7 days × count of non-producing weekly inspections** in the window. Missed inspections add zero. That matches the Dataset Guide and keeps the sealed set honest.

## 3. The intent pipeline (no sample script)

Older builds were a museum of sample phrases. The current path is:

```
text
  → resolve_query()     # wells, areas from DB, windows, visual hints, "my area"
  → try_capability_route()  # final-set tools + coverage refusals
  → legacy analytical handlers  # still area-resolved, no WELL-#### fallbacks
  → evidence envelope
```

**Resolve** looks up area names against the `areas` table (seven blocks in the test set, four in sample). “My area” maps the demo user’s `team_id` to wells/areas that team actually runs — including Northwest Production for Nathan Pierce.

**Capabilities** are pure functions over `(Session, as_of)`:

| Tool | Algorithm in one line |
|---|---|
| `coverage.*` | Refuse when the measurement class is absent |
| `ops.gas_odor_compliance` | Gas-odor notes → next manual inspection or maintenance → 24h/12h deadline (OPS-1) |
| `ops.temporary_bypasses` | Bypass in/out notes × MOC well lists × expiry → Allowed / Expired / Not approved |
| `ops.status_disagreements` | Latest inspection vs shut-in/restart note; OPS-3 precedence + unconfirmed |
| `regulator.letter_spill_compliance` | Letter scope ∩ reportable spills ∩ “Soil samples sent to the lab.” |
| `equipment.recalled_pumps` | Latest `Parts installed` lot ∈ recall lots − shared replacement assertions |
| `analytics_ext.repair_risk_rank` | Anomaly operator notes without later non-spill corrective repair |
| `analytics_ext.wait_reasons_by_area` | Classify waiting-on language; shares + typical extra days |
| `analytics_ext.hotter_regions` | Mean/median ΔT by area over a lookback window |

If a question asks for reservoir pressure or “most oil produced,” we **do not** invent a heatmap or a BOPD ranking. Coverage objects say `unsupported` and list the missing fields. Judges reward honesty; fake charts fail.

## 4. OPS engines as state machines

**Gas (OPS-1).** Detect gas language in `operator_note` text. Find the earliest response after the note: a maintenance `started_at`, or a **manual** inspection (drones do not count). Deadline hours flip on 1 Jan 2027 (24 → 12). Met/Missed is a pure comparison.

**Bypass (OPS-2).** Notes toggle an interval open (`bypass in`) or closed (`bypass out`). MOC markdown files are parsed for WELL-IDs and expiry dates. An open interval after expiry is Expired; a well never named in an MOC is Not approved — even if the crew wrote a note.

**Status (OPS-3).** The more recent of (a) effective latest inspection and (b) shut-in/restart operator note wins. A restart newer than the inspection is **producing (unconfirmed)** until an inspection confirms. We surface disagreements in a table instead of quietly picking a side.

## 5. Recall without hardcoding lots

The supplier notice is a document. We extract recalled LOT-* tokens from it. Maintenance reports contribute `Parts installed` lines → `ExtractedFact` rows (`pump_lot`, `pump_serial`). For each well, the **latest install at or before as_of** is the pump in the ground. Shared assertions of kind `pump_replaced` remove a well from the list; second-hand claims (`Nathan told me…`) stay **unconfirmed** with provenance on the row.

Private preferences (`UserPreference`) are the opposite: Nathan’s “sort by area, costs in thousands” never applies to Robert or Olivia.

## 6. Memory that knows its scope

| Layer | Who sees it | Examples |
|---|---|---|
| Shared | Everyone | Corrections, pump replacements, FYI-for-everyone notes |
| Private | One user | Conversation references, list-display prefs |
| Session | One chat | Topic labels (“recalled pumps”) for “back to the pumps…” |

“Wells we discussed yesterday” requires a multi-well reference for **that** user. Coaching text never names another user’s wells as examples.

## 7. Harness-oriented development

Final questions live as YAML under `tests/harness/scenarios/final/`. Each turn states **invariants** — visual kind, required columns, allowed cell values, evidence and citation counts, and (for a later turn) that the answer still names a well from earlier in that chat. The file is schema-checked before it runs, and it refuses a database with fewer than 500 wells so the sample import cannot pass the final suite. Failures quote the actual summary and write the answer JSON under `tests/harness/_failures/`. They do not memorize barrel totals.

```bash
make DATASET_PROFILE=test up
make DATASET_PROFILE=test import-data
make harness-final
```

Sample Q1–Q18 stay on `DATASET_PROFILE=sample` via `make evaluate`. Same code paths; different clock and data root.

## 8. What we refuse to do

- Hardcode WELL-0333, LOT-2409-A, or “15.1 barrels” in application code.
- Map pressure that isn’t in the files.
- Let private prefs leak across the demo user picker.
- Quietly resolve conflicts between people and inspections.

The algorithm is the product: evidence-backed, clock-aware, and boring in the places oilfield software should be boring.
