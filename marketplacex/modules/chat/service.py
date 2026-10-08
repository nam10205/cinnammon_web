"""Customer <-> seller chat (use cases: Chat with Seller / Chat with Customer)."""
from __future__ import annotations

from ...errors import NotFound, ValidationError
from ...extensions import db
from ..admin import policy
from ..seller import service as seller_service
from ..seller.models import Shop
from .models import ChatMessage, Conversation


def get_or_create(customer, shop_id: int) -> Conversation:
    seller_service.get_shop(shop_id)
    c = Conversation.query.filter_by(customer_id=customer.id, shop_id=shop_id).first()
    if c is None:
        c = Conversation(customer_id=customer.id, shop_id=shop_id, created_at=policy.now())
        db.session.add(c)
        db.session.commit()
    return c


def _participant(user, conversation_id: int) -> Conversation:
    c = db.session.get(Conversation, conversation_id)
    if c is None or user.id not in (c.customer_id, c.shop.owner_id):
        raise NotFound("Conversation not found")
    return c


def send(user, conversation_id: int, body: str) -> ChatMessage:
    c = _participant(user, conversation_id)
    body = (body or "").strip()
    if not body or len(body) > 1000:
        raise ValidationError("Message must be 1 to 1000 characters")
    m = ChatMessage(conversation_id=c.id, sender_id=user.id, body=body, at=policy.now())
    db.session.add(m)
    other = c.shop.owner_id if user.id == c.customer_id else c.customer_id
    from ..notification import service as notif
    notif.notify(other, "chat_message", f"New message from {user.name}: {body[:60]}", link=f"/chat/{c.id}")
    db.session.commit()
    return m


def conversations_for(user) -> list[Conversation]:
    if user.role == "seller":
        return (Conversation.query.join(Shop).filter(Shop.owner_id == user.id)
                .order_by(Conversation.id.desc()).all())
    return Conversation.query.filter_by(customer_id=user.id).order_by(Conversation.id.desc()).all()


def messages(user, conversation_id: int) -> list[ChatMessage]:
    return _participant(user, conversation_id).messages


def get(user, conversation_id: int) -> Conversation:
    return _participant(user, conversation_id)
