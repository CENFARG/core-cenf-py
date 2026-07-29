"""Unit tests for PII scrubber — regex-based PII masking.

Tests cover:
- Email masking preserves domain
- JWT token truncation to first 10 chars
- Password/secret key=value masking
- Credit card redaction
- API key truncation
- IP address redaction
- Edge cases: empty string, no PII text, partial patterns
- scrub_dict recursive scrubbing
- Real stack trace PII scrubbing

Author: CENF AI Team
Version: 0.1.0
"""

from __future__ import annotations

from core_infrastructure.maintenance.pii_scrubber import scrub_dict, scrub_pii


class TestEmailMasking:
    """Tests for email PII masking."""

    def test_masks_email_domain_preserved(self) -> None:
        """Email is masked but domain is preserved."""
        result = scrub_pii("Contact: user@example.com")
        assert "***@example.com" in result
        assert "user@" not in result

    def test_masks_multiple_emails(self) -> None:
        """Multiple emails in same text are all masked."""
        result = scrub_pii("user@example.com and admin@test.org")
        assert "***@example.com" in result
        assert "***@test.org" in result
        assert "user@" not in result

    def test_no_false_positive_on_normal_text(self) -> None:
        """Normal text without emails is unchanged."""
        result = scrub_pii("This is a normal error message")
        assert result == "This is a normal error message"


class TestJwtMasking:
    """Tests for JWT token masking."""

    def test_truncates_jwt_to_10_chars(self) -> None:
        """JWT token is truncated to first 10 chars."""
        token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.dozwN8i1FYRg8Q9JX7X9Q"
        result = scrub_pii(f"jwt={token}")
        assert token[:10] in result
        assert "..." in result
        # Full token beyond 10 chars is not present
        assert token[10:] not in result.replace("...", "")

    def test_masks_jwt_in_text(self) -> None:
        """JWT in sentence is masked."""
        result = scrub_pii("Found jwt: eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dozwN8i1FYRg")
        assert "..." in result


class TestPasswordMasking:
    """Tests for password/secret masking."""

    def test_masks_password_key_value(self) -> None:
        """password=value becomes password=***"""
        result = scrub_pii('password=mySecret123!')
        assert "password=***" in result
        assert "mySecret123" not in result

    def test_masks_secret_with_colon(self) -> None:
        """secret: value becomes secret: ***"""
        result = scrub_pii('secret: super-secret-key')
        assert "secret: ***" in result
        assert "super-secret-key" not in result

    def test_masks_api_key_assignment(self) -> None:
        """api_key=value becomes api_key=***"""
        result = scrub_pii('api_key=sk-1234567890abcdef')
        assert "api_key=***" in result
        assert "sk-1234567890abcdef" not in result


class TestCreditCardMasking:
    """Tests for credit card number redaction."""

    def test_redacts_credit_card(self) -> None:
        """16-digit credit card is redacted."""
        result = scrub_pii("CC: 4111 1111 1111 1111")
        assert "[REDACTED-CC]" in result
        assert "4111" not in result

    def test_redacts_condensed_credit_card(self) -> None:
        """16-digit card without spaces is redacted."""
        result = scrub_pii("CC=4111111111111111")
        assert "[REDACTED-CC]" in result


class TestApiKeyMasking:
    """Tests for API key truncation."""

    def test_truncates_long_api_key(self) -> None:
        """Long alphanumeric string is truncated to 8 chars."""
        key = "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
        result = scrub_pii(f"key={key}")
        assert key[:8] in result
        assert key[9:] not in result

    def test_short_strings_untouched(self) -> None:
        """Strings shorter than 32 chars are not truncated."""
        short = "short-key-here"
        result = scrub_pii(f"key={short}")
        assert short in result


class TestIpMasking:
    """Tests for IP address redaction."""

    def test_redacts_ipv4(self) -> None:
        """IPv4 address is redacted."""
        result = scrub_pii("IP: 192.168.1.1")
        assert "[REDACTED-IP]" in result
        assert "192.168.1.1" not in result

    def test_redacts_multiple_ips(self) -> None:
        """Multiple IPs in same text are all redacted."""
        result = scrub_pii("from 10.0.0.1 to 10.0.0.2")
        assert result.count("[REDACTED-IP]") == 2


class TestEdgeCases:
    """Tests for edge cases."""

    def test_empty_string(self) -> None:
        """Empty string returns empty string."""
        assert scrub_pii("") == ""

    def test_none_text(self) -> None:
        """None-ish text returns empty."""
        result = scrub_pii("")
        assert result == ""

    def test_no_pii_unchanged(self) -> None:
        """Text without PII is unchanged."""
        text = "Normal operational log message"
        assert scrub_pii(text) == text


class TestScrubDict:
    """Tests for recursive dict scrubbing."""

    def test_scrubs_string_values(self) -> None:
        """Dict with PII in string values is scrubbed."""
        data = {
            "email": "user@example.com",
            "message": "Error: password=secret123",
        }
        result = scrub_dict(data)
        assert "***@example.com" in result["email"]
        assert "password=***" in result["message"]

    def test_scrubs_nested_dicts(self) -> None:
        """Nested dicts are recursively scrubbed."""
        data = {
            "user": {
                "email": "admin@test.com",
                "token": "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.dozwN8i1FYRg",
            }
        }
        result = scrub_dict(data)
        assert "***@test.com" in result["user"]["email"]
        assert "..." in result["user"]["token"]

    def test_non_string_values_untouched(self) -> None:
        """Non-string values are not modified."""
        data = {"count": 42, "active": True, "email": "user@example.com"}
        result = scrub_dict(data)
        assert result["count"] == 42
        assert result["active"] is True
        assert "***@example.com" in result["email"]


class TestRealStackTraces:
    """Test PII scrubbing with realistic stack traces."""

    def test_scrubs_email_in_traceback(self) -> None:
        """Email in stack trace is masked."""
        trace = """Traceback (most recent call last):
  File "app.py", line 10, in login
    user = db.find(email="user@example.com")
ValueError: user not found"""
        result = scrub_pii(trace)
        assert "***@example.com" in result
        assert "user@example.com" not in result

    def test_scrubs_token_in_traceback(self) -> None:
        """JWT token in stack trace is truncated."""
        trace = """Traceback:
  File "auth.py", line 5, in verify
    decode("eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxIn0.SflKxwRJSMeKKF2QT4fwpM")
KeyError: expired"""
        result = scrub_pii(trace)
        assert "..." in result
