import logging
import os
from typing import Any

try:  # Optional at import time to keep tests and tools lightweight
    from telegram import Update  # type: ignore
except ImportError:  # pragma: no cover - telegram is only required for the bot process
    Update = Any  # type: ignore

from config import ADMIN_ID

RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RST = "\033[0m"

logger = logging.getLogger("usage")

_level_name = os.getenv("LOG_LEVEL", "WARNING").upper()
_level = getattr(logging, _level_name, logging.INFO)

handler = logging.FileHandler("usage.log")
formatter = logging.Formatter("%(message)s")
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

    colored_entry = f"{GREEN}{log_entry}{RST}" if str(user_id) == str(ADMIN_ID) else f"{RED}{log_entry}{RST}"

    logger.warning(colored_entry)

def error(msg: str):
    logger.error(msg)

def info(msg: str):
    logger.info(msg)

def warn(msg: str):
    logger.warning(msg)

def debug(msg: str):
    logger.debug(msg)

def debug_payload(label: str, payload: Any) -> None:
    from logging import DEBUG, Logger
    import json
    log_instance = getattr(logger, "logger", None)
    if isinstance(log_instance, Logger):
        if not log_instance.isEnabledFor(DEBUG):
            return
    elif isinstance(logger, Logger):
        log_instance = logger
        if not log_instance.isEnabledFor(DEBUG):
            return
    else:
        return

    try:
        serialized = json.dumps(payload, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = repr(payload)

    if log_instance is not None:
        log_instance.debug(f"{YELLOW}{label}{RST}: {serialized}")
    elif hasattr(logger, "debug"):
        logger.debug(f"{YELLOW}{label}{RST}: {serialized}")