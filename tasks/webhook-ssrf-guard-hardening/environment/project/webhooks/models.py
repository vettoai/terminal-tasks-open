"""Records passed between subscription management, storage and dispatch."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from uuid import uuid4


def utc_timestamp():
    return datetime.now(timezone.utc).isoformat(timespec='milliseconds')


def new_id(prefix):
    return f'{prefix}_{uuid4().hex}'


class DeliveryState(str, Enum):
    PENDING = 'pending'
    LEASED = 'leased'
    DELIVERED = 'delivered'
    RETRY = 'retry'
    EXHAUSTED = 'exhausted'
    CANCELLED = 'cancelled'


@dataclass(frozen=True)
class Subscription:
    subscription_id: str
    customer_id: str
    url: str
    topics: tuple[str, ...]
    enabled: bool = True
    created_at: str = field(default_factory=utc_timestamp)

    def matches(self, topic):
        return self.enabled and (topic in self.topics or '*' in self.topics)

    def as_dict(self):
        return {
            'subscription_id': self.subscription_id,
            'customer_id': self.customer_id,
            'url': self.url,
            'topics': list(self.topics),
            'enabled': self.enabled,
            'created_at': self.created_at,
        }

    @classmethod
    def from_row(cls, row):
        import json
        return cls(
            row['subscription_id'], row['customer_id'], row['url'],
            tuple(json.loads(row['topics'])), bool(row['enabled']), row['created_at'],
        )


@dataclass(frozen=True)
class Event:
    event_id: str
    customer_id: str
    topic: str
    payload: dict
    occurred_at: str = field(default_factory=utc_timestamp)

    def envelope(self):
        return {
            'id': self.event_id,
            'topic': self.topic,
            'occurred_at': self.occurred_at,
            'data': self.payload,
        }


@dataclass(frozen=True)
class Delivery:
    delivery_id: str
    subscription_id: str
    event_id: str
    url: str
    body: bytes
    state: DeliveryState = DeliveryState.PENDING
    attempts: int = 0
    next_attempt_at: float = 0
    lease_until: float = 0

    @classmethod
    def from_row(cls, row):
        return cls(
            row['delivery_id'], row['subscription_id'], row['event_id'],
            row['url'], bytes(row['body']), DeliveryState(row['state']),
            row['attempts'], row['next_attempt_at'], row['lease_until'],
        )


@dataclass(frozen=True)
class Attempt:
    delivery_id: str
    sequence: int
    status: int | None
    error: str | None
    started_at: float
    finished_at: float

    @property
    def successful(self):
        return self.error is None and self.status is not None and 200 <= self.status < 300

    @property
    def duration(self):
        return max(0, self.finished_at - self.started_at)
