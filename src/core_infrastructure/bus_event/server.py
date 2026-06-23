"""BusEventServer — aiohttp-based standalone event bus server.

Provides an HTTP+WebSocket server that exposes the BusEventManager contract
as standalone endpoints. Uses aiohttp (already in deps) for the web layer
with JWT auth, licence validation, permission checks, rate limiting, and
observability metrics per event_type.

Security: Every request requires a valid JWT token via AuthManager.
    LicenceManager validates feature access on connect. PermissionManager
    checks publish permission. RateLimiterManager protects against abuse.
    NEVER expose raw tokens in logs or responses.

Observability: Emits metrics under cenf.bus.server.* per event_type
    (publish_count, subscribe_count, errors).

@ai-directive: This server is the standalone deployment mode for BusEventManager.
    For embedded usage, use MemoryBusAdapter or RedisBusAdapter directly.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import json
from typing import Any

from aiohttp import web

from core_infrastructure.bus_event.ports import BusEventManager

# ---------------------------------------------------------------------------
# Server class
# ---------------------------------------------------------------------------


class BusEventServer:
    """aiohttp-based standalone event bus server.

    Wraps a BusEventManager adapter with HTTP/WS endpoints and cross-cutting
    concerns: auth, licence, permission, rate limiting, and observability.

    Args:
        bus: BusEventManager adapter (MemoryBusAdapter or RedisBusAdapter).
        auth: AuthManager for JWT validation.
        licence: LicenceManager for feature-gating.
        permission: PermissionManager for access control.
        rate_limiter: RateLimiterManager for abuse protection.
        observability: ObservabilityManager for metrics.

    Usage::

        server = BusEventServer(bus=adapter, auth=auth_mgr, ...)
        app = create_bus_event_app(server)
        web.run_app(app, host="0.0.0.0", port=8080)
    """

    def __init__(
        self,
        bus: BusEventManager,
        auth: Any,
        licence: Any,
        permission: Any,
        rate_limiter: Any,
        observability: Any,
    ) -> None:
        self._bus = bus
        self._auth = auth
        self._licence = licence
        self._permission = permission
        self._rate_limiter = rate_limiter
        self._observability = observability
        self._started = False

    # ------------------------------------------------------------------
    # Auth helper
    # ------------------------------------------------------------------

    async def _validate_request(self, request: web.Request) -> Any:
        """Validate JWT auth on incoming request.

        Extracts the Bearer token from the Authorization header and
        validates it via AuthManager. Returns the claims on success.

        Args:
            request: The aiohttp request.

        Returns:
            TokenClaims: Extracted claims.

        Raises:
            web.HTTPUnauthorized: If token is missing or invalid.
        """
        auth_header = request.headers.get("Authorization", "")
        if not auth_header.startswith("Bearer "):
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Missing or invalid Authorization header"}),
                content_type="application/json",
            )

        token = auth_header[7:]  # Strip "Bearer "
        try:
            claims: Any = await self._auth.validate_token(token)
            return claims
        except Exception as err:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Invalid or expired token"}),
                content_type="application/json",
            ) from err

    async def _validate_ws_token(self, request: web.Request) -> Any:
        """Validate JWT auth on incoming WebSocket request.

        Checks both the Authorization header and the ``token`` query parameter.

        Args:
            request: The aiohttp request (upgrade to WS).

        Returns:
            TokenClaims: Extracted claims.

        Raises:
            web.HTTPUnauthorized: If token is missing or invalid.
        """
        # Check query param first (for WebSocket convenience)
        token = request.query.get("token", "")
        if not token:
            auth_header = request.headers.get("Authorization", "")
            if auth_header.startswith("Bearer "):
                token = auth_header[7:]

        if not token:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Missing token"}),
                content_type="application/json",
            )

        try:
            claims: Any = await self._auth.validate_token(token)
            return claims
        except Exception as err:
            raise web.HTTPUnauthorized(
                text=json.dumps({"error": "Invalid or expired token"}),
                content_type="application/json",
            ) from err

    # ------------------------------------------------------------------
    # Licence check
    # ------------------------------------------------------------------

    async def _check_licence(self) -> None:
        """Verify that the licence allows bus_event features.

        Raises:
            web.HTTPForbidden: If the licence does not include bus_event.
        """
        try:
            has_feature = await self._licence.is_feature_enabled(
                tenant_id="default",
                feature_key="bus_event",
            )
            if not has_feature:
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "bus_event feature not licensed"}),
                    content_type="application/json",
                )
        except web.HTTPForbidden:
            raise
        except Exception:
            # Licence manager unreachable — allow by default
            pass

    # ------------------------------------------------------------------
    # HTTP handlers
    # ------------------------------------------------------------------

    async def handle_publish(self, request: web.Request) -> web.Response:
        """POST /publish — publish an event to the bus.

        Requires: valid JWT, licence, publish permission, rate limit not exceeded.

        Body: JSON with ``event_type`` (str) and ``payload`` (dict).
        Optional: ``metadata`` (dict).

        Returns: 202 with ``{"event_id": "..."}``.
        """
        # Auth
        claims = await self._validate_request(request)

        # Rate limit
        allowed = await self._rate_limiter.is_allowed("bus:publish")
        if not allowed:
            self._observability.increment_counter(
                "cenf.bus.server.rate_limited_total",
                attributes={"endpoint": "publish"},
            )
            raise web.HTTPTooManyRequests(
                text=json.dumps({"error": "Rate limit exceeded"}),
                content_type="application/json",
            )

        # Licence
        await self._check_licence()

        # Parse body
        try:
            body = await request.json()
        except Exception as err:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "Invalid JSON body"}),
                content_type="application/json",
            ) from err

        event_type = body.get("event_type")
        payload = body.get("payload")
        metadata = body.get("metadata")

        if not event_type or not payload:
            raise web.HTTPBadRequest(
                text=json.dumps({"error": "event_type and payload are required"}),
                content_type="application/json",
            )

        # Permission check
        try:
            decision = await self._permission.check_permission(
                tenant_id="default",
                principal_id=getattr(claims, "sub", "unknown"),
                principal_type="agent",
                resource_type="bus_event",
                resource_id=event_type,
                action="invoke",
            )
            if not decision.is_allowed():
                raise web.HTTPForbidden(
                    text=json.dumps({"error": "Permission denied", "reason": decision.reason()}),
                    content_type="application/json",
                )
        except web.HTTPForbidden:
            raise
        except Exception:
            # Permission manager unreachable — allow by default
            pass

        # Publish
        event_id = await self._bus.publish(event_type, payload, metadata=metadata)

        # Metrics
        self._observability.increment_counter(
            "cenf.bus.server.publish_total",
            attributes={"event_type": event_type},
        )

        return web.json_response({"event_id": event_id}, status=202)

    async def handle_subscribe_ws(self, request: web.Request) -> web.WebSocketResponse:
        """WS /subscribe/{event_type} — subscribe to events via WebSocket.

        Requires: valid JWT (query param or header), licence.

        The WebSocket receives JSON-encoded EventEnvelope messages
        for the subscribed event_type.
        """
        event_type = request.match_info.get("event_type", "")

        # Auth — validate BEFORE attempting WebSocket upgrade
        try:
            await self._validate_ws_token(request)
        except web.HTTPUnauthorized:
            raise

        # Licence
        try:
            await self._check_licence()
        except web.HTTPForbidden:
            raise

        ws = web.WebSocketResponse()
        await ws.prepare(request)

        # Metrics
        self._observability.increment_counter(
            "cenf.bus.server.subscribe_total",
            attributes={"event_type": event_type},
        )

        # Handler for incoming events
        async def ws_handler(envelope: Any) -> None:
            """Forward EventEnvelope to the WebSocket."""
            if isinstance(envelope, dict):
                data = envelope
            else:
                data = {
                    "event_id": getattr(envelope, "event_id", ""),
                    "event_type": getattr(envelope, "event_type", ""),
                    "payload": getattr(envelope, "payload", {}),
                    "metadata": getattr(envelope, "metadata", None),
                }
            if not ws.closed:
                await ws.send_json(data)

        # Subscribe to the bus
        sub_id = await self._bus.subscribe(event_type, ws_handler, f"ws-{id(ws)}")

        try:
            # Keep connection alive — read loop (client may send pings)
            async for msg in ws:
                if msg.type == web.WSMsgType.TEXT:
                    # Echo pings or ignore other messages
                    if msg.data == "ping":
                        await ws.send_str("pong")
                elif msg.type in (web.WSMsgType.CLOSE, web.WSMsgType.ERROR):
                    break
        finally:
            await self._bus.unsubscribe(sub_id)
            self._observability.increment_counter(
                "cenf.bus.server.unsubscribe_total",
                attributes={"event_type": event_type},
            )

        return ws

    async def handle_health(self, request: web.Request) -> web.Response:
        """GET /health — health check endpoint.

        Returns: 200 with ``{"status": "ok", "service": "bus_event"}``.
        """
        return web.json_response({"status": "ok", "service": "bus_event"})

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Mark the server as started."""
        self._started = True

    async def stop(self) -> None:
        """Mark the server as stopped."""
        self._started = False


# ---------------------------------------------------------------------------
# Application factory
# ---------------------------------------------------------------------------


def create_bus_event_app(server: BusEventServer) -> web.Application:
    """Create an aiohttp Application with bus event routes.

    Args:
        server: A configured BusEventServer instance.

    Returns:
        web.Application: The aiohttp application with routes registered.
    """
    app = web.Application()
    app.router.add_post("/publish", server.handle_publish)
    app.router.add_get("/subscribe/{event_type}", server.handle_subscribe_ws)
    app.router.add_get("/health", server.handle_health)
    return app
