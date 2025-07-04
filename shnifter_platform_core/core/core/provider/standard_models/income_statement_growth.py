# Generated: 2025-07-04T09:50:40.354897
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""Income Statement Growth Standard Model."""

from datetime import date as dateType
from typing import Optional

from shnifter_core.provider.abstract.data import Data
from shnifter_core.provider.abstract.query_params import QueryParams
from shnifter_core.provider.utils.descriptions import QUERY_DESCRIPTIONS
from pydantic import Field, field_validator


class IncomeStatementGrowthQueryParams(QueryParams):
    """Income Statement Growth Query."""

    symbol: str = Field(description=QUERY_DESCRIPTIONS.get("symbol", ""))
    limit: Optional[int] = Field(
        default=10, description=QUERY_DESCRIPTIONS.get("limit", "")
    )

    @field_validator("symbol", mode="before", check_fields=False)
    @classmethod
    def to_upper(cls, v: str) -> str:
        """Convert field to uppercase."""
        return v.upper()


class IncomeStatementGrowthData(Data):
    """Income Statement Growth Data."""

    period_ending: dateType = Field(description="The end date of the reporting period.")
    fiscal_period: Optional[str] = Field(
        description="The fiscal period of the report.", default=None
    )
    fiscal_year: Optional[int] = Field(
        description="The fiscal year of the fiscal period.", default=None
    )
