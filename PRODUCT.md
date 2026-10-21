# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

A teacher / grader and classmates watching a class demo. The site exists to show off an
8-table ERD (`Picture1.png`) through a working shop, so it must look polished and credible,
like a real store.

## Product Purpose

MarketplaceX is a demo storefront over a Supabase database of exactly 8 tables (FullName, Address,
Customer, SearchHistory, Category, Product, ProductImage, Order). Success means every table is
visibly exercised: browsing, text/voice/image search, cart, checkout, payment, simulated
shipping, seller and admin views.

## Operating Context

Presented live from a Mac browser. One-click logins (Customer Alice, Seller, Admin) on the
login page; no passwords. Shipping advances every 20 s on its own during the demo.

## Capabilities and Constraints

- Flask + Jinja templates, Bootstrap 5 via CDN, one `static/app.css`, small vanilla JS files.
- Catalogue: 8 Tiki categories × 65 products, Vietnamese product data, prices in ₫.
- UI chrome stays English; product names, descriptions and ₫ prices stay exactly as stored.
- Simulated card (4242…) or cash on delivery; nothing real is charged or shipped.

## Brand Commitments

- Name: **MarketplaceX** (renamed from MarketplaceX).
- Voice: clean and premium: calm, editorial, boutique-like.

## Evidence on Hand

Real Tiki product names, images (remote URLs), prices and ratings in `data/tiki_catalog.json`.
No testimonials, reviews, press or customer counts exist; do not invent any.

## Product Principles

1. The data is the star: every screen should make the underlying table rows easy to read.
2. Credible over flashy: it should pass for a real boutique shop.
3. Demo-proof: the main flows work in one click with no explanation needed.
