"""`email` channel: plain-text mail over SMTP (Mailpit in the demo).

Uses stdlib `smtplib` in a worker thread; replaces aiosmtplib from the plan (no new dependency).
"""

import asyncio
import smtplib
from email.message import EmailMessage

from alerting_contracts.alerts import DeliveryJob, DeliveryPurpose
from alerting_contracts.config import ChannelConfig, ChannelType, Recipient

from .base import (
    ChannelContext,
    ChannelPlugin,
    ChannelRejectedError,
    ChannelUnavailableError,
    check_host_allowed,
)
from .registry import register_channel_plugin

DEFAULT_TIMEOUT_SECONDS = 5.0


def _one_line(value: str) -> str:
    return " ".join(value.split())


def build_message(job: DeliveryJob, address: str, config: ChannelConfig) -> EmailMessage:
    """Format `job.content` as a plain-text email according to `config.runbook_presentation`."""
    content = job.content
    message = EmailMessage()
    # Collapse CR/LF and whitespace so user-controlled text cannot inject headers.
    message["To"] = _one_line(address)
    message["From"] = _one_line(str(config.settings.get("from_address", "alerts@example.com")))
    message["Subject"] = _one_line(f"[{content.severity.value.upper()}] {content.title}")
    message["Message-ID"] = f"<delivery-{job.delivery_id}@alerting.local>"
    message["X-Delivery-Id"] = str(job.delivery_id)

    lines: list[str] = []
    if content.body:
        lines += [content.body, ""]
    lines += [f"{field.path}: {field.value}" for field in content.fields]
    if content.fields:
        lines.append("")
    lines.append(f"Alert: {content.alert_url}")
    if config.runbook_presentation == "full" and content.runbook_steps:
        lines += ["", "Runbook:"]
        lines += [f"{number}. {step}" for number, step in enumerate(content.runbook_steps, 1)]
    if job.purpose == DeliveryPurpose.approval_request and content.approval_code:
        code = content.approval_code
        lines += ["", f"Reply APPROVE {code} or REJECT {code}"]
    message.set_content("\n".join(lines) + "\n")
    return message


def _send_smtp(message: EmailMessage, host: str, port: int, timeout: float) -> None:
    """Blocking SMTP send; run in a thread. Maps smtplib errors to channel errors."""
    try:
        with smtplib.SMTP(host, port, timeout=timeout) as smtp:
            smtp.send_message(message)
    except smtplib.SMTPRecipientsRefused as error:
        # Mailbox-full style 4xx refusals are transient; any permanent code makes it permanent.
        if all(400 <= code < 500 for code, _ in error.recipients.values()):
            raise ChannelUnavailableError(f"recipient temporarily refused: {error}") from error
        raise ChannelRejectedError(f"recipient refused: {error}") from error
    except smtplib.SMTPResponseException as error:
        if 500 <= error.smtp_code < 600:
            raise ChannelRejectedError(f"smtp {error.smtp_code}: {error.smtp_error!r}") from error
        raise ChannelUnavailableError(f"smtp {error.smtp_code}: {error.smtp_error!r}") from error
    except (OSError, smtplib.SMTPException) as error:  # refused, timeout, disconnect
        raise ChannelUnavailableError(f"smtp unavailable: {error}") from error


class EmailChannel(ChannelPlugin):
    """Sends to `recipient.contacts.email`."""

    channel_type = ChannelType.email

    async def send(
        self,
        job: DeliveryJob,
        recipient: Recipient | None,
        config: ChannelConfig,
        context: ChannelContext,
    ) -> None:
        address = recipient.contacts.email if recipient else None
        if not address:
            raise ChannelRejectedError("recipient has no email address")
        host = config.settings.get("smtp_host", context.settings.smtp_host)
        try:
            check_host_allowed(str(host), context)
            message = build_message(job, address, config)
            port = int(config.settings.get("smtp_port", context.settings.smtp_port))
            timeout = float(config.settings.get("smtp_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        except (ValueError, TypeError) as error:
            raise ChannelRejectedError(f"invalid email configuration: {error}") from error
        try:
            await asyncio.wait_for(
                asyncio.to_thread(_send_smtp, message, str(host), port, timeout), timeout * 3
            )
        except TimeoutError as error:
            raise ChannelUnavailableError("smtp send timed out") from error


register_channel_plugin(EmailChannel())
