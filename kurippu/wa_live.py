"""WhatsApp Web bridge API: receive messages and send keeper-approved replies."""
import base64
import hmac
import io
import os

import httpx
import qrcode
from fastapi import APIRouter, Header, HTTPException, Response
from pydantic import BaseModel, Field


class Incoming(BaseModel):
    msg_id: str = Field(max_length=200)
    chat_id: str = Field(max_length=100)
    name: str = Field("", max_length=80)
    phone: str = Field("", max_length=20)
    body: str = Field(min_length=1, max_length=4000)


class SendIn(BaseModel):
    msg_id: str = Field(max_length=200)
    reply: str = Field(min_length=1, max_length=4000)
    upi_uri: str | None = Field(None, max_length=2048)
    order_id: int | None = Field(None, ge=1)


class RetryIn(BaseModel):
    msg_id: str = Field(max_length=200)


def qr_png_b64(uri: str) -> str:
    buf = io.BytesIO()
    qrcode.make(uri).save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def send(bridge: str, token: str, chat_id: str, text: str, upi_uri: str | None = None):
    payload = {"chat_id": chat_id, "text": text}
    if upi_uri:
        payload["image_base64"] = qr_png_b64(upi_uri)
    response = httpx.post(f"{bridge}/send", json=payload,
                          headers={"X-Kurippu-Token": token}, timeout=60)
    response.raise_for_status()


def build_router(app):
    router = APIRouter(prefix="/api/wa")
    bridge = os.environ.get("WA_BRIDGE_URL", "http://127.0.0.1:8766").rstrip("/")
    token = os.environ.get("KURIPPU_WA_TOKEN", "").strip()

    def auth(received):
        if not token:
            raise HTTPException(503, "WhatsApp bridge is not configured")
        if not received or not hmac.compare_digest(received, token):
            raise HTTPException(401, "bad token")

    def deliver(msg_id, message, reply, upi_uri, order_id):
        if not token:
            raise HTTPException(503, "WhatsApp bridge is not configured")
        if message["status"] not in {"received", "send_failed"}:
            raise HTTPException(409, "This WhatsApp message is not ready to send")
        if upi_uri and not upi_uri.startswith("upi://pay?"):
            raise HTTPException(400, "Invalid UPI payment link")
        if order_id is not None and not app.state.store.order_exists(order_id):
            raise HTTPException(404, "No such order")
        if not app.state.store.wa_claim_send(msg_id, reply, upi_uri, order_id):
            raise HTTPException(409, "This WhatsApp message is already being sent or was sent")
        try:
            send(bridge, token, message["chat_id"], reply, upi_uri)
        except httpx.HTTPStatusError as error:
            try:
                detail = error.response.json().get("error")
            except ValueError:
                detail = None
            note = detail if isinstance(detail, str) else "WhatsApp rejected the send request"
            app.state.store.wa_set_delivery(
                msg_id, "send_failed", reply, upi_uri, note=note, order_id=order_id)
            raise HTTPException(502, note) from None
        except httpx.HTTPError:
            app.state.store.wa_set_delivery(
                msg_id, "send_failed", reply, upi_uri,
                note="Could not confirm delivery; check WhatsApp before retrying",
                order_id=order_id)
            raise HTTPException(502, "WhatsApp send failed; check the chat before retrying") from None
        app.state.store.wa_set_delivery(msg_id, "sent", reply, upi_uri, order_id=order_id)
        return {"ok": True}

    @router.post("/incoming")
    def incoming(message: Incoming, x_kurippu_token: str | None = Header(None)):
        auth(x_kurippu_token)
        claimed = app.state.store.wa_claim(
            message.msg_id, message.chat_id, message.name, message.phone, message.body)
        return {"status": "received" if claimed else "duplicate"}

    @router.get("/inbox")
    def inbox(response: Response):
        response.headers["Cache-Control"] = "no-store"
        return app.state.store.wa_inbox()

    @router.post("/send")
    def send_reviewed(body: SendIn):
        store = app.state.store
        message = store.wa_get(body.msg_id)
        if not message:
            raise HTTPException(404, "No such WhatsApp message")
        return deliver(body.msg_id, message, body.reply, body.upi_uri, body.order_id)

    @router.post("/retry")
    def retry_delivery(body: RetryIn):
        store = app.state.store
        message = store.wa_get(body.msg_id)
        if not message:
            raise HTTPException(404, "No such WhatsApp message")
        if message["status"] != "send_failed" or not message["reply"]:
            raise HTTPException(409, "There is no failed WhatsApp reply to retry")
        return deliver(body.msg_id, message, message["reply"], message["upi_uri"], message["order_id"])

    @router.post("/dismiss/{msg_id}")
    def dismiss(msg_id: str):
        store = app.state.store
        if not store.wa_get(msg_id):
            raise HTTPException(404, "No such WhatsApp message")
        if not store.wa_dismiss(msg_id):
            raise HTTPException(409, "This WhatsApp message cannot be dismissed")
        return {"ok": True}

    @router.get("/status")
    def status(out: Response):
        out.headers["Cache-Control"] = "no-store"
        if not token:
            return {"configured": False, "ready": False, "qr_png_base64": None,
                    "bridge_down": True}
        try:
            bridge_response = httpx.get(f"{bridge}/status",
                                        headers={"X-Kurippu-Token": token}, timeout=5)
            bridge_response.raise_for_status()
            result = bridge_response.json()
            qr = result.pop("qr", None)
            result["qr_png_base64"] = qr_png_b64(qr) if qr else None
            result["configured"] = True
            result["bridge_down"] = False
            return result
        except (httpx.HTTPError, ValueError):
            return {"configured": True, "ready": False, "qr_png_base64": None,
                    "bridge_down": True}

    return router
