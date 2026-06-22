# Security Policy

## Supported Versions

| Version | Status | Security Updates | EOL |
|---------|--------|-----------------|-----|
| 0.1.x (MVP) | ✅ Active | ✅ Critical + High | TBD |
| < 0.1.0 | ❌ Pre-release | ❌ None | — |

**Policy**: Only the latest minor version receives security patches. Major version 1.0.0 will define LTS windows.

## Reporting a Vulnerability

**DO NOT open a public issue.** Send vulnerability reports to: gonzalo@cenf.tech

Include:
- Description of the vulnerability
- Steps to reproduce
- Affected manager(s) and version
- Potential impact

Response time: within 72 hours.

## Security Principles

core-cenf implements Zero-Trust security by design:
- All credentials handled through SecretManager (never hardcoded)
- SecretValue.__repr__ is auto-masked
- JWT validation includes exp/iat/nbf/iss/aud checks
- DependencyManager validates all imports against allowlist
- ExternalAPIManager propagates W3C trace context
- No PII is ever sent to external feature flag providers

## Dependency Security

All external dependencies must be MIT or Apache 2.0 licensed. Dependencies are pinned in pyproject.toml. Optional production adapters (SQLAlchemy, Redis, cloud storage) are declared as optional-deps.
