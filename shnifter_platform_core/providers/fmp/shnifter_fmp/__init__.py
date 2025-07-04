# Generated: 2025-07-04T09:50:39.744209
# Target: Shnifter Trader Platform with PySide6 and LLM integration
# Python Version: 3.13.2+

"""FMP Provider Modules."""

from shnifter_core.provider.abstract.provider import Provider
from shnifter_fmp.models.analyst_estimates import FMPAnalystEstimatesFetcher
from shnifter_fmp.models.available_indices import FMPAvailableIndicesFetcher
from shnifter_fmp.models.balance_sheet import FMPBalanceSheetFetcher
from shnifter_fmp.models.balance_sheet_growth import FMPBalanceSheetGrowthFetcher
from shnifter_fmp.models.calendar_dividend import FMPCalendarDividendFetcher
from shnifter_fmp.models.calendar_earnings import FMPCalendarEarningsFetcher
from shnifter_fmp.models.calendar_events import FMPCalendarEventsFetcher
from shnifter_fmp.models.calendar_splits import FMPCalendarSplitsFetcher
from shnifter_fmp.models.cash_flow import FMPCashFlowStatementFetcher
from shnifter_fmp.models.cash_flow_growth import FMPCashFlowStatementGrowthFetcher
from shnifter_fmp.models.company_filings import FMPCompanyFilingsFetcher
from shnifter_fmp.models.company_news import FMPCompanyNewsFetcher
from shnifter_fmp.models.company_overview import FMPCompanyOverviewFetcher
from shnifter_fmp.models.crypto_historical import FMPCryptoHistoricalFetcher
from shnifter_fmp.models.crypto_search import FMPCryptoSearchFetcher
from shnifter_fmp.models.currency_historical import FMPCurrencyHistoricalFetcher
from shnifter_fmp.models.currency_pairs import FMPCurrencyPairsFetcher
from shnifter_fmp.models.currency_snapshots import FMPCurrencySnapshotsFetcher
from shnifter_fmp.models.discovery_filings import FMPDiscoveryFilingsFetcher
from shnifter_fmp.models.earnings_call_transcript import FMPEarningsCallTranscriptFetcher
from shnifter_fmp.models.economic_calendar import FMPEconomicCalendarFetcher
from shnifter_fmp.models.equity_historical import FMPEquityHistoricalFetcher
from shnifter_fmp.models.equity_ownership import FMPEquityOwnershipFetcher
from shnifter_fmp.models.equity_peers import FMPEquityPeersFetcher
from shnifter_fmp.models.equity_profile import FMPEquityProfileFetcher
from shnifter_fmp.models.equity_quote import FMPEquityQuoteFetcher
from shnifter_fmp.models.equity_screener import FMPEquityScreenerFetcher
from shnifter_fmp.models.equity_valuation_multiples import (
    FMPEquityValuationMultiplesFetcher,
)
from shnifter_fmp.models.etf_countries import FMPEtfCountriesFetcher
from shnifter_fmp.models.etf_equity_exposure import FMPEtfEquityExposureFetcher
from shnifter_fmp.models.etf_holdings import FMPEtfHoldingsFetcher
from shnifter_fmp.models.etf_holdings_date import FMPEtfHoldingsDateFetcher
from shnifter_fmp.models.etf_info import FMPEtfInfoFetcher
from shnifter_fmp.models.etf_search import FMPEtfSearchFetcher
from shnifter_fmp.models.etf_sectors import FMPEtfSectorsFetcher
from shnifter_fmp.models.executive_compensation import FMPExecutiveCompensationFetcher
from shnifter_fmp.models.financial_ratios import FMPFinancialRatiosFetcher
from shnifter_fmp.models.forward_ebitda_estimates import FMPForwardEbitdaEstimatesFetcher
from shnifter_fmp.models.forward_eps_estimates import FMPForwardEpsEstimatesFetcher
from shnifter_fmp.models.government_trades import FMPGovernmentTradesFetcher
from shnifter_fmp.models.historical_dividends import FMPHistoricalDividendsFetcher
from shnifter_fmp.models.historical_employees import FMPHistoricalEmployeesFetcher
from shnifter_fmp.models.historical_eps import FMPHistoricalEpsFetcher
from shnifter_fmp.models.historical_market_cap import FmpHistoricalMarketCapFetcher
from shnifter_fmp.models.historical_splits import FMPHistoricalSplitsFetcher
from shnifter_fmp.models.income_statement import FMPIncomeStatementFetcher
from shnifter_fmp.models.income_statement_growth import FMPIncomeStatementGrowthFetcher
from shnifter_fmp.models.index_constituents import FMPIndexConstituentsFetcher
from shnifter_fmp.models.index_historical import FMPIndexHistoricalFetcher
from shnifter_fmp.models.insider_trading import FMPInsiderTradingFetcher
from shnifter_fmp.models.institutional_ownership import FMPInstitutionalOwnershipFetcher
from shnifter_fmp.models.key_executives import FMPKeyExecutivesFetcher
from shnifter_fmp.models.key_metrics import FMPKeyMetricsFetcher
from shnifter_fmp.models.market_snapshots import FMPMarketSnapshotsFetcher
from shnifter_fmp.models.price_performance import FMPPricePerformanceFetcher
from shnifter_fmp.models.price_target import FMPPriceTargetFetcher
from shnifter_fmp.models.price_target_consensus import FMPPriceTargetConsensusFetcher
from shnifter_fmp.models.revenue_business_line import FMPRevenueBusinessLineFetcher
from shnifter_fmp.models.revenue_geographic import FMPRevenueGeographicFetcher
from shnifter_fmp.models.risk_premium import FMPRiskPremiumFetcher
from shnifter_fmp.models.share_statistics import FMPShareStatisticsFetcher
from shnifter_fmp.models.treasury_rates import FMPTreasuryRatesFetcher
from shnifter_fmp.models.world_news import FMPWorldNewsFetcher
from shnifter_fmp.models.yield_curve import FMPYieldCurveFetcher

fmp_provider = Provider(
    name="fmp",
    website="https://financialmodelingprep.com",
    description="""Financial Modeling Prep is a new concept that informs you about
stock market information (news, currencies, and stock prices).""",
    credentials=["api_key"],
    fetcher_dict={
        "AnalystEstimates": FMPAnalystEstimatesFetcher,
        "AvailableIndices": FMPAvailableIndicesFetcher,
        "BalanceSheet": FMPBalanceSheetFetcher,
        "BalanceSheetGrowth": FMPBalanceSheetGrowthFetcher,
        "CalendarDividend": FMPCalendarDividendFetcher,
        "CalendarEarnings": FMPCalendarEarningsFetcher,
        "CalendarEvents": FMPCalendarEventsFetcher,
        "CalendarSplits": FMPCalendarSplitsFetcher,
        "CashFlowStatement": FMPCashFlowStatementFetcher,
        "CashFlowStatementGrowth": FMPCashFlowStatementGrowthFetcher,
        "CompanyFilings": FMPCompanyFilingsFetcher,
        "CompanyNews": FMPCompanyNewsFetcher,
        "CompanyOverview": FMPCompanyOverviewFetcher,
        "CryptoHistorical": FMPCryptoHistoricalFetcher,
        "CryptoSearch": FMPCryptoSearchFetcher,
        "CurrencyHistorical": FMPCurrencyHistoricalFetcher,
        "CurrencyPairs": FMPCurrencyPairsFetcher,
        "CurrencySnapshots": FMPCurrencySnapshotsFetcher,
        "DiscoveryFilings": FMPDiscoveryFilingsFetcher,
        "EarningsCallTranscript": FMPEarningsCallTranscriptFetcher,
        "EconomicCalendar": FMPEconomicCalendarFetcher,
        "EquityHistorical": FMPEquityHistoricalFetcher,
        "EquityOwnership": FMPEquityOwnershipFetcher,
        "EquityPeers": FMPEquityPeersFetcher,
        "EquityInfo": FMPEquityProfileFetcher,
        "EquityQuote": FMPEquityQuoteFetcher,
        "EquityScreener": FMPEquityScreenerFetcher,
        "EquityValuationMultiples": FMPEquityValuationMultiplesFetcher,
        "EtfCountries": FMPEtfCountriesFetcher,
        "EtfEquityExposure": FMPEtfEquityExposureFetcher,
        "EtfHoldings": FMPEtfHoldingsFetcher,
        "EtfHoldingsDate": FMPEtfHoldingsDateFetcher,
        "EtfInfo": FMPEtfInfoFetcher,
        "EtfPricePerformance": FMPPricePerformanceFetcher,
        "EtfSearch": FMPEtfSearchFetcher,
        "EtfSectors": FMPEtfSectorsFetcher,
        "ExecutiveCompensation": FMPExecutiveCompensationFetcher,
        "FinancialRatios": FMPFinancialRatiosFetcher,
        "ForwardEbitdaEstimates": FMPForwardEbitdaEstimatesFetcher,
        "ForwardEpsEstimates": FMPForwardEpsEstimatesFetcher,
        "HistoricalDividends": FMPHistoricalDividendsFetcher,
        "HistoricalEmployees": FMPHistoricalEmployeesFetcher,
        "HistoricalEps": FMPHistoricalEpsFetcher,
        "HistoricalMarketCap": FmpHistoricalMarketCapFetcher,
        "HistoricalSplits": FMPHistoricalSplitsFetcher,
        "IncomeStatement": FMPIncomeStatementFetcher,
        "IncomeStatementGrowth": FMPIncomeStatementGrowthFetcher,
        "IndexConstituents": FMPIndexConstituentsFetcher,
        "IndexHistorical": FMPIndexHistoricalFetcher,
        "InsiderTrading": FMPInsiderTradingFetcher,
        "InstitutionalOwnership": FMPInstitutionalOwnershipFetcher,
        "KeyExecutives": FMPKeyExecutivesFetcher,
        "KeyMetrics": FMPKeyMetricsFetcher,
        "MarketSnapshots": FMPMarketSnapshotsFetcher,
        "PricePerformance": FMPPricePerformanceFetcher,
        "PriceTarget": FMPPriceTargetFetcher,
        "PriceTargetConsensus": FMPPriceTargetConsensusFetcher,
        "RevenueBusinessLine": FMPRevenueBusinessLineFetcher,
        "RevenueGeographic": FMPRevenueGeographicFetcher,
        "RiskPremium": FMPRiskPremiumFetcher,
        "ShareStatistics": FMPShareStatisticsFetcher,
        "TreasuryRates": FMPTreasuryRatesFetcher,
        "WorldNews": FMPWorldNewsFetcher,
        "EtfHistorical": FMPEquityHistoricalFetcher,
        "YieldCurve": FMPYieldCurveFetcher,
        "GovernmentTrades": FMPGovernmentTradesFetcher,
    },
    repr_name="Financial Modeling Prep (FMP)",
    deprecated_credentials={"API_KEY_FINANCIALMODELINGPREP": "fmp_api_key"},
    instructions='Go to: https://site.financialmodelingprep.com/developer/docs\n\n![FinancialModelingPrep](https://user-images.gitcoreusercontent.com/46355364/207821920-64553d05-d461-4984-b0fe-be0368c71186.png)\n\nClick on, "Get my API KEY here", and sign up for a free account.\n\n![FinancialModelingPrep](https://user-images.gitcoreusercontent.com/46355364/207822184-a723092e-ef42-4f87-8c55-db150f09741b.png)\n\nWith an account created, sign in and navigate to the Dashboard, which shows the assigned token. by pressing the "Dashboard" button which will show the API key.\n\n![FinancialModelingPrep](https://user-images.gitcoreusercontent.com/46355364/207823170-dd8191db-e125-44e5-b4f3-2df0e115c91d.png)',  # noqa: E501  pylint: disable=line-too-long
)
