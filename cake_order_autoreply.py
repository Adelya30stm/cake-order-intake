"""
Cake Order Intake & Auto-Reply — merenga cakes
================================================

Локальный «черновик мозгов» автоматизации (тот же flow, что собираем в Zapier):

    Gmail (новая заявка)
        -> извлечь поля заказа
        -> создать карточку в Notion
        -> сгенерировать ответ клиенту (черновик / Approve)

Этот файл можно запускать и править прямо в Cursor, чтобы придумывать:
  - какие поля вытаскивать,
  - текст автоответа (REPLY_TEMPLATE),
  - расписание проверки почты (SCHEDULE).

Запуск:  python3 cake_order_autoreply.py
(работает на чистом Python, без внешних зависимостей — это «песочница» логики)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, asdict


# ---------------------------------------------------------------------------
# 1. CONFIG — edit these freely in Cursor
# ---------------------------------------------------------------------------

BUSINESS_NAME = "merenga cakes"

# How often the automation should check Gmail for new order emails.
# In Zapier this maps to the trigger polling interval; here it's just a note
# you can tweak while planning the schedule.
SCHEDULE = {
    "check_every_minutes": 15,        # how often to poll Gmail
    "active_hours": "08:00-22:00",    # only notify you during these hours
    "timezone": "America/New_York",   # bakery local time
}

# Notion board columns (order status pipeline).
STATUS_PIPELINE = [
    "New Order",
    "Reviewing",
    "Quote Sent",
    "Confirmed",
    "Completed",
]
DEFAULT_STATUS = "New Order"

# Customer auto-reply. {fields} are filled from the parsed order.
# Set AUTO_SEND = False to only create a draft (safe "Approve" mode).
AUTO_SEND = False

REPLY_TEMPLATE = (
    "Hi {customer_name},\n\n"
    "Thank you for your cake request! \U0001F382\n\n"
    "We received the details for your {cake_size} cake on {order_date} "
    "({delivery_or_pickup}). We'll review the design — \"{design_description}\" — "
    "and get back to you shortly with pricing and availability.\n\n"
    "Feel free to reply with the logo photo if you have one.\n\n"
    "Warmly,\n"
    f"{BUSINESS_NAME}"
)


# ---------------------------------------------------------------------------
# 2. ORDER MODEL
# ---------------------------------------------------------------------------

@dataclass
class Order:
    customer_name: str | None = None
    email: str | None = None
    phone: str | None = None
    order_date: str | None = None
    cake_size: str | None = None
    servings: str | None = None
    delivery_or_pickup: str | None = None
    address: str | None = None
    design_description: str | None = None
    special_notes: str | None = None
    status: str = DEFAULT_STATUS


# ---------------------------------------------------------------------------
# 3. PARSE — extract order fields from a Squarespace form-submission email
# ---------------------------------------------------------------------------

# Maps a label in the email to a field on Order. Add/rename labels here to
# match your own Squarespace form questions.
LABEL_TO_FIELD = {
    "Name": "customer_name",
    "Email": "email",
    "Phone": "phone",
    "Date for order": "order_date",
    "Cake size or dessert.": "cake_size",
    "Pickup or Delivery?": "delivery_or_pickup",
    "Address for delivery if you chose this option.": "address",
    "Design Description": "design_description",
}


def parse_order_email(body: str) -> Order:
    """Pull order fields out of the raw email body using the labels above."""
    order = Order()

    # Build one big regex: capture text after each known label up to the next label.
    labels = list(LABEL_TO_FIELD.keys())
    for i, label in enumerate(labels):
        # Stop at the next label, "Create Invoice", or end of string.
        stops = [re.escape(l) for l in labels[i + 1:]] + ["Create Invoice", "$"]
        pattern = re.escape(label) + r"\s*:?\s*(.*?)(?=" + "|".join(stops) + ")"
        match = re.search(pattern, body, re.DOTALL)
        if match:
            value = match.group(1).strip(" \n\t,")
            if value:
                setattr(order, LABEL_TO_FIELD[label], value)

    # Servings is usually written inside the cake-size answer ("7-10 serving size").
    if order.cake_size:
        serv = re.search(r"(\d+\s*-\s*\d+)\s*serv", order.cake_size, re.IGNORECASE)
        if serv:
            order.servings = serv.group(1).replace(" ", "")

    # Clean up email if it carries extra text ("..., accepts marketing: true").
    if order.email:
        email_match = re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", order.email)
        if email_match:
            order.email = email_match.group(0)

    return order


# ---------------------------------------------------------------------------
# 4. REPLY — build the customer message
# ---------------------------------------------------------------------------

def generate_reply(order: Order) -> str:
    """Fill the reply template, tolerating any missing fields."""
    safe = {k: (v if v else "—") for k, v in asdict(order).items()}
    return REPLY_TEMPLATE.format(**safe)


# ---------------------------------------------------------------------------
# 5. INTEGRATION HOOKS — wire these to Zapier / Notion / Gmail later
# ---------------------------------------------------------------------------

def push_to_notion(order: Order) -> None:
    """TODO: create a row in the Notion 'Orders' database.

    In Zapier this is the 'Notion -> Create Database Item' step.
    Locally we just print what would be sent.
    """
    print("[Notion] Would create card:")
    for key, value in asdict(order).items():
        print(f"    {key:20} = {value}")


def send_or_draft_reply(order: Order, reply: str) -> None:
    """TODO: create a Gmail draft (or send) reply to the customer.

    In Zapier this is 'Gmail -> Create Draft Reply' (AUTO_SEND=False)
    or 'Gmail -> Send Email' (AUTO_SEND=True).
    """
    action = "SEND" if AUTO_SEND else "DRAFT"
    print(f"\n[Gmail] Would {action} to {order.email}:\n")
    print(reply)


# ---------------------------------------------------------------------------
# 6. PIPELINE
# ---------------------------------------------------------------------------

def handle_email(body: str) -> Order:
    order = parse_order_email(body)
    push_to_notion(order)
    reply = generate_reply(order)
    send_or_draft_reply(order, reply)
    return order


# ---------------------------------------------------------------------------
# 7. DEMO — real example (Jocelyn Castro), so you can run & tweak immediately
# ---------------------------------------------------------------------------

EXAMPLE_EMAIL = """\
Name: Jocelyn Castro
Email: customer@example.com, accepts marketing: true
Phone: (571) 430-5222
Date for order: June 13, 2026
Cake size or dessert.: medium cake. 6 inches cake. 7-10 serving size.
Pickup or Delivery?: Delivery
Address for delivery if you chose this option.: 13982 Flagtree Pl, Manassas, VA 22309, United States
Design Description: I would like a black cake with the words in white except for LiftNova which will be in orange: "Happy 1 year LiftNova!" I have a photo of a logo if we could add it to the cake or similar I can send it to you
Create Invoice
"""


if __name__ == "__main__":
    print(f"Schedule: every {SCHEDULE['check_every_minutes']} min, "
          f"{SCHEDULE['active_hours']} {SCHEDULE['timezone']}")
    print(f"Pipeline: {' -> '.join(STATUS_PIPELINE)}\n")
    print("=" * 70)
    handle_email(EXAMPLE_EMAIL)
    print("=" * 70)
