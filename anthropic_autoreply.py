"""
Anthropic invoice -> auto-reply "thanks" + log payment to Notion
=================================================================

Что делает (когда ты запускаешь скрипт руками):
  1. Заходит в твой Gmail, ищет НОВЫЕ (непрочитанные) письма от Anthropic.
  2. На каждое отправляет авто-ответ "Thank you! — Adelia" в ту же ветку.
  3. Достаёт из письма сумму ($) и создаёт запись в базе Notion "Anthropic Payments".
  4. Помечает письмо прочитанным, чтобы не обработать дважды.

Запуск:
    python3 anthropic_autoreply.py

Зависимостей нет — только стандартная библиотека Python.
По умолчанию DRY_RUN = True: скрипт ничего не отправляет и не пишет, только показывает,
что СДЕЛАЛ БЫ. Убедись, что вывод правильный, потом поставь DRY_RUN = False.

------------------------------------------------------------------
НАСТРОЙКА (один раз) — заполни блок CONFIG ниже:

A) Gmail App Password (для чтения и отправки писем):
   1. Включи 2-Step Verification: https://myaccount.google.com/security
   2. Создай пароль приложения: https://myaccount.google.com/apppasswords
      (выбери "Mail" -> "Other", получишь 16 символов, например "abcd efgh ijkl mnop")
   3. Впиши его в GMAIL_APP_PASSWORD (можно с пробелами или без).

B) Notion (для записи суммы):
   1. Создай интеграцию: https://www.notion.so/my-integrations -> New integration
      -> скопируй "Internal Integration Secret" (начинается с "secret_" или "ntn_").
   2. Создай в Notion базу "Anthropic Payments" с полями:
        Name (Title) | Amount (Number) | Currency (Text) | Invoice Date (Date)
        Invoice Number (Text) | Sender Email (Email) | Status (Select: Logged/Reviewed/Paid)
   3. Открой базу -> ... -> Connections -> добавь свою интеграцию.
   4. Скопируй Database ID из URL базы:
        notion.so/<workspace>/<DATABASE_ID>?v=...   (32 символа hex)
   5. Впиши NOTION_TOKEN и NOTION_DATABASE_ID ниже.
------------------------------------------------------------------
"""

from __future__ import annotations

import imaplib
import smtplib
import ssl
import re
import json
import email
from email.header import decode_header, make_header
from email.utils import parsedate_to_datetime, formataddr
from email.mime.text import MIMEText
from urllib import request as urlrequest
from urllib.error import HTTPError


# ============================ CONFIG ============================

# --- Gmail ---
GMAIL_ADDRESS = "your-bakery@gmail.com"
GMAIL_APP_PASSWORD = "qwuf nhxy rzit xurz"  # <-- 16-значный App Password (см. инструкцию выше)
YOUR_NAME = "Adelia"             # имя в подписи и в поле From

# Кого считать "письмом от Anthropic". Substring-совпадение по адресу отправителя.
# По умолчанию — только настоящие чеки об оплате (рекомендуется!).
# Хочешь отвечать вообще на ВСЕ письма Anthropic — поставь "anthropic.com"
# (но тогда ответы уйдут и на no-reply / failed-payments, это бессмысленно).
SENDER_FILTER = "invoice+statements@mail.anthropic.com"

# Ограничить число обрабатываемых писем за один запуск (защита от рассылки 76 писем разом).
# Скрипт берёт самые СТАРЫЕ непрочитанные. Поставь 0, чтобы снять лимит.
MAX_PER_RUN = 5

# Текст авто-ответа
REPLY_BODY = "Thank you! — Adelia"

# --- Notion ---
NOTION_TOKEN = ""                # <-- secret_... / ntn_...  (пусто = шаг Notion пропускается)
NOTION_DATABASE_ID = ""          # <-- ID базы "Anthropic Payments"

# Названия свойств в твоей базе Notion (поменяй, если назвала иначе)
NOTION_PROPS = {
    "title": "Name",
    "amount": "Amount",
    "currency": "Currency",
    "invoice_date": "Invoice Date",
    "invoice_number": "Invoice Number",
    "sender_email": "Sender Email",
    "status": "Status",
}
NOTION_DEFAULT_STATUS = "Logged"

# --- Safety ---
DRY_RUN = True   # True = только показать, что сделал бы. Поставь False, когда проверишь.

# ===============================================================


IMAP_HOST = "imap.gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465
NOTION_API = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"


def _decode(value: str | None) -> str:
    """Decode MIME-encoded header (e.g. =?UTF-8?...) to plain text."""
    if not value:
        return ""
    try:
        return str(make_header(decode_header(value)))
    except Exception:
        return value


def get_body_text(msg: email.message.Message) -> str:
    """Return the plain-text body, falling back to a stripped HTML part."""
    if msg.is_multipart():
        plain, html = None, None
        for part in msg.walk():
            ctype = part.get_content_type()
            disp = str(part.get("Content-Disposition") or "")
            if "attachment" in disp:
                continue
            try:
                payload = part.get_payload(decode=True)
                if payload is None:
                    continue
                charset = part.get_content_charset() or "utf-8"
                text = payload.decode(charset, errors="replace")
            except Exception:
                continue
            if ctype == "text/plain" and plain is None:
                plain = text
            elif ctype == "text/html" and html is None:
                html = text
        if plain:
            return plain
        if html:
            return re.sub(r"<[^>]+>", " ", html)
        return ""
    payload = msg.get_payload(decode=True)
    if payload is None:
        return ""
    charset = msg.get_content_charset() or "utf-8"
    text = payload.decode(charset, errors="replace")
    if msg.get_content_type() == "text/html":
        text = re.sub(r"<[^>]+>", " ", text)
    return text


def extract_payment(body: str, subject: str = "") -> dict:
    """Pull the paid amount, invoice number, and currency out of an invoice email."""
    # All dollar amounts like $1,234.56 or $20.00
    amounts = re.findall(r"\$\s?([\d,]+\.\d{2})", body)
    amount = ""
    if amounts:
        # Prefer the amount near a "total"/"paid"/"amount due" keyword; else the largest.
        keyed = re.findall(
            r"(?:total|amount paid|amount due|paid|charged)[^$]{0,40}\$\s?([\d,]+\.\d{2})",
            body, re.IGNORECASE,
        )
        pick = keyed[0] if keyed else max(amounts, key=lambda a: float(a.replace(",", "")))
        amount = pick.replace(",", "")

    # Anthropic receipt numbers look like #2303-5903-4350 and live in the subject.
    inv = re.search(r"#\s*(\d{4}-\d{4}-\d{4})", subject) or re.search(r"#\s*(\d{4}-\d{4}-\d{4})", body)
    invoice_number = inv.group(1) if inv else ""

    currency = "USD" if "$" in body else ""
    return {"amount": amount, "currency": currency, "invoice_number": invoice_number}


def send_reply(to_addr: str, subject: str, message_id: str) -> None:
    """Send the 'thanks' reply in the same thread via Gmail SMTP."""
    reply_subject = subject if subject.lower().startswith("re:") else f"Re: {subject}"
    mime = MIMEText(REPLY_BODY, "plain", "utf-8")
    mime["From"] = formataddr((YOUR_NAME, GMAIL_ADDRESS))
    mime["To"] = to_addr
    mime["Subject"] = reply_subject
    if message_id:
        mime["In-Reply-To"] = message_id
        mime["References"] = message_id

    if DRY_RUN:
        print(f"   [DRY_RUN] would REPLY to {to_addr} | subject: {reply_subject!r}")
        return

    ctx = ssl.create_default_context()
    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT, context=ctx) as server:
        server.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD.replace(" ", ""))
        server.sendmail(GMAIL_ADDRESS, [to_addr], mime.as_string())
    print(f"   ✓ replied to {to_addr}")


def create_notion_record(data: dict, sender_email: str, iso_date: str) -> None:
    """Create one row in the Anthropic Payments database."""
    if not NOTION_TOKEN or not NOTION_DATABASE_ID:
        print("   [skip Notion] NOTION_TOKEN/NOTION_DATABASE_ID not set")
        return

    title = data["invoice_number"] or f"Anthropic {iso_date or ''}".strip()
    props: dict = {
        NOTION_PROPS["title"]: {"title": [{"text": {"content": title}}]},
        NOTION_PROPS["status"]: {"select": {"name": NOTION_DEFAULT_STATUS}},
    }
    if data["amount"]:
        props[NOTION_PROPS["amount"]] = {"number": float(data["amount"])}
    if data["currency"]:
        props[NOTION_PROPS["currency"]] = {"rich_text": [{"text": {"content": data["currency"]}}]}
    if data["invoice_number"]:
        props[NOTION_PROPS["invoice_number"]] = {"rich_text": [{"text": {"content": data["invoice_number"]}}]}
    if iso_date:
        props[NOTION_PROPS["invoice_date"]] = {"date": {"start": iso_date}}
    if sender_email:
        props[NOTION_PROPS["sender_email"]] = {"email": sender_email}

    payload = {"parent": {"database_id": NOTION_DATABASE_ID}, "properties": props}

    if DRY_RUN:
        print(f"   [DRY_RUN] would CREATE Notion row: {title} | ${data['amount'] or '?'}")
        return

    req = urlrequest.Request(
        NOTION_API,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {NOTION_TOKEN}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with urlrequest.urlopen(req) as resp:
            body = json.loads(resp.read())
        print(f"   ✓ Notion row created: {body.get('url', '(no url)')}")
    except HTTPError as e:
        print(f"   ✗ Notion error {e.code}: {e.read().decode(errors='replace')[:300]}")


def main() -> None:
    if not GMAIL_APP_PASSWORD:
        print("ERROR: set GMAIL_APP_PASSWORD in CONFIG first (see setup instructions at top).")
        return

    print(f"{'[DRY RUN] ' if DRY_RUN else ''}Checking Gmail for unread mail from '{SENDER_FILTER}'...\n")

    imap = imaplib.IMAP4_SSL(IMAP_HOST)
    imap.login(GMAIL_ADDRESS, GMAIL_APP_PASSWORD.replace(" ", ""))
    imap.select("INBOX")

    # Unread messages from Anthropic
    status, data = imap.search(None, "UNSEEN", "FROM", SENDER_FILTER)
    uids = data[0].split() if data and data[0] else []
    print(f"Found {len(uids)} new message(s).")
    if MAX_PER_RUN and len(uids) > MAX_PER_RUN:
        uids = uids[:MAX_PER_RUN]
        print(f"Processing the {MAX_PER_RUN} oldest this run (MAX_PER_RUN limit).")
    print()

    total_paid = 0.0
    count_paid = 0

    for uid in uids:
        # Use BODY.PEEK so we don't mark as read until we've handled it.
        _, msg_data = imap.fetch(uid, "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])

        sender = _decode(msg.get("From"))
        subject = _decode(msg.get("Subject"))
        message_id = msg.get("Message-ID", "")
        sender_email = email.utils.parseaddr(sender)[1]

        # Date -> ISO (YYYY-MM-DD)
        iso_date = ""
        try:
            iso_date = parsedate_to_datetime(msg.get("Date")).date().isoformat()
        except Exception:
            pass

        body = get_body_text(msg)
        payment = extract_payment(body, subject)

        if payment["amount"]:
            total_paid += float(payment["amount"])
            count_paid += 1

        print(f"• {subject}")
        print(f"   from: {sender_email} | date: {iso_date} | amount: ${payment['amount'] or '?'} "
              f"| invoice: {payment['invoice_number'] or '-'}")

        send_reply(sender_email, subject, message_id)
        create_notion_record(payment, sender_email, iso_date)

        # Mark as read so it isn't processed again next run.
        if not DRY_RUN:
            imap.store(uid, "+FLAGS", "\\Seen")
        print()

    imap.logout()
    print(f"Total paid to Anthropic in this batch: ${total_paid:.2f} across {count_paid} receipt(s).")
    print("Done." + ("  (DRY RUN — nothing was sent or written)" if DRY_RUN else ""))


if __name__ == "__main__":
    main()
