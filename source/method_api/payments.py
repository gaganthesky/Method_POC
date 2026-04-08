from __future__ import annotations

from source.method_api.models import ApiLogEntry


class PaymentsMixin:
    def create_payment(
        self,
        *,
        source: str,
        destination: str,
        amount: int,
        description: str,
    ) -> tuple[dict[str, object], ApiLogEntry]:
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
