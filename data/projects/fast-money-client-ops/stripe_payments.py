"""Stripe sandbox adapter. Never store or log API secrets."""
from __future__ import annotations
import hashlib
import hmac
import json
import os
import time
from uuid import uuid4
from urllib.parse import urlencode
from urllib.request import Request, urlopen

class StripeConfigurationError(RuntimeError):
    pass

def checkout_session(*, invoice_id: str, amount_cents: int, success_url: str, cancel_url: str) -> dict:
    secret = os.environ.get("STRIPE_SECRET_KEY", "")
    if not secret.startswith("sk_test_"):
        raise StripeConfigurationError("Stripe test secret key is not configured.")
    if not invoice_id or amount_cents < 50:
        raise ValueError("Valid invoice ID and amount of at least 50 cents required.")
    if not success_url.startswith("https://") or not cancel_url.startswith("https://"):
        raise ValueError("Checkout return URLs must use HTTPS.")
    form = urlencode({
        "mode":"payment", "payment_method_types[0]":"card",
        "line_items[0][price_data][currency]":"usd",
        "line_items[0][price_data][unit_amount]":str(amount_cents),
        "line_items[0][price_data][product_data][name]":"WhatIf Company invoice "+invoice_id,
        "line_items[0][quantity]":"1",
        "client_reference_id":invoice_id,
        "metadata[invoice_id]":invoice_id,
        "success_url":success_url,
        "cancel_url":cancel_url,
    }).encode()
    req=Request("https://api.stripe.com/v1/checkout/sessions",data=form,headers={
        "Authorization":"Bearer "+secret,
        "Content-Type":"application/x-www-form-urlencoded",
        "Idempotency-Key":"whatif-checkout-"+invoice_id+"-"+uuid4().hex,
    },method="POST")
    with urlopen(req,timeout=20) as response:
        return json.load(response)

def verified_webhook(raw_body: bytes, signature_header: str, *, now: int | None = None) -> dict:
    secret=os.environ.get("STRIPE_WEBHOOK_SECRET","")
    if not secret.startswith("whsec_"):
        raise StripeConfigurationError("Stripe webhook secret is not configured.")
    parts={}
    for segment in signature_header.split(","):
        if "=" in segment:
            k,v=segment.strip().split("=",1)
            parts.setdefault(k,[]).append(v)
    try:
        stamp=int(parts.get("t",[""])[0])
    except ValueError as exc:
        raise ValueError("Invalid Stripe signature timestamp") from exc
    if stamp <= 0 or abs((now if now is not None else int(time.time()))-stamp)>300:
        raise ValueError("Stripe webhook timestamp outside tolerance")
    expected=hmac.new(secret.encode(),str(stamp).encode()+b"."+raw_body,hashlib.sha256).hexdigest()
    if not any(hmac.compare_digest(expected,sig) for sig in parts.get("v1",[])):
        raise ValueError("Invalid Stripe webhook signature")
    event=json.loads(raw_body)
    if not isinstance(event,dict) or not isinstance(event.get("id"),str) or not event["id"].startswith("evt_") or not isinstance(event.get("type"),str):
        raise ValueError("Invalid Stripe event")
    return event
