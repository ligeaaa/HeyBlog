"""Unified logging setup, event helpers, and HTTP request context support."""

from __future__ import annotations

from contextvars import ContextVar
from datetime import UTC
from datetime import datetime
from datetime import timedelta
import json
import logging
from logging import FileHandler
from pathlib import Path
from time import monotonic
from typing import Any
from uuid import uuid4

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

DEFAULT_LOG_FORMAT = "json"
DEFAULT_LOG_LEVEL = "INFO"
DEFAULT_LOG_RETENTION_DAYS = 7
REQUEST_ID_HEADER = "x-request-id"
PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_LOG_DIR = PROJECT_ROOT / "logs"
_REQUEST_ID: ContextVar[str | None] = ContextVar("heyblog_request_id", default=None)
_CONFIGURED_SERVICE: str | None = None


class JsonLineFormatter(logging.Formatter):
    """Format log records as one compact JSON object per line.

    Args:
        service: Name of the emitting service, such as ``backend`` or
            ``crawler``.

    Returns:
        A formatter instance that preserves known structured log fields and
        keeps arbitrary extras under stable top-level keys.
    """

    _RESERVED = frozenset(
        {
            "args",
            "asctime",
            "created",
            "exc_info",
            "exc_text",
            "filename",
            "funcName",
            "levelname",
            "levelno",
            "lineno",
            "module",
            "msecs",
            "message",
            "msg",
            "name",
            "pathname",
            "process",
            "processName",
            "relativeCreated",
            "stack_info",
            "thread",
            "threadName",
        }
    )

    def __init__(self, *, service: str) -> None:
        """Store the service name used in every formatted record.

        Args:
            service: Stable service identifier to attach to emitted records.

        Returns:
            ``None``. The formatter stores the service for future records.
        """

        super().__init__()
        self.service = service

    def format(self, record: logging.LogRecord) -> str:
        """Return a JSON line for one logging record.

        Args:
            record: Standard logging record produced by Python's logging
                package.

        Returns:
            A JSON string containing the normalized log payload.
        """

        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC).isoformat(),
            "level": record.levelname,
            "service": getattr(record, "service", self.service),
            "logger": record.name,
            "event": getattr(record, "event", None),
            "message": record.getMessage(),
            "request_id": getattr(record, "request_id", None) or get_request_id(),
        }
        for key, value in record.__dict__.items():
            if key in self._RESERVED or key in payload:
                continue
            payload[key] = _json_safe(value)
        if record.exc_info:
            payload.setdefault("error_type", record.exc_info[0].__name__)
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(
            {key: value for key, value in payload.items() if value is not None},
            ensure_ascii=False,
            separators=(",", ":"),
        )


class ContextFormatter(logging.Formatter):
    """Format human-readable logs while appending structured context fields."""

    def format(self, record: logging.LogRecord) -> str:
        """Format one record and append useful structured context.

        Args:
            record: Standard logging record.

        Returns:
            Human-readable log line with compact key-value context.
        """

        line = super().format(record)
        context: dict[str, Any] = {}
        for key in (
            "event",
            "request_id",
            "run_id",
            "blog_id",
            "url",
            "normalized_url",
            "stage",
            "duration_ms",
            "status_code",
            "error_type",
            "error_message",
        ):
            value = getattr(record, key, None)
            if value is not None:
                context[key] = value
        if context:
            suffix = " ".join(f"{key}={value}" for key, value in context.items())
            return f"{line} {suffix}"
        return line


class MaxLevelFilter(logging.Filter):
    """Allow only records below or equal to a configured level.

    Args:
        max_level: Highest numeric logging level that should pass.

    Returns:
        A logging filter used by the general application log file so errors can
        be kept in error hourly slices without duplicating normal event review.
    """

    def __init__(self, max_level: int) -> None:
        """Store the maximum allowed level.

        Args:
            max_level: Numeric logging level threshold.

        Returns:
            ``None``.
        """

        super().__init__()
        self.max_level = max_level

    def filter(self, record: logging.LogRecord) -> bool:
        """Return whether the record should be handled.

        Args:
            record: Candidate logging record.

        Returns:
            ``True`` when ``record.levelno`` is at or below ``max_level``.
        """

        return record.levelno <= self.max_level


class HourlySliceFileHandler(logging.Handler):
    """Write log records into hourly files grouped by log type.

    Args:
        log_dir: Root logging directory.
        log_type: Type directory such as ``app``, ``error``, or ``access``.
        service: Service name used in each hourly file name.
        retention_days: Number of recent days to keep.
        encoding: File encoding for log writes.

    Returns:
        A logging handler that lazily opens
        ``<log_type>/<service>/<service>-YYYYMMDD-HH.log``.
    """

    def __init__(
        self,
        *,
        log_dir: Path | str,
        log_type: str,
        service: str,
        retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
        encoding: str = "utf-8",
    ) -> None:
        """Store hourly slicing and retention configuration."""

        super().__init__()
        self.log_dir = Path(log_dir)
        self.log_type = log_type
        self.service = service
        self.retention_days = max(1, int(retention_days))
        self.encoding = encoding
        self._slice_key: str | None = None
        self._handler: FileHandler | None = None
        self._last_cleanup_key: str | None = None

    def emit(self, record: logging.LogRecord) -> None:
        """Write one record to the active hourly file.

        Args:
            record: Logging record to format and append.

        Returns:
            ``None``. Errors are delegated to logging's error handling path.
        """

        try:
            slice_key = datetime.fromtimestamp(record.created, UTC).strftime("%Y%m%d-%H")
            if slice_key != self._slice_key:
                self._switch_slice(slice_key)
            if self._handler is None:
                return
            self._handler.emit(record)
            if self._last_cleanup_key != slice_key:
                self._cleanup_old_slices(now=datetime.fromtimestamp(record.created, UTC))
                self._last_cleanup_key = slice_key
        except Exception:
            self.handleError(record)

    def close(self) -> None:
        """Close the active file handler, if any."""

        if self._handler is not None:
            self._handler.close()
            self._handler = None
        super().close()

    def _switch_slice(self, slice_key: str) -> None:
        """Open the file for a new hourly slice."""

        if self._handler is not None:
            self._handler.close()
        type_dir = self.log_dir / self.log_type / self.service
        type_dir.mkdir(parents=True, exist_ok=True)
        self._handler = FileHandler(
            type_dir / f"{self.service}-{slice_key}.log",
            encoding=self.encoding,
        )
        self._handler.setFormatter(self.formatter)
        self._slice_key = slice_key

    def _cleanup_old_slices(self, *, now: datetime) -> None:
        """Delete hourly slices for this service older than retention."""

        cutoff = now - timedelta(days=self.retention_days)
        type_dir = self.log_dir / self.log_type / self.service
        for path in type_dir.glob(f"{self.service}-*.log"):
            slice_at = _parse_hourly_slice_time(path, service=self.service)
            if slice_at is not None and slice_at < cutoff:
                try:
                    path.unlink()
                except FileNotFoundError:
                    continue


def configure_logging(
    *,
    service: str,
    log_dir: Path | str = DEFAULT_LOG_DIR,
    level: str = DEFAULT_LOG_LEVEL,
    file_enabled: bool = True,
    console_enabled: bool = True,
    log_format: str = DEFAULT_LOG_FORMAT,
    retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
) -> None:
    """Configure process-wide logging for one HeyBlog service.

    Args:
        service: Stable service name used as the log subdirectory and payload
            field.
        log_dir: Root directory under which service log files are stored.
        level: Logging level name such as ``INFO`` or ``DEBUG``.
        file_enabled: Whether to write rotating files under ``log_dir``.
        console_enabled: Whether to also emit logs to stderr.
        log_format: ``json`` for JSON lines, otherwise a human-readable format.
        retention_days: Number of recent days of hourly log slices to keep.

    Returns:
        ``None``. The root logger and selected third-party loggers are
        configured in place.
    """

    global _CONFIGURED_SERVICE
    resolved_level = _resolve_level(level)
    formatter = _build_formatter(service=service, log_format=log_format)
    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(resolved_level)

    if console_enabled:
        console = logging.StreamHandler()
        console.setLevel(resolved_level)
        console.setFormatter(formatter)
        root_logger.addHandler(console)

    if file_enabled:
        access_logger = logging.getLogger("heyblog.access")
        access_logger.handlers.clear()
        access_logger.propagate = False
        access_logger.setLevel(logging.INFO)

        app_file = HourlySliceFileHandler(
            log_dir=log_dir,
            log_type="app",
            service=service,
            retention_days=retention_days,
        )
        app_file.setLevel(resolved_level)
        app_file.addFilter(MaxLevelFilter(logging.INFO))
        app_file.setFormatter(formatter)
        root_logger.addHandler(app_file)

        error_file = HourlySliceFileHandler(
            log_dir=log_dir,
            log_type="error",
            service=service,
            retention_days=retention_days,
        )
        error_file.setLevel(logging.WARNING)
        error_file.setFormatter(formatter)
        root_logger.addHandler(error_file)

        access_file = HourlySliceFileHandler(
            log_dir=log_dir,
            log_type="access",
            service=service,
            retention_days=retention_days,
        )
        access_file.setLevel(logging.INFO)
        access_file.setFormatter(formatter)
        access_logger.addHandler(access_file)
        if console_enabled:
            access_console = logging.StreamHandler()
            access_console.setLevel(logging.INFO)
            access_console.setFormatter(formatter)
            access_logger.addHandler(access_console)

    for logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access", "httpx"):
        logging.getLogger(logger_name).setLevel(resolved_level)
    _CONFIGURED_SERVICE = service


def configure_dedicated_event_logger(
    *,
    logger_name: str,
    service: str,
    log_dir: Path | str = DEFAULT_LOG_DIR,
    level: str = DEFAULT_LOG_LEVEL,
    file_enabled: bool = True,
    console_enabled: bool = True,
    log_format: str = DEFAULT_LOG_FORMAT,
    retention_days: int = DEFAULT_LOG_RETENTION_DAYS,
) -> logging.Logger:
    """Configure one dedicated event logger with its own service directory.

    Args:
        logger_name: Python logging name to configure.
        service: Stable log service name used for files and payload fields.
        log_dir: Root directory under which service log files are stored.
        level: Logging level name such as ``INFO`` or ``DEBUG``.
        file_enabled: Whether to write hourly files under ``log_dir``.
        console_enabled: Whether to also emit records to stderr.
        log_format: ``json`` for JSON lines, otherwise a readable format.
        retention_days: Number of recent days of hourly log slices to keep.

    Returns:
        Configured logger. It does not propagate to the root logger, so its
        records stay out of the parent service's normal app/error files.
    """

    resolved_level = _resolve_level(level)
    formatter = _build_formatter(service=service, log_format=log_format)
    logger = logging.getLogger(logger_name)
    logger.handlers.clear()
    logger.propagate = False
    logger.setLevel(resolved_level)

    if console_enabled:
        console = logging.StreamHandler()
        console.setLevel(resolved_level)
        console.setFormatter(formatter)
        logger.addHandler(console)

    if file_enabled:
        app_file = HourlySliceFileHandler(
            log_dir=log_dir,
            log_type="app",
            service=service,
            retention_days=retention_days,
        )
        app_file.setLevel(resolved_level)
        app_file.addFilter(MaxLevelFilter(logging.INFO))
        app_file.setFormatter(formatter)
        logger.addHandler(app_file)

        error_file = HourlySliceFileHandler(
            log_dir=log_dir,
            log_type="error",
            service=service,
            retention_days=retention_days,
        )
        error_file.setLevel(logging.WARNING)
        error_file.setFormatter(formatter)
        logger.addHandler(error_file)

    return logger


def get_logger(name: str) -> logging.Logger:
    """Return a standard logger for application code.

    Args:
        name: Logger name, usually ``__name__``.

    Returns:
        A standard ``logging.Logger`` instance.
    """

    return logging.getLogger(name)


def get_request_id() -> str | None:
    """Return the current request id from context, if one exists.

    Returns:
        The request id assigned by ``RequestIdMiddleware`` or ``None`` outside
        an HTTP request.
    """

    return _REQUEST_ID.get()


def set_request_id(request_id: str | None) -> object:
    """Set the current request id context.

    Args:
        request_id: Request identifier to expose to downstream log records.

    Returns:
        The context token that callers can later pass to ``reset_request_id``.
    """

    return _REQUEST_ID.set(request_id)


def reset_request_id(token: object) -> None:
    """Restore the previous request id context.

    Args:
        token: Context token returned by ``set_request_id``.

    Returns:
        ``None``.
    """

    _REQUEST_ID.reset(token)  # type: ignore[arg-type]


def log_event(
    logger: logging.Logger,
    *,
    event: str,
    message: str,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit one normalized application event log record.

    Args:
        logger: Logger used as the record source.
        event: Stable dot-delimited event name.
        message: Human-readable summary.
        level: Numeric logging level.
        **fields: Optional structured context fields.

    Returns:
        ``None``. The event is emitted through Python logging.
    """

    logger.log(level, message, extra={"event": event, **fields})


def log_access(
    *,
    service: str,
    method: str,
    path: str,
    status_code: int,
    duration_ms: float,
    request_id: str | None,
    client_ip: str | None = None,
    user_agent: str | None = None,
) -> None:
    """Emit one normalized HTTP access log record.

    Args:
        service: Service that handled the request.
        method: HTTP method.
        path: Request path.
        status_code: Response status code.
        duration_ms: Request duration in milliseconds.
        request_id: Request id carried by middleware.
        client_ip: Best-effort client IP address.
        user_agent: Request user-agent header.

    Returns:
        ``None``. A record is emitted on the dedicated access logger.
    """

    logging.getLogger("heyblog.access").info(
        "http request completed",
        extra={
            "service": service,
            "event": "http.request.completed",
            "method": method,
            "path": path,
            "status_code": status_code,
            "duration_ms": round(duration_ms, 3),
            "request_id": request_id,
            "client_ip": client_ip,
            "user_agent": user_agent,
        },
    )


class RequestIdMiddleware(BaseHTTPMiddleware):
    """Attach request ids and access logs to every HTTP request.

    Args:
        app: ASGI app passed by Starlette.
        service: Stable service name included in access log records.

    Returns:
        Middleware instance installed on a FastAPI application.
    """

    def __init__(self, app: Any, *, service: str) -> None:
        """Store the target service name.

        Args:
            app: Downstream ASGI app.
            service: Stable service identifier for emitted access logs.

        Returns:
            ``None``.
        """

        super().__init__(app)
        self.service = service

    async def dispatch(self, request: Request, call_next: Any) -> Response:
        """Process one request with request-id context and access logging.

        Args:
            request: Incoming Starlette request.
            call_next: ASGI callback that invokes downstream handlers.

        Returns:
            Response with an ``x-request-id`` header.
        """

        request_id = request.headers.get(REQUEST_ID_HEADER) or uuid4().hex
        token = set_request_id(request_id)
        started = monotonic()
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            response.headers[REQUEST_ID_HEADER] = request_id
            return response
        except Exception:
            status_code = 500
            raise
        finally:
            duration_ms = (monotonic() - started) * 1000
            client_ip = request.client.host if request.client is not None else None
            log_access(
                service=self.service,
                method=request.method,
                path=request.url.path,
                status_code=status_code,
                duration_ms=duration_ms,
                request_id=request_id,
                client_ip=client_ip,
                user_agent=request.headers.get("user-agent"),
            )
            reset_request_id(token)


def _resolve_level(level: str) -> int:
    """Resolve a configured level string to a numeric logging level."""

    return getattr(logging, level.strip().upper(), logging.INFO)


def _build_formatter(*, service: str, log_format: str) -> logging.Formatter:
    """Build the configured record formatter."""

    if log_format.strip().lower() == "json":
        return JsonLineFormatter(service=service)
    return ContextFormatter(
        "%(asctime)s %(levelname)s [%(name)s] %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S%z",
    )


def _json_safe(value: Any) -> Any:
    """Return a JSON-serializable representation for one structured value."""

    if isinstance(value, Path):
        return str(value)
    try:
        json.dumps(value)
    except TypeError:
        return str(value)
    return value


def _parse_hourly_slice_time(path: Path, *, service: str) -> datetime | None:
    """Parse a service hourly log filename into a UTC datetime."""

    prefix = f"{service}-"
    if not path.name.startswith(prefix) or not path.name.endswith(".log"):
        return None
    raw = path.name.removeprefix(prefix).removesuffix(".log")
    try:
        parsed = datetime.strptime(raw, "%Y%m%d-%H")
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC)
