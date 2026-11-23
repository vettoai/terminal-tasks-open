"""Internal WSGI interface, served behind the customer-authentication gateway."""

import json
import logging

from webhooks.encoding import InvalidEvent, decode_document, required_string
from webhooks.guard import BlockedURL
from webhooks.subscriptions import SubscriptionNotFound

logger = logging.getLogger(__name__)


class Application:
    def __init__(self, subscriptions, events, store, metrics):
        self.subscriptions = subscriptions
        self.events = events
        self.store = store
        self.metrics = metrics

    def __call__(self, environ, start_response):
        try:
            status, document = self.route(environ)
        except (InvalidEvent, BlockedURL) as error:
            status, document = '400 Bad Request', {'error': str(error)}
        except SubscriptionNotFound:
            status, document = '404 Not Found', {'error': 'Subscription not found'}
        except Exception:
            logger.exception('API request failed')
            status, document = '500 Internal Server Error', {'error': 'Internal error'}
        body = json.dumps(document, separators=(',', ':')).encode()
        start_response(status, [('Content-Type', 'application/json'), ('Content-Length', str(len(body)))])
        return [body]

    def read_document(self, environ):
        try:
            length = int(environ.get('CONTENT_LENGTH') or '0')
        except ValueError as error:
            raise InvalidEvent('Invalid content length') from error
        if length < 0 or length > 1024 * 1024:
            raise InvalidEvent('Request exceeds payload quota')
        return decode_document(environ['wsgi.input'].read(length))

    def route(self, environ):
        method = environ.get('REQUEST_METHOD', 'GET')
        path = environ.get('PATH_INFO', '/')
        if path == '/health' and method == 'GET':
            return '200 OK', {'status': 'ok'}
        if path == '/status' and method == 'GET':
            return '200 OK', {'queue': self.store.counts(), 'dispatcher': self.metrics.snapshot()}
        customer_id = environ.get('HTTP_X_CUSTOMER_ID')
        if not customer_id:
            return '401 Unauthorized', {'error': 'Customer identity is required'}
        if path == '/subscriptions':
            return self.subscription_collection(method, customer_id, environ)
        if path.startswith('/subscriptions/'):
            subscription_id = path.rsplit('/', 1)[-1]
            return self.subscription_item(method, customer_id, subscription_id, environ)
        if path == '/events' and method == 'POST':
            receipt = self.events.publish(customer_id, self.read_document(environ))
            return '202 Accepted', receipt.as_dict()
        if path == '/deliveries' and method == 'GET':
            return '200 OK', {'deliveries': [
                {'delivery_id': delivery.delivery_id, 'event_id': delivery.event_id,
                 'state': delivery.state.value, 'attempts': delivery.attempts}
                for delivery in self.store.recent_deliveries(customer_id)
            ]}
        return '404 Not Found', {'error': 'Unknown resource'}

    def subscription_collection(self, method, customer_id, environ):
        if method == 'GET':
            return '200 OK', {'subscriptions': [item.as_dict() for item in self.subscriptions.list(customer_id)]}
        if method == 'POST':
            document = self.read_document(environ)
            subscription = self.subscriptions.register(
                customer_id, required_string(document, 'url', limit=8192), document.get('topics'),
            )
            return '201 Created', subscription.as_dict()
        return '405 Method Not Allowed', {'error': 'Use GET or POST'}

    def subscription_item(self, method, customer_id, subscription_id, environ):
        if method == 'GET':
            return '200 OK', self.subscriptions.get(customer_id, subscription_id).as_dict()
        if method == 'DELETE':
            cancelled = self.subscriptions.disable(customer_id, subscription_id)
            return '200 OK', {'cancelled_deliveries': cancelled}
        if method == 'PATCH':
            document = self.read_document(environ)
            if 'url' in document:
                self.subscriptions.change_url(customer_id, subscription_id, required_string(document, 'url', limit=8192))
            if 'enabled' in document:
                if document['enabled'] is True:
                    self.subscriptions.enable(customer_id, subscription_id)
                elif document['enabled'] is False:
                    self.subscriptions.disable(customer_id, subscription_id)
                else:
                    raise InvalidEvent('enabled must be a boolean')
            return '200 OK', self.subscriptions.get(customer_id, subscription_id).as_dict()
        return '405 Method Not Allowed', {'error': 'Use GET, PATCH or DELETE'}
