from __future__ import annotations

from flask import Blueprint, jsonify, request

from ...auth import current_user
from ...errors import ValidationError
from . import service

bp = Blueprint("assistant", __name__)


@bp.post("/api/assistant")
def chat():
    data = request.get_json(silent=True) or {}
    message = str(data.get("message") or "").strip()
    if not message:
        raise ValidationError("Please type a question")
    u = current_user()
    service.check_rate(f"user:{u.id}" if u else f"ip:{request.remote_addr}")
    reply = service.ask(message[:1000], data.get("history") or [], u if u and u.role == "customer" else None)
    return jsonify({"reply": reply})
