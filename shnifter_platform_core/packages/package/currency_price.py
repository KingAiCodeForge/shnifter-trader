# Generated: 2025-07-04T09:50:39.964633
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

### THIS FILE IS AUTO-GENERATED. DO NOT EDIT. ###

import datetime
from typing import Literal, Optional, Union

from shnifter_core.app.model.field import ShnifterField
from shnifter_core.app.model.shnifterject import Shnifterject
from shnifter_core.app.static.container import Container
from shnifter_core.app.static.utils.decorators import exception_handler, validate
from shnifter_core.app.static.utils.filters import filter_inputs
from typing_extensions import Annotated


class ROUTER_currency_price(Container):
    """/currency/price
    historical
    """

    def __repr__(self) -> str:
        return self.__doc__ or ""

    @exception_handler
    @validate
    def historical(
        self,
        symbol: Annotated[
            Union[str, list[str]],
            ShnifterField(
                description="Symbol to get data for. Can use CURR1-CURR2 or CURR1CURR2 format. Multiple comma separated items allowed for provider(s): fmp, polygon, tiingo, yfinance."
            ),
        ],
        start_date: Annotated[
            Union[datetime.date, None, str],
            ShnifterField(description="Start date of the data, in YYYY-MM-DD format."),
        ] = None,
        end_date: Annotated[
            Union[datetime.date, None, str],
            ShnifterField(description="End date of the data, in YYYY-MM-DD format."),
        ] = None,
        provider: Annotated[
            Optional[Literal["fmp", "polygon", "tiingo", "yfinance"]],
            ShnifterField(
                description="The provider to use, by default None. If None, the priority list configured in the settings is used. Default priority: fmp, polygon, tiingo, yfinance."
            ),
        ] = None,
        **kwargs
    ) -> Shnifterject:
        """Currency Historical Price. Currency historical data.

        Currency historical prices refer to the past exchange rates of one currency against
        another over a specific period.
        This data provides insight into the fluctuations and trends in the foreign exchange market,
        helping analysts, traders, and economists understand currency performance,
        evaluate economic health, and make predictions about future movements.


        Parameters
        ----------
        provider : str
            The provider to use, by default None. If None, the priority list configured in the settings is used. Default priority: fmp, polygon, tiingo, yfinance.
        symbol : Union[str, list[str]]
            Symbol to get data for. Can use CURR1-CURR2 or CURR1CURR2 format. Multiple comma separated items allowed for provider(s): fmp, polygon, tiingo, yfinance.
        start_date : Union[date, None, str]
            Start date of the data, in YYYY-MM-DD format.
        end_date : Union[date, None, str]
            End date of the data, in YYYY-MM-DD format.
        interval : str
            Time interval of the data to return. (provider: fmp, polygon, tiingo, yfinance)
            Choices for fmp: '1m', '5m', '15m', '30m', '1h', '4h', '1d'
            Choices for yfinance: '1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1W', '1M', '1Q'
        sort : Literal['asc', 'desc']
            Sort order of the data. This impacts the results in combination with the 'limit' parameter. The results are always returned in ascending order by date. (provider: polygon)
        limit : int
            The number of data entries to return. (provider: polygon)

        Returns
        -------
        Shnifterject
            results : list[CurrencyHistorical]
                Serializable results.
            provider : Optional[str]
                Provider name.
            warnings : Optional[list[Warning_]]
                list of warnings.
            chart : Optional[Chart]
                Chart object.
            extra : Dict[str, Any]
                Extra info.

        CurrencyHistorical
        ------------------
        date : Union[date, datetime]
            The date of the data.
        open : float
            The open price.
        high : float
            The high price.
        low : float
            The low price.
        close : float
            The close price.
        volume : Optional[float]
            The trading volume.
        vwap : Optional[Annotated[float, Gt(gt=0)]]
            Volume Weighted Average Price over the period.
        adj_close : Optional[float]
            The adjusted close price. (provider: fmp)
        change : Optional[float]
            Change in the price from the previous close. (provider: fmp)
        change_percent : Optional[float]
            Change in the price from the previous close, as a normalized percent. (provider: fmp)
        transactions : Optional[Annotated[int, Gt(gt=0)]]
            Number of transactions for the symbol in the time period. (provider: polygon)

        Examples
        --------
        >>> from shnifter import shnifter
        >>> shnifter.currency.price.historical(symbol='EURUSD', provider='fmp')
        >>> # Filter historical data with specific start and end date.
        >>> shnifter.currency.price.historical(symbol='EURUSD', start_date='2023-01-01', end_date='2023-12-31', provider='fmp')
        >>> # Get data with different granularity.
        >>> shnifter.currency.price.historical(symbol='EURUSD', provider='polygon', interval='15m')
        """  # noqa: E501

        return self._run(
            "/currency/price/historical",
            **filter_inputs(
                provider_choices={
                    "provider": self._get_provider(
                        provider,
                        "currency.price.historical",
                        ("fmp", "polygon", "tiingo", "yfinance"),
                    )
                },
                standard_params={
                    "symbol": symbol,
                    "start_date": start_date,
                    "end_date": end_date,
                },
                extra_params=kwargs,
                info={
                    "symbol": {
                        "fmp": {"multiple_items_allowed": True, "choices": None},
                        "polygon": {"multiple_items_allowed": True, "choices": None},
                        "tiingo": {"multiple_items_allowed": True, "choices": None},
                        "yfinance": {"multiple_items_allowed": True, "choices": None},
                    },
                    "interval": {
                        "fmp": {
                            "multiple_items_allowed": False,
                            "choices": ["1m", "5m", "15m", "30m", "1h", "4h", "1d"],
                        },
                        "tiingo": {
                            "multiple_items_allowed": False,
                            "choices": [
                                "1m",
                                "5m",
                                "15m",
                                "30m",
                                "90m",
                                "1h",
                                "2h",
                                "4h",
                                "1d",
                                "5d",
                                "21d",
                            ],
                        },
                        "yfinance": {
                            "multiple_items_allowed": False,
                            "choices": [
                                "1m",
                                "2m",
                                "5m",
                                "15m",
                                "30m",
                                "60m",
                                "90m",
                                "1h",
                                "1d",
                                "5d",
                                "1W",
                                "1M",
                                "1Q",
                            ],
                        },
                    },
                },
            )
        )
