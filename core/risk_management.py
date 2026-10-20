# core/risk_management.py - Comprehensive risk controls with detailed logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging

from core.events import EventLog, EventBus
from core.execution import OrderRequest, OrderSide, OrderType
from core.safe_risk_math import check_proposed_order, whole_share_size

# Configure module-specific logger
logger = logging.getLogger(__name__)

@dataclass
class RiskLimits:
    """
    Comprehensive risk management configuration.
    All limits are designed to protect capital and prevent catastrophic losses.
    """
    max_position_size: Decimal = Decimal('10000')      # Maximum dollar value per position
    max_daily_loss: Decimal = Decimal('1000')          # Maximum daily loss threshold
    max_portfolio_exposure: Decimal = Decimal('0.8')   # Maximum percentage of portfolio at risk
    max_sector_exposure: Decimal = Decimal('0.3')      # Maximum exposure to any single sector
    max_single_asset_exposure: Decimal = Decimal('0.1') # Maximum exposure to any single asset
    stop_loss_percentage: Decimal = Decimal('0.02')    # Default stop loss percentage (2%)
    take_profit_percentage: Decimal = Decimal('0.06')  # Default take profit percentage (6%)
    max_correlation_exposure: Decimal = Decimal('0.5') # Maximum exposure to correlated assets

class RiskManager:
    """
    Advanced risk management system with real-time monitoring and circuit breakers.
    Implements multiple layers of protection to preserve capital and manage downside risk.
    """
    
    def __init__(self, risk_limits: RiskLimits, initial_balance: Decimal):
        """
        Initialize risk manager with comprehensive tracking capabilities.
        
        Args:
            risk_limits: Configuration object with all risk parameters
            initial_balance: Starting account balance for risk calculations
        """
        self.risk_limits = risk_limits
        self.initial_balance = initial_balance
        self.current_balance = initial_balance
        self.daily_pnl = Decimal('0')
        self.positions = {}  # Track all open positions
        self.daily_trades = []  # Track all trades for the day
        self.circuit_breaker_active = False
        # This legacy class has no broker/ledger reconciliation adapter.
        # Its order gate is disabled until a verified position snapshot is supplied.
        self.position_snapshot_verified = False
        self.last_reset = datetime.now().date()
        
        # Risk monitoring metrics
        self.risk_events = []  # Track all risk-related events
        self.max_drawdown = Decimal('0')
        self.peak_balance = initial_balance
        
        logger.info(f"Risk manager initialized with balance: ${initial_balance}")
        EventLog.emit("INFO", f"Risk manager initialized - Initial balance: ${initial_balance}")
        
    async def validate_order(self, order_request: OrderRequest,
                             current_price: Decimal) -> tuple[bool, str]:
        """Fail-closed, position-aware paper candidate validation.

        A broker adapter must *independently* reconcile all outstanding orders,
        positions, cash and quote freshness before marking state verified.
        Setting position_snapshot_verified in this class is NOT a substitute
        for broker reconciliation and does not authorise live orders.
        """
        await self._reset_daily_counters()  # Never clears a latched risk halt.
        if not self.position_snapshot_verified:
            return False, "legacy risk manager has no reconciled account snapshot"
        try:
            side = order_request.side.value
            symbol = order_request.symbol
            accepted, reason = check_proposed_order(
                equity=self.current_balance, positions=self.positions,
                symbol=symbol, side=side, quantity=order_request.quantity,
                market_price=current_price, order_price=order_request.price,
                max_position_value=self.risk_limits.max_position_size,
                max_asset_fraction=self.risk_limits.max_single_asset_exposure,
                max_portfolio_fraction=self.risk_limits.max_portfolio_exposure,
                daily_pnl=self.daily_pnl,
                max_daily_loss=self.risk_limits.max_daily_loss,
                entry_halted=self.circuit_breaker_active,
            )
        except (AttributeError, TypeError, ValueError, ArithmeticError) as exc:
            accepted, reason = False, f"invalid order details: {exc}"
        EventLog.emit("INFO" if accepted else "WARNING",
                      f"Legacy risk validation: {reason}")
        return accepted, reason

    async def calculate_position_size(self, account_balance: Decimal,
                                      risk_percentage: Decimal,
                                      entry_price: Decimal,
                                      stop_loss_price: Decimal,
                                      confidence_score: float = 1.0) -> Decimal:
        """Return a bounded whole-share long quantity; never scale by AI score.

        Invalid stop geometry, a zero stop distance, NaN, excessive requested
        risk, or missing values return zero, not an arbitrary fallback size.
        Caller must separately verify authoritative equity/positions and
        commission-adjusted affordability before a broker order.
        """
        try:
            return whole_share_size(
                equity=account_balance, risk_fraction=risk_percentage,
                entry=entry_price, stop=stop_loss_price,
                max_asset_fraction=self.risk_limits.max_single_asset_exposure,
                max_position_value=self.risk_limits.max_position_size,
            )
        except (ValueError, ArithmeticError, TypeError) as exc:
            EventLog.emit("WARNING", f"Rejected legacy position sizing: {exc}")
            return Decimal("0")

    async def generate_stop_orders(self, 
                                 symbol: str, 
                                 entry_price: Decimal, 
                                 quantity: Decimal, 
                                 side: OrderSide) -> List[OrderRequest]:
        """
        Generate stop-loss and take-profit orders for risk management.
        Automatically creates protective orders for every position.
        
        Args:
            symbol: Trading symbol
            entry_price: Entry price of the position
            quantity: Position size
            side: Original order side (BUY or SELL)
            
        Returns:
            List of OrderRequest objects for stop orders
        """
        logger.info(f"Generating stop orders for {symbol}: {side.value} {quantity} @ ${entry_price}")
        
        orders = []
        
        if side == OrderSide.BUY:
            # Long position - stop below entry, profit above entry
            stop_loss_price = entry_price * (1 - self.risk_limits.stop_loss_percentage)
            take_profit_price = entry_price * (1 + self.risk_limits.take_profit_percentage)
            
            logger.debug(f"Long position stops - SL: ${stop_loss_price}, TP: ${take_profit_price}")
            
            # Stop-loss order (sell if price drops)
            stop_order = OrderRequest(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type=OrderType.STOP,
                stop_price=stop_loss_price,
                client_order_id=f"SL_{symbol}_{datetime.now().timestamp()}"
            )
            orders.append(stop_order)
            
            # Take-profit order (sell at target price)
            profit_order = OrderRequest(
                symbol=symbol,
                side=OrderSide.SELL,
                quantity=quantity,
                order_type=OrderType.LIMIT,
                price=take_profit_price,
                client_order_id=f"TP_{symbol}_{datetime.now().timestamp()}"
            )
            orders.append(profit_order)
            
        else:  # SELL (short position)
            # Short position - stop above entry, profit below entry
            stop_loss_price = entry_price * (1 + self.risk_limits.stop_loss_percentage)
            take_profit_price = entry_price * (1 - self.risk_limits.take_profit_percentage)
            
            logger.debug(f"Short position stops - SL: ${stop_loss_price}, TP: ${take_profit_price}")
            
            # Stop-loss order (buy if price rises)
            stop_order = OrderRequest(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.STOP,
                stop_price=stop_loss_price,
                client_order_id=f"SL_{symbol}_{datetime.now().timestamp()}"
            )
            orders.append(stop_order)
            
            # Take-profit order (buy at target price)
            profit_order = OrderRequest(
                symbol=symbol,
                side=OrderSide.BUY,
                quantity=quantity,
                order_type=OrderType.LIMIT,
                price=take_profit_price,
                client_order_id=f"TP_{symbol}_{datetime.now().timestamp()}"
            )
            orders.append(profit_order)
            
        logger.info(f"Generated {len(orders)} stop orders for {symbol}")
        EventLog.emit("INFO", f"Stop orders generated for {symbol}: SL @ ${stop_loss_price:.2f}, TP @ ${take_profit_price:.2f}")
        
        return orders
        
    async def update_pnl(self, symbol: str, realized_pnl: Decimal):
        """
        Update P&L tracking and check circuit breaker conditions.
        Monitors portfolio performance and triggers protective measures if needed.
        
        Args:
            symbol: Symbol that generated the P&L
            realized_pnl: Realized profit or loss amount
        """
        logger.info(f"Updating P&L for {symbol}: ${realized_pnl}")
        
        # Update daily and total P&L
        self.daily_pnl += realized_pnl
        self.current_balance += realized_pnl
        
        # Update peak balance and drawdown tracking
        if self.current_balance > self.peak_balance:
            self.peak_balance = self.current_balance
            logger.debug(f"New peak balance: ${self.peak_balance}")
            
        # Calculate current drawdown
        current_drawdown = (self.peak_balance - self.current_balance) / self.peak_balance
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown
            logger.warning(f"New maximum drawdown: {current_drawdown:.2%}")
            
        logger.info(f"P&L Update - {symbol}: ${realized_pnl}, Daily: ${self.daily_pnl}, Balance: ${self.current_balance}")
        EventLog.emit("INFO", f"P&L Update: {symbol} ${realized_pnl}, Daily P&L: ${self.daily_pnl}, Balance: ${self.current_balance}")
        
        # Check circuit breaker conditions
        if self.daily_pnl < -self.risk_limits.max_daily_loss:
            await self._activate_circuit_breaker(f"Daily loss limit exceeded: ${self.daily_pnl}")
        elif current_drawdown > Decimal('0.20'):
            await self._activate_circuit_breaker(f"Maximum drawdown exceeded: {current_drawdown:.2%}")
            
    async def _activate_circuit_breaker(self, reason: str):
        """
        Activate emergency circuit breaker to halt all trading.
        Critical safety mechanism to prevent catastrophic losses.
        
        Args:
            reason: Reason for circuit breaker activation
        """
        self.circuit_breaker_active = True
        
        logger.critical(f"🚨 CIRCUIT BREAKER ACTIVATED: {reason}")
        EventLog.emit("CRITICAL", f"🚨 CIRCUIT BREAKER ACTIVATED: {reason}")
        
        # Publish circuit breaker event to entire system
        EventBus.publish("CIRCUIT_BREAKER_ACTIVATED", {
            "reason": reason, 
            "timestamp": datetime.now(),
            "daily_pnl": float(self.daily_pnl),
            "current_balance": float(self.current_balance),
            "drawdown": float(self.max_drawdown)
        })
        
        # Log risk event for analysis
        self.risk_events.append({
            "type": "circuit_breaker",
            "reason": reason,
            "timestamp": datetime.now(),
            "daily_pnl": self.daily_pnl,
            "balance": self.current_balance
        })
        
    def _calculate_total_exposure(self) -> Decimal:
        """
        Calculate total portfolio exposure across all positions.
        
        Returns:
            Total dollar value at risk across all positions
        """
        total_exposure = sum(pos.get('value', Decimal('0')) for pos in self.positions.values())
        logger.debug(f"Total portfolio exposure: ${total_exposure}")
        return total_exposure
        
    def _get_asset_exposure(self, symbol: str) -> Decimal:
        """
        Get current exposure to a specific asset.
        
        Args:
            symbol: Asset symbol to check
            
        Returns:
            Current dollar exposure to the asset
        """
        exposure = self.positions.get(symbol, {}).get('value', Decimal('0'))
        logger.debug(f"Asset exposure for {symbol}: ${exposure}")
        return exposure
        
    def _validate_price_sanity(self, current_price: Decimal, order_price: Optional[Decimal]) -> bool:
        """
        Validate order price against current market price to prevent fat-finger errors.
        
        Args:
            current_price: Current market price
            order_price: Proposed order price (None for market orders)
            
        Returns:
            True if price is reasonable, False if potentially erroneous
        """
        if order_price is None:
            return True  # Market orders are always valid
            
        # Check if order price is within 10% of current market price
        price_diff = abs(order_price - current_price) / current_price
        is_valid = price_diff < Decimal('0.10')
        
        if not is_valid:
            logger.warning(f"Price sanity check failed: Order ${order_price} vs Market ${current_price} (diff: {price_diff:.2%})")
            
        return is_valid
        
    async def _reset_daily_counters(self):
        """
        Reset daily tracking counters for new trading day.
        Called automatically when date changes.
        """
        today = datetime.now().date()
        
        if today > self.last_reset:
            logger.info("Resetting daily risk counters for new trading day")
            
            # Reset daily tracking
            self.daily_pnl = Decimal('0')
            self.daily_trades = []
            self.last_reset = today
            
            # Circuit breakers require explicit operator recovery and must
            # never reset because the local date advanced.
            if self.circuit_breaker_active:
                logger.warning("Risk halt remains latched across day rollover")
                
            EventLog.emit("INFO", "Daily risk counters reset for new trading day")
