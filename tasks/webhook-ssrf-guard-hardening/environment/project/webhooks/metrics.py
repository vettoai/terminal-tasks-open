"""Process-local counters for the operations status endpoint."""

import threading
from collections import Counter, deque


class Metrics:
    def __init__(self, recent_limit=256):
        self.lock = threading.Lock()
        self.counters = Counter()
        self.durations = deque(maxlen=recent_limit)
        self.in_flight = 0

    def started(self):
        with self.lock:
            self.in_flight += 1
            self.counters['started'] += 1

    def completed(self, attempt):
        with self.lock:
            self.in_flight = max(0, self.in_flight - 1)
            self.counters['completed'] += 1
            self.counters['successful' if attempt.successful else 'failed'] += 1
            if attempt.status is not None:
                self.counters[f'http_{attempt.status // 100}xx'] += 1
            self.durations.append(attempt.duration)

    def snapshot(self):
        with self.lock:
            durations = sorted(self.durations)
            result = dict(self.counters)
            result['in_flight'] = self.in_flight
            result['recent_samples'] = len(durations)
            result['recent_mean_seconds'] = sum(durations) / len(durations) if durations else 0
            result['recent_max_seconds'] = durations[-1] if durations else 0
            return result
