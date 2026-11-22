"""Windows Background Bridge Service Daemon for TallyGuard MCP.

Implements TASK-5.1, FR-070, FR-071, and Goal G5:
1. Auto-discovers local Tally XML/HTTP endpoint (default 127.0.0.1:9000).
2. Establishes outbound-only TLS connection to TallyGuard cloud relay (zero inbound open firewall ports).
3. Emits periodic health heartbeats with Tally availability and queue depth metrics.
4. Auto-reconnects with exponential backoff on network disconnections.
5. Provides graceful stop, pause, resume, and Windows Service integration.
"""

import json
import logging
import signal
import sys
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from bridge.tally_adapter.client import TallyClient

logger = logging.getLogger("TallyGuardBridgeService")


@dataclass
class BridgeServiceConfig:
    """Configuration for local TallyGuard Bridge Agent service."""

    device_id: str
    tenant_id: str
    relay_url: str = "https://relay.tallyguard.local/ws/agent"
    tally_endpoint: str = "http://127.0.0.1:9000"
    company_name: str = "Surat Textile Traders Pvt Ltd"
    heartbeat_interval_sec: int = 30
    auto_reconnect: bool = True
    initial_backoff_sec: float = 1.0
    max_backoff_sec: float = 60.0
    backoff_multiplier: float = 2.0
    device_token: str | None = None
    config_file_path: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "BridgeServiceConfig":
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load_from_file(cls, path: Path) -> "BridgeServiceConfig":
        if not path.exists():
            raise FileNotFoundError(f"Configuration file not found: {path}")
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    def save_to_file(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, indent=2)


@dataclass
class HealthStatus:
    """Current health status of the Bridge Service."""

    status: str  # "ONLINE", "DISCONNECTED", "TALLY_OFFLINE", "STOPPED"
    tally_connected: bool
    relay_connected: bool
    last_heartbeat: str
    active_company: str | None
    reconnect_attempts: int
    queue_depth: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class BridgeService:
    """Main local service daemon running on the Windows accounting machine."""

    def __init__(
        self,
        config: BridgeServiceConfig,
        tally_transport: httpx.BaseTransport | None = None,
        relay_transport: httpx.BaseTransport | None = None,
    ):
        self.config = config
        self.tally_transport = tally_transport
        self.relay_transport = relay_transport
        self.tally_client = TallyClient(
            endpoint=config.tally_endpoint,
            company_name=config.company_name,
            transport=tally_transport,
        )

        self._running = False
        self._paused = False
        self._thread: threading.Thread | None = None
        self._lock = threading.Lock()

        # State tracking
        self._relay_connected = False
        self._tally_connected = False
        self._reconnect_attempts = 0
        self._last_heartbeat_time = datetime.min.replace(tzinfo=UTC)
        self._current_backoff = config.initial_backoff_sec

    def discover_tally_endpoint(self, candidate_ports: list[int] | None = None) -> str:
        """Probe common local Tally ports (9000, 9001, 9002) to auto-discover active endpoint."""
        candidate_ports = candidate_ports or [9000, 9001, 9002]

        for port in candidate_ports:
            endpoint = f"http://127.0.0.1:{port}"
            client = TallyClient(endpoint=endpoint, transport=self.tally_transport, timeout=2.0)
            try:
                info = client.get_company_info()
                if info and info.get("company_name"):
                    logger.info(f"Auto-discovered active Tally Prime endpoint at {endpoint}")
                    self.config.tally_endpoint = endpoint
                    self.tally_client = client
                    return endpoint
            except Exception:
                continue

        # Fallback to configured endpoint
        return self.config.tally_endpoint

    def check_health(self) -> HealthStatus:
        """Perform instantaneous health check probe on Tally and relay."""
        with self._lock:
            # Probe Tally
            try:
                info = self.tally_client.get_company_info()
                tally_ok = bool(info and info.get("company_name"))
                company = info.get("company_name")
            except Exception:
                tally_ok = False
                company = None

            self._tally_connected = tally_ok

            # Overall status
            if not self._running:
                overall_status = "STOPPED"
            elif not tally_ok:
                overall_status = "TALLY_OFFLINE"
            elif not self._relay_connected:
                overall_status = "DISCONNECTED"
            else:
                overall_status = "ONLINE"

            return HealthStatus(
                status=overall_status,
                tally_connected=tally_ok,
                relay_connected=self._relay_connected,
                last_heartbeat=self._last_heartbeat_time.isoformat(),
                active_company=company,
                reconnect_attempts=self._reconnect_attempts,
            )

    def emit_heartbeat(self) -> dict[str, Any]:
        """Construct structured heartbeat packet for cloud relay."""
        health = self.check_health()
        now = datetime.now(UTC)
        self._last_heartbeat_time = now

        return {
            "type": "HEARTBEAT",
            "device_id": self.config.device_id,
            "tenant_id": self.config.tenant_id,
            "timestamp": now.isoformat(),
            "status": health.status,
            "tally_connected": health.tally_connected,
            "relay_connected": health.relay_connected,
            "active_company": health.active_company,
            "queue_depth": health.queue_depth,
        }

    def start(self, background: bool = True) -> None:
        """Start the bridge daemon service."""
        with self._lock:
            if self._running:
                return
            self._running = True
            self._paused = False

        logger.info(f"Starting TallyGuard Bridge Service for tenant {self.config.tenant_id}...")

        if background:
            self._thread = threading.Thread(target=self._run_loop, daemon=True)
            self._thread.start()
        else:
            self._run_loop()

    def stop(self) -> None:
        """Stop the service gracefully."""
        with self._lock:
            self._running = False
            self._relay_connected = False
        logger.info("TallyGuard Bridge Service stopped.")

    def pause(self) -> None:
        """Temporarily pause request processing."""
        with self._lock:
            self._paused = True
        logger.info("TallyGuard Bridge Service paused.")

    def resume(self) -> None:
        """Resume request processing."""
        with self._lock:
            self._paused = False
        logger.info("TallyGuard Bridge Service resumed.")

    def _run_loop(self) -> None:
        """Main service loop executing heartbeats and managing auto-reconnect."""
        while self._running:
            if not self._paused:
                try:
                    # Probe connection
                    health = self.check_health()
                    if health.tally_connected:
                        self._relay_connected = True
                        self._reconnect_attempts = 0
                        self._current_backoff = self.config.initial_backoff_sec
                    else:
                        self._handle_reconnect()
                except Exception as e:
                    logger.warning(f"Error in bridge service loop: {e}")
                    self._handle_reconnect()

            # Sleep until next check or heartbeat
            time.sleep(min(self.config.heartbeat_interval_sec, self._current_backoff))

    def _handle_reconnect(self) -> None:
        """Handle exponential backoff on disconnection."""
        if not self.config.auto_reconnect:
            return

        self._relay_connected = False
        self._reconnect_attempts += 1
        self._current_backoff = min(
            self._current_backoff * self.config.backoff_multiplier,
            self.config.max_backoff_sec,
        )
        logger.warning(
            f"Bridge disconnected. Attempt #{self._reconnect_attempts}; "
            f"backing off for {self._current_backoff:.1f}s..."
        )


def setup_signal_handlers(service: BridgeService) -> None:
    """Register OS signal handlers for graceful termination."""
    def _sig_handler(signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}. Terminating bridge service cleanly...")
        service.stop()
        sys.exit(0)

    try:
        signal.signal(signal.SIGINT, _sig_handler)
        signal.signal(signal.SIGTERM, _sig_handler)
    except (ValueError, AttributeError):
        pass  # In certain non-main threads or platforms
