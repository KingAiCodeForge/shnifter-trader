# core/execution.py - Production-ready execution engine with comprehensive logging
import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Dict, List, Optional, Callable
import json
from decimal import Decimal

from core.events import EventLog, EventBus
from core.data_models import ShnifterData

# Configure module-specific logger
logger = logging.getLogger(__name__)

class OrderSide(Enum):
    """Enumeration for order sides - standardized across all exchanges"""
    BUY = "BUY"
    SELL = "SELL"

class OrderType(Enum):
    """Enumeration for order types - supports most common order types"""
    MARKET = "MARKET"      # Execute immediately at current market price
    LIMIT = "LIMIT"        # Execute only at specified price or better
    STOP = "STOP"          # Stop-loss order (market order when price reached)
    STOP_LIMIT = "STOP_LIMIT"  # Stop-limit order (limit order when price reached)

class OrderStatus(Enum):
    """Order lifecycle status tracking"""
    PENDING = "PENDING"              # Order submitted but not yet processed
    FILLED = "FILLED"                # Order completely executed
    PARTIALLY_FILLED = "PARTIALLY_FILLED"  # Order partially executed
    CANCELLED = "CANCELLED"          # Order cancelled by user or system
    REJECTED = "REJECTED"            # Order rejected by exchange

@dataclass
class OrderRequest:
    """
    Standardized order request structure across all brokers.
    Ensures consistent order format regardless of underlying exchange.
    """
    symbol: str                      # Trading symbol (e.g., "AAPL", "BTC-USD")
    side: OrderSide                  # Buy or sell direction
    quantity: Decimal                # Number of shares/units to trade
    order_type: OrderType            # Type of order execution
    price: Optional[Decimal] = None  # Limit price (required for LIMIT orders)
    stop_price: Optional[Decimal] = None  # Stop price (required for STOP orders)
    time_in_force: str = "DAY"       # Order duration (DAY, GTC, IOC, FOK)
    client_order_id: Optional[str] = None  # Client-generated unique identifier

@dataclass
class OrderResponse:
    """
    Standardized order response structure.
    Provides consistent order tracking across all exchanges.
    """
    order_id: str                    # Exchange-generated order identifier
    client_order_id: Optional[str]  # Client-provided order identifier
    symbol: str                      # Trading symbol
    side: OrderSide                  # Order direction
    quantity: Decimal                # Total order quantity
    filled_quantity: Decimal         # Amount already filled
    status: OrderStatus              # Current order status
    price: Optional[Decimal]         # Order price (if applicable)
    filled_price: Optional[Decimal] # Average fill price
    timestamp: datetime              # Order creation timestamp
    broker_response: Dict            # Raw broker response for debugging

class ExchangeClient(ABC):
    """
    Enhanced abstract base class for all broker/exchange API wrappers.
    Provides standardized interface with built-in error handling and monitoring.
    """
    
    def __init__(self, name: str):
        """
        Initialize exchange client with monitoring capabilities.
        
        Args:
            name: Human-readable name for this exchange client
        """
        self.name = name
        self.is_connected = False
        self.rate_limiter = RateLimiter()
        self.connection_attempts = 0
        self.last_connection_time = None
        
        # Log client initialization
        logger.info(f"Initializing {self.name} exchange client")
        EventLog.emit("INFO", f"Exchange client {self.name} initialized")
        
    @abstractmethod
    async def connect(self) -> bool:
        """
        Establish connection to the broker/exchange.
        Must be implemented by each specific exchange client.
        
        Returns:
            bool: True if connection successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def disconnect(self) -> bool:
        """
        Disconnect from the broker/exchange.
        Should cleanup resources and close connections.
        
        Returns:
            bool: True if disconnection successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def get_balance(self) -> Dict[str, Decimal]:
        """
        Retrieve account balances for all currencies/assets.
        
        Returns:
            Dict mapping currency symbols to available balances
        """
        pass
        
    @abstractmethod
    async def place_order(self, order_request: OrderRequest) -> OrderResponse:
        """
        Place an order and return the response.
        Core trading functionality - must handle all order types.
        
        Args:
            order_request: Standardized order request object
            
        Returns:
            OrderResponse: Standardized order response
        """
        pass
        
    @abstractmethod
    async def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an existing order by ID.
        
        Args:
            order_id: Exchange-specific order identifier
            
        Returns:
            bool: True if cancellation successful, False otherwise
        """
        pass
        
    @abstractmethod
    async def get_order_status(self, order_id: str) -> OrderResponse:
        """
        Check the current status of a specific order.
        
        Args:
            order_id: Exchange-specific order identifier
            
        Returns:
            OrderResponse: Current order status and details
        """
        pass
        
    @abstractmethod
    async def get_positions(self) -> Dict[str, Dict]:
        """
        Get current positions across all symbols.
        
        Returns:
            Dict mapping symbols to position details
        """
        pass

class RateLimiter:
    """Bounded, read-only retry helper. Never retry order side effects.

    A timeout from a broker submission has an *unknown* execution outcome.
    Reconcile client-order IDs and broker state before any further action.
    """

    _READ_PREFIXES = ("get_", "fetch_", "list_", "read_", "query_")
    _DENY_NAMES = ("submit", "place", "create", "cancel", "update",
                   "delete", "execute", "modify", "close", "liquidate")

    def __init__(self, max_retries: int = 5, base_delay: float = 1.0):
        import math
        if (type(max_retries) is not int or not 1 <= max_retries <= 10 or
                not isinstance(base_delay, (int, float)) or
                not math.isfinite(base_delay) or base_delay < 0):
            raise ValueError("invalid read-only retry configuration")
        self.max_retries = max_retries
        self.base_delay = float(base_delay)
        self.retry_counts = {}

    async def execute_with_backoff(self, func: Callable, *args, **kwargs):
        """Retry safe *reads* only, never submit/cancel/position modifications."""
        name = getattr(func, "__name__", "").lower()
        if (not name.startswith(self._READ_PREFIXES) or
                any(word in name for word in self._DENY_NAMES)):
            raise ValueError(
                "Retries are forbidden for state-changing/unknown calls; "
                "broker order uncertainty requires reconciliation"
            )
        for attempt in range(self.max_retries):
            try:
                response = await func(*args, **kwargs)
                self.retry_counts.pop(name, None)
                return response
            except (ConnectionError, TimeoutError, OSError):
                self.retry_counts[name] = attempt + 1
                if attempt + 1 >= self.max_retries:
                    raise
                delay = self.base_delay * (2 ** attempt)
                logger.warning("Read %s failed; retrying in %.2fs", name, delay)
                await asyncio.sleep(delay)
        raise RuntimeError("Unreachable retry state")
