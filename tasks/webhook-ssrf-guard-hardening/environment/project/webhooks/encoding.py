"""Event envelope serialization."""

import json
import re

TOPIC_PATTERN = re.compile(r'[a-z][a-z0-9_]*(?:\.[a-z][a-z0-9_]*)+\Z')
MAX_EVENT_BYTES = 1024 * 1024


class InvalidEvent(ValueError):
    pass


def validate_topic(topic):
    if not isinstance(topic, str) or not TOPIC_PATTERN.fullmatch(topic):
        raise InvalidEvent('Event topics use dotted lowercase names')
    if len(topic) > 120:
        raise InvalidEvent('Event topic exceeds 120 characters')
    return topic


def encode_event(event):
    validate_topic(event.topic)
    try:
        body = json.dumps(
            event.envelope(), ensure_ascii=False, separators=(',', ':'),
            allow_nan=False,
        ).encode('utf-8')
    except (TypeError, ValueError) as error:
        raise InvalidEvent('Event payload must be JSON serializable') from error
    if len(body) > MAX_EVENT_BYTES:
        raise InvalidEvent('Event exceeds the one MiB payload quota')
    return body


def decode_document(body):
    if len(body) > MAX_EVENT_BYTES:
        raise InvalidEvent('Document exceeds the payload quota')
    try:
        document = json.loads(body)
    except (UnicodeError, ValueError) as error:
        raise InvalidEvent('Document must contain UTF-8 JSON') from error
    if not isinstance(document, dict):
        raise InvalidEvent('Document must be an object')
    return document


def required_string(document, name, limit=255):
    value = document.get(name)
    if not isinstance(value, str) or not value.strip():
        raise InvalidEvent(f'{name} is required')
    if len(value) > limit:
        raise InvalidEvent(f'{name} exceeds {limit} characters')
    return value


def normalize_topics(topics):
    if not isinstance(topics, list) or not topics:
        raise InvalidEvent('At least one topic is required')
    if len(topics) > 64:
        raise InvalidEvent('A subscription supports at most 64 topics')
    result = []
    for topic in topics:
        if topic != '*':
            validate_topic(topic)
        if topic not in result:
            result.append(topic)
    return tuple(result)
