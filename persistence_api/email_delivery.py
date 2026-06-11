"""Email delivery adapters for user lifecycle messages."""

from __future__ import annotations

from dataclasses import dataclass
from email.message import EmailMessage
import smtplib
import ssl
from typing import Protocol

from shared.config import Settings


class EmailDeliveryError(Exception):
    """Raised when a configured email provider cannot deliver a message.

    Args:
        message: Stable error code suitable for API translation.
    """


class EmailDelivery(Protocol):
    """Interface for sending user lifecycle email messages.

    Implementations send already-generated verification and reset URLs. They
    must not persist raw lifecycle tokens or expose provider credentials.
    """

    def send_verification_email(self, *, to_email: str, verification_url: str) -> None:
        """Send a verification-link email.

        Args:
            to_email: Recipient account email address.
            verification_url: Public one-time verification URL.

        Returns:
            None after the message has been accepted by the provider.
        """

    def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
        """Send a password-reset-link email.

        Args:
            to_email: Recipient account email address.
            reset_url: Public one-time password reset URL.

        Returns:
            None after the message has been accepted by the provider.
        """


@dataclass(slots=True)
class NoopEmailDelivery:
    """Email adapter that intentionally performs no provider call.

    This keeps local development and tests independent from networked SMTP
    credentials while still exercising token generation flows.
    """

    def send_verification_email(self, *, to_email: str, verification_url: str) -> None:
        """Ignore one verification message.

        Args:
            to_email: Recipient account email address.
            verification_url: Public one-time verification URL.

        Returns:
            None.
        """

        del to_email, verification_url

    def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
        """Ignore one password reset message.

        Args:
            to_email: Recipient account email address.
            reset_url: Public one-time password reset URL.

        Returns:
            None.
        """

        del to_email, reset_url


@dataclass(slots=True)
class SmtpEmailDelivery:
    """SMTP-backed email adapter for verification and reset messages.

    Args:
        host: SMTP server hostname.
        port: SMTP server port.
        from_email: Sender address used in lifecycle emails.
        username: Optional SMTP username.
        password: Optional SMTP password.
        use_tls: Whether to upgrade the connection with STARTTLS.
        use_ssl: Whether to connect with implicit SMTP-over-SSL.
        timeout_seconds: Network timeout for SMTP operations.
    """

    host: str
    port: int
    from_email: str
    username: str | None = None
    password: str | None = None
    use_tls: bool = True
    use_ssl: bool = False
    timeout_seconds: float = 10.0

    def send_verification_email(self, *, to_email: str, verification_url: str) -> None:
        """Send a verification-link email.

        Args:
            to_email: Recipient account email address.
            verification_url: Public one-time verification URL.

        Returns:
            None after the SMTP server accepts the message.
        """

        self._send(
            to_email=to_email,
            subject="Verify your HeyBlog email",
            text_body=(
                "Verify your HeyBlog email address by opening this link:\n\n"
                f"{verification_url}\n\n"
                "If you did not request this, you can ignore this email."
            ),
        )

    def send_password_reset_email(self, *, to_email: str, reset_url: str) -> None:
        """Send a password-reset-link email.

        Args:
            to_email: Recipient account email address.
            reset_url: Public one-time password reset URL.

        Returns:
            None after the SMTP server accepts the message.
        """

        self._send(
            to_email=to_email,
            subject="Reset your HeyBlog password",
            text_body=(
                "Reset your HeyBlog password by opening this link:\n\n"
                f"{reset_url}\n\n"
                "If you did not request this, you can ignore this email."
            ),
        )

    def _send(self, *, to_email: str, subject: str, text_body: str) -> None:
        """Build and send one plain-text email over SMTP.

        Args:
            to_email: Recipient email address.
            subject: Message subject line.
            text_body: Plain-text message body.

        Returns:
            None after the provider accepts the message.

        Raises:
            EmailDeliveryError: Raised when the SMTP call fails or is
                misconfigured.
        """

        if not self.host or not self.from_email:
            raise EmailDeliveryError("email_delivery_not_configured")

        message = EmailMessage()
        message["From"] = self.from_email
        message["To"] = to_email
        message["Subject"] = subject
        message.set_content(text_body)

        try:
            if self.use_ssl:
                context = ssl.create_default_context()
                with smtplib.SMTP_SSL(self.host, self.port, timeout=self.timeout_seconds, context=context) as smtp:
                    self._authenticate_if_configured(smtp)
                    smtp.send_message(message)
                return

            with smtplib.SMTP(self.host, self.port, timeout=self.timeout_seconds) as smtp:
                if self.use_tls:
                    context = ssl.create_default_context()
                    smtp.starttls(context=context)
                self._authenticate_if_configured(smtp)
                smtp.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            raise EmailDeliveryError("email_delivery_failed") from exc

    def _authenticate_if_configured(self, smtp: smtplib.SMTP) -> None:
        """Authenticate with SMTP when username and password are configured.

        Args:
            smtp: Open SMTP connection.

        Returns:
            None.
        """

        if self.username and self.password:
            smtp.login(self.username, self.password)


def build_email_delivery(settings: Settings) -> EmailDelivery:
    """Create the configured email delivery adapter.

    Args:
        settings: Runtime settings loaded from environment variables.

    Returns:
        SMTP adapter when `HEYBLOG_EMAIL_PROVIDER=smtp`; otherwise a no-op
        adapter for development and tests.

    Raises:
        ValueError: Raised when an unsupported email provider is configured.
    """

    provider = settings.email_provider.strip().lower()
    if provider in {"", "disabled", "noop"}:
        return NoopEmailDelivery()
    if provider == "smtp":
        return SmtpEmailDelivery(
            host=settings.smtp_host,
            port=settings.smtp_port,
            from_email=settings.email_from,
            username=settings.smtp_username,
            password=settings.smtp_password,
            use_tls=settings.smtp_use_tls,
            use_ssl=settings.smtp_use_ssl,
            timeout_seconds=settings.smtp_timeout_seconds,
        )
    raise ValueError("unsupported_email_provider")
