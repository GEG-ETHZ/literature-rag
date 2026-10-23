"""Wait for the corpus to be free: RAG Engine runs only one import per corpus at a time."""

import time
from collections.abc import Callable
from typing import TypeVar

T = TypeVar("T")

BUSY_MARKER = "other operations running on the RagCorpus"
WAIT_SECONDS = 20
MAX_WAIT_SECONDS = 480


def is_corpus_busy(error: Exception) -> bool:
    """Whether ``error`` is RAG Engine refusing an import because another one is running."""
    return BUSY_MARKER in str(error)


def call_when_free[T](
    action: Callable[[], T],
    sleep: Callable[[float], None] = time.sleep,
    wait_seconds: float = WAIT_SECONDS,
    max_wait_seconds: float = MAX_WAIT_SECONDS,
) -> T:
    """Run ``action``, retrying while the corpus is busy, at most ``max_wait_seconds``; other errors raise."""
    waited = 0.0
    while True:
        try:
            return action()
        except Exception as error:
            if not is_corpus_busy(error) or waited >= max_wait_seconds:
                raise
            sleep(wait_seconds)
            waited += wait_seconds
