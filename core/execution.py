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
    """
    Exponential backoff rate limiter for API calls.
    Prevents overwhelming exchange APIs and handles temporary failures gracefully.
    """
    
    def __init__(self, max_retries: int = 5, base_delay: float = 1.0):
        """
        Initialize rate limiter with configurable retry parameters.
        
        Args:
            max_retries: Maximum number of retry attempts
            base_delay: Base delay in seconds for exponential backoff
        """
        self.max_retries = max_retries
        self.base_delay = base_delay
        self.retry_counts = {}  # Track retry counts per function
        
        logger.info(f"Rate limiter initialized: max_retries={max_retries}, base_delay={base_delay}")
        
    async def execute_with_backoff(self, func: Callable, *args, **kwargs):
        """
        Execute function with exponential backoff on failure.
        Implements intelligent retry logic with jitter to prevent thundering herd.
        
        Args:
            func: Function to execute with retry logic
            *args: Positional arguments for function
            **kwargs: Keyword arguments for function
            
        Returns:
            Function result on success
            
        Raises:
            Exception: If max retries exceeded
        """
        func_name = func.__name__
        retries = 0
        
        logger.debug(f"Executing {func_name} with backoff protection")
        
        while retries < self.max_retries:
            try:
                result = await func(*args, **kwargs)
                
                # Reset retry count on success
                if func_name in self.retry_counts:
                    del self.retry_counts[func_name]
                    
                logger.debug(f"Successfully executed {func_name}")
                return result
                
            except Exception as e:
                retries += 1
                self.retry_counts[func_name] = retries
                
                logger.warning(f"Attempt {retries}/{self.max_retries} failed for {func_name}: {e}")
                
                if retries >= self.max_retries:
                    error_msg = f"Max retries exceeded for {func_name}"
                    logger.error(error_msg)
                    EventLog.emit("ERROR", error_msg)
                    raise Exception(error_msg)
                    
                # Calculate delay with jitter
                delay = self.base_delay * (2 ** (retries - 1))
                jitter = delay * 0.1 * (0.5 - asyncio.get_event_loop().time() % 1)
                delay += jitter
                
                logger.info(f"Retrying {func_name} in {delay:.2f} seconds...")
                EventLog.emit("INFO", f"Retrying {func_name} in {delay:.2f} seconds...")
                await asyncio.sleep(delay)
                
        # This should never be reached due to the raise above
        raise Exception(f"Failed to execute {func_name} after {self.max_retries} attempts")
