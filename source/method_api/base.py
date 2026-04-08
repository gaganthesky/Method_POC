from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
import copy
import time
import uuid

import requests

from source.logging import get_logger
from source.method_api.models import ApiLogEntry, MethodApiError
from source.method_api.utils import (
    extract_error_message,
    mask_api_key,
    parse_response_body,
    redact_payload,
    serialize_for_log,
)


logger = get_logger(__name__)


class BaseMethodClient:
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
            "Idempotency-Key": str(uuid.uuid4()),
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
            serialize_for_log(safe_headers),
            serialize_for_log(params),
            serialize_for_log(safe_body),
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
        response_body = parse_response_body(response)
        request_id = response.headers.get("Request-Id")
        logger.debug(
            "Method API response received | label=%s | method=%s | url=%s | status=%s | request_id=%s | idempotency_key=%s | duration_ms=%s | body=%s",
            label,
            method,
            response.url,
            response.status_code,
            request_id,
            headers["Idempotency-Key"],
            duration_ms,
            serialize_for_log(response_body),
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
                "Idempotency-Key": headers["Idempotency-Key"],
            },
            request_body=redact_payload(copy.deepcopy(json_body)),
            response_status=response.status_code,
            response_body=response_body,
            duration_ms=duration_ms,
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

        if isinstance(response_body, dict) and response_body.get("success") is False:
            message = extract_error_message(response_body) or f"{label} failed."
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
            message = extract_error_message(response_body) or f"{label} failed with HTTP {response.status_code}."
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
            serialize_for_log(response_body),
        )
        raise MethodApiError(
            f"{label} returned an unexpected response shape.",
            response_body=response_body,
        )
