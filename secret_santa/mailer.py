"""Emailing everyone their match."""

import os
import smtplib
from collections.abc import Callable
from dataclasses import dataclass
from email.headerregistry import Address
from email.message import EmailMessage
from html import escape
from pathlib import Path

from dotenv import load_dotenv

from .group import Group, Participant

ENV_FILE = Path(__file__).resolve().parent.parent / ".env"
SUBJECT = "🎅 Your Secret Santa match is here!"


class MailConfigError(Exception):
    """The email settings in .env are missing or wrong."""


@dataclass
class SmtpSettings:
    host: str
    port: int
    user: str
    password: str
    sender_name: str = "Secret Santa"

    @classmethod
    def from_env(cls) -> "SmtpSettings":
        """Read the settings from the .env file (or from environment variables)."""
        load_dotenv(ENV_FILE)
        missing = [name for name in ("SMTP_USER", "SMTP_PASSWORD") if not os.getenv(name)]
        if missing:
            raise MailConfigError(f"Missing {' and '.join(missing)}. Copy .env.example to .env and fill it in.")
        try:
            port = int(os.getenv("SMTP_PORT") or 587)
        except ValueError:
            raise MailConfigError("SMTP_PORT in .env must be a number.") from None
        return cls(
            host=os.getenv("SMTP_HOST") or "smtp.gmail.com",
            port=port,
            user=os.environ["SMTP_USER"],
            password=os.environ["SMTP_PASSWORD"],
            sender_name=os.getenv("SENDER_NAME") or "Secret Santa",
        )


class Mailer:
    """A logged-in connection to the email server, to use with `with`."""

    def __init__(self, settings: SmtpSettings):
        self.settings = settings

    def __enter__(self) -> "Mailer":
        s = self.settings
        if s.port == 465:
            self._smtp = smtplib.SMTP_SSL(s.host, s.port, timeout=30)
        else:
            self._smtp = smtplib.SMTP(s.host, s.port, timeout=30)
        try:
            if s.port != 465:
                self._smtp.starttls()
            self._smtp.login(s.user, s.password)
        except BaseException:
            self._smtp.close()
            raise
        return self

    def send(self, message: EmailMessage) -> None:
        self._smtp.send_message(message)

    def __exit__(self, *exc_info) -> None:
        try:
            self._smtp.quit()
        except (smtplib.SMTPException, OSError):
            self._smtp.close()


def build_message(settings: SmtpSettings, group: Group, giver: Participant, receiver: str) -> EmailMessage:
    """The email telling `giver` who they're giving a gift to."""
    details = [("Budget", group.budget)] if group.budget else []

    message = EmailMessage()
    message["Subject"] = SUBJECT
    message["From"] = Address(settings.sender_name, addr_spec=settings.user)
    message["To"] = Address(giver.name, addr_spec=giver.email)
    message.set_content(_text_body(giver.name, receiver, details))
    message.add_alternative(_html_body(giver.name, receiver, details), subtype="html")
    return message


def send_draw(
    settings: SmtpSettings,
    group: Group,
    pairs: dict[str, str],
    on_progress: Callable[[int, int], None] | None = None,
) -> list[str]:
    """Email each giver in `pairs` who they got. Returns the givers whose email couldn't be sent.

    Raises smtplib.SMTPException or OSError if connecting or logging in fails, before anything is sent.
    """
    by_name = {p.name: p for p in group.participants}
    failed = []
    with Mailer(settings) as mailer:
        for i, (giver, receiver) in enumerate(pairs.items(), start=1):
            if on_progress:
                on_progress(i, len(pairs))
            try:
                mailer.send(build_message(settings, group, by_name[giver], receiver))
            except (smtplib.SMTPException, OSError):
                failed.append(giver)
    return failed


def send_test_email(settings: SmtpSettings, group: Group) -> None:
    """Send the organizer a sample email with a made-up match, to check the settings and the layout."""
    message = build_message(settings, group, Participant("Organizer", settings.user), "Example Person")
    message.replace_header("Subject", f"[TEST] {SUBJECT}")
    with Mailer(settings) as mailer:
        mailer.send(message)


def _text_body(giver: str, receiver: str, details: list[tuple[str, str]]) -> str:
    lines = [f"Hi {giver},", "", "this year you are the Secret Santa of...", "", f"    {receiver}"]
    if details:
        lines += [""] + [f"{label}: {value}" for label, value in details]
    return "\n".join(lines) + "\n"


def _html_body(giver: str, receiver: str, details: list[tuple[str, str]]) -> str:
    # Email clients ignore <style> blocks and modern CSS, hence the tables and inline styles.
    rows = "".join(
        f'<tr><td style="padding:4px 10px;text-align:right;color:#8a7f73;">{escape(label)}</td>'
        f'<td style="padding:4px 10px;text-align:left;font-weight:bold;">{escape(value)}</td></tr>'
        for label, value in details
    )
    details_table = (
        f'<table role="presentation" cellpadding="0" cellspacing="0" '
        f'style="margin:24px auto 0;font-size:15px;color:#4a4038;">{rows}</table>'
        if rows
        else ""
    )
    return f"""\
<!doctype html>
<html>
<body style="margin:0;padding:24px 12px;background:#f4efe6;font-family:Georgia,'Times New Roman',serif;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"><tr><td align="center">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
         style="max-width:480px;background:#ffffff;border:1px solid #e6dccb;border-radius:16px;overflow:hidden;">
    <tr><td style="background:#b3202a;padding:28px 24px;text-align:center;color:#ffffff;">
      <div style="font-size:42px;line-height:1;">🎅</div>
      <div style="margin-top:10px;font-size:22px;letter-spacing:1px;">Secret Santa</div>
    </td></tr>
    <tr><td style="padding:32px 24px;text-align:center;color:#2b2b2b;">
      <p style="margin:0 0 6px;font-size:17px;">Hi {escape(giver)},</p>
      <p style="margin:0 0 22px;font-size:17px;">this year you are the Secret Santa of</p>
      <div style="display:inline-block;padding:14px 28px;border:2px dashed #1f6f43;border-radius:12px;
                  font-size:28px;font-weight:bold;color:#1f6f43;">{escape(receiver)}</div>
      {details_table}
    </td></tr>
  </table>
</td></tr></table>
</body>
</html>
"""
