from __future__ import annotations


class DomainError(Exception):
    code = "domain_error"
    status = 400

    def __init__(self, message: str = ""):
        super().__init__(message)
        self.message = message or self.code.replace("_", " ").capitalize()


class IllegalTransition(DomainError):
    code = "illegal_transition"


class InsufficientStock(DomainError):
    code = "insufficient_stock"


class PurchaseLimitExceeded(DomainError):
    code = "purchase_limit_exceeded"


class VoucherInvalid(DomainError):
    code = "voucher_invalid"


class VoucherExhausted(DomainError):
    code = "voucher_exhausted"


class QuoteChanged(DomainError):
    code = "quote_changed"

    def __init__(self, message: str = "Prices or availability changed", changed: list | None = None):
        super().__init__(message)
        self.changed = changed or []


class QuoteExpired(DomainError):
    code = "quote_expired"


class RefundExceedsCaptured(DomainError):
    code = "refund_exceeds_captured"


class NotEligible(DomainError):
    code = "not_eligible"


class StaleVersion(DomainError):
    code = "stale_version"

    def __init__(self, message: str = "This item was updated elsewhere, please retry."):
        super().__init__(message)


class Forbidden(DomainError):
    code = "forbidden"
    status = 403


class InvalidSignature(DomainError):
    code = "invalid_signature"


class NotFound(DomainError):
    code = "not_found"
    status = 404


class ValidationError(DomainError):
    code = "validation_error"
