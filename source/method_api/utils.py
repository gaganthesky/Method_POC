from __future__ import annotations

from typing import Any
import json

import requests

from source.method_api.models import ApiLogEntry


SENSITIVE_KEYS = {
    "api_key",
    "auth_token",
    "hmac_secret",
    "authorization",
}


def redact_payload(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in SENSITIVE_KEYS:
                sanitized[key] = "••••••••"
            else:
                sanitized[key] = redact_payload(item)
        return sanitized
    if isinstance(value, list):
        return [redact_payload(item) for item in value]
    return value


def build_curl_command(log: ApiLogEntry) -> str:
    command = [f"curl '{log.url}'", f"  -X {log.method}"]
    for key, value in log.request_headers.items():
        command.append(f"  -H '{key}: {value}'")
    if log.request_body is not None:
        body = json.dumps(log.request_body, indent=2)
        command.append(f"  -d '{body}'")
    return " \\\n".join(command)


def mask_api_key(api_key: str) -> str:
    if len(api_key) <= 8:
        return "••••••••"
    return f"{api_key[:4]}••••••••{api_key[-4:]}"


def parse_response_body(response: requests.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def extract_error_message(response_body: Any) -> str | None:
    if isinstance(response_body, dict):
        for key in ("message", "error", "detail", "debugMessage"):
            value = response_body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def serialize_for_log(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return repr(value)
