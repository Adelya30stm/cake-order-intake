"""Extract a structured cake order AND draft the customer reply, using OpenAI.

Swapping to Claude later is a one-function change (use the Anthropic SDK here).
"""

from __future__ import annotations

import json
import os

from openai import OpenAI

from app.models import CakeOrder

_client: OpenAI | None = None


def _get_client() -> OpenAI:
    global _client
    if _client is None:
        _client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])
    return _client


def _system_prompt() -> str:
    business = os.environ.get("BUSINESS_NAME", "our bakery")
    return f"""\
You are an order-intake assistant for a cake bakery ({business}).
Read the customer email and return ONLY valid JSON with EXACTLY these keys
(use an empty string if a field is missing — never invent facts):
{{
  "customer_name": "", "customer_email": "", "event_type": "", "event_date": "",
  "cake_type": "", "cake_flavor": "", "servings": "", "delivery_or_pickup": "",
  "delivery_address": "", "budget": "", "phone_number": "", "special_requests": "",
  "order_summary": "", "customer_reply": ""
}}

Rules:
- "delivery_or_pickup" must be exactly "Delivery" or "Pickup" (or "").
- "servings" = just the number or range (e.g. "7-10").
- "order_summary" = one short sentence summarizing the request (for internal notes).
- "customer_reply" = a warm, professional reply email body (3-5 sentences):
  greet by name, confirm you received the request and restate the key details,
  say you'll follow up shortly with pricing and availability, invite a reference
  photo if relevant. Do NOT promise a price. Sign off as "{business}".
"""


def parse_cake_order(email_text: str) -> CakeOrder:
    """Call the model and return a validated CakeOrder (incl. drafted reply)."""
    resp = _get_client().chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        temperature=0.3,
        response_format={"type": "json_object"},
        messages=[
            {"role": "system", "content": _system_prompt()},
            {"role": "user", "content": email_text},
        ],
    )
    data = json.loads(resp.choices[0].message.content or "{}")
    return CakeOrder(**{k: (v or "") for k, v in data.items() if k in CakeOrder.model_fields})
