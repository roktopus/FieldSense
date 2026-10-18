"""Model loop binds visuals to tool rows and refuses ungrounded numbers."""

import json
from datetime import datetime, timezone

from app.agent.llm_answer import answer_with_model, bind_answer
from app.agent.provider import ModelConfigError, completions_url, require_model
from app.core.config import Settings


def _settings() -> Settings:
    return Settings(
        answer_mode="llm",
        model_base_url="http://localhost:11434/v1",
        model_api_key="ollama",
        model_name="llama3.1",
        tool_call_limit=4,
        agent_max_result_rows=20,
    )


def test_default_answer_mode_is_llm(monkeypatch):
    monkeypatch.delenv("ANSWER_MODE", raising=False)
    assert Settings(_env_file=None).answer_mode == "llm"


def test_completions_url_accepts_v1_base():
    assert completions_url("http://localhost:11434/v1") == "http://localhost:11434/v1/chat/completions"
    assert completions_url("https://api.openai.com") == "https://api.openai.com/v1/chat/completions"


def test_google_provider_asks_for_gemini_key():
    settings = Settings(
        answer_mode="llm",
        model_provider="google",
        model_name="gemma-4-26b-a4b-it",
        gemini_api_key="",
        _env_file=None,
    )
    answer = answer_with_model(
        db=None,
        text="Which wells are down?",
        user_id="u1",
        conversation_id="00000000-0000-0000-0000-000000000001",
        as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
        settings=settings,
        complete=lambda *_args: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )
    assert "GEMINI_API_KEY" in answer["summary"]
    assert "aistudio.google.com/apikey" in answer["summary"]
    assert "gemma-4-26b-a4b-it" in answer["summary"]


def test_missing_model_is_a_chat_answer_not_the_router():
    settings = Settings(answer_mode="llm", model_base_url="", model_name="", _env_file=None)
    try:
        require_model(settings)
        raised = False
    except ModelConfigError:
        raised = True
    assert raised
    answer = answer_with_model(
        db=None,
        text="Which wells are down?",
        user_id="u1",
        conversation_id="00000000-0000-0000-0000-000000000001",
        as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
        settings=settings,
        complete=lambda *_args: (_ for _ in ()).throw(AssertionError("provider should not be called")),
    )
    assert answer["warnings"] == ["model_unavailable"]
    assert "MODEL_BASE_URL" in answer["summary"]
    assert "ANSWER_MODE=router" in answer["summary"]


def test_submit_answer_uses_tool_rows_not_model_rows():
    calls = {"n": 0}

    def complete(messages, tools, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "content": None,
                "tool_calls": [
                    {
                        "id": "c1",
                        "type": "function",
                        "function": {
                            "name": "get_well_summary",
                            "arguments": json.dumps({"asset_id": "WELL-0001"}),
                        },
                    }
                ],
            }
        return {
            "content": None,
            "tool_calls": [
                {
                    "id": "c2",
                    "type": "function",
                    "function": {
                        "name": "submit_answer",
                        "arguments": json.dumps(
                            {
                                "summary": "WELL-0001 is not producing. Delta is 4.0 C.",
                                "kind": "status_card",
                                "result_handle": "r1",
                                "title": "WELL-0001",
                            }
                        ),
                    },
                }
            ],
        }

    def execute(name, arguments, ctx):
        assert name == "get_well_summary"
        return {
            "asset_id": "WELL-0001",
            "status": "not_producing",
            "delta_c": 4.0,
            "threshold_c": 15,
            "latest_inspection": {"inspection_id": "INSP-1", "inspected_at": "2026-10-09"},
        }

    # Patch the executor used by the loop.
    import app.agent.llm_answer as loop

    original = loop.execute_tool
    loop.execute_tool = execute
    try:
        answer = answer_with_model(
            db=None,
            text="Is WELL-0001 producing?",
            user_id="u1",
            conversation_id="00000000-0000-0000-0000-000000000001",
            as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
            settings=_settings(),
            complete=complete,
        )
    finally:
        loop.execute_tool = original

    assert calls["n"] == 2
    assert answer["kind"] == "status_card"
    assert answer["data"]["delta_c"] == 4.0
    assert answer["data"]["asset_id"] == "WELL-0001"
    assert answer["versions"]["model"] == "llama3.1"
    assert answer["visuals"][0]["kind"] == "status_card"


def test_ungrounded_number_is_sent_back_once():
    calls = {"n": 0}

    def complete(messages, tools, settings):
        calls["n"] += 1
        if calls["n"] == 1:
            return {
                "tool_calls": [
                    {
                        "id": "c1",
                        "function": {
                            "name": "submit_answer",
                            "arguments": json.dumps(
                                {"summary": "Downtime was 49 days.", "kind": "short_answer"}
                            ),
                        },
                    }
                ]
            }
        tool_payload = messages[-1]["content"]
        assert "ungrounded_numbers" in tool_payload
        assert "49" in tool_payload
        return {
            "tool_calls": [
                {
                    "id": "c2",
                    "function": {
                        "name": "submit_answer",
                        "arguments": json.dumps(
                            {"summary": "I do not have a downtime figure yet.", "kind": "short_answer"}
                        ),
                    },
                }
            ]
        }

    answer = answer_with_model(
        db=None,
        text="How long was the well down?",
        user_id="u1",
        conversation_id="00000000-0000-0000-0000-000000000001",
        as_of=datetime(2026, 10, 16, tzinfo=timezone.utc),
        settings=_settings(),
        complete=complete,
    )
    assert calls["n"] == 2
    assert "49" not in answer["summary"]


def test_known_question_skips_the_model_tool_loop(monkeypatch):
    def route(db, **kwargs):
        assert db is not None
        assert kwargs["text"] == "Gas odor reports since November"
        return {
            "kind": "table",
            "summary": "26 reports. 17 met the deadline.",
            "rows": [{"met": "Met", "area_name": "North"}],
            "visuals": [{"kind": "table", "title": "Gas reports"}],
        }

    monkeypatch.setattr("app.agent.intents.try_capability_route", route)
    answer = answer_with_model(
        db=object(),
        text="Gas odor reports since November",
        user_id="u1",
        conversation_id="00000000-0000-0000-0000-000000000001",
        as_of=datetime(2027, 1, 15, tzinfo=timezone.utc),
        settings=_settings(),
        complete=lambda *_args: (_ for _ in ()).throw(AssertionError("tool loop should not run")),
    )
    assert answer["kind"] == "table"
    assert answer["rows"][0]["met"] == "Met"
    assert answer["versions"]["model"] == "llama3.1"


def test_bind_answer_drops_chart_without_rows():
    answer = bind_answer(
        {"summary": "Nothing to plot.", "kind": "bar_chart", "result_handle": "missing"},
        {},
        "llama3.1",
    )
    assert answer["kind"] == "short_answer"
    assert answer["visuals"] == []
    assert answer["warnings"]
