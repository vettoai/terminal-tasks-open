"""Publish immutable event envelopes to matching subscriptions."""

from dataclasses import dataclass

from webhooks.encoding import encode_event, required_string, validate_topic
from webhooks.models import Delivery, Event, new_id


@dataclass(frozen=True)
class PublishReceipt:
    event_id: str
    destination_count: int
    duplicate: bool

    def as_dict(self):
        return {
            'event_id': self.event_id,
            'destination_count': self.destination_count,
            'duplicate': self.duplicate,
        }


class EventService:
    def __init__(self, store, subscriptions):
        self.store = store
        self.subscriptions = subscriptions

    def publish(self, customer_id, document):
        topic = required_string(document, 'topic', limit=120)
        validate_topic(topic)
        event_id = document.get('event_id') or new_id('evt')
        event = Event(
            event_id=event_id, customer_id=customer_id,
            topic=topic, payload=document.get('data', {}),
        )
        body = encode_event(event)
        destinations = self.subscriptions.destinations_for(customer_id, topic)
        if not self.store.insert_event(event, body):
            return PublishReceipt(event_id, 0, True)
        deliveries = [
            Delivery(
                delivery_id=new_id('dlv'), subscription_id=subscription.subscription_id,
                event_id=event.event_id, url=subscription.url, body=body,
            )
            for subscription in destinations
        ]
        self.store.enqueue(deliveries)
        return PublishReceipt(event_id, len(deliveries), False)
