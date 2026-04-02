"""Unit tests for security functions."""

import pytest
from datetime import datetime, timedelta

from app.core.security import (
    hash_password,
    verify_password,
    create_access_token,
    decode_access_token,
)


@pytest.mark.unit
class TestPasswordHashing:
    """Test password hashing and verification."""

    def test_hash_password_returns_different_hash_each_time(self):
        """Test that hashing the same password returns different hashes."""
        password = "test_password_123"
        hash1 = hash_password(password)
        hash2 = hash_password(password)

        assert hash1 != hash2
        assert len(hash1) > 0
        assert len(hash2) > 0

    def test_hash_password_with_empty_string(self):
        """Test hashing an empty string."""
        password = ""
        hashed = hash_password(password)
        assert len(hashed) > 0
        assert verify_password(password, hashed)

    def test_verify_password_correct_password(self):
        """Test password verification with correct password."""
        password = "correct_password_123!"
        hashed = hash_password(password)

        assert verify_password(password, hashed) is True

    def test_verify_password_incorrect_password(self):
        """Test password verification with incorrect password."""
        correct_password = "correct_password_123!"
        wrong_password = "wrong_password_456!"
        hashed = hash_password(correct_password)

        assert verify_password(wrong_password, hashed) is False

    def test_verify_password_empty_password(self):
        """Test password verification with empty password."""
        password = "some_password"
        hashed = hash_password(password)

        assert verify_password("", hashed) is False

    def test_verify_password_with_malformed_hash(self):
        """Test password verification with malformed hash."""
        password = "some_password"
        malformed_hash = "not_a_real_hash"

        with pytest.raises(ValueError):
            verify_password(password, malformed_hash)


@pytest.mark.unit
class TestJWTTokens:
    """Test JWT token creation and verification."""

    def test_create_access_token_default_expiration(self):
        """Test creating token with default expiration."""
        subject = "test_user_id"
        token = create_access_token(subject)

        assert len(token) > 0
        assert isinstance(token, str)

        # Verify token can be decoded
        decoded_subject = decode_access_token(token)
        assert decoded_subject == subject

    def test_create_access_token_custom_expiration(self):
        """Test creating token with custom expiration."""
        subject = "test_user_id"
        expires_delta = timedelta(minutes=30)
        token = create_access_token(subject, expires_delta)

        assert len(token) > 0
        decoded_subject = decode_access_token(token)
        assert decoded_subject == subject

    def test_create_access_token_with_non_string_subject(self):
        """Test creating token with non-string subject."""
        subject = 12345
        token = create_access_token(subject)

        decoded_subject = decode_access_token(token)
        assert decoded_subject == "12345"  # Should be converted to string

    def test_decode_access_token_valid_token(self):
        """Test decoding a valid token."""
        subject = "test_user_123"
        token = create_access_token(subject)

        decoded_subject = decode_access_token(token)
        assert decoded_subject == subject

    def test_decode_access_token_invalid_token(self):
        """Test decoding an invalid token."""
        invalid_token = "invalid.token.here"

        decoded_subject = decode_access_token(invalid_token)
        assert decoded_subject is None

    def test_decode_access_token_malformed_token(self):
        """Test decoding a malformed token."""
        malformed_token = "not_a_jwt_token_at_all"

        decoded_subject = decode_access_token(malformed_token)
        assert decoded_subject is None

    def test_decode_access_token_empty_token(self):
        """Test decoding an empty token."""
        empty_token = ""

        decoded_subject = decode_access_token(empty_token)
        assert decoded_subject is None

    def test_create_access_token_expiration_time(self):
        """Test that token expiration is set correctly."""
        subject = "test_user"
        expires_delta = timedelta(minutes=60)

        # Create token
        token = create_access_token(subject, expires_delta)

        # Token should be valid immediately after creation
        decoded_subject = decode_access_token(token)
        assert decoded_subject == subject

    def test_token_round_trip_multiple_subjects(self):
        """Test creating and decoding tokens for multiple subjects."""
        subjects = ["user1", "user2", "user3", "123", "test@email.com"]

        for subject in subjects:
            token = create_access_token(subject)
            decoded_subject = decode_access_token(token)
            assert decoded_subject == subject
