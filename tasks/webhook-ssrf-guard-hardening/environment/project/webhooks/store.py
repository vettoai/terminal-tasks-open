"""Durable records with short per-operation SQLite transactions."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path

from webhooks.models import Delivery, DeliveryState, Subscription
from webhooks.schema import configure, initialize


class Store:
    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            initialize(connection)

    @contextmanager
    def connection(self):
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        configure(connection)
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def create_subscription(self, subscription):
        with self.connection() as connection:
            connection.execute(
                'INSERT INTO subscriptions VALUES (?, ?, ?, ?, ?, ?)',
                (subscription.subscription_id, subscription.customer_id,
                 subscription.url, json.dumps(subscription.topics),
                 subscription.enabled, subscription.created_at),
            )
        return subscription

    def get_subscription(self, subscription_id):
        with self.connection() as connection:
            row = connection.execute(
                'SELECT * FROM subscriptions WHERE subscription_id=?',
                (subscription_id,),
            ).fetchone()
        return Subscription.from_row(row) if row else None

    def list_subscriptions(self, customer_id, *, enabled_only=False):
        query = 'SELECT * FROM subscriptions WHERE customer_id=?'
        if enabled_only:
            query += ' AND enabled=1'
        query += ' ORDER BY created_at, subscription_id'
        with self.connection() as connection:
            rows = connection.execute(query, (customer_id,)).fetchall()
        return [Subscription.from_row(row) for row in rows]

    def set_subscription_enabled(self, subscription_id, enabled):
        with self.connection() as connection:
            result = connection.execute(
                'UPDATE subscriptions SET enabled=? WHERE subscription_id=?',
                (bool(enabled), subscription_id),
            )
        return result.rowcount == 1

    def replace_destination(self, subscription_id, url):
        with self.connection() as connection:
            result = connection.execute(
                'UPDATE subscriptions SET url=? WHERE subscription_id=?',
                (url, subscription_id),
            )
        return result.rowcount == 1

    def insert_event(self, event, body):
        with self.connection() as connection:
            result = connection.execute(
                'INSERT OR IGNORE INTO events VALUES (?, ?, ?, ?, ?)',
                (event.event_id, event.customer_id, event.topic, body, event.occurred_at),
            )
        return result.rowcount == 1

    def event_exists(self, event_id):
        with self.connection() as connection:
            row = connection.execute('SELECT 1 FROM events WHERE event_id=?', (event_id,)).fetchone()
        return row is not None

    def enqueue(self, deliveries):
        with self.connection() as connection:
            for delivery in deliveries:
                connection.execute(
                    'INSERT OR IGNORE INTO deliveries VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)',
                    (delivery.delivery_id, delivery.subscription_id, delivery.event_id,
                     delivery.url, delivery.body, delivery.state.value, delivery.attempts,
                     delivery.next_attempt_at, delivery.lease_until),
                )

    def claim(self, now, *, limit=16, lease_seconds=120):
        with self.connection() as connection:
            connection.execute('BEGIN IMMEDIATE')
            rows = connection.execute(
                "SELECT * FROM deliveries WHERE "
                "(state IN ('pending', 'retry') AND next_attempt_at<=?) "
                "OR (state='leased' AND lease_until<=?) "
                'ORDER BY next_attempt_at, delivery_id LIMIT ?',
                (now, now, limit),
            ).fetchall()
            for row in rows:
                connection.execute(
                    "UPDATE deliveries SET state='leased', lease_until=? WHERE delivery_id=?",
                    (now + lease_seconds, row['delivery_id']),
                )
        return [Delivery.from_row(row) for row in rows]

    def finish(self, attempt, state, next_attempt_at=0):
        with self.connection() as connection:
            connection.execute(
                'INSERT INTO attempts VALUES (?, ?, ?, ?, ?, ?)',
                (attempt.delivery_id, attempt.sequence, attempt.status,
                 attempt.error, attempt.started_at, attempt.finished_at),
            )
            connection.execute(
                'UPDATE deliveries SET state=?, attempts=?, next_attempt_at=?, lease_until=0 '
                'WHERE delivery_id=?',
                (state.value, attempt.sequence, next_attempt_at, attempt.delivery_id),
            )

    def cancel_pending(self, subscription_id):
        with self.connection() as connection:
            result = connection.execute(
                "UPDATE deliveries SET state='cancelled' WHERE subscription_id=? "
                "AND state IN ('pending', 'retry')", (subscription_id,),
            )
        return result.rowcount

    def get_delivery(self, delivery_id):
        with self.connection() as connection:
            row = connection.execute(
                'SELECT * FROM deliveries WHERE delivery_id=?', (delivery_id,),
            ).fetchone()
        return Delivery.from_row(row) if row else None

    def attempts(self, delivery_id):
        with self.connection() as connection:
            rows = connection.execute(
                'SELECT * FROM attempts WHERE delivery_id=? ORDER BY sequence',
                (delivery_id,),
            ).fetchall()
        return [dict(row) for row in rows]

    def counts(self):
        with self.connection() as connection:
            rows = connection.execute(
                'SELECT state, COUNT(*) AS count FROM deliveries GROUP BY state',
            ).fetchall()
        return {row['state']: row['count'] for row in rows}

    def recent_deliveries(self, customer_id, limit=100):
        with self.connection() as connection:
            rows = connection.execute(
                'SELECT deliveries.* FROM deliveries JOIN subscriptions '
                'USING (subscription_id) WHERE subscriptions.customer_id=? '
                'ORDER BY deliveries.rowid DESC LIMIT ?', (customer_id, limit),
            ).fetchall()
        return [Delivery.from_row(row) for row in rows]

    def retry_delivery(self, delivery_id, now):
        with self.connection() as connection:
            result = connection.execute(
                "UPDATE deliveries SET state='retry', next_attempt_at=? "
                "WHERE delivery_id=? AND state IN ('exhausted', 'cancelled')",
                (now, delivery_id),
            )
        return result.rowcount == 1
