"""Binance CCXT exchange client with market filter normalization and precision rounding."""

import math
import time
from typing import Any, Dict, Optional, Tuple
import ccxt
from loguru import logger

from config.settings import get_settings


class BinanceExchangeClient:
    """Production-grade CCXT wrapper for Binance with strict lot sizing and precision safeguards."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        testnet: Optional[bool] = None,
        default_type: Optional[str] = None,
    ) -> None:
        settings = get_settings()
        self.api_key = api_key if api_key is not None else settings.API_KEY
        self.api_secret = api_secret if api_secret is not None else settings.API_SECRET
        self.testnet = testnet if testnet is not None else settings.TESTNET
        self.default_type = default_type if default_type is not None else getattr(settings, "DEFAULT_TYPE", "future")

        self._markets_loaded: bool = False
        self._market_rules: Dict[str, Dict[str, float]] = {}

        # Initialize CCXT Binance instance
        exchange_config: Dict[str, Any] = {
            "apiKey": self.api_key,
            "secret": self.api_secret,
            "enableRateLimit": True,
            "options": {
                "defaultType": self.default_type,  # "future" or "spot"
                "adjustForTimeDifference": True,
            },
        }

        try:
            self.client = ccxt.binance(exchange_config)
            if self.testnet:
                self.client.set_sandbox_mode(True)
                logger.info("BinanceExchangeClient: Initialized in SANDBOX (Testnet) mode.")
            else:
                logger.warning("BinanceExchangeClient: Initialized in PRODUCTION mode.")
        except Exception as e:
            logger.error(f"Failed to instantiate CCXT Binance client: {e}")
            self.client = None

    def load_market_rules(self, symbol: str = "BTC/USDT") -> Dict[str, float]:
        """Loads and caches tickSize, stepSize, minQty, and minNotional from exchange market filters."""
        if symbol in self._market_rules:
            return self._market_rules[symbol]

        default_rules = {
            "tickSize": 0.01,
            "stepSize": 0.001,
            "minQty": 0.001,
            "maxQty": 1000.0,
            "minNotional": 10.0,
        }

        if self.client is None:
            self._market_rules[symbol] = default_rules
            return default_rules

        try:
            if not self._markets_loaded:
                self.client.load_markets()
                self._markets_loaded = True

            market = self.client.market(symbol)
            if market:
                precision_price = market.get("precision", {}).get("price", 2)
                precision_amount = market.get("precision", {}).get("amount", 3)

                # Extract filters
                limits = market.get("limits", {})
                cost_limit = limits.get("cost", {}).get("min", 10.0) or 10.0
                amount_limit = limits.get("amount", {}).get("min", 0.001) or 0.001

                tick_size = 10.0 ** (-precision_price) if isinstance(precision_price, int) else 0.01
                step_size = 10.0 ** (-precision_amount) if isinstance(precision_amount, int) else 0.001

                rules = {
                    "tickSize": tick_size,
                    "stepSize": step_size,
                    "minQty": float(amount_limit),
                    "maxQty": float(limits.get("amount", {}).get("max", 1000.0) or 1000.0),
                    "minNotional": float(cost_limit),
                }
                self._market_rules[symbol] = rules
                logger.debug(f"Loaded market rules for {symbol}: {rules}")
                return rules
        except Exception as e:
            logger.warning(f"Could not load market rules from exchange for {symbol}: {e}. Using fallback defaults.")

        self._market_rules[symbol] = default_rules
        return default_rules

    def format_price(self, symbol: str, price: float) -> float:
        """Rounds price to the exchange tick size."""
        rules = self.load_market_rules(symbol)
        tick_size = rules["tickSize"]
        if tick_size <= 0:
            return round(price, 2)
        precision = max(0, int(round(-math.log10(tick_size))))
        return round(round(price / tick_size) * tick_size, precision)

    def format_quantity(self, symbol: str, quantity: float) -> float:
        """Floors quantity down to the exchange lot step size to prevent insufficient balance rejections."""
        rules = self.load_market_rules(symbol)
        step_size = rules["stepSize"]
        if step_size <= 0:
            return float(quantity)
        precision = max(0, int(round(-math.log10(step_size))))
        floored = math.floor(quantity / step_size) * step_size
        return round(floored, precision)

    def check_min_notional(self, symbol: str, price: float, quantity: float) -> Tuple[bool, float]:
        """Verifies if order notional meets the Binance minimum ($10.00 default)."""
        rules = self.load_market_rules(symbol)
        min_notional = rules.get("minNotional", 10.0)
        notional = price * quantity
        return notional >= min_notional, round(notional, 2)

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: Optional[float] = None,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Dispatches an order to Binance CCXT with formatted precision."""
        if self.client is None:
            raise RuntimeError("CCXT client is not initialized.")

        formatted_amount = self.format_quantity(symbol, amount)
        formatted_price = self.format_price(symbol, price) if price is not None else None

        valid_notional, notional = self.check_min_notional(
            symbol, formatted_price or 1.0, formatted_amount
        )
        if not valid_notional:
            raise ValueError(
                f"Order notional ${notional:.2f} is below minimum requirement of ${self.load_market_rules(symbol)['minNotional']:.2f}"
            )

        order_params = params or {}
        return self.client.create_order(
            symbol=symbol,
            type=order_type.lower(),
            side=side.lower(),
            amount=formatted_amount,
            price=formatted_price,
            params=order_params,
        )

    def cancel_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Cancels an active order on Binance."""
        if self.client is None:
            raise RuntimeError("CCXT client is not initialized.")
        return self.client.cancel_order(order_id, symbol)

    def fetch_order(self, order_id: str, symbol: str) -> Dict[str, Any]:
        """Fetches status of a specific order."""
        if self.client is None:
            raise RuntimeError("CCXT client is not initialized.")
        return self.client.fetch_order(order_id, symbol)

    def fetch_open_orders(self, symbol: Optional[str] = None) -> list:
        """Fetches all currently open orders."""
        if self.client is None:
            raise RuntimeError("CCXT client is not initialized.")
        return self.client.fetch_open_orders(symbol)

    def fetch_balance(self) -> Dict[str, Any]:
        """Fetches current account balances."""
        if self.client is None:
            raise RuntimeError("CCXT client is not initialized.")
        return self.client.fetch_balance()
