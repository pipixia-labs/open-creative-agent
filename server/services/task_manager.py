"""Track in-process workflow tasks and their event queues."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Dict, Optional


@dataclass
class TaskEntry:
    """Running workflow task metadata for one session."""

    session_id: str
    user_id: str
    task: asyncio.Task
    queue: asyncio.Queue


class TaskManager:
    """Manage running workflow tasks in the current process."""

    def __init__(self) -> None:
        self._entries: Dict[str, TaskEntry] = {}
        self._lock = asyncio.Lock()

    async def register(
        self,
        session_id: str,
        user_id: str,
        task: asyncio.Task,
        queue: asyncio.Queue,
    ) -> None:
        """Register a running workflow task for a session."""
        async with self._lock:
            self._entries[session_id] = TaskEntry(
                session_id=session_id,
                user_id=user_id,
                task=task,
                queue=queue,
            )

        def _cleanup_done(_: asyncio.Task) -> None:
            asyncio.create_task(self.unregister(session_id))

        task.add_done_callback(_cleanup_done)

    async def unregister(self, session_id: str) -> None:
        """Remove a running workflow task entry for a session."""
        async with self._lock:
            self._entries.pop(session_id, None)

    async def is_running(self, session_id: str) -> bool:
        """Return whether a session currently has a running workflow task."""
        async with self._lock:
            entry = self._entries.get(session_id)
            return bool(entry and not entry.task.done())

    async def get_queue(self, session_id: str) -> Optional[asyncio.Queue]:
        """Return the event queue for a running session task, if any."""
        async with self._lock:
            entry = self._entries.get(session_id)
            if not entry:
                return None
            return entry.queue

    async def get_task(self, session_id: str) -> Optional[asyncio.Task]:
        """Return the asyncio task for a running session, if any."""
        async with self._lock:
            entry = self._entries.get(session_id)
            if not entry:
                return None
            return entry.task


task_manager = TaskManager()
