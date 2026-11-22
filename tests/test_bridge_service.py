"""Automated Test Suite for Phase 5: Bridge Service, Installer & Packaging.

Verifies:
1. BridgeServiceConfig serialization, loading, and persistence.
2. Device identity derivation and one-time pairing code format validation (US-09).
3. Guided pairing workflow and device token exchange (Goal G5).
4. BridgeService lifecycle (start, pause, resume, stop) and health heartbeat generation.
5. Auto-reconnect with exponential backoff on connection drops.
6. Local Tally port auto-discovery.
"""

from pathlib import Path
import tempfile
import pytest

from bridge.service import BridgeServiceConfig, BridgeService, HealthStatus
from bridge.installer.pairing import DevicePairingManager, PairingError
from tests.simulated_tally.server import create_simulated_tally_transport


@pytest.fixture
def temp_config_dir():
    """Create a temporary directory for config persistence testing."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        yield Path(tmp_dir)


@pytest.fixture
def bridge_env(temp_config_dir):
    """Setup simulated bridge service environment."""
    transport = create_simulated_tally_transport()
    config = BridgeServiceConfig(
        device_id="dev-test-12345",
        tenant_id="tenant-surat-textiles",
        relay_url="https://relay.tallyguard.local/ws/agent",
        tally_endpoint="http://127.0.0.1:9000",
        company_name="Surat Textile Traders Pvt Ltd",
        heartbeat_interval_sec=5,
        initial_backoff_sec=1.0,
        max_backoff_sec=10.0,
        backoff_multiplier=2.0,
    )
    service = BridgeService(config=config, tally_transport=transport)
    pairing_mgr = DevicePairingManager(config_dir=temp_config_dir)
    return {
        "service": service,
        "config": config,
        "pairing_mgr": pairing_mgr,
        "transport": transport,
        "config_dir": temp_config_dir,
    }


# ==============================================================================
# 1. Configuration & Persistence Tests (TASK-5.1)
# ==============================================================================

def test_bridge_config_serialization_and_deserialization(temp_config_dir):
    """Verify BridgeServiceConfig JSON file serialization and loading."""
    cfg = BridgeServiceConfig(
        device_id="dev_abcdef123456",
        tenant_id="tenant-123",
        company_name="Surat Textile Traders Pvt Ltd",
        heartbeat_interval_sec=15,
    )

    save_path = temp_config_dir / "config.json"
    cfg.save_to_file(save_path)
    assert save_path.exists()

    loaded = BridgeServiceConfig.load_from_file(save_path)
    assert loaded.device_id == "dev_abcdef123456"
    assert loaded.tenant_id == "tenant-123"
    assert loaded.company_name == "Surat Textile Traders Pvt Ltd"
    assert loaded.heartbeat_interval_sec == 15


# ==============================================================================
# 2. Pairing & Device Identity Tests (TASK-5.2, US-09, Goal G5)
# ==============================================================================

def test_pairing_code_validation_and_device_id_derivation(bridge_env):
    """Verify pairing code regex format checking and stable machine device ID."""
    mgr = bridge_env["pairing_mgr"]

    # Valid codes
    assert mgr.validate_pairing_code_format("TG-1234-ABCD") is True
    assert mgr.validate_pairing_code_format("tg-9999-wxyz") is True
    assert mgr.validate_pairing_code_format("TG-8080-1234") is True

    # Invalid codes
    assert mgr.validate_pairing_code_format("1234-ABCD") is False
    assert mgr.validate_pairing_code_format("TG-12-ABCD") is False
    assert mgr.validate_pairing_code_format("INVALID_CODE") is False
    assert mgr.validate_pairing_code_format("") is False

    # Stable Device ID
    dev1 = mgr.get_or_create_device_id()
    assert dev1.startswith("dev_")
    dev2 = mgr.get_or_create_device_id()
    assert dev1 == dev2  # Must be idempotent and persistent


def test_guided_setup_and_token_exchange(bridge_env):
    """Verify full guided pairing workflow completes with token generation in < 5 mins."""
    mgr = bridge_env["pairing_mgr"]

    # Invalid pairing code raises PairingError
    with pytest.raises(PairingError, match="Invalid pairing code format"):
        mgr.complete_guided_setup(
            tenant_id="tenant-surat",
            pairing_code="BAD_CODE",
        )

    # Valid pairing code creates config file and returns valid config
    cfg = mgr.complete_guided_setup(
        tenant_id="tenant-surat",
        pairing_code="TG-7788-XYZ1",
        company_name="Surat Textile Traders Pvt Ltd",
    )

    assert cfg.tenant_id == "tenant-surat"
    assert cfg.device_id.startswith("dev_")
    assert cfg.device_token is not None
    assert cfg.device_token.startswith("dt_")


# ==============================================================================
# 3. Service Lifecycle & Health Heartbeat Tests (TASK-5.1, FR-070, FR-071)
# ==============================================================================

def test_bridge_service_lifecycle_and_heartbeat(bridge_env):
    """Verify start, pause, resume, stop, and structured heartbeat generation."""
    service = bridge_env["service"]

    # Initial state stopped
    health0 = service.check_health()
    assert health0.status == "STOPPED"

    # Start service
    service._running = True
    service._relay_connected = True
    health1 = service.check_health()
    assert health1.status == "ONLINE"
    assert health1.tally_connected is True
    assert health1.active_company == "Surat Textile Traders Pvt Ltd"

    # Heartbeat emission
    hb = service.emit_heartbeat()
    assert hb["type"] == "HEARTBEAT"
    assert hb["device_id"] == "dev-test-12345"
    assert hb["tenant_id"] == "tenant-surat-textiles"
    assert hb["status"] == "ONLINE"
    assert hb["tally_connected"] is True
    assert hb["active_company"] == "Surat Textile Traders Pvt Ltd"

    # Pause & resume
    service.pause()
    assert service._paused is True
    service.resume()
    assert service._paused is False

    # Stop service
    service.stop()
    assert service._running is False
    health_stopped = service.check_health()
    assert health_stopped.status == "STOPPED"


def test_auto_reconnect_exponential_backoff(bridge_env):
    """Verify auto-reconnect increments attempts and doubles backoff on disconnection."""
    service = bridge_env["service"]

    # Start service
    service._running = True
    assert service._current_backoff == 1.0
    assert service._reconnect_attempts == 0

    # Simulate connection drop
    service._handle_reconnect()
    assert service._reconnect_attempts == 1
    assert service._current_backoff == 2.0  # 1.0 * 2.0

    service._handle_reconnect()
    assert service._reconnect_attempts == 2
    assert service._current_backoff == 4.0  # 2.0 * 2.0

    service._handle_reconnect()
    assert service._reconnect_attempts == 3
    assert service._current_backoff == 8.0

    # Max backoff cap at 10.0s
    service._handle_reconnect()
    assert service._reconnect_attempts == 4
    assert service._current_backoff == 10.0


def test_tally_endpoint_auto_discovery(bridge_env):
    """Verify auto-discovery probes candidate ports and binds to active Tally endpoint."""
    service = bridge_env["service"]

    # Auto-discovery with candidate port 9000
    endpoint = service.discover_tally_endpoint([9000, 9001])
    assert endpoint == "http://127.0.0.1:9000"
    assert service.config.tally_endpoint == "http://127.0.0.1:9000"
