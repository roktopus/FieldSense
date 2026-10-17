# Known Limitations

- Demo user picker is not production authentication (server session / `X-User-Id` for the challenge). Set `APP_ENV=production` with a strong `SESSION_SECRET` and replace identity before any real deployment.
- Embeddings are optional; lexical FTS is the always-on fallback.
- Report-fact extraction uses structured heuristics/regex over maintenance reports; unsupported facts stay `unknown`.
- Map tiles require network; offline mode shows coordinate table.
- LLM provider may be unavailable; a deterministic intent router answers analytical questions without a model.
- Final Hack Day sealed questions are not pre-filled; example scenarios Q1–Q18 are covered by the evaluation suite.
- Intent routing is phrase/heuristic based — paraphrases of challenge questions may need new patterns or an optional tool-calling LLM.
