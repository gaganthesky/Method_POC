from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
import copy
import json
import time

import requests

from source.logging import get_logger


logger = get_logger(__name__)

SENSITIVE_KEYS = {
    "api_key",
    "auth_token",
    "hmac_secret",
    "authorization",
}


class MethodApiError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        response_body: Any = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.response_body = response_body


@dataclass
class ApiLogEntry:
    step: int
    label: str
    method: str
    url: str
    request_headers: dict[str, str]
    request_body: Any
    response_status: int
    response_body: Any
    duration_ms: int
    timestamp: str


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


class MethodClient:
    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        method_version: str,
        timeout_seconds: int = 45,
        session: requests.Session | None = None,
    ) -> None:
        self.api_key = api_key.strip()
        self.base_url = base_url.rstrip("/")
        self.method_version = method_version.strip()
        self.timeout_seconds = timeout_seconds
        self.session = session or requests.Session()

    def create_individual(self, payload: dict[str, Any]) -> tuple[dict[str, Any], ApiLogEntry]:
        body = {
            "type": "individual",
            "individual": {
                "first_name": payload["first_name"],
                "last_name": payload["last_name"],
                "phone": payload["phone"],
                "email": payload["email"],
                "dob": payload["dob"],
                "ssn": payload.get("ssn") or None,
            },
            "address": {
                "line1": payload["line1"],
                "line2": payload.get("line2") or None,
                "city": payload["city"],
                "state": payload["state"],
                "zip": payload["zip"],
            },
        }
        response, log = self._request(
            step=0,
            label="Create Entity",
            method="POST",
            path="/entities",
            json_body=body,
        )
        return self._expect_resource(response, label="Create Entity", required_keys=("id", "type")), log

    def connect_liabilities(
        self,
        entity_id: str,
        *,
        requested_products: list[str] | None = None,
        requested_subscriptions: list[str] | None = None,
    ) -> tuple[dict[str, Any], ApiLogEntry]:
        body: dict[str, Any] | None = None
        if requested_products or requested_subscriptions:
            body = {}
            if requested_products:
                body["products"] = requested_products
            if requested_subscriptions:
                body["subscriptions"] = requested_subscriptions

        response, log = self._request(
            step=1,
            label="Connect Liabilities",
            method="POST",
            path=f"/entities/{entity_id}/connect",
            json_body=body,
        )
        return self._expect_resource(response, label="Connect Liabilities", required_keys=("id", "status")), log

    def list_accounts(
        self,
        holder_id: str,
        *,
        account_type: str,
        status: str,
        expand: list[str] | None,
    ) -> tuple[list[dict[str, Any]], ApiLogEntry]:
        params: list[tuple[str, str]] = [
            ("holder_id", holder_id),
            ("type", account_type),
            ("status", status),
        ]
        for item in expand or []:
            params.append(("expand[]", item))

        response, log = self._request(
            step=2,
            label="List Accounts",
            method="GET",
            path="/accounts",
            params=params,
        )
        if isinstance(response, dict) and "data" in response:
            return response["data"], log
        if isinstance(response, list):
            return response, log
        raise MethodApiError("Unexpected account list response format.", response_body=response)

    def create_webhook(
        self,
        *,
        event_type: str,
        url: str,
        auth_token: str,
        hmac_secret: str | None = None,
        expand_event: bool = True,
    ) -> tuple[dict[str, Any], ApiLogEntry]:
        body: dict[str, Any] = {
            "type": event_type,
            "url": url,
            "auth_token": auth_token,
            "expand_event": expand_event,
        }
        if hmac_secret:
            body["hmac_secret"] = hmac_secret

        response, log = self._request(
            step=3,
            label=f"Create Webhook ({event_type})",
            method="POST",
            path="/webhooks",
            json_body=body,
        )
        return self._expect_resource(response, label=f"Create Webhook ({event_type})", required_keys=("id", "type")), log

    def subscribe_account(
        self,
        account_id: str,
        *,
        enroll: str,
    ) -> tuple[dict[str, Any], ApiLogEntry]:
        response, log = self._request(
            step=3,
            label=f"Subscribe Account ({account_id[-6:]})",
            method="POST",
            path=f"/accounts/{account_id}/subscriptions",
            json_body={"enroll": enroll},
        )
        return self._expect_resource(
            response,
            label=f"Subscribe Account ({account_id[-6:]})",
            required_keys=("id", "status"),
        ), log

    def create_payment_instrument(
        self,
        account_id: str,
        *,
        instrument_type: str,
    ) -> tuple[dict[str, Any], ApiLogEntry]:
        response, log = self._request(
            step=4,
            label=f"Create Payment Instrument ({account_id[-6:]})",
            method="POST",
            path=f"/accounts/{account_id}/payment_instruments",
            json_body={"type": instrument_type},
        )
        return self._expect_resource(
            response,
            label=f"Create Payment Instrument ({account_id[-6:]})",
            required_keys=("id", "account_id", "status"),
        ), log

    def create_payment(
        self,
        *,
        source: str,
        destination: str,
        amount: int,
        description: str,
    ) -> tuple[dict[str, Any], ApiLogEntry]:
        response, log = self._request(
            step=5,
            label="Create Payment",
            method="POST",
            path="/payments",
            json_body={
                "amount": amount,
                "source": source,
                "destination": destination,
                "description": description,
            },
        )
        return self._expect_resource(response, label="Create Payment", required_keys=("id", "status")), log

    def _request(
        self,
        *,
        step: int,
        label: str,
        method: str,
        path: str,
        json_body: dict[str, Any] | None = None,
        params: list[tuple[str, str]] | None = None,
    ) -> tuple[Any, ApiLogEntry]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "Method-Version": self.method_version,
        }
        url = f"{self.base_url}{path}"
        started = time.perf_counter()
        safe_headers = redact_payload(copy.deepcopy(headers))
        safe_body = redact_payload(copy.deepcopy(json_body))

        logger.debug(
            "Method API request starting | label=%s | method=%s | url=%s | headers=%s | params=%s | body=%s",
            label,
            method,
            url,
            _serialize_for_log(safe_headers),
            _serialize_for_log(params),
            _serialize_for_log(safe_body),
        )

        try:
            response = self.session.request(
                method=method,
                url=url,
                headers=headers,
                json=json_body,
                params=params,
                timeout=self.timeout_seconds,
            )
        except requests.RequestException as exc:
            logger.debug(
                "Method API request failed before response | label=%s | method=%s | url=%s | error=%s",
                label,
                method,
                url,
                str(exc),
            )
            raise MethodApiError(f"{label} failed before a response was received: {exc}") from exc

        duration_ms = int((time.perf_counter() - started) * 1000)
        response_body = _parse_response_body(response)
        logger.debug(
            "Method API response received | label=%s | method=%s | url=%s | status=%s | duration_ms=%s | body=%s",
            label,
            method,
            response.url,
            response.status_code,
            duration_ms,
            _serialize_for_log(response_body),
        )
        log = ApiLogEntry(
            step=step,
            label=label,
            method=method,
            url=response.url,
            request_headers={
                "Authorization": f"Bearer {mask_api_key(self.api_key)}",
                "Content-Type": headers["Content-Type"],
                "Method-Version": headers["Method-Version"],
            },
            request_body=redact_payload(copy.deepcopy(json_body)),
            response_status=response.status_code,
            response_body=response_body,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if isinstance(response_body, dict) and response_body.get("success") is False:
            message = _extract_error_message(response_body) or f"{label} failed."
            logger.debug(
                "Method API logical failure | label=%s | method=%s | url=%s | status=%s | error=%s",
                label,
                method,
                response.url,
                response.status_code,
                message,
            )
            raise MethodApiError(
                message,
                status_code=response.status_code,
                response_body=response_body,
            )

        if not response.ok:
            message = _extract_error_message(response_body) or f"{label} failed with HTTP {response.status_code}."
            logger.debug(
                "Method API HTTP failure | label=%s | method=%s | url=%s | status=%s | error=%s",
                label,
                method,
                response.url,
                response.status_code,
                message,
            )
            raise MethodApiError(
                message,
                status_code=response.status_code,
                response_body=response_body,
            )

        if not isinstance(response_body, (dict, list)):
            raise MethodApiError(
                f"{label} returned an unexpected non-JSON response.",
                status_code=response.status_code,
                response_body=response_body,
            )
        return response_body, log

    def _expect_resource(
        self,
        response_body: Any,
        *,
        label: str,
        required_keys: tuple[str, ...],
    ) -> dict[str, Any]:
        candidates: list[dict[str, Any]] = []
        if isinstance(response_body, dict):
            data = response_body.get("data")
            if isinstance(data, dict):
                candidates.append(data)
            candidates.append(response_body)

        for candidate in candidates:
            if all(key in candidate for key in required_keys):
                return candidate

        logger.debug(
            "Method API response shape mismatch | label=%s | required_keys=%s | response=%s",
            label,
            required_keys,
            _serialize_for_log(response_body),
        )
        raise MethodApiError(
            f"{label} returned an unexpected response shape.",
            response_body=response_body,
        )


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


def _parse_response_body(response: requests.Response) -> Any:
    if not response.content:
        return {}
    try:
        return response.json()
    except ValueError:
        return response.text


def _extract_error_message(response_body: Any) -> str | None:
    if isinstance(response_body, dict):
        for key in ("message", "error", "detail", "debugMessage"):
            value = response_body.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return None


def _serialize_for_log(value: Any) -> str:
    if value is None:
        return "null"
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, default=str)
    except TypeError:
        return repr(value)
