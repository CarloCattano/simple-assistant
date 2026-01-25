import logging
import os
from typing import Any

try:  # Optional at import time to keep tests and tools lightweight
    from telegram import Update  # type: ignore
except ImportError:  # pragma: no cover - telegram is only required for the bot process
    Update = Any  # type: ignore

from config import ADMIN_ID, DEBUG_USER_ACTIONS


import logging


RED = "\033[91m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RST = "\033[0m"



LOG_LEVEL = os.getenv("LOG_LEVEL", "WARNING").upper()
logger = logging.getLogger("simple_assistant")
logger.setLevel(getattr(logging, LOG_LEVEL, logging.INFO))

if not logger.hasHandlers():
    handler = logging.FileHandler("usage.log")
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

def debug(msg: str):
    if logger.isEnabledFor(logging.DEBUG):
        logger.debug(msg)

def info(msg: str):
    if logger.isEnabledFor(logging.INFO):
        logger.info(msg)

def warn(msg: str):
    if logger.isEnabledFor(logging.WARNING):
        logger.warning(msg)

def error(msg: str):
    if logger.isEnabledFor(logging.ERROR):
        logger.error(msg)

def debug_payload(label: str, payload: Any) -> None:
    try:
        serialized = json.dumps(payload, indent=2, sort_keys=True, default=str)
    except (TypeError, ValueError):
        serialized = repr(payload)
    logger.debug(f"{label}: {serialized}")

def log_user_action(action: str, update: Update, extra: str = ""):
    if not DEBUG_USER_ACTIONS:
        return
    effective_user = getattr(update, "effective_user", None)
    effective_message = getattr(update, "effective_message", None)
    if not effective_user and effective_message and hasattr(effective_message, "from_user"):
        effective_user = effective_message.from_user
    user_id = getattr(effective_user, "id", "unknown")
    username = getattr(effective_user, "username", None) or "N/A"
    full_name = (
        getattr(effective_user, "full_name", None)
        or getattr(effective_user, "name", None)
        or "?"
    )
    user_info = f"User: {user_id} - @{username} ({full_name})"
    log_entry = f"{user_info} | Action: {action}"
    if extra:
        log_entry += f" | Detail: {extra}"
    logger.info(log_entry)


def log_user_action(action: str, update: Update, extra: str = ""):
    if not DEBUG_USER_ACTIONS:
        return

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

    colored_entry = (
        f"{GREEN}{log_entry}{RST}"
        if str(user_id) == str(ADMIN_ID)
        else f"{RED}{log_entry}{RST}"
    )

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
    import json
    from logging import DEBUG, Logger

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
