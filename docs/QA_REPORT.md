# FieldSense QA Report (example scenarios Q1–Q18)

How we verified the sample pipeline, what broke, and how we fixed it.
The sealed Hack Day set will be new; this report is about process and regressions, not memorizing phrases.

## Method

1. **Clock alignment** — Dataset Guide + `03-evaluation-queries.md` set “today” to **16 Oct 2026**. We assert facts against that clock.
2. **Automated acceptance** — `make evaluate` runs `tests/evaluation/`:
   - Per-scenario unit/query checks (`test_q1_*` … `test_scenarios_q3_q18.py`)
   - End-to-end harness `test_qa_scenarios.py` (facts, visuals, evidence, Part B multi-user)
3. **Manual API spot-checks** — same wording as the brief, per-user `X-User-Id`, verify summary + visual kind + carry-forward.
4. **Pass criteria** (challenge brief): correct facts, cited evidence, requested/fitting visual, corrections that persist across users, private memory that does not leak.

## Clock fix (critical)

| Finding | Impact | Fix |
|---|---|---|
| App defaulted to **17 Oct 2026** | “Last 4 months / 90 days / 4 years” windows drifted from the brief (e.g. Q6 is explicitly 16 Jun–16 Oct) | Set `DEFAULT_AS_OF` / `EVALUATION_AS_OF` to **2026-10-16**; wire `parse_as_of(None)` through settings |

## Bugs found during Q1–Q18 QA (and fixes)

| # | Symptom | Root cause | Fix |
|---|---|---|---|
| Q2 | API 500 on area non-producing | Intent matched single-well status path; null-unsafe well match | Prefer area-not-producing routing; null-safe status card |
| Q7/Q8 | Spill map/heatmap overcount | “Not a crude spill” style notes not treated as exclusions | Broaden formal correction / exclusion handling for non-oil detections |
| Q8 | Heatmap intent lost to map | Phrase “map” matched before heatmap | Route heatmap before generic map |
| Q11 | Wrong wells recalled | Memory used analysis `as_of` as “yesterday”; single-well chats polluted recall | Wall-clock `discussed_at`; prefer downtime-labeled multi-well refs; require ≥3 wells for “three wells” |
| Q13 | Volume corrected to 4.5 not 5.4 | Parser preferred first number | Prefer “measured” volume language |
| Q16 | Empty-memory UX named Michael’s wells | Coaching examples reused Q6 IDs | Generic example WELL-0001; assert no cost leak |
| Envelope | Answer `kind` missing from API payload | Envelope dropped `kind` (only on `ResultSet`) | Include `kind` in run `answer_json` for clients/QA |
| Harness | Full E2E file not collected | Named `qa_scenarios.py` (pytest wants `test_*.py`) | Renamed `test_qa_scenarios.py` |

## Scenario matrix (sample-v1, as-of 16 Oct 2026)

| Q | Visual | Facts checked | Memory / feedback |
|---|---|---|---|
| Q1 | status card | Not producing; INS-0001-0203; ΔT 3.2 °C; CTX-0001-003; stale `active` | — |
| Q2 | table | WELL-0164/0170/0172/0175; reasons / “no recorded reason” | — |
| Q3 | line chart | 13 points; offline 8 Oct & 15 Oct | — |
| Q4 | table | 6 spills / 15.1 bbl; INS-0001-0070 excluded | — |
| Q5 | short answer | 21 days; MNT causes | — |
| Q6 | bar chart | 0121:49, 0138:42, 0107:42 | Seeds private memory |
| Q7 | map | 0151, 0165, 0175, 0186 | — |
| Q8 | heatmap | SW23=35, SW24=43, NE7=37, NE8=26 | — |
| Q9 | table | SR-01/02/03, RC-04; $5,000 open | — |
| Q10 | table | WELL-0082, WELL-0100 containment breaches | — |
| Q11 | table | Repair costs 25794 / 46942 / 5176 | Private recall of Q6 |
| Q12 | status + Q2 again | 0164 producing after 41.0 °C; conflict with pump-jack note; Q2 drops 0164 | Shared correction |
| Q13 | short answer | 5.4 bbl → SR-01/SR-03 flags | Shared analysis correction |
| Q14 | table | T350 threshold 2 adds WELL-0120; T200 WELL-0102 stays out | Team rule override |
| Q15 | status / table | Jessica sees 0164 producing; Laura sees 0151 reportable | Shared across users |
| Q16 | short answer | Jake shared note visible to Michael; Jessica has no Q11 history | Shared vs private |
| Q17 | short answer | Tyler / Jake claims marked unconfirmed vs inspections / CTX | Conflict handling |
| Q18 | short answer | Yes, real oil; shows Brooks vs Dalton disagreement | Conflict, not silent pick |

## How to re-run

```bash
docker compose up -d --build
make import-data   # if DB empty
make evaluate      # pytest tests/evaluation
```

## What we are *not* claiming

- Phrase-perfect routing for every paraphrase of the sealed set (router is deterministic + extensible; optional LLM can fill gaps).
- Perfect NLP over every free-text report edge case — unknown facts stay `unknown` rather than invented.
- That sample numbers alone prove final-day readiness — the suite encodes **rules and scopes** (production ΔT, 7× downtime, spill exclusions, shared vs private memory) so new wells/dates still exercise the same paths.
