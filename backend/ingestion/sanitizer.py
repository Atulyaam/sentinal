"""Data sanitization and pre-persistence redaction for Project Sentinel."""

import re
from typing import Any, Dict, List, Union


SENSITIVE_KEY_SUBSTRINGS = (
    "password",
    "passwd",
    "secret",
    "authorization",
    "auth_token",
    "access_token",
    "api_key",
    "apikey",
    "token",
    "private_key",
    "cookie",
    "set-cookie",
    "session_id",
    "session_token",
    "session_key",
    "session_secret",
)

# Regex patterns for scrubbing authorization tokens, cookies, and passwords in raw text/payloads
BEARER_PATTERN = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]{8,}", re.IGNORECASE)
PASSWORD_INLINE_PATTERN = re.compile(r"((?:password|passwd|secret)\s*[:=]\s*)[^\s,;\"]+", re.IGNORECASE)
API_KEY_INLINE_PATTERN = re.compile(r"((?:api[_-]?key)\s*[:=]\s*)[^\s,;\"]+", re.IGNORECASE)
COOKIE_PATTERN = re.compile(r"((?:set-cookie|cookie)\s*[:=]\s*)[^\s;\"]+", re.IGNORECASE)
AUTHORIZATION_INLINE_PATTERN = re.compile(
    r"((?:authorization)\s*[:=]\s*(?:basic|bearer|digest)?\s*)[^\s,;\"]+",
    re.IGNORECASE,
)


def is_sensitive_key(key_name: str) -> bool:
    """Check if an attribute key indicates sensitive credential content."""
    lower = key_name.lower()
    return any(sub in lower for sub in SENSITIVE_KEY_SUBSTRINGS)


def sanitize_value(val: Any) -> Any:
    """Recursively scrub sensitive keys and patterns from values."""
    if isinstance(val, dict):
        sanitized_dict: Dict[str, Any] = {}
        for k, v in val.items():
            if is_sensitive_key(str(k)):
                sanitized_dict[k] = "[REDACTED]"
            else:
                sanitized_dict[k] = sanitize_value(v)
        return sanitized_dict
    elif isinstance(val, list):
        return [sanitize_value(item) for item in val]
    elif isinstance(val, str):
        return sanitize_string(val)
    return val


def sanitize_string(text: str) -> str:
    """Scrub common authorization tokens, secrets, cookies, and credential patterns from text."""
    if not text:
        return text
    text = BEARER_PATTERN.sub(r"\1[REDACTED]", text)
    text = PASSWORD_INLINE_PATTERN.sub(r"\1[REDACTED]", text)
    text = API_KEY_INLINE_PATTERN.sub(r"\1[REDACTED]", text)
    text = COOKIE_PATTERN.sub(r"\1[REDACTED]", text)
    text = AUTHORIZATION_INLINE_PATTERN.sub(r"\1[REDACTED]", text)
    return text


def sanitize_attributes(attributes: Dict[str, Any]) -> Dict[str, Any]:
    """Scrub dictionary attributes before database persistence."""
    return sanitize_value(attributes)  # type: ignore
