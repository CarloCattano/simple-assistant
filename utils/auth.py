from typing import Any

from config import ADMIN_ID


ADMIN_DENY_MESSAGE = "This is a private bot. You are not authorized to use it."


def is_admin(update: Any) -> bool:
    """Return True if the update comes from the configured admin user.

    Uses update.effective_user.id when available and compares it to ADMIN_ID
    loaded from the environment. Falls back safely to False on any error.
    """

    try:
        user = getattr(update, "effective_user", None)
        user_id = getattr(user, "id", None)
        return user_id is not None and str(user_id) == str(ADMIN_ID)
    except Exception:
        return False
