import os
import time
import logging
import traceback
from logging.handlers import RotatingFileHandler
from . import constants

LOG_FILE = os.path.join(constants.APP_DIR, "debug.log")
LOG_LEVEL = os.environ.get("HERMS_LOG_LEVEL", "INFO").upper()

# Map string levels to logging constants
_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


class Logger:
    """Structured logger with level support, log rotation, and UI callbacks.

    Writes to debug.log with full timestamps; exposes a callback-based
    mechanism so the UI's Logs panel can display messages in real time.

    Usage:
        log = Logger()
        log.info("Macro started")
        log.error("Vision capture failed", exc_info=True)
        log.set_ui_callback(lambda msg: js_window.evaluate_js(...))
    """

    def __init__(self):
        self._ui_callback = None
        self._logger = logging.getLogger("herms-engine")
        self._logger.setLevel(_LEVELS.get(LOG_LEVEL, logging.INFO))

        # Avoid duplicate handlers on re-initialization
        if not self._logger.handlers:
            handler = RotatingFileHandler(
                LOG_FILE, maxBytes=2 * 1024 * 1024, backupCount=3, encoding="utf-8"
            )
            handler.setFormatter(logging.Formatter("[%(asctime)s] %(levelname)-7s %(message)s", datefmt="%H:%M:%S"))
            self._logger.addHandler(handler)

    def set_ui_callback(self, callback):
        """Register a callable that receives every log message for UI display."""
        self._ui_callback = callback

    def _log(self, level, message, exc_info=False):
        self._logger.log(level, message)
        if exc_info:
            self._logger.debug(traceback.format_exc())

        # Fire UI callback with plain text (no level prefix)
        if self._ui_callback:
            try:
                self._ui_callback(message)
            except Exception:
                pass  # UI callback must never crash logging

    def debug(self, message: str, exc_info=False):
        self._log(logging.DEBUG, message, exc_info)

    def info(self, message: str, exc_info=False):
        self._log(logging.INFO, message, exc_info)

    def warning(self, message: str, exc_info=False):
        self._log(logging.WARNING, message, exc_info)

    def error(self, message: str, exc_info=False):
        self._log(logging.ERROR, message, exc_info)

    # Legacy compat — the old single-argument log()
    def log(self, message: str) -> None:
        self.info(message)
