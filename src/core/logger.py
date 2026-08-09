"""Logger de consola con colores por nivel, sin dependencias externas."""

import contextlib
import logging
import sys
from typing import Literal

LogLevel = Literal["DEBUG", "INFO", "WARNING", "ERROR"]


class ColorFormatter(logging.Formatter):
    """Formatter que añade color ANSI según el nivel del mensaje."""

    GREY = "\x1b[38;20m"
    GREEN = "\x1b[32;20m"
    YELLOW = "\x1b[33;20m"
    RED = "\x1b[31;20m"
    BOLD_RED = "\x1b[31;1m"
    RESET = "\x1b[0m"

    FORMAT = "[%(levelname)s] %(message)s"

    LEVEL_COLORS = {
        logging.DEBUG: GREY,
        logging.INFO: GREEN,
        logging.WARNING: YELLOW,
        logging.ERROR: RED,
        logging.CRITICAL: BOLD_RED,
    }

    def format(self, record: logging.LogRecord) -> str:
        log_color = self.LEVEL_COLORS.get(record.levelno, self.RESET)
        formatter = logging.Formatter(f"{log_color}{self.FORMAT}{self.RESET}")
        return formatter.format(record)


class InfoFilter(logging.Filter):
    """Deja pasar solo DEBUG/INFO (para separarlos de WARNING/ERROR en stderr)."""

    def filter(self, record: logging.LogRecord) -> bool:
        return record.levelno <= logging.INFO


def setup_logger(level: LogLevel = "INFO") -> logging.Logger:
    """Configura y devuelve el logger principal de la aplicación."""
    for stream in (sys.stdout, sys.stderr):
        with contextlib.suppress(AttributeError, ValueError):
            stream.reconfigure(encoding="utf-8", errors="backslashreplace")

    logger = logging.getLogger("VintedBot")
    if logger.hasHandlers():
        logger.handlers.clear()

    level_map = {
        "DEBUG": logging.DEBUG,
        "INFO": logging.INFO,
        "WARNING": logging.WARNING,
        "ERROR": logging.ERROR,
    }
    logger.setLevel(level_map.get(level, logging.INFO))
    formatter = ColorFormatter()

    stdout_handler = logging.StreamHandler(sys.stdout)
    stdout_handler.setFormatter(formatter)
    stdout_handler.addFilter(InfoFilter())
    logger.addHandler(stdout_handler)

    stderr_handler = logging.StreamHandler(sys.stderr)
    stderr_handler.setFormatter(formatter)
    stderr_handler.setLevel(logging.WARNING)
    logger.addHandler(stderr_handler)

    return logger


logger = setup_logger("INFO")
