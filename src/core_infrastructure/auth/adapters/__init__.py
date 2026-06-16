"""CENF AuthManager adapters — concrete implementations of AuthManager Protocol.

Exports:
- JwtAuthAdapter: HS256 JWT validation using python-jose.
- StaticAuthAdapter: Test double returning always-valid configurable claims.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.auth.adapters.jwt_auth_adapter import JwtAuthAdapter
from core_infrastructure.auth.adapters.static_auth_adapter import StaticAuthAdapter

__all__ = [
    "JwtAuthAdapter",
    "StaticAuthAdapter",
]
