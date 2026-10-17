# Frontend Algorithms — Turning Envelopes into Trust

The UI’s job is not to “look AI.” It is to make a careful backend answer *legible*: what is known, what is conflicted, and what the dataset simply cannot support.

## 1. The answer envelope

Every completed run returns a JSON envelope. The React app treats this as the contract — not a free-form chat string.

| Field | Role |
|---|---|
| `kind` | Coarse answer type (`table`, `bar_chart`, `short_answer`, `stacked_bar`, …) |
| `summary` | One honest paragraph a supervisor can read aloud |
| `rows` / `data` | Tabular or nested payloads for visuals |
| `visuals[]` | Named views with `fields` (column order) |
| `citations` / evidence API | Traceability chips → evidence drawer |
| `conflicts` | Disclosed disagreements (never hidden in the summary alone) |
| `coverage` | `unsupported` when measurements are missing |

If `kind` is missing, the UI still renders from `visuals` and `rows`. The backend now echoes `kind` on the envelope so harnesses and the UI stay aligned.

## 2. Visual selection algorithm

```
if visuals named in the envelope:
    render each visual in order
else if rows present:
    fall back to a table
else:
    show summary only (+ coverage / conflict panels)
```

Named visuals win. That matches the challenge brief: when a question asks for a map, show a map; when it doesn’t, pick a fitting shape from the data.

| Shape | When |
|---|---|
| Status card | One well, right now |
| Table | Lists of wells, events, compliance rows |
| Line chart | Temperature (or similar) over time |
| Bar chart | Ranked comparison (downtime days **or** mean ΔT by area) |
| Stacked bar | Composition by area (wait reasons) |
| Map / heatmap | Geography / area×month |
| Coverage panel | `coverage.status === "unsupported"` — **no fake chart** |

The bar chart reader is polymorphic: if rows carry `mean_delta_c` + `area_name`, it plots regional heat; if they carry `downtime_days` + `asset_id`, it plots well rankings. One component, two semantics — driven by the payload, not by a per-question React page.

## 3. Conflicts and provenance

Conflict objects become an amber panel: “Conflicts disclosed.” Unconfirmed pump swaps, disagreeing operator notes, and second-hand claims stay visible. Provenance strings on recall rows (“Install MNT-… lot …; Recall notice …”) are ordinary table cells — judges can scroll them.

We deliberately do **not** auto-resolve conflicts in the UI. Picking a side quietly is how copilots become dangerous.

## 4. Identity is a header, not a theme

Demo users come from `/api/v1/users` (imported `fleet/users.json`). Selecting Nathan Pierce vs Olivia Grant sets `X-User-Id`. Private preferences and conversation memory are server-side keyed by that id. Switching users in the picker does not re-skin the app to “look private”; it changes which memory the API is allowed to see.

Optional `X-Analysis-Clock` (from `localStorage.fieldsense_as_of`) lets demos pin the evaluation clock without rebuilding the image.

## 5. Empty states that teach

A table with zero rows says “No matching wells,” not “error.” A coverage gap panel lists missing fields (reservoir pressure, BOPD, …) so the operator knows **why** there is no map. That is part of the product algorithm: refuse inventively.

## 6. Streaming and long runs

Runs can emit progress stages (`resolving` → `calculating` → complete). The UI keeps the chat responsive and only mounts heavy visuals (Leaflet maps, Recharts) when the final envelope arrives. Evidence is lazy: open the drawer → `GET /api/v1/evidence?result_set_id=…`.

## 7. Column schemas without per-question pages

Tables accept optional `fields` from the visual descriptor. Labels are humanized (`asset_id` → “Well”, unknown keys title-cased). New final-question columns (deadline hours, approval valid until, provenance) render without a new React route — the backend owns the schema, the frontend owns readability.

## 8. Design stance

One composition for the chat surface. Evidence and conflicts are secondary layers, not a dashboard of competing cards. Motion is reserved for progressive reveal of results, not decorative noise. The brand of FieldSense is competence: show the numbers, show the fight between sources, and when the data isn’t there — say so.
