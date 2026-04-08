from __future__ import annotations

from typing import Any

from source.method_api.models import ApiLogEntry, MethodApiError


class EntitiesMixin:
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

    def list_entity_products(self, entity_id: str) -> tuple[dict[str, Any], ApiLogEntry]:
        response, log = self._request(
            step=1,
            label="List Entity Products",
            method="GET",
            path=f"/entities/{entity_id}/products",
        )
        if isinstance(response, dict):
            return response, log
        raise MethodApiError("Unexpected product list response format.", response_body=response)

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
