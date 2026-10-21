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


class Forbidden(DomainError):
    code = "forbidden"
    status = 403


class NotFound(DomainError):
    code = "not_found"
    status = 404


class ValidationError(DomainError):
    code = "validation_error"
