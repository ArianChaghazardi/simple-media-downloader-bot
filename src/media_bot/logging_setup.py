"""
Functional logging configuration module with secret redaction.
Zero custom classes: uses functional filters and standard logging setup.
"""

import logging
import re
import sys
from typing import Optional

# Regular expressions for redaction
TOKEN_PATTERN = re.compile(r"\b\d{8,12}:[a-zA-Z0-9_-]{30,50}\b")
AUTH_PATTERN = re.compile(
    r"(?i)(authorization:\s*(?:bearer\s+)?)['\"]?([a-zA-Z0-9_\-\.]{15,})['\"]?"
)
DB_PASS_PATTERN = re.compile(r"://([^:]+):([^@]+)@")


def redact_sensitive_text(text: str) -> str:
    if not isinstance(text, str):
        text = str(text)
    # Redact Telegram bot token
    text = TOKEN_PATTERN.sub("[REDACTED_BOT_TOKEN]", text)
    # Redact Bearer / auth headers
    text = AUTH_PATTERN.sub(r"\1[REDACTED_AUTH]", text)
    # Redact DB password in connection URLs
    text = DB_PASS_PATTERN.sub(r"://\1:[REDACTED_DB_PASS]@", text)
    return text


def _redacting_log_filter(record: logging.LogRecord) -> bool:
    if isinstance(record.msg, str):
        record.msg = redact_sensitive_text(record.msg)
    if record.args:
        if isinstance(record.args, dict):
            new_args = {k: redact_sensitive_text(str(v)) for k, v in record.args.items()}
            record.args = new_args
        elif isinstance(record.args, (list, tuple)):
            new_args = tuple(
                redact_sensitive_text(str(arg)) if isinstance(arg, str) else arg
                for arg in record.args
            )
            record.args = new_args
    return True


def setup_logging(level_name: str = "INFO", log_file: Optional[str] = None) -> logging.Logger:
    level = getattr(logging, level_name.upper(), logging.INFO)

    # Root logger
    root_logger = logging.getLogger("media_bot")
    root_logger.setLevel(level)

    # Remove existing handlers to avoid duplication
    for h in list(root_logger.handlers):
        root_logger.removeHandler(h)

    formatter = logging.Formatter(
        fmt="%(asctime)s [%(levelname)s] [%(name)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(_redacting_log_filter)
    root_logger.addHandler(console_handler)

    if log_file:
        try:
            file_handler = logging.FileHandler(log_file, encoding="utf-8")
            file_handler.setFormatter(formatter)
            file_handler.addFilter(_redacting_log_filter)
            root_logger.addHandler(file_handler)
        except Exception:
            pass

    return root_logger


def get_logger(name: str = "media_bot") -> logging.Logger:
    return logging.getLogger(f"media_bot.{name}")
