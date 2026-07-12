"""Local identity helpers."""

from typing import Optional

from fastapi import Cookie

from conf.system import SYS_CONFIG


def get_current_user_id(
    token: Optional[str] = Cookie(None),
    user_id: Optional[str] = Cookie(None),
) -> str:
    """Resolve the local user id without requiring authentication.

    Args:
        token: Ignored. Kept for compatibility with older clients.
        user_id: Optional user id cookie.

    Returns:
        The provided user id, or the configured local default user id.
    """
    return str(user_id or SYS_CONFIG.user_id_default)
