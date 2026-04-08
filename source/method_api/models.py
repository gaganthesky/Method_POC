from __future__ import annotations

from dataclasses import dataclass
from typing import Any


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
