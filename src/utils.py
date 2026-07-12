import asyncio
import random
import re
import sqlite3
import time
from typing import Awaitable, Callable, Optional, TypeVar

from sqlalchemy.exc import OperationalError as SAOperationalError

_JSON_FENCE_RE = re.compile(r"```json\s*(.*?)\s*```", re.DOTALL | re.IGNORECASE)


def clean_json_string(s: str) -> str:
    """Extract the first fenced JSON block, or return a lightly trimmed string."""
    if not s:
        return ""

    m = _JSON_FENCE_RE.search(s)
    if m:
        return m.group(1).strip()

    return s.strip('`')


T = TypeVar("T")

_RETRYABLE_SQLITE_TOKENS = (
    "database is locked",
    "database table is locked",
    "database schema is locked",
    "database is busy",
    "sqlite_busy",
)


def _is_retryable_sqlite_error(exc: BaseException) -> bool:
    """Return whether an exception represents a retryable SQLite lock/busy error."""
    root = exc

    if isinstance(exc, SAOperationalError) and getattr(exc, "orig", None):
        root = exc.orig

    while getattr(root, "__cause__", None) is not None:
        root = root.__cause__

    if isinstance(root, sqlite3.OperationalError):
        msg = str(root).lower()
        return any(token in msg for token in _RETRYABLE_SQLITE_TOKENS)

    msg = str(exc).lower()
    return any(token in msg for token in _RETRYABLE_SQLITE_TOKENS)


async def database_op_with_retry(
    op: Callable[..., Awaitable[T]],
    *,
    retries: int = 5,
    base_delay: float = 0.05,
    max_delay: float = 1.0,
    jitter: float = 0.2,
    max_elapsed: float = 3.0,
    logger: Optional[object] = None,
    op_name: str = "sqlite_write",
    **kwargs,
) -> T:
    """Run one async SQLite operation with bounded retry/backoff for lock contention."""
    start = time.monotonic()
    attempt = 0
    while True:
        try:
            return await op(**kwargs)

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            if not _is_retryable_sqlite_error(exc):
                raise

            attempt += 1
            elapsed = time.monotonic() - start

            if attempt > retries or elapsed >= max_elapsed:
                raise

            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)

            if jitter > 0:
                delay = delay * (1 + random.uniform(-jitter, jitter))

            if logger:
                logger.warning(
                    f"{op_name} hit SQLite lock/busy, retrying "
                    f"(attempt={attempt}/{retries}, delay={delay:.3f}s, elapsed={elapsed:.3f}s): {exc}"
                )

            await asyncio.sleep(max(delay, 0.0))
