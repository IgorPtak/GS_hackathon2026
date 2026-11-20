"""`email` channel: plain-text mail over SMTP (Mailpit in the demo)."""

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
)
from .registry import register_channel_plugin

DEFAULT_TIMEOUT_SECONDS = 5.0


def build_message(job: DeliveryJob, address: str, config: ChannelConfig) -> EmailMessage:
    """Format `job.content` as a plain-text email according to `config.runbook_presentation`."""
    content = job.content
    message = EmailMessage()
    message["To"] = address
    message["From"] = config.settings.get("from_address", "alerts@example.com")
    message["Subject"] = f"[{content.severity.value.upper()}] {content.title}"
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
        message = build_message(job, address, config)
        host = str(config.settings.get("smtp_host", context.settings.smtp_host))
        port = int(config.settings.get("smtp_port", context.settings.smtp_port))
        timeout = float(config.settings.get("smtp_timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        await asyncio.to_thread(_send_smtp, message, host, port, timeout)


register_channel_plugin(EmailChannel())
