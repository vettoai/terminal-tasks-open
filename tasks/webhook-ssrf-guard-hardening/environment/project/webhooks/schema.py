"""SQLite schema for subscriptions and durable delivery queues."""

SCHEMA = """
CREATE TABLE IF NOT EXISTS subscriptions (
    subscription_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    url TEXT NOT NULL,
    topics TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS subscriptions_by_customer
ON subscriptions(customer_id, enabled);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    customer_id TEXT NOT NULL,
    topic TEXT NOT NULL,
    envelope BLOB NOT NULL,
    occurred_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_customer
ON events(customer_id, occurred_at);

CREATE TABLE IF NOT EXISTS deliveries (
    delivery_id TEXT PRIMARY KEY,
    subscription_id TEXT NOT NULL REFERENCES subscriptions(subscription_id),
    event_id TEXT NOT NULL REFERENCES events(event_id),
    url TEXT NOT NULL,
    body BLOB NOT NULL,
    state TEXT NOT NULL,
    attempts INTEGER NOT NULL DEFAULT 0,
    next_attempt_at REAL NOT NULL DEFAULT 0,
    lease_until REAL NOT NULL DEFAULT 0,
    UNIQUE(subscription_id, event_id)
);
CREATE INDEX IF NOT EXISTS deliveries_ready
ON deliveries(state, next_attempt_at, lease_until);

CREATE TABLE IF NOT EXISTS attempts (
    delivery_id TEXT NOT NULL REFERENCES deliveries(delivery_id),
    sequence INTEGER NOT NULL,
    status INTEGER,
    error TEXT,
    started_at REAL NOT NULL,
    finished_at REAL NOT NULL,
    PRIMARY KEY(delivery_id, sequence)
);
"""


def configure(connection):
    connection.execute('PRAGMA foreign_keys=ON')
    connection.execute('PRAGMA busy_timeout=5000')


def initialize(connection):
    configure(connection)
    connection.execute('PRAGMA journal_mode=WAL')
    connection.executescript(SCHEMA)


def schema_version(connection):
    return connection.execute('PRAGMA user_version').fetchone()[0]
