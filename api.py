"""FastAPI routes for CountryDatabaseManager; no scraping happens on startup."""

import logging
import math
import os
import sqlite3
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated, Any

from fastapi import FastAPI, HTTPException, Request, Response, status
from fastapi import Path as ApiPath
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from database import (
    DEFAULT_DB_PATH,
    CountryDatabaseManager,
    CountryNotFoundError,
    DuplicateCountryError,
)
from schemas import Country, CountryCreate, CountryDetails, CountryName

logger = logging.getLogger(__name__)
CountryPath = Annotated[
    CountryName,
    ApiPath(description="Case-sensitive country name; URL-encode spaces and Unicode."),
]


def _json_safe_validation(value: Any) -> Any:
    """Keep normal validation details serializable for invalid NaN/Infinity input."""
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, list):
        return [_json_safe_validation(item) for item in value]
    if isinstance(value, dict):
        return {key: _json_safe_validation(item) for key, item in value.items()}
    return value


def create_app(db_path: str | Path | None = None) -> FastAPI:
    """Build a testable app; COUNTRY_DB_PATH can override the project-local default."""
    selected_path = (
        db_path if db_path is not None else os.environ.get("COUNTRY_DB_PATH", DEFAULT_DB_PATH)
    )
    manager = CountryDatabaseManager(selected_path)

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        manager.initialize_schema()
        yield

    application = FastAPI(
        title="Country Data Pipeline API",
        version="1.0.0",
        description=(
            "CRUD access to a practice-site country dataset. Names are trimmed, "
            "case-sensitive natural keys. PUT replaces all details while keeping "
            "the country name immutable. Run scraper.py explicitly to seed data."
        ),
        lifespan=lifespan,
    )
    application.state.database = manager

    @application.exception_handler(RequestValidationError)
    async def invalid_request(request: Request, exc: RequestValidationError) -> JSONResponse:
        # Preserve FastAPI's normal 422 detail structure. Python's JSON decoder
        # accepts NaN/Infinity, but those rejected inputs cannot be echoed as JSON.
        details = _json_safe_validation(jsonable_encoder(exc.errors()))
        return JSONResponse(status_code=422, content={"detail": details})

    @application.exception_handler(sqlite3.Error)
    async def database_failure(request: Request, exc: sqlite3.Error) -> JSONResponse:
        logger.error("Database operation failed", exc_info=exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"detail": "A database operation failed. Check the server logs."},
        )

    @application.get(
        "/countries",
        response_model=list[Country],
        summary="List all countries",
        description="Return countries in case-sensitive name order; an empty table returns [].",
    )
    def list_countries() -> list[Country]:
        return manager.list_countries()

    @application.get(
        "/countries/{country_name:path}",
        response_model=Country,
        summary="Get a country by name",
        description="Return one country by its trimmed, case-sensitive natural name; 404 if absent.",
        responses={404: {"description": "No country with that normalized name exists."}},
    )
    def get_country(country_name: CountryPath) -> Country:
        try:
            return manager.get_country(country_name)
        except CountryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Country not found.") from exc

    @application.post(
        "/countries",
        response_model=Country,
        status_code=status.HTTP_201_CREATED,
        summary="Create a country",
        description="Insert a new record; duplicate trimmed names return 409.",
        responses={409: {"description": "A country with that normalized name exists."}},
    )
    def create_country(country: CountryCreate) -> Country:
        try:
            return manager.create_country(country)
        except DuplicateCountryError as exc:
            raise HTTPException(status_code=409, detail="Country already exists.") from exc

    @application.put(
        "/countries/{country_name:path}",
        response_model=Country,
        summary="Replace a country's details",
        description=(
            "Supply capital, population, and area together. The name in the URL "
            "is immutable and must not appear in the request body."
        ),
        responses={404: {"description": "No country with that normalized name exists."}},
    )
    def update_country(country_name: CountryPath, details: CountryDetails) -> Country:
        try:
            return manager.update_country(country_name, details)
        except CountryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Country not found.") from exc

    @application.delete(
        "/countries/{country_name:path}",
        status_code=status.HTTP_204_NO_CONTENT,
        response_class=Response,
        summary="Delete a country",
        description="Delete one country. A successful response has no body.",
        responses={404: {"description": "No country with that normalized name exists."}},
    )
    def delete_country(country_name: CountryPath) -> Response:
        try:
            manager.delete_country(country_name)
        except CountryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Country not found.") from exc
        return Response(status_code=status.HTTP_204_NO_CONTENT)

    return application


app = create_app()
