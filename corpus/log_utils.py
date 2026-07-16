"""
Structured logging for the downloader scripts: human-readable console output
plus one JSONL file per run under <log_dir>/<script>_<timestamp>.jsonl.
"""

import logging
from datetime import datetime, timezone
from pathlib import Path

import structlog

def _reorder_keys(logger, method, event_dict):
    ordered = {
        "timestamp": event_dict.pop("timestamp"),
        "level": event_dict.pop("level"),
    }
    ordered.update(event_dict)
    return ordered


SHARED_PROCESSORS = [
    structlog.stdlib.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    _reorder_keys,
]


def setup_logging(log_dir: str, script_name: str):
    """Configure structlog; returns a bound logger. Console gets pretty lines,
    the JSONL file gets one JSON object per event."""
    log_path = Path(log_dir)
    log_path.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    log_file = log_path / f"{script_name}_{timestamp}.jsonl"

    structlog.configure(
        processors=SHARED_PROCESSORS + [
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=True,
    )

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.dev.ConsoleRenderer(colors=False),
        foreign_pre_chain=SHARED_PROCESSORS,
    ))

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setFormatter(structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer(),
        foreign_pre_chain=SHARED_PROCESSORS,
    ))

    root_logger = logging.getLogger()
    root_logger.handlers = [console_handler, file_handler]
    root_logger.setLevel(logging.INFO)

    logger = structlog.get_logger(script_name)
    logger.info("logging_started", log_file=str(log_file))
    return logger
