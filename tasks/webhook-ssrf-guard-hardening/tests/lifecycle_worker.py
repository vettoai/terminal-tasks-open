"""Restricted application driver. Inputs describe only the current operation."""

import base64
import io
import json
from types import SimpleNamespace


def handle(work, message):
    from webhooks.api import Application
    from webhooks.events import EventService
    from webhooks.metrics import Metrics
    from webhooks.store import Store
    from webhooks.subscriptions import SubscriptionService

    store = Store(work / message['database'])
    customer = message['customer_id']
    if message['action'] == 'api':
        subscriptions = SubscriptionService(store)
        application = Application(subscriptions, EventService(store, subscriptions), store, Metrics())
        document = json.dumps(message['document']).encode()
        environ = dict(REQUEST_METHOD=message['method'], PATH_INFO=message['path'],
                       HTTP_X_CUSTOMER_ID=customer, CONTENT_TYPE='application/json',
                       CONTENT_LENGTH=str(len(document)))
        environ['wsgi.input'] = io.BytesIO(document)
        response = {}

        def start_response(status, headers, exc_info=None):
            response['status'] = int(status.split()[0])

        parts = application(environ, start_response)
        try:
            response['document'] = json.loads(b''.join(parts))
        finally:
            if hasattr(parts, 'close'):
                parts.close()
        return dict(kind='application', response=response)
    if message['action'] == 'batch':
        import webhooks.dispatcher as dispatch

        original_clock = dispatch.time
        if message.get('after_due'):
            deliveries = store.recent_deliveries(customer)
            now = max((delivery.next_attempt_at for delivery in deliveries), default=0) + 1
            dispatch.time = SimpleNamespace(time=lambda: now)
        dispatcher = dispatch.Dispatcher(store)
        try:
            dispatcher.run_batch()
        finally:
            dispatcher.close()
            dispatch.time = original_clock
        return dict(kind='application')
    if message['action'] in ('read', 'snapshot'):
        records = [dict(delivery_id=delivery.delivery_id, event_id=delivery.event_id,
                        url=delivery.url, body=base64.b64encode(delivery.body).decode(),
                        state=delivery.state.value, next_attempt_at=delivery.next_attempt_at,
                        history=store.attempts(delivery.delivery_id))
                   for delivery in store.recent_deliveries(customer)]
        result = dict(kind='application', records=records)
        if message['action'] == 'snapshot':
            result['subscriptions'] = [subscription.as_dict() for subscription in store.list_subscriptions(customer)]
        return result
    raise ValueError('Unknown application operation')
