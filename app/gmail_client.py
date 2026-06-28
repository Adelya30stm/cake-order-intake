"""Gmail access via IMAP/SMTP using a Google App Password (no OAuth needed).

Required Config Vars:
  GMAIL_ADDRESS         the inbox that receives orders (also the sender)
  GMAIL_APP_PASSWORD    16-char Google App Password
  BUSINESS_NAME         optional sender display name
"""

from __future__ import annotations

import email
import imaplib
import os
import re
import smtplib
import ssl
import time
from email.header import decode_header, make_header
from email.mime.text import MIMEText

IMAP_HOST = "imap.gmail.com"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 465


def _decode(value: str | None) -> str:
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def _body_text(msg: email.message.Message) -> str:
    """Plain-text body, falling back to stripped HTML."""
    if msg.is_multipart():
        plain = html = None
        for part in msg.walk():
            if "attachment" in str(part.get("Content-Disposition") or ""):
                continue
            payload = part.get_payload(decode=True)
            if payload is None:
                continue
            text = payload.decode(part.get_content_charset() or "utf-8", errors="replace")
            if part.get_content_type() == "text/plain" and plain is None:
                plain = text
            elif part.get_content_type() == "text/html" and html is None:
                html = text
        if plain:
            return plain
        return re.sub(r"<[^>]+>", " ", html) if html else ""
    payload = msg.get_payload(decode=True) or b""
    text = payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return re.sub(r"<[^>]+>", " ", text) if msg.get_content_type() == "text/html" else text


class Gmail:
    """One IMAP connection per intake run; SMTP opened per send."""

    def __init__(self) -> None:
        self.address = os.environ["GMAIL_ADDRESS"]
        self.password = os.environ["GMAIL_APP_PASSWORD"].replace(" ", "")
        self.imap = imaplib.IMAP4_SSL(IMAP_HOST)
        self.imap.login(self.address, self.password)
        # Search All Mail so archived/labeled emails are also found.
        # Gmail IMAP names vary by account language; try common variants.
        for folder in (
            b'"[Gmail]/All Mail"',
            b'"[Gmail]/&BBIEQQRP- &BD8EPgRHBEIEMA-"',  # Russian UI
            b"INBOX",
        ):
            res, _ = self.imap.select(folder)
            if res == "OK":
                self._folder = folder
                break

    def search_unread(self, sender: str = "") -> list[bytes]:
        """Return UIDs of unread inbox messages from the last 2 days (optionally from one sender)."""
        import datetime
        since = (datetime.date.today() - datetime.timedelta(days=4)).strftime("%d-%b-%Y")
        criteria = ["UNSEEN", "SINCE", since]
        if sender:
            criteria += ["FROM", sender]
        _, data = self.imap.uid("search", None, *criteria)
        return data[0].split() if data and data[0] else []

    def get_email(self, uid: bytes) -> dict:
        """Return {text, from, subject} without marking the message read."""
        _, md = self.imap.uid("fetch", uid, "(BODY.PEEK[])")
        msg = email.message_from_bytes(md[0][1])
        return {
            "text": _body_text(msg),
            "from": _decode(msg.get("From")),
            "subject": _decode(msg.get("Subject")),
        }

    def mark_read(self, uid: bytes) -> None:
        self.imap.uid("store", uid, "+FLAGS", "\\Seen")

    def send_email(self, to_addr: str, subject: str, body: str) -> None:
        mime = MIMEText(body, "plain", "utf-8")
        from email.utils import formataddr
        mime["From"] = formataddr((os.environ.get("BUSINESS_NAME", ""), self.address))
        mime["To"] = to_addr
        mime["Subject"] = subject
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as s:
            s.login(self.address, self.password)
            s.sendmail(self.address, [to_addr], mime.as_string())

    def close(self) -> None:
        try:
            self.imap.logout()
        except Exception:
            pass
