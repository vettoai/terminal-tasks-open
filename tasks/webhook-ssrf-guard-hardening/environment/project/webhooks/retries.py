"""Delivery retry policy."""

import hashlib

from config import MAX_ATTEMPTS, RETRY_BASE_SECONDS
from webhooks.models import DeliveryState


def retryable_status(status):
    return status in (408, 425, 429) or status >= 500


def retry_delay(delivery_id, attempt):
    digest = hashlib.sha256(f'{delivery_id}:{attempt}'.encode()).digest()
    jitter = int.from_bytes(digest[:2], 'big') / 65535
    base = min(3600, RETRY_BASE_SECONDS * 2 ** max(0, attempt - 1))
    return base * (0.8 + jitter * 0.4)


def outcome(attempt, *, permanent=False):
    if attempt.successful:
        return DeliveryState.DELIVERED, 0
    retry = not permanent and (
        attempt.status is None or retryable_status(attempt.status)
    )
    if retry and attempt.sequence < MAX_ATTEMPTS:
        delay = retry_delay(attempt.delivery_id, attempt.sequence)
        return DeliveryState.RETRY, attempt.finished_at + delay
    return DeliveryState.EXHAUSTED, 0
