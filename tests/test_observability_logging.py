"""Tests for the shared HeyBlog logging boundary."""

from __future__ import annotations

import json
import logging
from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from shared.http_clients.context import context_headers
from shared.http_clients.persistence_http import PersistenceHttpClient
from shared.observability import RequestIdMiddleware
from shared.observability import configure_dedicated_event_logger
from shared.observability import configure_logging
from shared.observability import get_logger
from shared.observability import log_event


def _read_json_lines(path: Path) -> list[dict[str, object]]:
    """Read a JSON-line log file into decoded payloads."""

    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _single_log_file(path: Path) -> Path:
    """Return the only log file in a directory."""

    files = list(path.glob("*.log"))
    assert len(files) == 1
    return files[0]


def test_configure_logging_writes_split_service_files(tmp_path: Path) -> None:
    """Application and error logs should land in type directories as hourly slices."""

    configure_logging(service="unit-service", log_dir=tmp_path, console_enabled=False)
    logger = get_logger("tests.logging")

    log_event(logger, event="unit.info", message="unit info", stage="unit")
    log_event(
        logger,
        event="unit.warning",
        message="unit warning",
        level=logging.WARNING,
        stage="unit",
        error_message="careful",
    )

    app_file = _single_log_file(tmp_path / "app" / "unit-service")
    error_file = _single_log_file(tmp_path / "error" / "unit-service")
    app_logs = _read_json_lines(app_file)
    error_logs = _read_json_lines(error_file)

    assert app_file.name.startswith("unit-service-")
    assert error_file.name.startswith("unit-service-")
    assert app_logs[-1]["event"] == "unit.info"
    assert app_logs[-1]["stage"] == "unit"
    assert error_logs[-1]["event"] == "unit.warning"
    assert error_logs[-1]["error_message"] == "careful"


def test_dedicated_event_logger_writes_parallel_service_files(tmp_path: Path) -> None:
    """Dedicated maintenance logs should land beside normal service logs."""

    configure_logging(service="persistence-api", log_dir=tmp_path, console_enabled=False)
    dedicated = configure_dedicated_event_logger(
        logger_name="tests.maintenance",
        service="maintenance",
        log_dir=tmp_path,
        console_enabled=False,
    )
    app_logger = get_logger("tests.persistence")

    log_event(app_logger, event="persistence.normal", message="normal persistence event")
    log_event(
        dedicated,
        event="maintenance.execute.started",
        message="maintenance execution started",
        stage="maintenance",
        run_id=42,
    )

    persistence_file = _single_log_file(tmp_path / "app" / "persistence-api")
    maintenance_file = _single_log_file(tmp_path / "app" / "maintenance")
    persistence_logs = _read_json_lines(persistence_file)
    maintenance_logs = _read_json_lines(maintenance_file)

    assert persistence_logs[-1]["service"] == "persistence-api"
    assert persistence_logs[-1]["event"] == "persistence.normal"
    assert maintenance_logs[-1]["service"] == "maintenance"
    assert maintenance_logs[-1]["event"] == "maintenance.execute.started"
    assert maintenance_logs[-1]["run_id"] == 42


def test_request_id_middleware_logs_access_and_propagates_context(tmp_path: Path) -> None:
    """HTTP middleware should assign request ids, expose them, and write access logs."""

    configure_logging(service="api-service", log_dir=tmp_path, console_enabled=False)
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware, service="api-service")

    @app.get("/ping")
    def ping() -> dict[str, str]:
        return context_headers()

    response = TestClient(app).get("/ping", headers={"x-request-id": "req-123"})

    assert response.status_code == 200
    assert response.headers["x-request-id"] == "req-123"
    assert response.json() == {"x-request-id": "req-123"}

    access_file = _single_log_file(tmp_path / "access" / "api-service")
    access_logs = _read_json_lines(access_file)
    assert access_file.name.startswith("api-service-")
    assert access_logs[-1]["event"] == "http.request.completed"
    assert access_logs[-1]["request_id"] == "req-123"
    assert access_logs[-1]["path"] == "/ping"


def test_hourly_logging_cleans_slices_older_than_retention(tmp_path: Path) -> None:
    """Hourly log cleanup should remove slices older than the configured retention."""

    old_log = tmp_path / "app" / "cleanup-service" / "cleanup-service-19990101-00.log"
    old_log.parent.mkdir(parents=True)
    old_log.write_text("{}\n", encoding="utf-8")

    configure_logging(
        service="cleanup-service",
        log_dir=tmp_path,
        console_enabled=False,
        retention_days=7,
    )
    log_event(get_logger("tests.cleanup"), event="cleanup.current", message="current")

    assert not old_log.exists()
    assert _single_log_file(tmp_path / "app" / "cleanup-service").name.startswith("cleanup-service-")


def test_context_headers_are_forwarded_by_httpx_clients(tmp_path: Path) -> None:
    """Downstream HTTP clients should forward the active request id."""

    configure_logging(service="forwarding-service", log_dir=tmp_path, console_enabled=False)
    app = FastAPI()
    app.add_middleware(RequestIdMiddleware, service="forwarding-service")

    @app.get("/capture")
    def capture() -> dict[str, str]:
        client = PersistenceHttpClient("http://downstream.local")
        client.client = httpx.Client(
            base_url="http://downstream.local",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, json={"forwarded": request.headers.get("x-request-id")})
            )
        )
        return client._get("/capture")

    response = TestClient(app).get("/capture", headers={"x-request-id": "req-forward"})

    assert response.status_code == 200
    assert response.json() == {"forwarded": "req-forward"}
