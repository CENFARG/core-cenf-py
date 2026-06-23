"""Unit tests for BusEvent Server — aiohttp-based standalone event bus.

Tests cover:
- POST /publish returns 202 with event_id
- POST /publish returns 401 without valid JWT
- POST /publish returns 403 without permission
- POST /publish returns 429 when rate limited
- WS /subscribe/{event_type} receives events
- WS /subscribe/{event_type} requires valid JWT on connect
- Health endpoint returns 200
- Server lifecycle (start/stop)

Uses aiohttp TestClient/TestServer for HTTP/WS testing with mocked managers.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from core_infrastructure.bus_event.adapters.memory_bus_adapter import MemoryBusAdapter
from core_infrastructure.bus_event.models import BusConfig
from core_infrastructure.bus_event.server import BusEventServer, create_bus_event_app

# ---------------------------------------------------------------------------
# Mock managers
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_auth() -> AsyncMock:
    """Mock AuthManager that validates tokens."""
    auth = AsyncMock()
    auth.validate_token.return_value = MagicMock(
        sub="svc-test",
        iss="cenf-test",
        aud="cenf-app",
        scopes=["bus:publish", "bus:subscribe"],
    )
    auth.get_claims.return_value = MagicMock(
        sub="svc-test",
        scopes=["bus:publish", "bus:subscribe"],
    )
    return auth


@pytest.fixture
def mock_licence() -> AsyncMock:
    """Mock LicenceManager with valid licence."""
    licence = AsyncMock()
    licence.is_feature_enabled.return_value = True
    return licence


@pytest.fixture
def mock_permission() -> AsyncMock:
    """Mock PermissionManager that allows all."""
    permission = AsyncMock()
    decision = MagicMock(is_allowed=lambda: True, reason=lambda: "mock_allow", attributes=lambda: {})
    permission.check_permission.return_value = decision
    return permission


@pytest.fixture
def mock_rate_limiter() -> AsyncMock:
    """Mock RateLimiterManager that allows all."""
    rate_limiter = AsyncMock()
    rate_limiter.is_allowed.return_value = True
    return rate_limiter


@pytest.fixture
def mock_observability() -> MagicMock:
    """Mock ObservabilityManager (sync)."""
    return MagicMock()


@pytest.fixture
def bus_adapter() -> MemoryBusAdapter:
    """Real MemoryBusAdapter for the server backend."""
    return MemoryBusAdapter(config=BusConfig(max_queue_size=100, default_handler_timeout=5.0))


@pytest.fixture
def server_instance(
    bus_adapter: MemoryBusAdapter,
    mock_auth: AsyncMock,
    mock_licence: AsyncMock,
    mock_permission: AsyncMock,
    mock_rate_limiter: AsyncMock,
    mock_observability: MagicMock,
) -> BusEventServer:
    """Create a BusEventServer with mock managers."""
    return BusEventServer(
        bus=bus_adapter,
        auth=mock_auth,
        licence=mock_licence,
        permission=mock_permission,
        rate_limiter=mock_rate_limiter,
        observability=mock_observability,
    )


@pytest.fixture
def app(server_instance: BusEventServer) -> web.Application:
    """Build an aiohttp Application from the server."""
    return create_bus_event_app(server_instance)


@pytest.fixture
async def test_client(app: web.Application) -> Any:
    """Create an aiohttp TestClient for the app.

    This is the aiohttp equivalent of pytest-aiohttp's aiohttp_client fixture.
    Uses TestServer + TestClient pattern from aiohttp.test_utils.
    """
    async with TestClient(TestServer(app)) as client:
        yield client


# ---------------------------------------------------------------------------
# HTTP tests
# ---------------------------------------------------------------------------


class TestPublishEndpoint:
    """Verify POST /publish endpoint."""

    @pytest.mark.asyncio
    async def test_publish_returns_202(self, test_client: Any) -> None:
        """POST /publish with valid payload returns 202 and event_id."""
        headers = {"Authorization": "Bearer valid-token"}
        body = {"event_type": "user.created", "payload": {"user_id": "usr-1"}}

        resp = await test_client.post("/publish", json=body, headers=headers)
        assert resp.status == 202

        data = await resp.json()
        assert "event_id" in data
        assert len(data["event_id"]) > 0

    @pytest.mark.asyncio
    async def test_publish_without_auth_header_returns_401(self, test_client: Any) -> None:
        """POST /publish without Authorization header returns 401."""
        body = {"event_type": "user.created", "payload": {"user_id": "usr-1"}}
        resp = await test_client.post("/publish", json=body)

        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_publish_with_empty_body_returns_400(self, test_client: Any) -> None:
        """POST /publish with empty body returns 400."""
        headers = {"Authorization": "Bearer valid-token"}
        resp = await test_client.post("/publish", headers=headers)

        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_publish_without_event_type_returns_400(self, test_client: Any) -> None:
        """POST /publish without event_type returns 400."""
        headers = {"Authorization": "Bearer valid-token"}
        body = {"payload": {"user_id": "usr-1"}}

        resp = await test_client.post("/publish", json=body, headers=headers)
        assert resp.status == 400

    @pytest.mark.asyncio
    async def test_publish_without_payload_returns_400(self, test_client: Any) -> None:
        """POST /publish without payload returns 400."""
        headers = {"Authorization": "Bearer valid-token"}
        body = {"event_type": "user.created"}

        resp = await test_client.post("/publish", json=body, headers=headers)
        assert resp.status == 400


class TestPublishWithRateLimiting:
    """Verify rate limiting on publish endpoint."""

    @pytest.mark.asyncio
    async def test_publish_rate_limited_returns_429(
        self, test_client: Any, server_instance: BusEventServer
    ) -> None:
        """POST /publish returns 429 when rate limited."""
        server_instance._rate_limiter.is_allowed.return_value = False  # type: ignore[union-attr]

        headers = {"Authorization": "Bearer valid-token"}
        body = {"event_type": "user.created", "payload": {"user_id": "usr-1"}}

        resp = await test_client.post("/publish", json=body, headers=headers)
        assert resp.status == 429


class TestPublishWithPermission:
    """Verify permission checks on publish endpoint."""

    @pytest.mark.asyncio
    async def test_publish_without_permission_returns_403(
        self, test_client: Any, server_instance: BusEventServer
    ) -> None:
        """POST /publish returns 403 when permission denied."""
        decision = MagicMock(is_allowed=lambda: False, reason=lambda: "rbac_deny", attributes=lambda: {})
        server_instance._permission.check_permission.return_value = decision  # type: ignore[union-attr]

        headers = {"Authorization": "Bearer valid-token"}
        body = {"event_type": "user.created", "payload": {"user_id": "usr-1"}}

        resp = await test_client.post("/publish", json=body, headers=headers)
        assert resp.status == 403


class TestWebSocketSubscribe:
    """Verify WS /subscribe/{event_type} endpoint."""

    @pytest.mark.asyncio
    async def test_ws_subscribe_requires_auth(self, test_client: Any) -> None:
        """WebSocket connection without auth token returns 401."""
        # TestClient's GET to a WS endpoint triggers the handler
        resp = await test_client.get("/subscribe/user.created")
        assert resp.status == 401

    @pytest.mark.asyncio
    async def test_ws_subscribe_receives_published_event(
        self, test_client: Any, bus_adapter: MemoryBusAdapter
    ) -> None:
        """WebSocket subscriber receives events published via the bus."""
        # Connect via WebSocket with auth query param
        async with test_client.ws_connect(
            "/subscribe/user.created?token=valid-token"
        ) as ws:
            # Wait briefly for subscription to set up
            await asyncio.sleep(0.05)

            # Publish an event via the bus adapter directly
            await bus_adapter.publish(
                "user.created",
                {"user_id": "usr-ws-test"},
                metadata={"trace_id": "ws-001"},
            )

            # Read the message from WebSocket
            msg = await ws.receive_json(timeout=2.0)
            assert msg["event_type"] == "user.created"
            assert msg["payload"] == {"user_id": "usr-ws-test"}
            assert "event_id" in msg

    @pytest.mark.asyncio
    async def test_ws_subscribe_isolated_by_event_type(
        self, test_client: Any, bus_adapter: MemoryBusAdapter
    ) -> None:
        """WebSocket only receives events for its subscribed event_type."""
        async with test_client.ws_connect(
            "/subscribe/user.created?token=valid-token"
        ) as ws:
            await asyncio.sleep(0.05)

            # Publish to a different event type
            await bus_adapter.publish("order.created", {"order_id": "ord-1"})

            # Publish to the subscribed event type
            await bus_adapter.publish("user.created", {"user_id": "usr-99"})

            # Should receive only the user.created message
            msg = await ws.receive_json(timeout=2.0)
            assert msg["event_type"] == "user.created"
            assert msg["payload"] == {"user_id": "usr-99"}

            # No more messages should arrive for order.created
            with pytest.raises(asyncio.TimeoutError):
                await ws.receive_json(timeout=0.3)


class TestHealthEndpoint:
    """Verify health endpoint."""

    @pytest.mark.asyncio
    async def test_health_returns_200(self, test_client: Any) -> None:
        """GET /health returns 200 OK with status."""
        resp = await test_client.get("/health")
        assert resp.status == 200

        data = await resp.json()
        assert data["status"] == "ok"
        assert data["service"] == "bus_event"


class TestServerLifecycle:
    """Verify server start/stop lifecycle."""

    def test_server_has_start_method(self, server_instance: BusEventServer) -> None:
        """Server exposes start() method."""
        assert hasattr(server_instance, "start")
        assert callable(server_instance.start)

    def test_server_has_stop_method(self, server_instance: BusEventServer) -> None:
        """Server exposes stop() method."""
        assert hasattr(server_instance, "stop")
        assert callable(server_instance.stop)
