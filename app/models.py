"""Data models for the cake-order intake app."""

from __future__ import annotations

from pydantic import BaseModel


class CakeOrder(BaseModel):
    """Structured order extracted from a customer email (+ the drafted reply)."""

    customer_name: str = ""
    customer_email: str = ""
    event_type: str = ""
    event_date: str = ""
    cake_type: str = ""
    cake_flavor: str = ""
    servings: str = ""
    delivery_or_pickup: str = ""        # "Delivery" | "Pickup" | ""
    delivery_address: str = ""
    budget: str = ""
    phone_number: str = ""
    special_requests: str = ""
    order_summary: str = ""             # short human summary for the Notion page body
    customer_reply: str = ""            # the email body to send back to the customer
