from __future__ import annotations

from ...extensions import db


class Order(db.Model):
    __tablename__ = "Order"
    id = db.Column("orderID", db.Integer, primary_key=True)
    customer_id = db.Column("customerID", db.Integer, db.ForeignKey("Customer.customerID"), nullable=False)
    product_id = db.Column("productID", db.Integer, db.ForeignKey("Product.productID"), nullable=False)
    address_id = db.Column("addressID", db.Integer, db.ForeignKey("Address.addressID"), nullable=False)
    quantity = db.Column("quantity", db.Integer, nullable=False)
    unit_price = db.Column("unitPrice", db.Integer, nullable=False)
    shipping_fee = db.Column("shippingFee", db.Integer, nullable=False, default=0)
    total_price = db.Column("totalPrice", db.Integer, nullable=False)
    payment_method = db.Column("paymentMethod", db.String(255), nullable=False)   # cod | card
    payment_status = db.Column("paymentStatus", db.String(255), nullable=False)   # unpaid | paid | refunded
    status = db.Column("status", db.String(255), nullable=False)
    ordered_at = db.Column("orderedAt", db.DateTime, nullable=False)
    shipped_at = db.Column("shippedAt", db.DateTime, nullable=True)
    delivered_at = db.Column("deliveredAt", db.DateTime, nullable=True)

    customer = db.relationship("Customer")
    product = db.relationship("Product")
    address = db.relationship("Address")
