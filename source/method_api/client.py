from source.method_api.accounts import AccountsMixin
from source.method_api.base import BaseMethodClient
from source.method_api.entities import EntitiesMixin
from source.method_api.payments import PaymentsMixin
from source.method_api.webhooks import WebhooksMixin


class MethodClient(
    EntitiesMixin,
    AccountsMixin,
    WebhooksMixin,
    PaymentsMixin,
    BaseMethodClient,
):
    """Composed Method API client split by endpoint area."""
