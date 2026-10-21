from __future__ import annotations

from sqlalchemy import func
from sqlalchemy.orm import selectinload

from ...extensions import db
from ..catalog.models import Category, Product, ProductImage
from ..identity.models import Address, Customer, FullName
from ..order.models import Order
from ..search.models import SearchHistory

_TABLES = (("FullName", FullName), ("Address", Address), ("Customer", Customer),
           ("SearchHistory", SearchHistory), ("Category", Category), ("Product", Product),
           ("ProductImage", ProductImage), ("Order", Order))


def table_counts() -> list[tuple[str, int]]:
    return [(name, db.session.query(func.count()).select_from(model).scalar()) for name, model in _TABLES]


def category_rows() -> list[tuple[Category, int]]:
    counts = dict(db.session.query(Product.category_id, func.count(Product.id)).group_by(Product.category_id).all())
    cats = db.session.query(Category).order_by(Category.id).all()
    return [(c, counts.get(c.id, 0)) for c in cats]


def customer_rows() -> list[tuple[Customer, int]]:
    counts = dict(db.session.query(Order.customer_id, func.count(Order.id)).group_by(Order.customer_id).all())
    custs = (db.session.query(Customer).options(selectinload(Customer.full_name))
             .order_by(Customer.id).all())
    return [(c, counts.get(c.id, 0)) for c in custs]


def get_customer(customer_id: int) -> Customer:
    from ...errors import NotFound
    c = db.session.query(Customer).options(selectinload(Customer.full_name), selectinload(Customer.address)) \
        .filter(Customer.id == customer_id).one_or_none()
    if c is None:
        raise NotFound("Customer not found")
    return c


def customer_orders(customer: Customer) -> list[Order]:
    return (db.session.query(Order).options(selectinload(Order.product))
            .filter(Order.customer_id == customer.id)
            .order_by(Order.ordered_at.desc(), Order.id.desc()).all())


def customer_searches(customer: Customer) -> list[SearchHistory]:
    return (db.session.query(SearchHistory).filter(SearchHistory.customer_id == customer.id)
            .order_by(SearchHistory.searched_at.desc(), SearchHistory.id.desc()).all())


def all_orders() -> list[Order]:
    return (db.session.query(Order)
            .options(selectinload(Order.product), selectinload(Order.customer).selectinload(Customer.full_name))
            .order_by(Order.ordered_at.desc(), Order.id.desc()).all())
