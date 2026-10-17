# FieldSense UI / UX rulebook

FieldSense is an **evidence-backed field operations copilot**. The interface should feel like a calm control room for people who work wells — clear, trustworthy, and grounded in real records — not a generic chat dashboard.

Use this document for product UI decisions. Agents also follow `.cursor/rules/frontend-ui.mdc`.

---

## 1. Design intent

| Principle | What it means |
|---|---|
| **Brand first** | “FieldSense” is the hero identity in the shell. The logo mark + wordmark outranks feature chrome; clicking the logo returns home (question catalog). |
| **One job per surface** | Chat answers; sidebar navigates; evidence drawer proves. Don’t merge jobs. |
| **Evidence over spectacle** | Prefer readable tables, honest empty/coverage states, and source links over decorative charts. |
| **Never invent** | If data is missing, say so plainly. No fake maps, scores, or “estimated” pressure/volume. |
| **Human language** | Labels speak to operators and analysts, not API field names. |

---

## 2. Best practices checklist

### Clarity & hierarchy
1. One primary action per region (e.g. **Ask** in the composer; **New conversation** in the sidebar).
2. Answer summary is readable before any chart or table.
3. Tables show human column titles (`Well`, not `asset_id`).
4. Dense data gets scannable meta (row counts, status badges) — not extra panels.

### Trust & honesty
5. Coverage gaps use the **missing-data** pattern: plain summary + “We don’t have this data” callout; **no empty Results table**.
6. Source disagreements use **Sources disagree**, never silent overwrite.
7. Every non-trivial answer offers **See sources** when a result set exists.
8. Demo identity is labeled as demo — never look like SSO production auth.

### Interaction
9. Keyboard: Enter sends; Shift+Enter newline.
10. Disabled states explain themselves (select who you are before asking).
11. Loading copy names the work (“Checking inspections and notes…”).
12. Empty-state **Question catalog** has two tabs: **HOST** (official `test-data/final-questions.md`, copper) vs **OURS** (FieldSense showcase, moss). Host Q1–Q2 may be honest coverage refusals — that is correct for submission.

### Visual craft
13. Use design tokens (`--fs-*`) — no one-off hex in components unless extending the palette.
14. Atmosphere comes from soft gradients / field grid — not flat gray or purple glow.
15. Motion is purposeful: message enter, suggestion hover, loading pulse (2–3 motions max).
16. Cards exist only for interactive answer surfaces (tables, status, charts) — not every text block.

### Accessibility
17. Contrast: body text ≥ 4.5:1 on canvas; sidebar text on pine ≥ 4.5:1.
18. Focus rings use `--fs-focus`; never remove outlines without a replacement.
19. Icons are decorative next to text; buttons have visible labels.
20. Status uses color **and** text (“Producing” / “Not producing”).

### Content voice
21. Prefer short verbs: Ask, See sources, New conversation, Close.
22. Avoid jargon in chrome: no “X-User-Id”, “result_set”, “envelope”.
23. SOP codes (OPS-1) may appear in **answer text** from the backend; UI chrome uses plain English tags (Safety, Compliance).
24. Errors are actionable: what failed + what to try.

---

## 3. Theme: “Wellhead”

Field pine + copper metal + stone canvas. Distinct from generic SaaS teal-on-navy and from cream/terracotta landing tropes.

### Color tokens

| Token | Hex | Use |
|---|---|---|
| `--fs-pine` | `#0b2420` | Sidebar, brand field |
| `--fs-pine-mid` | `#143832` | Sidebar hover / inset |
| `--fs-copper` | `#c46b2d` | Primary CTA, focus accent |
| `--fs-copper-deep` | `#9a5222` | CTA hover |
| `--fs-moss` | `#1a7a6d` | Links, data highlight, success-adjacent |
| `--fs-stone` | `#e8ece9` | App canvas |
| `--fs-paper` | `#f7f8f6` | Panels, chat bubbles (assistant) |
| `--fs-ink` | `#14201c` | Body text |
| `--fs-mute` | `#5c6b64` | Secondary labels |
| `--fs-warn` | `#b45309` | Warnings / conflicts |
| `--fs-danger` | `#b42318` | Errors / not producing |
| `--fs-ok` | `#0f6b4c` | Producing / success |

### Typography

| Role | Family | Notes |
|---|---|---|
| Brand / display | **Fraunces** | Wordmark, empty-state title, panel titles |
| UI / body | **Figtree** | Everything else |
| Mono | ui-monospace | IDs, timestamps, source paths |

Sizes: brand ~22–28px; body 14–15px; meta 12px. Line-height 1.5 for answers.

### Shape & elevation

- Radius: controls `10px`, panels `14px`, avatars full circle.
- Borders: `1px` soft stone (`rgba(20,32,28,0.08)`), not heavy rules.
- Elevation: single soft lift — avoid stacked multi-shadow “AI glass” stacks.
- No pill clusters of stats in the empty state.

### Atmosphere

Canvas uses a soft radial wash + faint field grid. Sidebar uses a deep pine gradient with a subtle copper glint — not purple nebula.

### Motion

- `fs-enter`: answers fade/slide 160ms.
- Suggestion hover: 1px lift + copper border tint.
- Loading: three-dot pulse in copper/moss.

---

## 4. Layout anatomy

```
┌──────── sidebar ────────┬────────── main ──────────────────┐
│ Brand                    │ Who’s asking · Answer as of · data │
│ New conversation         ├───────────────────────────────────┤
│ Recent questions         │ Messages / empty + suggestions    │
│ Field areas              │ Composer (Ask)                    │
└──────────────────────────┴──── optional: See sources drawer ─┘
```

- Sidebar width ~272px; evidence drawer ~380–400px.
- Empty state: brand-led title, one sentence, then suggestion grid (interactive cards OK).
- Chat: user messages copper-tint; assistant on paper with border.

---

## 5. Component rules

| Component | Rule |
|---|---|
| **Suggestion** | Tag (plain English) + short label + 2-line preview. Click runs the full prompt. |
| **Answer panel** | Icon + human title + optional meta; content below. |
| **Coverage callout** | Title “We don’t have this data”; list what’s missing in plain words; no table. |
| **Conflict callout** | Title “Sources disagree”; list messages. |
| **Evidence drawer** | Kind badge + title + id + excerpt. Empty: explain, don’t apologize vaguely. |
| **Status badge** | Text + icon + color. |

---

## 6. Voice & label dictionary

| Avoid (system-ish) | Prefer |
|---|---|
| Demo user | Who’s asking |
| As of | Answer as of |
| Import succeeded: x | Data ready — x |
| + New chat | New conversation |
| Conversations | Recent questions |
| Areas | Field areas |
| View evidence | See sources |
| Data coverage gap | We don’t have this data |
| Conflicts disclosed | Sources disagree |
| Results (empty) | *(don’t show)* / Nothing matched this question |
| Calculating from inspections… | Checking inspections and notes… |
| Select a demo user to begin | Choose who you are |
| Asset Intelligence Copilot | Field intelligence for your wells *(subtitle)* |

Column titles: map snake_case → operator language in `COL_LABELS` (`hours_to_response` → “Hours to respond”).

---

## 7. Do / don’t

**Do**
- Keep FieldSense as the strongest mark in the chrome.
- Ship suggestion prompts that return real tables/charts on the active dataset.
- Extend tokens in `index.css` + `tailwind.config.js` together.

**Don’t**
- Default to purple gradients, neon glow, or cream + terracotta poster layouts.
- Put stats strips or promo chips in the empty-state hero.
- Overlay badges on maps for decoration.
- Show empty “Results” tables for unsupported coverage answers.
- Use Inter / Roboto / Arial as the brand face.

---

## 8. Change process

1. Update tokens in `frontend/src/index.css` and `frontend/tailwind.config.js`.
2. Prefer semantic classes (`bg-pine`, `text-copper`, `font-display`).
3. Update this rulebook if you introduce a new pattern (new callout type, new drawer).
4. Rebuild `web` and spot-check empty state, one table answer, coverage refusal, evidence drawer.
