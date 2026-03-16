# core/risk_management.py - Comprehensive risk controls with detailed logging
from dataclasses import dataclass
from decimal import Decimal
from typing import Dict, List, Optional
from datetime import datetime, timedelta
import asyncio
import logging

from core.events import EventLog, EventBus
from core.execution import OrderRequest, OrderSide, OrderType

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
        self.last_reset = datetime.now().date()
        
        # Risk monitoring metrics
        self.risk_events = []  # Track all risk-related events
        self.max_drawdown = Decimal('0')
        self.peak_balance = initial_balance
        
        logger.info(f"Risk manager initialized with balance: ${initial_balance}")
        EventLog.emit("INFO", f"Risk manager initialized - Initial balance: ${initial_balance}")
        
    async def validate_order(self, order_request: OrderRequest, current_price: Decimal) -> tuple[bool, str]:
        """
        Comprehensive pre-trade risk validation.
        Multiple layers of checks to ensure order meets all risk criteria.
        
        Args:
            order_request: The order to validate
            current_price: Current market price for the symbol
            
        Returns:
            Tuple of (is_valid, reason_message)
        """
        logger.info(f"Validating order: {order_request.symbol} {order_request.side.value} {order_request.quantity}")
        
        # Check if circuit breaker is active
        if self.circuit_breaker_active:
            reason = "Circuit breaker active - trading halted"
            logger.warning(f"Order validation failed: {reason}")
            return False, reason
            
        # Reset daily counters if new trading day
        await self._reset_daily_counters()
        
        # Calculate position value for risk assessment
        position_value = order_request.quantity * current_price
        logger.debug(f"Position value: ${position_value}")
        
        # Validate maximum position size
        if position_value > self.risk_limits.max_position_size:
            reason = f"Position size ${position_value} exceeds limit ${self.risk_limits.max_position_size}"
            logger.warning(f"Order validation failed: {reason}")
            EventLog.emit("WARNING", f"Position size limit exceeded: {reason}")
            return False, reason
            
        # Check daily loss limit
        if self.daily_pnl < -self.risk_limits.max_daily_loss:
            reason = f"Daily loss limit exceeded: ${self.daily_pnl}"
            logger.warning(f"Order validation failed: {reason}")
            EventLog.emit("WARNING", f"Daily loss limit exceeded")
            return False, reason
            
        # Check portfolio exposure
        total_exposure = self._calculate_total_exposure()
        max_allowed_exposure = self.current_balance * self.risk_limits.max_portfolio_exposure
        
        if total_exposure > max_allowed_exposure:
            reason = f"Portfolio exposure limit exceeded: ${total_exposure} > ${max_allowed_exposure}"
            logger.warning(f"Order validation failed: {reason}")
            EventLog.emit("WARNING", f"Portfolio exposure limit exceeded")
            return False, reason
            
        # Check single asset exposure
        current_asset_exposure = self._get_asset_exposure(order_request.symbol)
        new_asset_exposure = current_asset_exposure + position_value
        max_asset_value = self.current_balance * self.risk_limits.max_single_asset_exposure
        
        if new_asset_exposure > max_asset_value:
            reason = f"Single asset exposure limit exceeded for {order_request.symbol}"
            logger.warning(f"Order validation failed: {reason}")
            EventLog.emit("WARNING", f"Asset exposure limit exceeded: {order_request.symbol}")
            return False, reason
            
        # Price sanity check to prevent fat-finger errors
        if not self._validate_price_sanity(current_price, order_request.price):
            reason = "Order price fails sanity check - price too far from market"
            logger.warning(f"Order validation failed: {reason}")
            EventLog.emit("WARNING", f"Price sanity check failed for {order_request.symbol}")
            return False, reason
            
        # All validations passed
        logger.info(f"Order validation successful for {order_request.symbol}")
        EventLog.emit("INFO", f"Order validated: {order_request.symbol} {order_request.side.value}")
        return True, "Order approved - all risk checks passed"
        
    async def calculate_position_size(self, 
                                    account_balance: Decimal, 
                                    risk_percentage: Decimal, 
                                    entry_price: Decimal, 
                                    stop_loss_price: Decimal,
                                    confidence_score: float = 1.0) -> Decimal:
        """
        Enhanced position sizing with confidence-based adjustment.
        Implements Kelly Criterion principles with risk management overlays.
        
        Args:
            account_balance: Current account balance
            risk_percentage: Percentage of account to risk (e.g., 0.01 for 1%)
            entry_price: Planned entry price
            stop_loss_price: Planned stop loss price
            confidence_score: AI confidence score (0.0 to 1.0)
            
        Returns:
            Optimal position size in shares/units
        """
        logger.info(f"Calculating position size - Balance: ${account_balance}, Risk: {risk_percentage:.1%}")
        
        # Base risk amount calculation
        base_risk_amount = account_balance * risk_percentage
        logger.debug(f"Base risk amount: ${base_risk_amount}")
        
        # Adjust for AI confidence (0.5x to 1.5x multiplier)
        # Lower confidence = smaller position, higher confidence = larger position
        confidence_multiplier = Decimal(str(0.5 + confidence_score))
        adjusted_risk_amount = base_risk_amount * confidence_multiplier
        
        logger.debug(f"Confidence score: {confidence_score:.2f}, Multiplier: {confidence_multiplier}")
        logger.debug(f"Adjusted risk amount: ${adjusted_risk_amount}")
        
        # Calculate stop loss distance
        stop_loss_distance = abs(entry_price - stop_loss_price)
        
        if stop_loss_distance == 0:
            logger.warning("Stop loss distance is zero - using minimum position size")
            EventLog.emit("WARNING", "Stop loss distance is zero - using minimum position size")
            return Decimal('100')  # Minimum position size fallback
            
        # Calculate position size based on risk amount and stop distance
        position_size = adjusted_risk_amount / stop_loss_distance
        logger.debug(f"Calculated position size: {position_size}")
        
        # Apply maximum position size limits
        max_position_value = min(
            self.risk_limits.max_position_size,
            account_balance * self.risk_limits.max_single_asset_exposure
        )
        max_quantity = max_position_value / entry_price
        
        # Use the smaller of calculated size or maximum allowed
        final_position_size = min(position_size, max_quantity)
        
        logger.info(f"Final position size: {final_position_size} (Risk: ${adjusted_risk_amount}, Distance: ${stop_loss_distance})")
        EventLog.emit("INFO", f"Position sizing complete: {final_position_size} shares, Risk: ${adjusted_risk_amount}")
        
        return final_position_size
        
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
            
            # Reset circuit breaker for new day (with caution)
            if self.circuit_breaker_active:
                logger.warning("Circuit breaker reset for new trading day - monitor closely")
                self.circuit_breaker_active = False
                
            EventLog.emit("INFO", "Daily risk counters reset for new trading day")
