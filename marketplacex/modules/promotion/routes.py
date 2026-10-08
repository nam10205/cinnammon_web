from __future__ import annotations

from flask import Blueprint, render_template

from . import service

bp = Blueprint("promotion", __name__)


@bp.get("/campaigns/<int:campaign_id>")
def campaign(campaign_id):
    c = service.get_campaign(campaign_id)
    shop_offers = {}
    for v in c.vouchers:
        if v.shop_id:
            from ..catalog import service as catalog
            shop_offers[v.id] = catalog.offers_of_shop(v.shop_id)
    return render_template("customer/campaign.html", campaign=c, offers=service.eligible_offers(c), shop_offers=shop_offers)
