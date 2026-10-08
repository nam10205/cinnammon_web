from __future__ import annotations

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))


class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-change-me")
    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL", "sqlite:///" + os.path.join(os.path.dirname(BASE_DIR), "instance", "marketplacex.db"))
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    PAYMENT_WEBHOOK_SECRET = os.environ.get("PAYMENT_WEBHOOK_SECRET", "demo-webhook-secret")
    NOTIFICATION_FAILURE_RATE = float(os.environ.get("NOTIFICATION_FAILURE_RATE", "0.05"))
    UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
    MAX_CONTENT_LENGTH = 5 * 1024 * 1024
