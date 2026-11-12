"""Answer inline queries without waiting behind private-message generation."""
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import logging
from threading import Lock
from time import monotonic

logger = logging.getLogger(__name__)


class InlineQueryDispatcher:
    """Bounded fast path; only the newest waiting query per user is retained.

    The pool executes query acknowledgements, never model generation. Drainers
    avoid an unbounded ThreadPoolExecutor task queue and serialize each sender.
    """

    def __init__(self, handler, *, max_workers=2, max_pending=128,
                 max_age=8, clock=monotonic):
        if max_workers < 1 or max_pending < 1 or max_age <= 0:
            raise ValueError('Dispatcher limits must be positive')
        self.handler = handler
        self.max_workers = max_workers
        self.max_pending = max_pending
        self.max_age = max_age
        self.clock = clock
        self._lock = Lock()
        self._pending = OrderedDict()
        self._active = set()
        self._workers = 0
        self._closed = False
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix='inline-query',
        )

    def dispatch(self, queries):
        """Receive an SDK inline-query batch without using its message pool."""
        with self._lock:
            if self._closed:
                return
            for query in queries:
                owner = getattr(getattr(query, 'from_user', None), 'id', None)
                if owner is None:
                    continue
                self._pending.pop(owner, None)
                if len(self._pending) >= self.max_pending:
                    self._pending.popitem(last=False)
                self._pending[owner] = (query, self.clock())
            while self._pending and self._workers < self.max_workers:
                self._workers += 1
                try:
                    self._executor.submit(self._drain)
                except Exception as error:
                    self._workers -= 1
                    logger.warning('Could not schedule inline query (%s)', type(error).__name__)
                    break

    def _drain(self):
        while True:
            with self._lock:
                if self._closed:
                    self._workers -= 1
                    return
                owner = next((key for key in self._pending if key not in self._active), None)
                if owner is None:
                    self._workers -= 1
                    return
                query, received = self._pending.pop(owner)
                if self.clock() - received > self.max_age:
                    continue
                self._active.add(owner)
            try:
                self.handler(query)
            except Exception as error:
                # Network/client errors can contain a bot token in their URL.
                logger.warning('Inline query failed (%s)', type(error).__name__)
            finally:
                with self._lock:
                    self._active.discard(owner)

    def close(self, *, wait=False):
        """Discard waiting queries; already executing calls may finish."""
        with self._lock:
            self._closed = True
            self._pending.clear()
        self._executor.shutdown(wait=wait, cancel_futures=True)
