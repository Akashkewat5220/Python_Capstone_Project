"""Shared validation rules for scraped data, database records, and HTTP bodies."""

from typing import Annotated, Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    TypeAdapter,
    field_validator,
)

# sqlite3 stores signed 64-bit integers; reject values it cannot store reliably.
SQLITE_MAX_INTEGER = 2**63 - 1
CountryName = Annotated[str, StringConstraints(strict=True, strip_whitespace=True, min_length=1)]
_COUNTRY_NAME_ADAPTER = TypeAdapter(CountryName)


def normalize_country_name(name: str) -> str:
    """Trim a name without changing case, spelling, punctuation, or Unicode."""
    return _COUNTRY_NAME_ADAPTER.validate_python(name)


class CountryDetails(BaseModel):
    """The three replaceable details of an existing country."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [{"capital": "Updated Demo City", "population": 1500, "area": 48.0}]
        },
    )

    capital: Annotated[str, StringConstraints(strict=True, strip_whitespace=True)] = Field(
        description='Capital as displayed by the source, including "None".'
    )
    population: int = Field(
        strict=True,
        ge=0,
        le=SQLITE_MAX_INTEGER,
        description="Nonnegative whole population, within SQLite's integer range.",
    )
    area: float = Field(
        strict=True,
        ge=0,
        allow_inf_nan=False,
        description="Finite, nonnegative area in square kilometers.",
    )

    @field_validator("area", mode="before")
    @classmethod
    def validate_numeric_area(cls, value: Any) -> float:
        """Allow JSON integers or floats while rejecting booleans and strings."""
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise ValueError("area must be a number, not a boolean or string")
        try:
            return float(value)
        except OverflowError as exc:
            raise ValueError("area must be a finite number") from exc


class Country(CountryDetails):
    """A complete country record, identified by its trimmed, case-sensitive name."""

    model_config = ConfigDict(
        extra="forbid",
        json_schema_extra={
            "examples": [
                {
                    "country_name": "Demo Country",
                    "capital": "Demo City",
                    "population": 1200,
                    "area": 45.5,
                }
            ]
        },
    )

    country_name: CountryName = Field(
        description="Natural key; surrounding whitespace is trimmed and case preserved."
    )


# Explicit names help explain the create and full-replacement request contracts.
CountryCreate = Country
CountryUpdate = CountryDetails
