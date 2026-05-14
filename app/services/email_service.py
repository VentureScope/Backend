"""
Email service with a provider-adapter pattern.

Adding a new provider:
  1. Subclass BaseEmailProvider and implement send_email().
  2. Add the provider key to get_email_provider().
  3. Add the required settings to app/core/config.py.

Current providers:
  - mailgun  (default)
"""

from abc import ABC, abstractmethod
import logging

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Abstract base
# ---------------------------------------------------------------------------


class BaseEmailProvider(ABC):
    """Common interface every email provider adapter must implement."""

    @abstractmethod
    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> None:
        """
        Send a transactional email.

        Args:
            to:      Recipient email address.
            subject: Email subject line.
            html:    HTML body (rich client rendering).
            text:    Plain-text fallback body.

        Raises:
            EmailDeliveryError: If the provider rejects the request.
        """


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class EmailDeliveryError(Exception):
    """Raised when an email provider fails to accept the message."""


# ---------------------------------------------------------------------------
# Mailgun adapter
# ---------------------------------------------------------------------------


class MailgunEmailProvider(BaseEmailProvider):
    """
    Sends email via the Mailgun Messages API (v3).

    Required settings:
        MAILGUN_API_KEY       – API key (starts with "key-...")
        MAILGUN_DOMAIN        – Sending domain verified in Mailgun
        MAILGUN_FROM_EMAIL    – Sender address shown to recipients
        MAILGUN_API_BASE_URL  – "https://api.mailgun.net/v3" (US)
                                or "https://api.eu.mailgun.net/v3" (EU)
    """

    def __init__(self) -> None:
        self._api_key = settings.MAILGUN_API_KEY
        self._domain = settings.MAILGUN_DOMAIN
        self._from_email = settings.MAILGUN_FROM_EMAIL
        self._base_url = settings.MAILGUN_API_BASE_URL.rstrip("/")

        if not self._api_key or not self._domain:
            raise ValueError(
                "MAILGUN_API_KEY and MAILGUN_DOMAIN must be set when EMAIL_PROVIDER=mailgun"
            )

    async def send_email(
        self,
        to: str,
        subject: str,
        html: str,
        text: str,
    ) -> None:
        url = f"{self._base_url}/{self._domain}/messages"

        payload = {
            "from": self._from_email,
            "to": to,
            "subject": subject,
            "html": html,
            "text": text,
        }

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    url,
                    auth=("api", self._api_key),
                    data=payload,
                    timeout=10.0,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                logger.error(
                    "Mailgun rejected email to %s: %s %s",
                    to,
                    exc.response.status_code,
                    exc.response.text,
                )
                raise EmailDeliveryError(
                    f"Mailgun error {exc.response.status_code}: {exc.response.text}"
                ) from exc
            except httpx.RequestError as exc:
                logger.error("Mailgun request failed for %s: %s", to, exc)
                raise EmailDeliveryError(f"Mailgun request error: {exc}") from exc

        logger.info("Email sent via Mailgun to %s (subject: %s)", to, subject)


# ---------------------------------------------------------------------------
# Factory
# ---------------------------------------------------------------------------


def get_email_provider() -> BaseEmailProvider:
    """
    Return the configured email provider instance.

    Controlled by the EMAIL_PROVIDER setting:
        "mailgun"  →  MailgunEmailProvider  (default)

    Extend here when adding new providers.
    """
    provider = settings.EMAIL_PROVIDER.lower()

    if provider == "mailgun":
        return MailgunEmailProvider()

    raise ValueError(
        f"Unknown EMAIL_PROVIDER '{settings.EMAIL_PROVIDER}'. Supported values: mailgun"
    )
