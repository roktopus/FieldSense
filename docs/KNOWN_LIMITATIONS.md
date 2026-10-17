# Known Limitations

- Demo user picker is not production authentication (server session / `X-User-Id` for the challenge). Set `APP_ENV=production` with a strong `SESSION_SECRET` and replace identity before any real deployment.
- Embeddings are optional; lexical FTS is the always-on fallback.
- Report-fact extraction uses structured heuristics/regex over maintenance reports; unsupported facts stay `unknown`.
- Map tiles require network; offline mode shows coordinate table.
- LLM provider may be unavailable; a deterministic intent router answers analytical questions without a model.
- Final Hack Day sealed questions are in the UI **HOST** catalog (`docs/HOST_FINAL_QUESTIONS.md`); sample-data Q1–Q18 stay in `make evaluate`.
- Intent routing is phrase/heuristic based — paraphrases of challenge questions may need new patterns or an optional tool-calling LLM.
- Final-set coverage refusals (no reservoir pressure / oil volumes) are intentional: the dataset does not contain those measurements.
- Sample evaluation (`make evaluate`) and final harness (`make harness-final`) require the matching dataset import (`DATASET_PROFILE=sample|test`).
- Worker process has no HTTP port; compose overrides the image healthcheck to a DB probe (do not curl `:8000` inside the worker).
