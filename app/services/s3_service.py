"""
S3/Supabase Storage Service for uploading user CVs and other files.
"""

import uuid
import boto3
from botocore.exceptions import ClientError

from app.core.config import settings


class S3UploadError(Exception):
    """Raised when S3/Supabase upload fails."""
    pass


class S3Service:
    """
    Service for uploading files to S3 or Supabase Storage.
    Supports AWS S3, Supabase Storage, and other S3-compatible services.
    """

    ALLOWED_CONTENT_TYPES = {
        "application/pdf",
        "application/msword",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    }

    ALLOWED_IMAGE_TYPES = {
        "image/jpeg",
        "image/png",
        "image/webp",
    }

    MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
    MAX_IMAGE_SIZE = 5 * 1024 * 1024  # 5MB

    def __init__(self):
        self.s3_client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize the S3 client based on configuration."""
        client_kwargs = {
            "aws_access_key_id": settings.AWS_ACCESS_KEY_ID,
            "aws_secret_access_key": settings.AWS_SECRET_ACCESS_KEY,
            "region_name": settings.AWS_REGION,
        }

        # Use custom endpoint for Supabase or other S3-compatible services
        if settings.S3_ENDPOINT_URL:
            client_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL

        self.s3_client = boto3.client("s3", **client_kwargs)

    def _validate_file(self, content: bytes, content_type: str) -> None:
        """Validate file size and content type."""
        if len(content) > self.MAX_FILE_SIZE:
            raise S3UploadError(
                f"File too large. Maximum size is {self.MAX_FILE_SIZE // (1024 * 1024)}MB"
            )

        if content_type not in self.ALLOWED_CONTENT_TYPES:
            raise S3UploadError(
                f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_CONTENT_TYPES)}"
            )

    def _generate_s3_key(self, user_id: str, filename: str) -> str:
        """Generate a unique S3 key for the file."""
        ext = filename.split(".")[-1] if "." in filename else ""
        unique_id = uuid.uuid4().hex[:8]
        return f"cvs/{user_id}/{unique_id}.{ext}"

    def _get_public_url(self, s3_key: str) -> str:
        """Generate public URL for the uploaded file."""
        if settings.S3_ENDPOINT_URL:
            # Supabase Storage format: https://{project}.supabase.co/storage/v1/object/public/{bucket}/{key}
            # S3_ENDPOINT_URL may contain /storage/v1/s3, so extract base URL first
            base_url = settings.S3_ENDPOINT_URL.split("/storage/v1/s3")[0]
            return f"{base_url}/storage/v1/object/public/{settings.S3_BUCKET_NAME}/{s3_key}"
        else:
            # AWS S3
            return f"https://{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    def _get_profile_picture_url(self, s3_key: str) -> str:
        """Generate public URL for the uploaded profile picture."""
        if settings.S3_ENDPOINT_URL:
            base_url = settings.S3_ENDPOINT_URL.split("/storage/v1/s3")[0]
            return f"{base_url}/storage/v1/object/public/{settings.S3_PROFILE_PICTURE_BUCKET}/{s3_key}"
        else:
            return f"https://{settings.S3_PROFILE_PICTURE_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    def _get_org_logo_url(self, s3_key: str) -> str:
        """Generate public URL for an org logo in the organization bucket."""
        if settings.S3_ENDPOINT_URL:
            base_url = settings.S3_ENDPOINT_URL.split("/storage/v1/s3")[0]
            return f"{base_url}/storage/v1/object/public/{settings.S3_ORG_BUCKET}/{s3_key}"
        else:
            return f"https://{settings.S3_ORG_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/{s3_key}"

    def _extract_key_from_org_logo_url(self, url: str) -> str | None:
        """Extract S3 key from an org logo URL."""
        if settings.S3_ENDPOINT_URL and ".supabase.co" in url:
            prefix = f"/storage/v1/object/public/{settings.S3_ORG_BUCKET}/"
            if prefix in url:
                return url.split(prefix)[1]
            return None
        else:
            parts = url.split(
                f"{settings.S3_ORG_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/"
            )
            if len(parts) > 1:
                return parts[1]
            return None

    def _extract_key_from_url(self, url: str) -> str | None:
        """Extract S3 key from URL."""
        if settings.S3_ENDPOINT_URL and ".supabase.co" in url:
            # Supabase Storage format: https://{project}.supabase.co/storage/v1/object/public/{bucket}/{key}
            prefix = f"/storage/v1/object/public/{settings.S3_BUCKET_NAME}/"
            if prefix in url:
                return url.split(prefix)[1]
            return None
        else:
            # AWS S3 URL format
            parts = url.split(f"{settings.S3_BUCKET_NAME}.s3.{settings.AWS_REGION}.amazonaws.com/")
            if len(parts) > 1:
                return parts[1]
            return None

    async def upload_cv(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload a CV file to S3/Supabase Storage.

        Args:
            user_id: The user's ID
            file_content: The file content as bytes
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            The URL of the uploaded file

        Raises:
            S3UploadError: If upload fails
        """
        self._validate_file(file_content, content_type)

        s3_key = self._generate_s3_key(user_id, filename)

        try:
            self.s3_client.put_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    "user_id": user_id,
                    "original_filename": filename,
                },
            )

            return self._get_public_url(s3_key)

        except ClientError as e:
            raise S3UploadError(f"Failed to upload file: {e}")

    async def upload_profile_picture(
        self,
        user_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload a profile picture to S3/Supabase Storage.

        Args:
            user_id: The user's ID
            file_content: The file content as bytes
            filename: Original filename
            content_type: MIME type of the file

        Returns:
            The URL of the uploaded file

        Raises:
            S3UploadError: If upload fails
        """
        if len(file_content) > self.MAX_IMAGE_SIZE:
            raise S3UploadError(
                f"Image too large. Maximum size is {self.MAX_IMAGE_SIZE // (1024 * 1024)}MB"
            )

        if content_type not in self.ALLOWED_IMAGE_TYPES:
            raise S3UploadError(
                f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_IMAGE_TYPES)}"
            )

        ext = filename.split(".")[-1] if "." in filename else "jpg"
        unique_id = uuid.uuid4().hex[:8]
        s3_key = f"profile-pictures/{user_id}/{unique_id}.{ext}"

        try:
            self.s3_client.put_object(
                Bucket=settings.S3_PROFILE_PICTURE_BUCKET,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    "user_id": user_id,
                    "original_filename": filename,
                },
            )

            return self._get_profile_picture_url(s3_key)

        except ClientError as e:
            raise S3UploadError(f"Failed to upload file: {e}")

    async def delete_cv(self, cv_url: str) -> bool:
        """
        Delete a CV file from S3/Supabase Storage.

        Args:
            cv_url: The full URL of the file

        Returns:
            True if deletion was successful
        """
        try:
            s3_key = self._extract_key_from_url(cv_url)
            if not s3_key:
                return False

            self.s3_client.delete_object(
                Bucket=settings.S3_BUCKET_NAME,
                Key=s3_key,
            )
            return True

        except ClientError:
            return False

    async def delete_profile_picture(self, profile_picture_url: str) -> bool:
        """
        Delete a profile picture from S3/Supabase Storage.

        Args:
            profile_picture_url: The full URL of the profile picture

        Returns:
            True if deletion was successful
        """
        try:
            s3_key = self._extract_key_from_profile_picture_url(profile_picture_url)
            if not s3_key:
                return False

            self.s3_client.delete_object(
                Bucket=settings.S3_PROFILE_PICTURE_BUCKET,
                Key=s3_key,
            )
            return True

        except ClientError:
            return False

    def _extract_key_from_profile_picture_url(self, url: str) -> str | None:
        """Extract S3 key from profile picture URL."""
        if settings.S3_ENDPOINT_URL and ".supabase.co" in url:
            prefix = f"/storage/v1/object/public/{settings.S3_PROFILE_PICTURE_BUCKET}/"
            if prefix in url:
                return url.split(prefix)[1]
            return None
        else:
            parts = url.split(f"{settings.S3_PROFILE_PICTURE_BUCKET}.s3.{settings.AWS_REGION}.amazonaws.com/")
            if len(parts) > 1:
                return parts[1]
            return None

    async def upload_org_logo(
        self,
        org_id: str,
        file_content: bytes,
        filename: str,
        content_type: str,
    ) -> str:
        """
        Upload an organization logo to the dedicated 'organization' bucket.

        Stored at: logos/org_{org_id}/{unique_id}.{ext}

        Args:
            org_id: The organization's ID
            file_content: Image bytes
            filename: Original filename
            content_type: MIME type (image/jpeg, image/png, image/webp)

        Returns:
            Public URL of the uploaded logo

        Raises:
            S3UploadError: If upload fails
        """
        if len(file_content) > self.MAX_IMAGE_SIZE:
            raise S3UploadError(
                f"Image too large. Maximum size is {self.MAX_IMAGE_SIZE // (1024 * 1024)}MB"
            )

        if content_type not in self.ALLOWED_IMAGE_TYPES:
            raise S3UploadError(
                f"Invalid file type. Allowed types: {', '.join(self.ALLOWED_IMAGE_TYPES)}"
            )

        ext = filename.rsplit(".", 1)[-1] if "." in filename else "jpg"
        unique_id = uuid.uuid4().hex[:8]
        s3_key = f"logos/org_{org_id}/{unique_id}.{ext}"

        try:
            self.s3_client.put_object(
                Bucket=settings.S3_ORG_BUCKET,
                Key=s3_key,
                Body=file_content,
                ContentType=content_type,
                Metadata={
                    "org_id": org_id,
                    "original_filename": filename,
                },
            )
            return self._get_org_logo_url(s3_key)

        except ClientError as e:
            raise S3UploadError(f"Failed to upload org logo: {e}")

    async def delete_org_logo(self, logo_url: str) -> bool:
        """
        Delete an org logo from the 'organization' bucket.

        Args:
            logo_url: Full public URL of the logo

        Returns:
            True if deletion was successful, False otherwise
        """
        try:
            s3_key = self._extract_key_from_org_logo_url(logo_url)
            if not s3_key:
                return False

            self.s3_client.delete_object(
                Bucket=settings.S3_ORG_BUCKET,
                Key=s3_key,
            )
            return True

        except ClientError:
            return False

    def get_presigned_url(self, cv_url: str, expiration: int = 3600) -> str | None:
        """
        Generate a presigned URL for downloading a CV.

        Args:
            cv_url: The full URL of the file
            expiration: URL expiration time in seconds (default: 1 hour)

        Returns:
            Presigned URL or None if generation fails
        """
        try:
            s3_key = self._extract_key_from_url(cv_url)
            if not s3_key:
                return None

            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={
                    "Bucket": settings.S3_BUCKET_NAME,
                    "Key": s3_key,
                },
                ExpiresIn=expiration,
            )

        except ClientError:
            return None


_s3_service: S3Service | None = None


def get_s3_service() -> S3Service:
    """Get or create the S3 service singleton."""
    global _s3_service
    if _s3_service is None:
        _s3_service = S3Service()
    return _s3_service
