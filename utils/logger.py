import logging

from telegram import Update

from config import ADMIN_ID

RED_COL = "\033[91m"
GREEN_COL = "\033[92m"
RST = "\033[0m"

logger = logging.getLogger("usage")
handler = logging.FileHandler("usage.log")
formatter = logging.Formatter("%(asctime)s - %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.WARN)


def log_user_action(action: str, update: Update, extra: str = ""):
    user = update.effective_user
    userId = update.message.from_user["id"]
    user_info = f"\nUser: {userId} - @{user.username or 'N/A'} ({user.full_name})"
    message = f"{user_info} \n Action: {action} \n ========== \n"
    if extra:
        message += f" | Detail: {extra}\n --- \n"

    if str(userId) == str(ADMIN_ID):
        logger.warning(f"{GREEN_COL}{message}{RST}")

    if str(userId) != str(ADMIN_ID):
        logger.warning(f"{RED_COL}{message}{RST}")

def error(msg: str):
    logger.error(msg)

def info(msg: str):
    logger.info(msg)

def warn(msg: str):
    logger.warning(msg)

def debug(msg: str):
    logger.debug(msg)