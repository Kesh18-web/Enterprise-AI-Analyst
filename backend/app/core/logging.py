import sys
import time
import uuid
from contextlib import contextmanager
from typing import Any, Dict, Optional
from loguru import logger
from backend.app.core.config import settings


def serialize_log(record: Dict[str, Any]) -> str:
    """Formatter to serialize log records into structured JSON or formatted console logs."""
    extra = record["extra"]
    trace_id = extra.get("trace_id", "N/A")
    duration_ms = extra.get("duration_ms", None)

    duration_str = f" [{duration_ms:.2f}ms]" if duration_ms is not None else ""

    func_name = str(record["function"]).replace("<", "\\<").replace(">", "\\>")
    msg = (
        str(record["message"])
        .replace("<", "\\<")
        .replace(">", "\\>")
        .replace("{", "{{")
        .replace("}", "}}")
    )

    return (
        f"<green>{record['time']:YYYY-MM-DD HH:mm:ss.SSS}</green> | "
        f"<level>{record['level']:<8}</level> | "
        f"<cyan>trace_id={trace_id}</cyan> | "
        f"<cyan>{record['name']}:{func_name}:{record['line']}</cyan>{duration_str} - "
        f"<level>{msg}</level>\n"
    )


def setup_logging():
    """Configure Loguru structured logging for dev and production environments."""
    logger.remove()  # Remove default handler

    log_level = settings.LOG_LEVEL.upper()

    # Console output handler (UTF-8 safe for Windows terminals)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    logger.add(
        sys.stdout,
        level=log_level,
        format=serialize_log,
        colorize=True,
        backtrace=True,
        diagnose=settings.ENVIRONMENT == "development",
    )

    logger.info(
        f"Initialized structured telemetry logger | level={log_level} | env={settings.ENVIRONMENT}"
    )


@contextmanager
def logger_timer(action_name: str, trace_id: Optional[str] = None):
    """Context manager to log the execution time of any node or function with trace correlation ID."""
    if not trace_id:
        trace_id = str(uuid.uuid4())[:8]

    start_time = time.perf_counter()
    bound_logger = logger.bind(trace_id=trace_id)
    bound_logger.debug(f"Starting execution: {action_name}")

    try:
        yield bound_logger
    except Exception as exc:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        bound_logger.bind(duration_ms=elapsed_ms).error(
            f"Failed execution: {action_name} | Error: {str(exc)}"
        )
        raise exc
    else:
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        bound_logger.bind(duration_ms=elapsed_ms).info(
            f"Completed execution: {action_name}"
        )


# Initialize default logger setup
setup_logging()
