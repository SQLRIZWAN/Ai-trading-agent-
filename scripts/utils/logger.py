"""
logger.py — Structured logging with Firestore persistence.
"""

import logging
import sys
import time
import traceback
from datetime import datetime, timezone


def get_logger(name: str) -> logging.Logger:
    """Return a logger that writes structured output to stdout."""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(_Formatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


class _Formatter(logging.Formatter):
    LEVEL_COLORS = {
        "DEBUG": "\033[36m",
        "INFO": "\033[32m",
        "WARNING": "\033[33m",
        "ERROR": "\033[31m",
        "CRITICAL": "\033[35m",
    }
    RESET = "\033[0m"

    def format(self, record: logging.LogRecord) -> str:
        ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        color = self.LEVEL_COLORS.get(record.levelname, "")
        level = f"{color}{record.levelname:<8}{self.RESET}"
        return f"{ts} | {level} | {record.name} | {record.getMessage()}"


def log_to_firestore(db, level: str, script: str, message: str, extra: dict = None):
    """Persist a log entry to Firestore logs collection (non-blocking attempt)."""
    try:
        doc = {
            "level": level,
            "script": script,
            "message": message,
            "extra": extra or {},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "epoch": int(time.time()),
        }
        db.collection("logs").add(doc)
    except Exception:
        pass  # Never let logging break the main flow
