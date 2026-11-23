"""Concurrent dispatch of durable delivery records."""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from config import DELIVERY_WORKERS
from webhooks.deliver import BlockedURL, post_webhook
from webhooks.metrics import Metrics
from webhooks.models import Attempt
from webhooks.retries import outcome

logger = logging.getLogger(__name__)


class Dispatcher:
    def __init__(self, store, *, metrics=None, poll_interval=0.5):
        self.store = store
        self.metrics = metrics or Metrics()
        self.poll_interval = poll_interval
        self.stopping = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=16, thread_name_prefix='webhook')

    def deliver(self, delivery):
        started = time.time()
        status = None
        error_message = None
        permanent = False
        self.metrics.started()
        try:
            status = post_webhook(delivery.url, delivery.body)
        except BlockedURL as error:
            error_message = str(error)
            permanent = True
        except Exception as error:
            error_message = f'{type(error).__name__}: {error}'
        attempt = Attempt(
            delivery.delivery_id, delivery.attempts + 1, status,
            error_message, started, time.time(),
        )
        state, next_attempt_at = outcome(attempt, permanent=permanent)
        self.store.finish(attempt, state, next_attempt_at)
        self.metrics.completed(attempt)
        logger.info(
            'webhook delivery=%s attempt=%s state=%s status=%s',
            delivery.delivery_id, attempt.sequence, state.value, status,
        )
        return attempt

    def run_batch(self):
        deliveries = self.store.claim(time.time(), limit=DELIVERY_WORKERS)
        futures = {self.executor.submit(self.deliver, delivery): delivery for delivery in deliveries}
        completed = []
        for future in as_completed(futures):
            delivery = futures[future]
            try:
                completed.append(future.result())
            except Exception:
                logger.exception('Could not persist delivery %s', delivery.delivery_id)
        return completed

    def run_forever(self):
        try:
            while not self.stopping.is_set():
                completed = self.run_batch()
                if not completed:
                    self.stopping.wait(self.poll_interval)
        finally:
            self.executor.shutdown(wait=True)

    def stop(self):
        self.stopping.set()

    def close(self):
        self.stop()
        self.executor.shutdown(wait=True)
