# Generated: 2025-07-04T09:50:40.406920
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""Secured Overnight Financing Rate Standard Model."""

from datetime import date as dateType
from typing import Optional

from shnifter_core.provider.abstract.data import Data
from shnifter_core.provider.abstract.query_params import QueryParams
from shnifter_core.provider.utils.descriptions import (
    DATA_DESCRIPTIONS,
    QUERY_DESCRIPTIONS,
)
from pydantic import Field


class SOFRQueryParams(QueryParams):
    """Secured Overnight Financing Rate Query."""

    start_date: Optional[dateType] = Field(
        default=None,
        description=QUERY_DESCRIPTIONS.get("start_date", ""),
    )
    end_date: Optional[dateType] = Field(
        default=None,
        description=QUERY_DESCRIPTIONS.get("end_date", ""),
    )


class SOFRData(Data):
    """SOFR Data."""

    date: dateType = Field(description=DATA_DESCRIPTIONS.get("date", ""))
    rate: float = Field(
        description="Effective federal funds rate.",
        json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100},
    )
    percentile_1: Optional[float] = Field(
        default=None,
        description="1st percentile of the distribution.",
        json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100},
    )
    percentile_25: Optional[float] = Field(
        default=None,
        description="25th percentile of the distribution.",
        json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100},
    )
    percentile_75: Optional[float] = Field(
        default=None,
        description="75th percentile of the distribution.",
        json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100},
    )
    percentile_99: Optional[float] = Field(
        default=None,
        description="99th percentile of the distribution.",
        json_schema_extra={"x-unit_measurement": "percent", "x-frontend_multiply": 100},
    )
    volume: Optional[float] = Field(
        default=None,
        description=DATA_DESCRIPTIONS.get("volume", "")
        + "The notional volume of transactions (Billions of $).",
        json_schema_extra={
            "x-unit_measurement": "currency",
            "x-frontend_multiply": 1e9,
        },
    )
