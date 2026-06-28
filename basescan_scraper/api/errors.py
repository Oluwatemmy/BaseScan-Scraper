# basescan_scraper/api/errors.py
from fastapi import Request
from fastapi.responses import JSONResponse

from basescan_scraper.api.validators import ValidationError
from basescan_scraper.fetchers.base import (
    UpstreamRateLimited,
    UpstreamTimeout,
    UpstreamUnavailable,
)
from basescan_scraper.models.common import ProblemDetail
from basescan_scraper.parsers.common import ParseError

_CT = "application/problem+json"


def _problem(status: int, type_: str, title: str, detail: str | None = None,
             headers: dict | None = None) -> JSONResponse:
    body = ProblemDetail(type=type_, title=title, status=status, detail=detail).model_dump()
    return JSONResponse(status_code=status, content=body, media_type=_CT, headers=headers)


def register_error_handlers(app) -> None:
    @app.exception_handler(ValidationError)
    async def _on_validation(_: Request, exc: ValidationError):
        return _problem(422, "/errors/invalid-parameter", "Invalid parameter", str(exc))

    @app.exception_handler(UpstreamRateLimited)
    async def _on_rate(_: Request, exc: UpstreamRateLimited):
        return _problem(503, "/errors/upstream-rate-limited",
                        "Upstream rate limited", "BaseScan is rate-limiting requests.",
                        headers={"Retry-After": "5"})

    @app.exception_handler(UpstreamTimeout)
    async def _on_timeout(_: Request, exc: UpstreamTimeout):
        return _problem(504, "/errors/upstream-timeout", "Upstream timeout",
                        "BaseScan did not respond in time.")

    @app.exception_handler(UpstreamUnavailable)
    async def _on_unavailable(_: Request, exc: UpstreamUnavailable):
        return _problem(502, "/errors/upstream-unavailable", "Upstream unavailable",
                        "Could not retrieve or parse data from BaseScan.")

    @app.exception_handler(ParseError)
    async def _on_parse_error(_: Request, exc: ParseError):
        return _problem(502, "/errors/parse-error", "Upstream parse error",
                        "Could not parse the BaseScan response.")
