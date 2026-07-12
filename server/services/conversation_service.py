import datetime as dt
import json
import uuid
from contextlib import contextmanager
from typing import Dict, List, Optional

from sqlalchemy import func

from server.database import SessionLocal
from server.models import ConversationMessage, ConversationSession
from src.logger import logger


def utc_now():
    """Return the current timezone-aware UTC datetime."""
    return dt.datetime.now(dt.timezone.utc)


class ConversationService:
    """Persist live conversation messages and session runtime state."""

    def __init__(self):
        self._sequence_cache: Dict[str, int] = {}

    @contextmanager
    def _get_db(self):
        """Yield a short-lived SQLAlchemy session."""
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    def _get_next_sequence(self, db, session_id: str) -> int:
        """Return the next persisted message sequence for a session."""
        if session_id not in self._sequence_cache:
            max_seq = db.query(func.max(ConversationMessage.sequence)).filter_by(
                session_id=session_id
            ).scalar()
            self._sequence_cache[session_id] = int(max_seq or 0)
        self._sequence_cache[session_id] += 1
        return self._sequence_cache[session_id]

    async def create_session(
        self,
        session_id: str,
        user_id: str,
        first_message: Optional[str] = None,
    ) -> Optional[ConversationSession]:
        """Create a conversation metadata row for a local session."""
        with self._get_db() as db:
            try:
                existing = db.query(ConversationSession).filter_by(
                    session_id=session_id
                ).first()
                if existing:
                    logger.warning(f"Conversation session already exists: {session_id}")
                    return existing

                title = None
                if first_message:
                    title = first_message[:50]
                    if len(first_message) > 50:
                        title += "..."

                session = ConversationSession(
                    session_id=session_id,
                    user_id=user_id,
                    first_message=first_message[:500] if first_message else None,
                    title=title,
                    status="active",
                    created_at=utc_now(),
                    updated_at=utc_now(),
                )
                db.add(session)
                db.commit()
                db.refresh(session)

                logger.info(f"Created conversation session: {session_id}")
                return session
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to create conversation session: {e}")
                return None

    async def append_message(
        self,
        session_id: str,
        user_id: str,
        msg_type: str,
        content: Optional[str] = None,
        artifacts: Optional[List[Dict]] = None,
        metadata: Optional[Dict] = None,
    ) -> Optional[ConversationMessage]:
        """Append one conversation event without interrupting the main workflow on failure."""
        with self._get_db() as db:
            try:
                message = ConversationMessage(
                    id=str(uuid.uuid4()),
                    session_id=session_id,
                    user_id=user_id,
                    msg_type=msg_type,
                    content=content,
                    artifacts=json.dumps(artifacts, ensure_ascii=False) if artifacts else None,
                    msg_metadata=json.dumps(metadata, ensure_ascii=False) if metadata else None,
                    sequence=self._get_next_sequence(db, session_id),
                    created_at=utc_now(),
                )
                db.add(message)

                db.query(ConversationSession).filter_by(
                    session_id=session_id
                ).update(
                    {
                        "updated_at": utc_now(),
                        "message_count": ConversationSession.message_count + 1,
                    }
                )

                db.commit()
                return message
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to append message to session {session_id}: {e}")
                return None

    async def update_session_status(
        self,
        session_id: str,
        status: str,
        error_message: Optional[str] = None,
        step_count: Optional[int] = None,
        artifact_count: Optional[int] = None,
    ):
        """Update the current runtime status for one conversation session."""
        with self._get_db() as db:
            try:
                updates = {
                    "status": status,
                    "updated_at": utc_now(),
                }
                if error_message:
                    updates["error_message"] = error_message
                if step_count is not None:
                    updates["step_count"] = step_count
                if artifact_count is not None:
                    updates["artifact_count"] = artifact_count

                affected = db.query(ConversationSession).filter_by(
                    session_id=session_id
                ).update(updates)
                db.commit()
                if int(affected or 0) <= 0:
                    logger.warning(
                        "Session status update skipped because metadata is missing | "
                        f"session_id={session_id}, status={status}"
                    )
                else:
                    logger.info(f"Updated session status | session_id={session_id}, status={status}")
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to update session status: {e}")

    async def mark_stale_running_sessions(self) -> int:
        """Mark sessions left in `running` state as failed after server restart."""
        with self._get_db() as db:
            try:
                affected = (
                    db.query(ConversationSession)
                    .filter(ConversationSession.status == "running")
                    .update(
                        {
                            "status": "error",
                            "error_message": "Server restarted while task was running.",
                            "updated_at": utc_now(),
                        },
                        synchronize_session=False,
                    )
                )
                db.commit()
                if affected > 0:
                    logger.warning(f"Marked stale running sessions as error: count={affected}")
                return int(affected or 0)
            except Exception as e:
                db.rollback()
                logger.error(f"Failed to mark stale running sessions: {e}")
                return 0


conversation_service = ConversationService()
