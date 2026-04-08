from __future__ import annotations

from source.method_api.models import ApiLogEntry, MethodApiError


class AccountsMixin:
    def list_accounts(
        self,
        holder_id: str,
        *,
        account_type: str,
        status: str,
        expand: list[str] | None,
    ) -> tuple[list[dict[str, object]], ApiLogEntry]:
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

    def subscribe_account(
        self,
        account_id: str,
        *,
        enroll: str,
    ) -> tuple[dict[str, object], ApiLogEntry]:
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
    ) -> tuple[dict[str, object], ApiLogEntry]:
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
