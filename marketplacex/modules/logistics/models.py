from __future__ import annotations

from ...extensions import db


class Shipment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    order_id = db.Column(db.Integer, db.ForeignKey("order.id"), nullable=False, index=True)
    kind = db.Column(db.String(10), nullable=False, default="forward")  # forward | return
    return_case_id = db.Column(db.Integer)
    carrier = db.Column(db.String(40), nullable=False, default="MX Express")
    tracking_no = db.Column(db.String(40), unique=True, nullable=False)
    label_url = db.Column(db.String(255))
    status = db.Column(db.String(30), nullable=False, default="label_created")
    weight_g = db.Column(db.Integer, default=0)
    promised_pickup_at = db.Column(db.DateTime)
    created_at = db.Column(db.DateTime)
    events = db.relationship("TrackingEvent", order_by="TrackingEvent.seq", cascade="all, delete-orphan")
    order = db.relationship("Order", backref=db.backref("shipments", order_by="Shipment.id"))


class TrackingEvent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shipment_id = db.Column(db.Integer, db.ForeignKey("shipment.id"), nullable=False)
    seq = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(30), nullable=False)
    location = db.Column(db.String(80))
    at = db.Column(db.DateTime, nullable=False)
    __table_args__ = (db.UniqueConstraint("shipment_id", "seq"),)
