"""One bounded diagnostic and retry classification for HTTP and workers."""

from sqlalchemy.exc import DBAPIError, SQLAlchemyError

from marketlab.analytics.bars import BarError
from marketlab.datasets.normalize import VerificationCancelled
from marketlab.datasets.v2.common import V2Error

STATUS = {
    "not_found": 404,
    "revision_conflict": 409,
    "coverage_gap": 409,
    "not_ready": 409,
    "capacity_exceeded": 429,
    "unavailable": 503,
    "deadline_exceeded": 504,
    "unsupported_media": 415,
    "body_too_large": 413,
    "origin_denied": 403,
}


def code(error: Exception) -> str:
    if isinstance(error, V2Error):
        return error.code
    if isinstance(error, BarError):
        return {
            404: "not_found",
            409: "coverage_gap",
            429: "capacity_exceeded",
            503: "unavailable",
            504: "deadline_exceeded",
        }.get(error.status, "invalid_request")
    if isinstance(error, VerificationCancelled):
        return "cancelled"
    if isinstance(error, TimeoutError):
        return "deadline_exceeded"
    if isinstance(error, SQLAlchemyError):
        return "unavailable"
    return "execution_failed"


def transient(error: Exception) -> bool:
    if isinstance(error, DBAPIError):
        return getattr(error.orig, "sqlstate", None) in {
            "40001",
            "40P01",
            "55P03",
            "57014",
            "08006",
            "08003",
        }
    return code(error) in {"unavailable", "deadline_exceeded", "capacity_exceeded"}
