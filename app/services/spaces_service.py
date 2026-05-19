"""
Shared DO Spaces (S3-compatible) client factory.

Used by admin_ml.py and admin_system.py to avoid duplicating the
boto3 client configuration.
"""

import boto3

from app.core.config import settings


def get_spaces_client():
    """Return a boto3 S3 client pointed at DO Spaces."""
    return boto3.client(
        "s3",
        region_name=settings.DO_SPACES_REGION,
        endpoint_url=settings.DO_SPACES_ENDPOINT,
        aws_access_key_id=settings.DO_SPACES_KEY,
        aws_secret_access_key=settings.DO_SPACES_SECRET,
    )
