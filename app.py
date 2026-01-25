# app.py
import os
import sys
from watchgod import run_process, DefaultWatcher


class PyWatcher(DefaultWatcher):
    """
    Watch only Python files recursively.
    """

    def should_watch_file(self, entry):
        return entry.name.endswith(".py")


def start_bot():
    """
    Start the Telegram bot using the current Python interpreter.
    """
    bot_path = os.path.join(os.path.dirname(__file__), "bot.py")
    os.execv(sys.executable, [sys.executable, bot_path])



import utils.logger  # Ensure logger is initialized
import sys

def log_uncaught_exceptions(exctype, value, tb):
    import traceback
    utils.logger.logger.error("Uncaught exception:", exc_info=(exctype, value, tb))

sys.excepthook = log_uncaught_exceptions

if __name__ == "__main__":
    run_process(".", start_bot, watcher_cls=PyWatcher)
