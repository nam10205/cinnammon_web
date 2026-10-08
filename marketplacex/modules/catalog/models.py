from __future__ import annotations

from datetime import datetime

from ...extensions import db


class Category(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    parent_id = db.Column(db.Integer, db.ForeignKey("category.id"))
    attribute_schema = db.Column(db.JSON, default=list)
    children = db.relationship("Category", backref=db.backref("parent", remote_side=[id]), order_by="Category.id")


class Product(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False, index=True)
    category_id = db.Column(db.Integer, db.ForeignKey("category.id"), nullable=False)
    title = db.Column(db.String(200), nullable=False)
    description = db.Column(db.Text, default="")
    brand = db.Column(db.String(80), default="")
    attributes = db.Column(db.JSON, default=dict)
    status = db.Column(db.String(20), nullable=False, default="draft")
    moderation_reason = db.Column(db.String(500))
    image_url = db.Column(db.String(255))
    image_vector = db.Column(db.JSON)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    shop = db.relationship("Shop")
    category = db.relationship("Category")
    variants = db.relationship("Variant", backref="product", order_by="Variant.id")


class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("product.id"), nullable=False)
    name = db.Column(db.String(80), nullable=False)
    sku = db.Column(db.String(64))
    offer = db.relationship("Offer", uselist=False, backref="variant")
    __table_args__ = (db.UniqueConstraint("product_id", "name"),)


class Offer(db.Model):
    """A sellable offer: exactly one shop and one product variant (BR01)."""
    id = db.Column(db.Integer, primary_key=True)
    shop_id = db.Column(db.Integer, db.ForeignKey("shop.id"), nullable=False)
    variant_id = db.Column(db.Integer, db.ForeignKey("variant.id"), nullable=False)
    price_vnd = db.Column(db.Integer, nullable=False)
    original_price_vnd = db.Column(db.Integer)
    purchase_limit = db.Column(db.Integer, nullable=False, default=10)
    sold_count = db.Column(db.Integer, nullable=False, default=0)
    rating_avg = db.Column(db.Float, nullable=False, default=0.0)
    rating_count = db.Column(db.Integer, nullable=False, default=0)
    version = db.Column(db.Integer, nullable=False, default=1)
    shop = db.relationship("Shop")
    __table_args__ = (db.UniqueConstraint("shop_id", "variant_id"),)

    @property
    def product(self):
        return self.variant.product
