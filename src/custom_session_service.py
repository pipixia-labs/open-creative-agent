from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Optional, TypeVar

from google.adk.sessions import BaseSessionService, DatabaseSessionService
from google.adk.events.event import Event
from google.adk.sessions.base_session_service import GetSessionConfig
from google.adk.sessions.base_session_service import ListSessionsResponse
from google.adk.sessions.session import Session
import asyncio

from src.utils import database_op_with_retry

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    retries: int = 5
    base_delay: float = 0.05
    max_delay: float = 1.0
    jitter: float = 0.2
    max_elapsed: float = 3.0


@dataclass(frozen=True)
class TimeoutPolicy:
    create_session: Optional[float] = 3.0
    get_session: Optional[float] = 3.0
    list_sessions: Optional[float] = 5.0
    delete_session: Optional[float] = 3.0
    append_event: Optional[float] = 3.0


class ReliableDatabaseSessionService(BaseSessionService):
    def __init__(
        self,
        inner: "DatabaseSessionService",
        *,
        retry_policy: RetryPolicy = RetryPolicy(),
        timeout_policy: TimeoutPolicy = TimeoutPolicy(),
        logger: Optional[object] = None,
        retry_on: frozenset[str] = frozenset({"append_event", "delete_session", "create_session"}),
    ) -> None:
        self._inner = inner
        self._rp = retry_policy
        self._tp = timeout_policy
        self._logger = logger
        self._retry_on = retry_on

    async def _with_timeout(
        self,
        coro: Awaitable[T],
        timeout_s: Optional[float],
        *,
        op_name: str,
    ) -> T:
        if timeout_s is None:
            return await coro
        try:
            return await asyncio.wait_for(coro, timeout=timeout_s)
        except asyncio.TimeoutError as exc:
            raise TimeoutError(f"{op_name} timed out after {timeout_s}s") from exc

    async def _call(
        self,
        op: Callable[..., Awaitable[T]],
        *,
        op_name: str,
        timeout_s: Optional[float],
        enable_retry: bool,
        **kwargs: Any,
    ) -> T:
        async def _invoke() -> T:
            return await self._with_timeout(op(**kwargs), timeout_s, op_name=op_name)

        if not enable_retry:
            return await _invoke()

        async def op_for_retry(**_kw: Any) -> T:
            return await _invoke()

        return await database_op_with_retry(
            op_for_retry,
            retries=self._rp.retries,
            base_delay=self._rp.base_delay,
            max_delay=self._rp.max_delay,
            jitter=self._rp.jitter,
            max_elapsed=self._rp.max_elapsed,
            logger=self._logger,
            op_name=op_name,
        )

    async def create_session(
        self,
        *,
        app_name: str,
        user_id: str,
        state: Optional[dict[str, Any]] = None,
        session_id: Optional[str] = None,
    ) -> "Session":
        return await self._call(
            self._inner.create_session,
            op_name="db.create_session",
            timeout_s=self._tp.create_session,
            enable_retry=("create_session" in self._retry_on),
            app_name=app_name,
            user_id=user_id,
            state=state,
            session_id=session_id,
        )

    async def get_session(
        self,
        *,
        app_name: str,
        user_id: str,
        session_id: str,
        config: Optional["GetSessionConfig"] = None,
    ) -> Optional["Session"]:
        return await self._call(
            self._inner.get_session,
            op_name="db.get_session",
            timeout_s=self._tp.get_session,
            enable_retry=("get_session" in self._retry_on),
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
            config=config,
        )

    async def list_sessions(
        self,
        *,
        app_name: str,
        user_id: Optional[str] = None,
    ) -> "ListSessionsResponse":
        return await self._call(
            self._inner.list_sessions,
            op_name="db.list_sessions",
            timeout_s=self._tp.list_sessions,
            enable_retry=("list_sessions" in self._retry_on),
            app_name=app_name,
            user_id=user_id,
        )

    async def delete_session(self, app_name: str, user_id: str, session_id: str) -> None:
        return await self._call(
            self._inner.delete_session,
            op_name="db.delete_session",
            timeout_s=self._tp.delete_session,
            enable_retry=("delete_session" in self._retry_on),
            app_name=app_name,
            user_id=user_id,
            session_id=session_id,
        )

    async def append_event(self, session: "Session", event: "Event") -> "Event":
        return await self._call(
            self._inner.append_event,
            op_name="db.append_event",
            timeout_s=self._tp.append_event,
            enable_retry=("append_event" in self._retry_on),
            session=session,
            event=event,
        )

    @property
    def inner(self) -> "DatabaseSessionService":
        return self._inner


def normalize_async_sqlite_db_url(db_url: str) -> str:
    """
    Ensure sqlite URLs use the async driver required by ADK's session service.

    Args:
        db_url: Raw database URL from configuration/runtime setup.

    Returns:
        Database URL compatible with SQLAlchemy asyncio engine initialization.
    """
    if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite+aiosqlite:///"):
        return db_url.replace("sqlite:///", "sqlite+aiosqlite:///", 1)
    return db_url


def build_session_service(db_url: str, *, logger: Optional[object] = None) -> ReliableDatabaseSessionService:
    normalized_db_url = normalize_async_sqlite_db_url(db_url)
    raw = DatabaseSessionService(normalized_db_url)
    return ReliableDatabaseSessionService(
        raw,
        logger=logger,
        retry_policy=RetryPolicy(retries=5, max_elapsed=3.0),
        timeout_policy=TimeoutPolicy(append_event=2.0),
        retry_on=frozenset({"append_event", "delete_session", "create_session"}),
    )
