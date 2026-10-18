import smtplib

import pytest

from secret_santa.group import Group, Participant
from secret_santa.mailer import MailConfigError, SmtpSettings, build_message, send_draw

SETTINGS = SmtpSettings(host="smtp.example.com", port=587, user="santa@example.com", password="secret")


def body(message, subtype):
    return message.get_body(preferencelist=(subtype,)).get_content()


def test_message_with_accents_names_the_receiver():
    group = Group(budget="20 €")
    message = build_message(SETTINGS, group, Participant("Niccolò", "nic@example.com"), "Zoë")
    assert str(message["To"]) == "Niccolò <nic@example.com>"
    text = body(message, "plain")
    assert text.startswith("Hi Niccolò,")
    assert "    Zoë" in text
    assert "Budget: 20 €" in text
    assert "Zoë" in body(message, "html")
    message.as_bytes()  # the old code crashed here on non-ASCII text


def test_missing_details_are_left_out():
    message = build_message(SETTINGS, Group(), Participant("Anna", "anna@example.com"), "Bruno")
    assert "Budget" not in body(message, "plain")
    assert "Budget" not in body(message, "html")


def test_names_are_escaped_in_html():
    message = build_message(SETTINGS, Group(), Participant("Anna", "anna@example.com"), "<b>Bruno</b>")
    assert "&lt;b&gt;Bruno&lt;/b&gt;" in body(message, "html")


def test_send_draw_reports_who_did_not_get_the_email(monkeypatch):
    sent = []

    class FakeSMTP:
        def __init__(self, host, port, timeout):
            pass

        def starttls(self):
            pass

        def login(self, user, password):
            pass

        def send_message(self, message):
            if message["To"].addresses[0].addr_spec == "bruno@example.com":
                raise smtplib.SMTPRecipientsRefused({})
            sent.append(str(message["To"]))

        def quit(self):
            pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    group = Group(participants=[Participant(n, f"{n.lower()}@example.com") for n in ("Anna", "Bruno", "Carla")])
    failed = send_draw(SETTINGS, group, {"Anna": "Bruno", "Bruno": "Carla", "Carla": "Anna"})
    assert failed == ["Bruno"]
    assert sent == ["Anna <anna@example.com>", "Carla <carla@example.com>"]


def test_settings_need_user_and_password(monkeypatch, tmp_path):
    monkeypatch.setattr("secret_santa.mailer.ENV_FILE", tmp_path / "missing.env")
    monkeypatch.delenv("SMTP_USER", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    with pytest.raises(MailConfigError, match="SMTP_USER and SMTP_PASSWORD"):
        SmtpSettings.from_env()
