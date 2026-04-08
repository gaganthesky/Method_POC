from __future__ import annotations

import logging
import sys


LOG_FORMAT = "%(asctime)s | %(name)s | %(levelname)s | %(message)s | %(filename)s:%(lineno)d"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"
HANDLER_NAME = "method_poc_console"


def configure_logging(level: int = logging.DEBUG) -> None:
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    for handler in root_logger.handlers:
        if getattr(handler, "name", "") == HANDLER_NAME:
            handler.setLevel(level)
            return

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.name = HANDLER_NAME
    console_handler.setLevel(level)
    console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
    root_logger.addHandler(console_handler)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    return logger
