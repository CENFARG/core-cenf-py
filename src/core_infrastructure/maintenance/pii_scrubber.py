"""PII Scrubber — regex-based PII masking for error reports.

Provides client-side PII scrubbing before OTLP export. Masks emails,
JWT tokens, passwords/secrets, credit card numbers, API keys, and
IP addresses using regex patterns.

Security:
    - PII is scrubbed at capture time, never after storage.
    - All patterns are compiled at module load for consistent behavior.
    - Token truncation preserves first 10 chars for debugging context.
@ai-directive: Always scrub PII before returning ErrorReport from
    capture_error(). Never send raw emails, tokens, or passwords.

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

import re
from typing import Any

# ── Compiled regex patterns ──────────────────────────────────────────────────

# Email addresses: user@example.com → ***@example.com
_EMAIL_PATTERN = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")

# JWT tokens: base64.base64.signature → first 10 chars + "..."
_JWT_PATTERN = re.compile(
    r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b"
)

# Passwords / secrets in key=value or "password": "value" patterns
_PASSWORD_PATTERN = re.compile(
    r'(?i)(password|passwd|secret|token|api_key|apikey|auth)\s*[:=]\s*["\']?[A-Za-z0-9_!@#$%^&*()\-=+]{4,}["\']?'
)

# Credit card numbers (16-digit, with optional spaces/dashes)
_CC_PATTERN = re.compile(r"\b(?:\d{4}[-\s]?){3}\d{4}\b")

# API keys (hex or base64 strings of length 32+)
_API_KEY_PATTERN = re.compile(r"\b[A-Za-z0-9_\-]{32,}\b")

# IP addresses (IPv4)
_IP_PATTERN = re.compile(r"\b\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b")


def scrub_pii(text: str) -> str:
    """Scrub PII from a text string.

    Applies all PII regex patterns in order. Handles overlapping matches
    by processing each pattern independently.

    Args:
        text: The input text to scrub (stack trace, message, etc.).

    Returns:
        str: The scrubbed text with PII masked.
    """
    if not text:
        return text

    # Order matters: process each pattern independently
    result = _PASSWORD_PATTERN.sub(_mask_password, text)
    result = _EMAIL_PATTERN.sub(_mask_email, result)
    result = _JWT_PATTERN.sub(_mask_jwt, result)
    result = _CC_PATTERN.sub("[REDACTED-CC]", result)
    result = _API_KEY_PATTERN.sub(_mask_api_key, result)
    result = _IP_PATTERN.sub("[REDACTED-IP]", result)
    return result


def scrub_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Recursively scrub PII from all string values in a dictionary.

    Args:
        data: The dictionary to scrub (modifies in place).

    Returns:
        dict[str, Any]: The scrubbed dictionary (same reference).
    """
    for key, value in data.items():
        if isinstance(value, str):
            data[key] = scrub_pii(value)
        elif isinstance(value, dict):
            scrub_dict(value)
    return data


# ── Masking helpers ──────────────────────────────────────────────────────────


def _mask_email(match: re.Match[str]) -> str:
    """Mask an email address preserving the domain.

    user@example.com → ***@example.com
    """
    email = match.group(0)
    _, domain = email.split("@", 1)
    return f"***@{domain}"


def _mask_jwt(match: re.Match[str]) -> str:
    """Truncate a JWT token to first 10 chars + '...'.

    eyJhbGciOiJI... → eyJhbGciOiJI...
    """
    token = match.group(0)
    return token[:10] + "..."


def _mask_password(match: re.Match[str]) -> str:
    """Mask the value portion of a password/secret assignment.

    password=mysecret → password=***
    """
    full = match.group(0)
    if "=" in full:
        key, _ = full.split("=", 1)
        return f"{key}=***"
    if ":" in full:
        key, _ = full.split(":", 1)
        return f"{key}: ***"
    return full


def _mask_api_key(match: re.Match[str]) -> str:
    """Truncate an API key to first 8 chars + '...'."""
    key = match.group(0)
    return key[:8] + "..."
