"""FastAPI app: Gmail -> filter -> AI parse + draft reply -> Notion -> auto-reply.

Endpoints:
  GET  /          health check
  POST /process   run one intake pass (call this from Heroku Scheduler via curl)
  GET  /process   same, convenient for manual testing in a browser

Flow:
  1. Gmail (IMAP): find unread inbox emails (optionally from one sender).
  2. Filter: keep only emails that look like cake orders/inquiries (keywords).
  3. AI: extract the order AND draft the customer reply (customer_reply).
  4. Notion: create the order card (Status = New Inquiry).
  5. Gmail (SMTP): send the AI-written reply, subject "Re: <original subject>".
  6. Mark the email read.

Safety: DRY_RUN=true (default) logs what WOULD happen — nothing is sent or written.
"""

from __future__ import annotations

import os

from fastapi import FastAPI

from app import notion_client
from app.ai_parser import parse_cake_order
from app.gmail_client import Gmail
from app.models import CakeOrder

app = FastAPI(title="Cake Order Intake")

# Optional: restrict to a sender (e.g. Squarespace). Empty = any sender.
SENDER_FILTER = os.environ.get("SENDER_FILTER", "")
BUSINESS_NAME = os.environ.get("BUSINESS_NAME", "merenga cakes")
REPLY_MODE = os.environ.get("REPLY_MODE", "send").lower()   # send | off
DRY_RUN = os.environ.get("DRY_RUN", "true").lower() == "true"
MAX_PER_RUN = int(os.environ.get("MAX_PER_RUN", "10"))      # 0 = no limit

ORDER_KEYWORDS = [
    k.strip() for k in os.environ.get(
        "ORDER_KEYWORDS",
        "cake,order,custom cake,inquiry,cupcake,dessert,birthday,wedding",
    ).split(",") if k.strip()
]


import re

def is_bakery_order(subject: str, body: str) -> bool:
    """Keep only emails that mention a bakery keyword as a whole word.

    NOTE: keyword matching alone is noisy ('order' appears in marketing mail).
    The reliable gate is SENDER_FILTER (your order channel, e.g. Squarespace).
    """
    text = f"{subject}\n{body}".lower()
    return any(re.search(rf"\b{re.escape(k.lower())}\b", text) for k in ORDER_KEYWORDS)


def fallback_reply(order: CakeOrder) -> str:
    """Used only if the AI did not produce a customer_reply."""
    name = order.customer_name or "there"
    return (
        f"Hi {name},\n\nThank you for your cake request! \U0001F382 "
        "We've received your details and will get back to you shortly with pricing "
        f"and availability.\n\nWarmly,\n{BUSINESS_NAME}"
    )


def run_once() -> dict:
    """Process matching unread emails once. Returns a summary dict."""
    gm = Gmail()
    results = []
    try:
        uids = gm.search_unread(SENDER_FILTER)
        uids = list(reversed(uids))   # newest first
        if MAX_PER_RUN:
            uids = uids[:MAX_PER_RUN]

        for uid in uids:
            mail = gm.get_email(uid)

            if not is_bakery_order(mail["subject"], mail["text"]):
                results.append({"subject": mail["subject"], "skipped": "not a bakery order"})
                continue

            order = parse_cake_order(mail["text"])
            reply_body = order.customer_reply or fallback_reply(order)
            reply_subject = f"Re: {mail['subject']}" if mail["subject"] else "Re: Your cake request \U0001F382"

            notion_url = None
            replied = False
            if not DRY_RUN:
                notion_url = notion_client.create_order(order)
                if REPLY_MODE == "send" and order.customer_email:
                    gm.send_email(order.customer_email, reply_subject, reply_body)
                    replied = True
                gm.mark_read(uid)

            results.append({
                "customer": order.customer_name,
                "email": order.customer_email,
                "summary": order.order_summary,
                "notion_url": notion_url,
                "replied": replied,
            })
    finally:
        gm.close()

    return {"processed": len(results), "dry_run": DRY_RUN, "results": results}


@app.get("/")
def health() -> dict:
    return {"status": "ok", "sender_filter": SENDER_FILTER or "(any)",
            "keywords": ORDER_KEYWORDS, "dry_run": DRY_RUN}


@app.api_route("/process", methods=["GET", "POST"])
def process() -> dict:
    return run_once()
