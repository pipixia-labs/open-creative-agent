"""Token usage service.

This service parses ADK event usage metadata and persists:
1. per-call token usage records
2. per-session token aggregates
"""

from __future__ import annotations

import datetime as dt
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable, Optional

from sqlalchemy.exc import IntegrityError

from server.database import SessionLocal
from server.models import ConversationSession, TokenUsageRecord
from src.logger import logger


def utc_now() -> dt.datetime:
    """Return timezone-aware UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


@dataclass
class TokenUsageMetrics:
    """Normalized token metrics extracted from a usage metadata object."""

    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    prompt_text_tokens: int
    prompt_image_tokens: int
    prompt_video_tokens: int
    completion_text_tokens: int
    completion_image_tokens: int
    completion_video_tokens: int
    breakdown_available: bool


class TokenUsageService:
    """Persist token usage details and maintain session-level aggregates."""

    def __init__(self, session_factory=SessionLocal):
        self._session_factory = session_factory

    @contextmanager
    def _get_db(self):
        db = self._session_factory()
        try:
            yield db
        finally:
            db.close()

    @staticmethod
    def _safe_int(value: Any) -> int:
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @classmethod
    def _normalize_modality(cls, modality: Any) -> str:
        if modality is None:
            return ""
        if hasattr(modality, "value"):
            modality = modality.value
        return str(modality).strip().upper()

    @classmethod
    def _split_modality_tokens(cls, details: Optional[Iterable[Any]]) -> tuple[int, int, int]:
        """Split modality token details into (text, image, video)."""
        text_tokens = 0
        image_tokens = 0
        video_tokens = 0

        if not details:
            return text_tokens, image_tokens, video_tokens

        for item in details:
            if item is None:
                continue

            modality = None
            token_count = 0
            if isinstance(item, dict):
                modality = item.get("modality")
                token_count = cls._safe_int(item.get("token_count"))
            else:
                modality = getattr(item, "modality", None)
                token_count = cls._safe_int(getattr(item, "token_count", 0))

            modality_value = cls._normalize_modality(modality)
            if modality_value in {"TEXT", "DOCUMENT"}:
                text_tokens += token_count
            elif modality_value == "IMAGE":
                image_tokens += token_count
            elif modality_value == "VIDEO":
                video_tokens += token_count

        return text_tokens, image_tokens, video_tokens

    @classmethod
    def parse_usage_metadata(cls, usage_metadata: Any) -> Optional[TokenUsageMetrics]:
        """Parse ADK usage metadata into normalized token metrics."""
        if usage_metadata is None:
            return None

        prompt_tokens = cls._safe_int(getattr(usage_metadata, "prompt_token_count", 0))
        completion_tokens = cls._safe_int(getattr(usage_metadata, "candidates_token_count", 0))
        total_tokens = cls._safe_int(getattr(usage_metadata, "total_token_count", 0))

        prompt_details = getattr(usage_metadata, "prompt_tokens_details", None)
        completion_details = getattr(usage_metadata, "candidates_tokens_details", None)
        breakdown_available = bool(prompt_details or completion_details)

        prompt_text_tokens, prompt_image_tokens, prompt_video_tokens = cls._split_modality_tokens(prompt_details)
        completion_text_tokens, completion_image_tokens, completion_video_tokens = cls._split_modality_tokens(
            completion_details
        )

        if total_tokens <= 0:
            total_tokens = prompt_tokens + completion_tokens

        if completion_tokens <= 0 and total_tokens > 0 and prompt_tokens > 0:
            completion_tokens = max(total_tokens - prompt_tokens, 0)

        return TokenUsageMetrics(
            prompt_tokens=prompt_tokens,
            completion_tokens=completion_tokens,
            total_tokens=total_tokens,
            prompt_text_tokens=prompt_text_tokens,
            prompt_image_tokens=prompt_image_tokens,
            prompt_video_tokens=prompt_video_tokens,
            completion_text_tokens=completion_text_tokens,
            completion_image_tokens=completion_image_tokens,
            completion_video_tokens=completion_video_tokens,
            breakdown_available=breakdown_available,
        )

    @staticmethod
    def _resolve_event_id(event: Any) -> Optional[str]:
        event_id = getattr(event, "id", None)
        if event_id:
            return str(event_id)

        invocation_id = getattr(event, "invocation_id", None)
        interaction_id = getattr(event, "interaction_id", None)
        timestamp = getattr(event, "timestamp", None)
        author = getattr(event, "author", None)

        if invocation_id or interaction_id or timestamp:
            return f"fallback:{invocation_id}:{interaction_id}:{timestamp}:{author}"
        return None

    async def record_event_usage(
        self,
        *,
        user_id: str,
        session_id: str,
        event: Any,
        component: str,
        agent_name: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> bool:
        """Record one event usage into detail and aggregate tables.

        Returns True when a new usage record is persisted, False otherwise.
        """
        usage_metadata = getattr(event, "usage_metadata", None)
        metrics = self.parse_usage_metadata(usage_metadata)
        if metrics is None:
            return False

        event_id = self._resolve_event_id(event)
        if not event_id:
            logger.warning("Token usage skipped: event has no stable identifier.")
            return False

        resolved_agent_name = agent_name or getattr(event, "author", None) or "unknown"
        resolved_model_name = model_name or getattr(event, "model_version", None)

        with self._get_db() as db:
            try:
                session = db.query(ConversationSession).filter_by(
                    session_id=session_id,
                    user_id=user_id,
                ).first()

                if not session:
                    session = ConversationSession(
                        session_id=session_id,
                        user_id=user_id,
                        status="active",
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    db.add(session)
                    db.flush()

                db.add(
                    TokenUsageRecord(
                        id=str(uuid.uuid4()),
                        event_id=event_id,
                        session_id=session_id,
                        user_id=user_id,
                        component=component,
                        agent_name=resolved_agent_name,
                        model_name=resolved_model_name,
                        prompt_tokens=metrics.prompt_tokens,
                        completion_tokens=metrics.completion_tokens,
                        total_tokens=metrics.total_tokens,
                        prompt_text_tokens=metrics.prompt_text_tokens,
                        prompt_image_tokens=metrics.prompt_image_tokens,
                        prompt_video_tokens=metrics.prompt_video_tokens,
                        completion_text_tokens=metrics.completion_text_tokens,
                        completion_image_tokens=metrics.completion_image_tokens,
                        completion_video_tokens=metrics.completion_video_tokens,
                        breakdown_available=metrics.breakdown_available,
                        created_at=utc_now(),
                    )
                )

                session.prompt_tokens_total = (session.prompt_tokens_total or 0) + metrics.prompt_tokens
                session.completion_tokens_total = (session.completion_tokens_total or 0) + metrics.completion_tokens
                session.total_tokens_total = (session.total_tokens_total or 0) + metrics.total_tokens
                session.llm_call_count = (session.llm_call_count or 0) + 1
                session.prompt_text_tokens_total = (session.prompt_text_tokens_total or 0) + metrics.prompt_text_tokens
                session.prompt_image_tokens_total = (session.prompt_image_tokens_total or 0) + metrics.prompt_image_tokens
                session.prompt_video_tokens_total = (session.prompt_video_tokens_total or 0) + metrics.prompt_video_tokens
                session.completion_text_tokens_total = (session.completion_text_tokens_total or 0) + metrics.completion_text_tokens
                session.completion_image_tokens_total = (
                    (session.completion_image_tokens_total or 0) + metrics.completion_image_tokens
                )
                session.completion_video_tokens_total = (
                    (session.completion_video_tokens_total or 0) + metrics.completion_video_tokens
                )
                session.updated_at = utc_now()

                db.commit()
                return True

            except IntegrityError:
                db.rollback()
                logger.debug(f"Token usage duplicate skipped: event_id={event_id}")
                return False
            except Exception as exc:
                db.rollback()
                logger.error(
                    f"Failed to persist token usage | user_id={user_id}, session_id={session_id}, error={exc}"
                )
                return False

    async def record_external_usage(
        self,
        *,
        user_id: str,
        session_id: str,
        component: str,
        agent_name: str,
        model_name: Optional[str],
        usage: dict[str, Any],
        event_id: Optional[str] = None,
    ) -> bool:
        """Record token usage from non-ADK-event provider responses."""
        metrics = TokenUsageMetrics(
            prompt_tokens=self._safe_int(usage.get("prompt_tokens", 0)),
            completion_tokens=self._safe_int(usage.get("completion_tokens", 0)),
            total_tokens=self._safe_int(usage.get("total_tokens", 0)),
            prompt_text_tokens=self._safe_int(usage.get("prompt_text_tokens", 0)),
            prompt_image_tokens=self._safe_int(usage.get("prompt_image_tokens", 0)),
            prompt_video_tokens=self._safe_int(usage.get("prompt_video_tokens", 0)),
            completion_text_tokens=self._safe_int(usage.get("completion_text_tokens", 0)),
            completion_image_tokens=self._safe_int(usage.get("completion_image_tokens", 0)),
            completion_video_tokens=self._safe_int(usage.get("completion_video_tokens", 0)),
            breakdown_available=bool(usage.get("breakdown_available", False)),
        )
        if metrics.total_tokens <= 0:
            metrics.total_tokens = metrics.prompt_tokens + metrics.completion_tokens
        if metrics.total_tokens <= 0:
            # Nothing to record.
            return False

        resolved_event_id = event_id or f"external:{uuid.uuid4()}"
        with self._get_db() as db:
            try:
                session = db.query(ConversationSession).filter_by(
                    session_id=session_id,
                    user_id=user_id,
                ).first()
                if not session:
                    session = ConversationSession(
                        session_id=session_id,
                        user_id=user_id,
                        status="active",
                        created_at=utc_now(),
                        updated_at=utc_now(),
                    )
                    db.add(session)
                    db.flush()

                db.add(
                    TokenUsageRecord(
                        id=str(uuid.uuid4()),
                        event_id=resolved_event_id,
                        session_id=session_id,
                        user_id=user_id,
                        component=component,
                        agent_name=agent_name,
                        model_name=model_name,
                        prompt_tokens=metrics.prompt_tokens,
                        completion_tokens=metrics.completion_tokens,
                        total_tokens=metrics.total_tokens,
                        prompt_text_tokens=metrics.prompt_text_tokens,
                        prompt_image_tokens=metrics.prompt_image_tokens,
                        prompt_video_tokens=metrics.prompt_video_tokens,
                        completion_text_tokens=metrics.completion_text_tokens,
                        completion_image_tokens=metrics.completion_image_tokens,
                        completion_video_tokens=metrics.completion_video_tokens,
                        breakdown_available=metrics.breakdown_available,
                        created_at=utc_now(),
                    )
                )

                session.prompt_tokens_total = (session.prompt_tokens_total or 0) + metrics.prompt_tokens
                session.completion_tokens_total = (session.completion_tokens_total or 0) + metrics.completion_tokens
                session.total_tokens_total = (session.total_tokens_total or 0) + metrics.total_tokens
                session.llm_call_count = (session.llm_call_count or 0) + 1
                session.prompt_text_tokens_total = (session.prompt_text_tokens_total or 0) + metrics.prompt_text_tokens
                session.prompt_image_tokens_total = (session.prompt_image_tokens_total or 0) + metrics.prompt_image_tokens
                session.prompt_video_tokens_total = (session.prompt_video_tokens_total or 0) + metrics.prompt_video_tokens
                session.completion_text_tokens_total = (session.completion_text_tokens_total or 0) + metrics.completion_text_tokens
                session.completion_image_tokens_total = (
                    (session.completion_image_tokens_total or 0) + metrics.completion_image_tokens
                )
                session.completion_video_tokens_total = (
                    (session.completion_video_tokens_total or 0) + metrics.completion_video_tokens
                )
                session.updated_at = utc_now()

                db.commit()
                return True
            except IntegrityError:
                db.rollback()
                return False
            except Exception as exc:
                db.rollback()
                logger.error(
                    f"Failed to persist external token usage | user_id={user_id}, session_id={session_id}, error={exc}"
                )
                return False


token_usage_service = TokenUsageService()
