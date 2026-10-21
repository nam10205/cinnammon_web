from __future__ import annotations

from datetime import datetime

from ...extensions import db


class Category(db.Model):
    __tablename__ = "Category"
    id = db.Column("categoryID", db.Integer, primary_key=True)
    name = db.Column("name", db.String(255), nullable=False)
    description = db.Column("description", db.String(255), default="")
    products = db.relationship("Product", back_populates="category", order_by="Product.id")


class Product(db.Model):
    __tablename__ = "Product"
    id = db.Column("productID", db.Integer, primary_key=True)
    category_id = db.Column("categoryID", db.Integer, db.ForeignKey("Category.categoryID"), nullable=False)
    title = db.Column("name", db.String(255), nullable=False)
    brand = db.Column("brandName", db.String(255), default="")
    description = db.Column("description", db.String(255), default="")
    price = db.Column("price", db.Integer, nullable=False, default=0)
    stock_quantity = db.Column("stockQuantity", db.Integer, nullable=False, default=0)
    avg_rating = db.Column("avgRating", db.Float, nullable=False, default=0.0)
    created_at = db.Column("createdAt", db.DateTime, default=datetime.utcnow)
    updated_at = db.Column("updatedAt", db.DateTime, default=datetime.utcnow)
    category = db.relationship("Category", back_populates="products")
    images = db.relationship("ProductImage", back_populates="product", order_by="ProductImage.id",
                             cascade="all, delete-orphan")

    @property
    def image_url(self) -> str | None:
        return self.images[0].url if self.images else None

    @property
    def image_vector(self) -> list[float] | None:
        from ..search.images import unpack
        return unpack(self.images[0].feature_vector) if self.images else None


class ProductImage(db.Model):
    __tablename__ = "ProductImage"
    id = db.Column("imageID", db.Integer, primary_key=True)
    product_id = db.Column("productID", db.Integer, db.ForeignKey("Product.productID"), nullable=False, index=True)
    url = db.Column("imageUrl", db.String(500), nullable=False)
    feature_vector = db.Column("featureVector", db.LargeBinary, nullable=True)
    product = db.relationship("Product", back_populates="images")
