from telegram import ForceReply, Update
from telegram.ext import ContextTypes

from utils.logger import log_user_action


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    await update.message.reply_markdown(
        f"Hi {user.name}! \n *THIS* is an _experimental_ private bot, please do not use *it* !n",
        reply_markup=ForceReply(selective=True),
    )

    log_user_action("User used /start", update, user)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Help!")

