import logging

from telegram import Update

RED_COL = "\033[91m"
GREEN_COL = "\033[92m"
RST = "\033[0m"

logger = logging.getLogger("usage")
handler = logging.FileHandler("usage.log")
formatter = logging.Formatter('%(asctime)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)
logger.setLevel(logging.WARN)

def log_user_action(action: str, update: Update, extra: str = ""):
    user = update.effective_user
    userId = update.message.from_user['id']
    user_info = f"\nUser: {userId} - @{user.username or 'N/A'} ({user.full_name})"
    message = f"{user_info} \n Action: {action} \n ========== \n"
    if extra:
        message += f" | Detail: {extra}"

    if userId == 6661376010:
        logger.warning(f"{GREEN_COL}{message}{RST}")

    if userId != 6661376010:
        logger.warning(f"{RED_COL}{message}{RST}")

