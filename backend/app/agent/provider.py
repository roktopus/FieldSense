"""Model calls. Google Gemma uses the Gemini SDK; other providers stay OpenAI-compatible."""

from __future__ import annotations

import json
from typing import Any

import httpx

from app.core.config import Settings

_GOOGLE = {"google", "gemini", "google_genai"}


class ModelConfigError(RuntimeError):
    """Required model settings are empty while ANSWER_MODE=llm."""


class ModelCallError(RuntimeError):
    """The provider rejected the request or returned an unusable body."""


def is_google(settings: Settings) -> bool:
    return (settings.model_provider or "").strip().lower() in _GOOGLE


def _google_key(settings: Settings) -> str:
    return (settings.gemini_api_key or settings.model_api_key or "").strip()


def require_model(settings: Settings) -> None:
    if is_google(settings):
        missing = []
        if not (settings.model_name or "").strip():
            missing.append("MODEL_NAME")
        if not _google_key(settings):
            missing.append("GEMINI_API_KEY")
        if missing:
            joined = " and ".join(missing)
            raise ModelConfigError(
                f"This copilot answers with Gemma on the Gemini API, and {joined} is not set. "
                "Create a key at https://aistudio.google.com/apikey and put it in GEMINI_API_KEY. "
                "MODEL_NAME is gemma-4-26b-a4b-it (faster) or gemma-4-31b-it (stronger)."
            )
        return

    missing = []
    if not (settings.model_base_url or "").strip():
        missing.append("MODEL_BASE_URL")
    if not (settings.model_name or "").strip():
        missing.append("MODEL_NAME")
    if missing:
        joined = " and ".join(missing)
        raise ModelConfigError(
            f"This copilot answers with a model, and {joined} is not set. "
            "Point MODEL_BASE_URL at an OpenAI-compatible /v1 endpoint and set MODEL_NAME. "
            "Hosted APIs also need MODEL_API_KEY. "
            "The offline phrase router is optional: set ANSWER_MODE=router to use it instead."
        )


def completions_url(base_url: str) -> str:
    base = base_url.strip().rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def _clean_schema(node: Any) -> Any:
    if isinstance(node, dict):
        return {key: _clean_schema(value) for key, value in node.items() if key != "additionalProperties"}
    if isinstance(node, list):
        return [_clean_schema(value) for value in node]
    return node


def _declarations(tools: list[dict]) -> list[dict]:
    decls = []
    for tool in tools:
        function = tool.get("function") or tool
        name = function.get("name")
        if not name:
            continue
        parameters = _clean_schema(function.get("parameters") or {"type": "object", "properties": {}})
        decls.append(
            {
                "name": name,
                "description": function.get("description") or "",
                "parameters": parameters,
            }
        )
    return decls


def _tool_name(messages: list[dict], call_id: str | None) -> str:
    for message in reversed(messages):
        for call in message.get("tool_calls") or []:
            if str(call.get("id")) == str(call_id):
                function = call.get("function") or {}
                return str(function.get("name") or "tool")
    return "tool"


def _parse_args(raw: Any) -> dict:
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


def _to_contents(messages: list[dict]) -> tuple[str | None, list]:
    from google.genai import types

    system_parts: list[str] = []
    contents: list = []
    for message in messages:
        role = message.get("role")
        if role == "system":
            if message.get("content"):
                system_parts.append(str(message["content"]))
            continue
        if role == "user":
            contents.append(
                types.Content(role="user", parts=[types.Part(text=str(message.get("content") or ""))])
            )
            continue
        if role == "assistant":
            parts = []
            if message.get("content"):
                parts.append(types.Part(text=str(message["content"])))
            for call in message.get("tool_calls") or []:
                function = call.get("function") or {}
                parts.append(
                    types.Part(
                        function_call=types.FunctionCall(
                            name=str(function.get("name") or ""),
                            args=_parse_args(function.get("arguments")),
                            id=str(call.get("id") or "") or None,
                        )
                    )
                )
            if parts:
                contents.append(types.Content(role="model", parts=parts))
            continue
        if role == "tool":
            payload = _parse_args(message.get("content"))
            if not payload and message.get("content"):
                payload = {"result": message.get("content")}
            part = types.Part(
                function_response=types.FunctionResponse(
                    name=_tool_name(messages, message.get("tool_call_id")),
                    response=payload or {"result": None},
                    id=str(message.get("tool_call_id") or "") or None,
                )
            )
            if contents and contents[-1].role == "user" and _has_function_response(contents[-1]):
                contents[-1].parts.append(part)
            else:
                contents.append(types.Content(role="user", parts=[part]))
    system = "\n\n".join(system_parts) or None
    return system, contents


def _has_function_response(content: Any) -> bool:
    parts = getattr(content, "parts", None) or []
    return any(getattr(part, "function_response", None) is not None for part in parts)


def message_from_google(response: Any) -> dict:
    """Map a Gemini response onto the assistant message the tool loop expects."""
    calls = []
    for index, function_call in enumerate(getattr(response, "function_calls", None) or []):
        args = getattr(function_call, "args", None) or {}
        if not isinstance(args, dict):
            try:
                args = dict(args)
            except (TypeError, ValueError):
                args = {}
        calls.append(
            {
                "id": getattr(function_call, "id", None) or f"call_{index}",
                "type": "function",
                "function": {
                    "name": function_call.name,
                    "arguments": json.dumps(args),
                },
            }
        )
    text = None
    try:
        text = response.text
    except (ValueError, AttributeError):
        text = None
    return {"role": "assistant", "content": text or None, "tool_calls": calls}


def complete_google(messages: list[dict], tools: list[dict], settings: Settings) -> dict:
    from google import genai
    from google.genai import types

    key = _google_key(settings)
    client = genai.Client(api_key=key)
    system, contents = _to_contents(messages)
    config_kwargs: dict[str, Any] = {"temperature": 0}
    if system:
        config_kwargs["system_instruction"] = system
    declarations = _declarations(tools)
    if declarations:
        config_kwargs["tools"] = [types.Tool(function_declarations=declarations)]
    try:
        response = client.models.generate_content(
            model=settings.model_name,
            contents=contents,
            config=types.GenerateContentConfig(**config_kwargs),
        )
    except Exception as exc:  # noqa: BLE001 — SDK raises several provider errors
        detail = str(exc).replace(key, "***")[:400]
        raise ModelCallError(f"Gemma request failed: {detail}") from exc
    return message_from_google(response)


def complete_openai(messages: list[dict], tools: list[dict], settings: Settings) -> dict:
    url = completions_url(settings.model_base_url)
    key = (settings.model_api_key or "").strip() or "ollama"
    body = {
        "model": settings.model_name,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0,
    }
    try:
        with httpx.Client(timeout=90.0) as client:
            response = client.post(
                url,
                headers={
                    "Authorization": f"Bearer {key}",
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except httpx.HTTPError as exc:
        raise ModelCallError(f"Model request failed: {exc}") from exc
    if response.status_code >= 400:
        detail = response.text[:400].replace("\n", " ").replace(key, "***")
        raise ModelCallError(f"Model returned HTTP {response.status_code}: {detail}")
    try:
        payload = response.json()
        message = payload["choices"][0]["message"]
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        raise ModelCallError("Model response did not include choices[0].message.") from exc
    if not isinstance(message, dict):
        raise ModelCallError("Model response message was not an object.")
    return message


def complete_chat(messages: list[dict], tools: list[dict], settings: Settings) -> dict:
    """Return the assistant message dict (content + optional tool_calls)."""
    require_model(settings)
    if is_google(settings):
        return complete_google(messages, tools, settings)
    return complete_openai(messages, tools, settings)
