"""CENF LicenceManager — cryptographically signed feature licences.

Provides a Protocol-based interface for licence validation and feature-gating.
Supports RS256 JWT validation, offline activation from ``.lic`` files, and
grace-period degraded mode instead of hard blocking.

Security: All licence validation includes exp, iat, nbf checks plus RS256
    signature verification via a public JWK from SecretManager.
Observability: Licence validation emits RED counters
    ``cenf.licence.validate_total``, ``cenf.licence.expired_total``, and
    ``cenf.licence.grace_period_active_total``.
@ai-directive: Use LicenceManager to determine which features exist for a
    tenant. It does NOT decide who can use features — that is the
    PermissionManager's responsibility.

Author: CENF AI Team
Version: 0.1.0
"""

from core_infrastructure.licence.models import LicenceConfig, LicenseClaims
from core_infrastructure.licence.ports import LicenceManager, LicenseInfo

__all__ = [
    "LicenceConfig",
    "LicenceManager",
    "LicenseClaims",
    "LicenseInfo",
]
