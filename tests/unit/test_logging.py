import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path

from memex.infrastructure.config import LoggingConfig
from memex.infrastructure.logging import setup_logging


def test_setup_writes_rotating_file(tmp_path: Path) -> None:
    log_file = tmp_path / "logs/memex.log"
    logger = setup_logging(LoggingConfig(level="DEBUG", file=log_file))

    assert logger.level == logging.DEBUG
    assert isinstance(logger.handlers[0], RotatingFileHandler)
    logger.info("operation=write slug=test-node")
    for handler in logger.handlers:
        handler.flush()
    content = log_file.read_text(encoding="utf-8")
    assert "operation=write slug=test-node" in content


def test_setup_replaces_existing_handlers(tmp_path: Path) -> None:
    log_file = tmp_path / "a.log"
    setup_logging(LoggingConfig(level="INFO", file=log_file))
    logger = setup_logging(LoggingConfig(level="ERROR", file=log_file))

    assert len(logger.handlers) == 1
    assert logger.level == logging.ERROR
