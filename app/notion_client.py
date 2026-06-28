"""Create cake-order cards in the Merenga Schedule Notion database.

Each order becomes a page with:
  - Name (title) + Date properties
  - Rich ORDER DETAILS content blocks

Required Config Vars: NOTION_TOKEN, NOTION_DATABASE_ID
"""

from __future__ import annotations

import os
from datetime import datetime, timezone

import requests

from app.models import CakeOrder

NOTION_API    = "https://api.notion.com/v1/pages"
NOTION_VERSION = "2022-06-28"
DEFAULT_STATUS = os.environ.get("NOTION_STATUS", "New Order")


def _heading(text: str) -> dict:
    return {
        "object": "block",
        "type": "heading_3",
        "heading_3": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _para(text: str) -> dict:
    return {
        "object": "block",
        "type": "paragraph",
        "paragraph": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _bullet(text: str) -> dict:
    return {
        "object": "block",
        "type": "bulleted_list_item",
        "bulleted_list_item": {"rich_text": [{"type": "text", "text": {"content": text}}]},
    }


def _divider() -> dict:
    return {"object": "block", "type": "divider", "divider": {}}


def _build_blocks(order: CakeOrder) -> list[dict]:
    blocks: list[dict] = []

    blocks.append(_heading("📋 ORDER DETAILS"))
    blocks.append(_divider())

    # Date
    blocks.append(_heading("DATE"))
    blocks.append(_para(order.event_date or "—"))

    # Contact
    blocks.append(_heading("CONTACT"))
    lines = []
    if order.customer_email:
        lines.append(f"Email: {order.customer_email}")
    if order.phone_number:
        lines.append(f"Phone: {order.phone_number}")
    blocks.append(_para("\n".join(lines) if lines else "—"))

    # Cake size
    blocks.append(_heading("CAKE SIZE"))
    size_text = order.cake_type or "—"
    if order.servings:
        size_text += f" (serves {order.servings})"
    blocks.append(_para(size_text))

    # Flavor
    blocks.append(_heading("CAKE FLAVOR"))
    blocks.append(_para(order.cake_flavor or "—"))

    # Design details
    blocks.append(_heading("DESIGN DETAILS"))
    if order.special_requests:
        for line in order.special_requests.split("\n"):
            line = line.strip("-• ").strip()
            if line:
                blocks.append(_bullet(line))
    else:
        blocks.append(_para("—"))

    # Delivery
    blocks.append(_heading("DELIVERY / PICKUP"))
    pickup = order.delivery_or_pickup or "—"
    blocks.append(_para(pickup))
    if order.delivery_address:
        blocks.append(_para(order.delivery_address))

    # Budget / pricing
    if order.budget:
        blocks.append(_heading("BUDGET"))
        blocks.append(_para(order.budget))

    # Internal summary
    if order.order_summary:
        blocks.append(_divider())
        blocks.append(_heading("📝 SUMMARY (internal)"))
        blocks.append(_para(order.order_summary))

    return blocks


def create_order(order: CakeOrder) -> str:
    """Create a Notion page for the order and return its URL."""
    today = datetime.now(timezone.utc).date().isoformat()
    event_date = order.event_date or today

    # Try to parse event_date as ISO
    try:
        from datetime import datetime as dt
        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d", "%m/%d/%Y"):
            try:
                event_date = dt.strptime(event_date.strip(), fmt).date().isoformat()
                break
            except ValueError:
                continue
    except Exception:
        event_date = today

    props = {
        "Name": {"title": [{"text": {"content": order.customer_name or "New inquiry"}}]},
        "Date": {"date": {"start": event_date}},
    }

    payload = {
        "parent": {"database_id": os.environ["NOTION_DATABASE_ID"]},
        "properties": props,
        "children": _build_blocks(order),
    }

    resp = requests.post(
        NOTION_API,
        headers={
            "Authorization": f"Bearer {os.environ['NOTION_TOKEN']}",
            "Notion-Version": NOTION_VERSION,
            "Content-Type": "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("url", "")
