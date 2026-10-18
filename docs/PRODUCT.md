# FieldSense

Evidence-backed asset intelligence for one oil lease. The person in the chat is **Wells Bennett**, the well analyst. The product name is FieldSense.

## What you see

The window is one screen. The page itself does not scroll.

- Center: Wells Bennett (a nodding hard-hat mark), then the thread and the ask box.
- Left: brand, new conversation, a north-up lease plat (Northeast, Northwest, Southeast, Southwest blocks), and recent questions.
- Right: a **Questions** toolbar. Host Q1–Q11 and the FieldSense demos stay closed until you open it. The list scrolls inside that panel.
- Answers stay in the thread. Charts and tables are chosen from the shape of the rows. A spill map draws OpenStreetMap tiles and well pins. Coverage gaps (reservoir pressure, oil volume) stay text: Wells Bennett does not invent those numbers.

## How an answer is made

`ANSWER_MODE=llm` is the product path. Wells Bennett is Gemma (`gemma-4-26b-a4b-it` on the Gemini API). He calls tools. Every figure in the summary has to appear in a tool result.

Known questions skip the model loop and return the tool result directly, including the spill map and the spill heatmap. Questions the fast path does not recognize still go through Gemma.

`ANSWER_MODE=router` is the optional offline phrase router. Evaluation sets that mode so the harness stays deterministic. The product does not fall back to the router when the API key is missing; the chat says the model is not configured.

The analysis clock is `X-Analysis-Clock` or `EVALUATION_AS_OF`. Sample data uses 16 Oct 2026. The test profile uses 15 Jan 2027. “Last 90 days” is measured from that clock.

Production status comes from wellhead minus ambient temperature against the well-type threshold (T200 15°C, T350 20°C, T500 25°C). Downtime days are seven times the non-producing inspections in the window. Formal corrections change the effective reading; the original record stays.

## Runtime

| Service | Role |
|---|---|
| `web` | React SPA behind nginx on port 5173 |
| `api` | FastAPI on port 8000 |
| `worker` | Postgres job consumer, no HTTP port |
| `db` | PostgreSQL 16 |

Demo identity is the **Who’s asking** picker (`X-User-Id`). It is not production sign-in. Private chats stay with that person. Shared notes are visible across users.

## Limits that are still true

- No reservoir-pressure readings and no oil-production volumes in this dataset. Those questions are refused on purpose.
- Map tiles need a network. The coordinate table is still returned with the pins.
- The phrase router only matches the patterns it was written for. Paraphrases belong on the model path.
- `make evaluate` needs the sample import. `make harness-final` needs the test import.

How to run the stack is in the repository README.
