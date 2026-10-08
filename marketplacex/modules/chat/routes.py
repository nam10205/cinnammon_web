from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, url_for

from ...auth import current_user, require_role
from . import service

bp = Blueprint("chat", __name__)


@bp.post("/chat/start")
@require_role("customer")
def start():
    c = service.get_or_create(current_user(), request.form.get("shop_id", type=int))
    return redirect(url_for("chat.thread", conversation_id=c.id))


@bp.get("/chat")
@require_role("customer", "seller")
def inbox():
    return render_template("customer/chat.html", conversations=service.conversations_for(current_user()), active=None)


@bp.get("/chat/<int:conversation_id>")
@require_role("customer", "seller")
def thread(conversation_id):
    u = current_user()
    return render_template("customer/chat.html", conversations=service.conversations_for(u),
                           active=service.get(u, conversation_id))


@bp.post("/chat/<int:conversation_id>/send")
@require_role("customer", "seller")
def send(conversation_id):
    service.send(current_user(), conversation_id, request.form.get("body"))
    return redirect(url_for("chat.thread", conversation_id=conversation_id))
