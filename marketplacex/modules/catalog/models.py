from __future__ import annotations

from datetime import datetime

from ...extensions import db


class Category(db.Model):
    __tablename__ = "Category"
    id = db.Column("categoryID", db.Integer, primary_key=True)
    name = db.Column("name", db.String(255), nullable=False)
    description = db.Column("description", db.String(255), default="")
    parent_id = db.Column("parentID", db.Integer, db.ForeignKey("Category.categoryID"))
    attribute_schema = db.Column("attributeSchema", db.JSON, default=list)
    children = db.relationship("Category", backref=db.backref("parent", remote_side=[id]), order_by="Category.id")


class Product(db.Model):
    __tablename__ = "Product"
    id = db.Column("productID", db.Integer, primary_key=True)
    category_id = db.Column("categoryID", db.Integer, db.ForeignKey("Category.categoryID"), nullable=False)
    title = db.Column("name", db.String(255), nullable=False)
    brand = db.Column("brandName", db.String(255), default="")
    description = db.Column("description", db.String(255), default="")
    # Derived from offers, stock ledgers and reviews by catalog.service.sync_product.
    price = db.Column("price", db.Integer, nullable=False, default=0)
    stock_quantity = db.Column("stockQuantity", db.Integer, nullable=False, default=0)
    avg_rating = db.Column("avgRating", db.Float, nullable=False, default=0.0)
    created_at = db.Column("createdAt", db.DateTime, default=datetime.utcnow)
    updated_at = db.Column("updatedAt", db.DateTime, default=datetime.utcnow)
    shop_id = db.Column("shopID", db.Integer, db.ForeignKey("shop.id"), nullable=False, index=True)
    status = db.Column("status", db.String(20), nullable=False, default="draft")
    attributes = db.Column("attributes", db.JSON, default=dict)
    moderation_reason = db.Column("moderationReason", db.String(500))
    shop = db.relationship("Shop")
    category = db.relationship("Category")
    variants = db.relationship("Variant", backref="product", order_by="Variant.id")
    images = db.relationship("ProductImage", backref="product", order_by="[ProductImage.sort_order, ProductImage.id]",
                             cascade="all, delete-orphan")

    @property
    def image_url(self) -> str | None:
        return self.images[0].url if self.images else None

    @property
    def image_vector(self) -> list[float] | None:
        # Feature vectors are packed into ProductImage.featureVector in Task 6; nothing is stored yet.
        return None


class ProductImage(db.Model):
    __tablename__ = "ProductImage"
    id = db.Column("imageID", db.Integer, primary_key=True)
    product_id = db.Column("productID", db.Integer, db.ForeignKey("Product.productID"), nullable=False, index=True)
    url = db.Column("imageUrl", db.String(500), nullable=False)
    feature_vector = db.Column("featureVector", db.LargeBinary, nullable=True)
    sort_order = db.Column("sortOrder", db.Integer, nullable=False, default=0)


class Variant(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.Integer, db.ForeignKey("Product.productID"), nullable=False)
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
