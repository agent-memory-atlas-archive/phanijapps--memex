"""Operation audit logging.

Handlers log operation metadata (slugs, counts, durations) only — never
memory contents, tool inputs, or credentials.
"""

from __future__ import annotations

import logging
from logging.handlers import RotatingFileHandler

from memex.infrastructure.config import LoggingConfig

_FORMAT = "%(asctime)s %(levelname)s %(name)s %(message)s"


def setup_logging(config: LoggingConfig) -> logging.Logger:
    """Configure the shared ``memex`` logger with a rotating file handler."""
    logger = logging.getLogger("memex")
    logger.setLevel(config.level)
    for handler in list(logger.handlers):
        logger.removeHandler(handler)
        handler.close()
    if config.file is not None:
        config.file.parent.mkdir(parents=True, exist_ok=True)
        handler = RotatingFileHandler(
            config.file, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8"
        )
        handler.setFormatter(logging.Formatter(_FORMAT))
        logger.addHandler(handler)
    logger.propagate = False
    return logger
