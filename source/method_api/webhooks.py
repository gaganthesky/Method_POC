from __future__ import annotations

from source.method_api.models import ApiLogEntry


class WebhooksMixin:
    def create_webhook(
        self,
        *,
        event_type: str,
        url: str,
        auth_token: str,
        hmac_secret: str | None = None,
        expand_event: bool = True,
    ) -> tuple[dict[str, object], ApiLogEntry]:
        body: dict[str, object] = {
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
