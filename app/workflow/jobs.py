"""
Background execution for long-running workflow steps.

Workflow routes validate state synchronously, mark entities as ``processing``,
return HTTP 202, then run LLM work in a thread pool so the request is not held
open for minutes.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="ghostwriter-workflow")


def enqueue(fn: Callable[..., T], /, *args, **kwargs) -> None:
    """Run *fn* in the workflow thread pool; log unexpected failures."""

    def _run() -> None:
        try:
            fn(*args, **kwargs)
        except Exception:
            logger.exception("Background workflow job failed")

    _executor.submit(_run)


def shutdown() -> None:
    _executor.shutdown(wait=False, cancel_futures=True)
