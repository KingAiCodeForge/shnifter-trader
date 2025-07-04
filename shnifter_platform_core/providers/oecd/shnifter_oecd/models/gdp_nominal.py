# Generated: 2025-07-04T09:50:39.593749
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""OECD Nominal GDP Model."""

# pylint: disable=unused-argument

from datetime import date
from typing import Any, Dict, List, Literal, Optional
from warnings import warn

from shnifter_core.app.model.abstract.error import ShnifterError
from shnifter_core.provider.abstract.fetcher import Fetcher
from shnifter_core.provider.standard_models.gdp_nominal import (
    GdpNominalData,
    GdpNominalQueryParams,
)
from shnifter_core.provider.utils.descriptions import QUERY_DESCRIPTIONS
from shnifter_core.provider.utils.errors import EmptyDataError
from shnifter_oecd.utils.constants import CODE_TO_COUNTRY_GDP, COUNTRY_TO_CODE_GDP
from pydantic import Field, field_validator

COUNTRIES = list(COUNTRY_TO_CODE_GDP) + ["all"]


class OECDGdpNominalQueryParams(GdpNominalQueryParams):
    """OECD Nominal GDP Query.

    Source: https://www.oecd.org/en/data/datasets/gdp-and-non-financial-accounts.html

    This table presents Gross Domestic Product (GDP) and its main components according to the expenditure approach.
    Data is presented in US dollars. In the expenditure approach, the components of GDP are:
    final consumption expenditure of households and non-profit institutions serving households (NPISH)
    plus final consumption expenditure of General Government plus gross fixed capital formation (or investment)
    plus net trade (exports minus imports).
    """

    __json_schema_extra__ = {
        "country": {
            "multiple_items_allowed": True,
            "choices": COUNTRIES,
        }
    }

    country: str = Field(
        description=QUERY_DESCRIPTIONS.get("country", "")
        + " Use 'all' to get data for all available countries.",
        default="united_states",
    )
    frequency: Literal["quarter", "annual"] = Field(
        description="Frequency of the data.",
        default="quarter",
        json_schema_extra={"choices": ["quarter", "annual"]},
    )
    units: Literal["level", "index", "capita"] = Field(
        default="level",
        description=QUERY_DESCRIPTIONS.get("units", "")
        + "Both 'level' and 'capita' (per) are measured in USD.",
        json_schema_extra={"choices": ["level", "index", "capita"]},
    )
    price_base: Literal["current_prices", "volume"] = Field(
        default="current_prices",
        description="Price base for the data, volume is chain linked volume.",
        json_schema_extra={"choices": ["current_prices", "volume"]},
    )

    @field_validator("country", mode="before", check_fields=False)
    @classmethod
    def validate_country(cls, c):
        """Validate country."""
        # pylint: disable=import-outside-toplevel
        from shnifter_core.provider.utils.helpers import check_item

        result: List = []
        values = c.replace(" ", "_").split(",")
        for v in values:
            if v.upper() in CODE_TO_COUNTRY_GDP:
                result.append(CODE_TO_COUNTRY_GDP.get(v.upper()))
                continue
            try:
                check_item(v.lower(), COUNTRIES)
            except Exception as e:
                if len(values) == 1:
                    raise e from e
                warn(f"Invalid country: {v}. Skipping...")
                continue
            result.append(v.lower())
        if result:
            return ",".join(result)
        raise ShnifterError(f"No valid country found. -> {values}")


class OECDGdpNominalData(GdpNominalData):
    """OECD Nominal GDP Data."""


class OECDGdpNominalFetcher(
    Fetcher[OECDGdpNominalQueryParams, List[OECDGdpNominalData]]
):
    """OECD GDP Nominal Fetcher."""

    @staticmethod
    def transform_query(params: Dict[str, Any]) -> OECDGdpNominalQueryParams:
        """Transform the query."""
        transformed_params = params.copy()
        if transformed_params.get("start_date") is None:
            transformed_params["start_date"] = (
                date(2020, 1, 1)
                if transformed_params.get("country") == "all"
                else date(1947, 1, 1)
            )
        if transformed_params.get("end_date") is None:
            transformed_params["end_date"] = date(date.today().year, 12, 31)
        if transformed_params.get("country") is None:
            transformed_params["country"] = "united_states"

        return OECDGdpNominalQueryParams(**transformed_params)

    @staticmethod
    async def aextract_data(
        query: OECDGdpNominalQueryParams,
        credentials: Optional[Dict[str, str]],
        **kwargs: Any,
    ) -> List[Dict]:
        """Return the raw data from the OECD endpoint."""
        # pylint: disable=import-outside-toplevel
        from io import StringIO  # noqa
        from shnifter_oecd.utils.helpers import oecd_date_to_python_date
        from numpy import nan
        from pandas import read_csv
        from shnifter_core.provider.utils.helpers import amake_request

        if query.units == "index":
            unit = "INDICES"
        elif query.units == "capita":
            unit = "CAPITA"
        else:
            unit = "USD"

        frequency = "Q" if query.frequency == "quarter" else "A"
        price_base = "V" if query.price_base == "current_prices" else "LR"

        if unit == "INDICES" and price_base == "V":
            price_base = "DR"

        def country_string(input_str: str):
            """Convert the list of countries to an abbreviated string."""
            if input_str == "all":
                return ""
            _countries = input_str.split(",")

            return "+".join([COUNTRY_TO_CODE_GDP[country] for country in _countries])

        country = country_string(query.country) if query.country else ""

        url = (
            f"https://sdmx.oecd.org/public/rest/data/OECD.SDD.NAD,DSD_NAMAIN1@DF_QNA_EXPENDITURE_{unit},1.1"
            + f"/{frequency}..{country}.S1..B1GQ.....{price_base}..?"
            + f"&startPeriod={query.start_date}&endPeriod={query.end_date}"
            + "&dimensionAtObservation=TIME_PERIOD&detail=dataonly&format=csvfile"
        )
        if query.units == "capita":
            url = url.replace("B1GQ", "B1GQ_POP")

        async def response_callback(response, _):
            """Response callback."""
            if response.status != 200:
                raise ShnifterError(f"Error with the OECD request: {response.status}")
            return await response.text()

        response = await amake_request(
            url, timeout=30, response_callback=response_callback
        )

        df = read_csv(StringIO(response)).get(  # type: ignore
            ["REF_AREA", "TIME_PERIOD", "OBS_VALUE"]
        )
        if df.empty:  # type: ignore
            raise EmptyDataError()
        df = df.rename(  # type: ignore
            columns={"REF_AREA": "country", "TIME_PERIOD": "date", "OBS_VALUE": "value"}
        )

        def apply_map(x):
            """Apply the country map."""
            v = CODE_TO_COUNTRY_GDP.get(x, x)
            v = v.replace("_", " ").title()
            return v

        df["country"] = df["country"].apply(apply_map).str.replace("Oecd", "OECD")
        df["date"] = df["date"].apply(oecd_date_to_python_date)
        df = df[(df["date"] <= query.end_date) & (df["date"] >= query.start_date)]
        if query.units == "level":
            df["value"] = (df["value"].astype(float) * 1_000_000).astype("int64")

        df = df.sort_values(by=["date", "value"], ascending=[True, False])

        return df.replace({nan: None}).to_dict(orient="records")

    @staticmethod
    def transform_data(
        query: OECDGdpNominalQueryParams,
        data: List[Dict],
        **kwargs: Any,
    ) -> List[OECDGdpNominalData]:
        """Transform the data from the OECD endpoint."""
        return [OECDGdpNominalData.model_validate(d) for d in data]
