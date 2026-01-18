import logging
import os
from typing import Any

try:  # Optional at import time to keep tests and tools lightweight
    from telegram import Update  # type: ignore
except ImportError:  # pragma: no cover - telegram is only required for the bot process
    Update = Any  # type: ignore

from config import ADMIN_ID

RED_COL = "\033[91m"
GREEN_COL = "\033[92m"
RST = "\033[0m"

logger = logging.getLogger("usage")

_level_name = os.getenv("LOG_LEVEL", "INFO").upper()
_level = getattr(logging, _level_name, logging.INFO)

handler = logging.FileHandler("usage.log")
formatter = logging.Formatter("%(asctime)s - %(message)s")
handler.setFormatter(formatter)
handler.setLevel(_level)
logger.addHandler(handler)

logger.setLevel(_level)


def log_user_action(action: str, update: Update, extra: str = ""):
    effective_user = update.effective_user
    effective_message = update.effective_message

    if not effective_user and effective_message and effective_message.from_user:
        effective_user = effective_message.from_user

    user_id = getattr(effective_user, "id", "unknown")
    username = getattr(effective_user, "username", None) or "N/A"
    full_name = (
        getattr(effective_user, "full_name", None)
        or getattr(effective_user, "name", None)
        or "?"
    )

    user_info = f"\nUser: {user_id} - @{username} ({full_name})"
    log_entry = f"{user_info} \n Action: {action} \n ========== \n"
    if extra:
        log_entry += f" | Detail: {extra}\n --- \n"

    colored_entry = f"{GREEN_COL}{log_entry}{RST}" if str(user_id) == str(ADMIN_ID) else f"{RED_COL}{log_entry}{RST}"

    logger.warning(colored_entry)

def error(msg: str):
    logger.error(msg)

def info(msg: str):
    logger.info(msg)

def warn(msg: str):
    logger.warning(msg)

def debug(msg: str):
    logger.debug(msg)