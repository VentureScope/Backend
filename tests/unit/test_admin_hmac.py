"""
Unit tests for HMAC verification helpers used in admin webhook endpoints.
No DB, no HTTP client — pure logic tests.
"""

import hashlib
import hmac

import pytest
from fastapi import HTTPException
from unittest.mock import patch

from app.api.admin_ml import _verify_pipeline_hmac
from app.api.admin_sentry import _verify_sentry_hmac


def _make_sig(secret: str, body: bytes, prefix: str = "sha256=") -> str:
    digest = hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
    return prefix + digest


# ---------------------------------------------------------------------------
# Pipeline HMAC (_verify_pipeline_hmac)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestPipelineHmac:
    """Tests for app.api.admin_ml._verify_pipeline_hmac"""

    def test_valid_signature_passes(self):
        body = b'{"event_type": "training_complete"}'
        secret = "test-secret-abc"
        sig = _make_sig(secret, body)

        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = secret
            # Should not raise
            _verify_pipeline_hmac(body, sig)

    def test_invalid_signature_raises_401(self):
        body = b'{"event_type": "training_complete"}'
        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = "correct-secret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_pipeline_hmac(body, "sha256=badhexdigest")
            assert exc_info.value.status_code == 401

    def test_missing_signature_raises_401(self):
        body = b'{"event_type": "training_complete"}'
        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = "some-secret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_pipeline_hmac(body, None)
            assert exc_info.value.status_code == 401

    def test_no_secret_configured_skips_verification(self):
        """When PIPELINE_WEBHOOK_SECRET is empty, verification is skipped (dev mode)."""
        body = b'{"event_type": "test"}'
        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = ""
            # No exception — verification skipped
            _verify_pipeline_hmac(body, None)

    def test_tampered_body_raises_401(self):
        original_body = b'{"event_type": "training_complete"}'
        tampered_body = b'{"event_type": "malicious"}'
        secret = "test-secret"
        sig = _make_sig(secret, original_body)

        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = secret
            with pytest.raises(HTTPException) as exc_info:
                _verify_pipeline_hmac(tampered_body, sig)
            assert exc_info.value.status_code == 401

    def test_wrong_prefix_raises_401(self):
        body = b'{"event_type": "test"}'
        secret = "test-secret"
        digest = hmac.new(secret.encode(), body, digestmod=hashlib.sha256).hexdigest()
        bad_sig = "md5=" + digest  # wrong prefix

        with patch("app.api.admin_ml.settings") as mock_settings:
            mock_settings.PIPELINE_WEBHOOK_SECRET = secret
            with pytest.raises(HTTPException) as exc_info:
                _verify_pipeline_hmac(body, bad_sig)
            assert exc_info.value.status_code == 401


# ---------------------------------------------------------------------------
# Sentry HMAC (_verify_sentry_hmac)
# ---------------------------------------------------------------------------


@pytest.mark.unit
class TestSentryHmac:
    """Tests for app.api.admin_sentry._verify_sentry_hmac"""

    def test_valid_signature_passes(self):
        body = b'{"action": "triggered", "data": {}}'
        secret = "sentry-secret-xyz"
        sig = _make_sig(secret, body)

        with patch("app.api.admin_sentry.settings") as mock_settings:
            mock_settings.SENTRY_WEBHOOK_SECRET = secret
            _verify_sentry_hmac(body, sig)  # Should not raise

    def test_invalid_signature_raises_401(self):
        body = b'{"action": "triggered"}'
        with patch("app.api.admin_sentry.settings") as mock_settings:
            mock_settings.SENTRY_WEBHOOK_SECRET = "correct-secret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_sentry_hmac(body, "sha256=wrongdigest")
            assert exc_info.value.status_code == 401

    def test_missing_signature_raises_401(self):
        body = b'{"action": "triggered"}'
        with patch("app.api.admin_sentry.settings") as mock_settings:
            mock_settings.SENTRY_WEBHOOK_SECRET = "some-secret"
            with pytest.raises(HTTPException) as exc_info:
                _verify_sentry_hmac(body, None)
            assert exc_info.value.status_code == 401

    def test_no_secret_skips_verification(self):
        body = b'{"action": "triggered"}'
        with patch("app.api.admin_sentry.settings") as mock_settings:
            mock_settings.SENTRY_WEBHOOK_SECRET = ""
            _verify_sentry_hmac(body, None)  # No exception

    def test_tampered_body_raises_401(self):
        original = b'{"action": "triggered"}'
        tampered = b'{"action": "rate_threshold"}'
        secret = "sentry-secret"
        sig = _make_sig(secret, original)

        with patch("app.api.admin_sentry.settings") as mock_settings:
            mock_settings.SENTRY_WEBHOOK_SECRET = secret
            with pytest.raises(HTTPException) as exc_info:
                _verify_sentry_hmac(tampered, sig)
            assert exc_info.value.status_code == 401
