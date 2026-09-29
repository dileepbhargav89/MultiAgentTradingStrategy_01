"""Market Intelligence Agent: Analyzes derivatives funding, open interest momentum, and macro sentiment."""

import asyncio
from datetime import datetime, timezone
from typing import Any, Dict, Optional
import pandas as pd
from loguru import logger

from agents.positioning_analyzer import PositioningAnalyzer
from core.events import (
    EVENT_MARKET_INTELLIGENCE_ALERT,
    EVENT_MARKET_INTELLIGENCE_REPORT,
    event_bus,
)
from core.types import (
    CrowdingBias,
    DataPacket,
    MarketIntelligenceReport,
    PositioningQuadrant,
)
from data.derivatives_fetcher import DerivativesFetcher
from data.sentiment_fetcher import SentimentFetcher


class MarketIntelligenceAgent:
    """
    Agent #3: Market Intelligence Agent.
    Monitors Binance USD-M Futures positioning dynamics, calculates Funding Rate Z-Scores,
    analyzes Open Interest momentum quadrants, tracks Top Trader Long/Short positioning,
    and incorporates macro Fear & Greed sentiment to generate crowding risk penalties.
    """

    def __init__(
        self,
        derivatives_fetcher: Optional[DerivativesFetcher] = None,
        sentiment_fetcher: Optional[SentimentFetcher] = None,
        analyzer: Optional[PositioningAnalyzer] = None,
    ) -> None:
        self.derivatives_fetcher = derivatives_fetcher or DerivativesFetcher()
        self.sentiment_fetcher = sentiment_fetcher or SentimentFetcher()
        self.analyzer = analyzer or PositioningAnalyzer()
        self.last_report: Optional[MarketIntelligenceReport] = None

    def analyze(self, packet: DataPacket) -> MarketIntelligenceReport:
        """Evaluates positioning metrics for backtesting using synthetic proxies derived from candle data."""
        synthetic = self._compute_synthetic_market_data(packet)
        return self.evaluate_market_data(
            packet=packet,
            funding_data=synthetic["funding_data"],
            funding_hist=synthetic["funding_hist"],
            oi_data=synthetic["oi_data"],
            oi_hist=synthetic["oi_hist"],
            top_trader_df=synthetic["top_trader_df"],
            sentiment_data=synthetic["sentiment_data"],
        )

    def _compute_synthetic_market_data(self, packet: DataPacket) -> dict:
        """Derives synthetic funding rate, OI, and sentiment proxies from price/volume candle data."""
        import numpy as np

        df_1h = packet.timeframes.get("1h")
        if df_1h is None or len(df_1h) < 30:
            df_1h = packet.timeframes.get("15m", next(iter(packet.timeframes.values())))

        close = df_1h["close"].values.astype(float)
        high = df_1h["high"].values.astype(float)
        low = df_1h["low"].values.astype(float)
        volume = df_1h["volume"].values.astype(float) if "volume" in df_1h.columns else np.ones(len(df_1h))

        n = len(close)

        # 1. Synthetic Funding Rate: premium/discount to VWAP proxy
        #    Positive funding = longs pay shorts (bullish crowding)
        typical_price = (high + low + close) / 3.0
        vwap_proxy = np.cumsum(typical_price * volume) / np.maximum(np.cumsum(volume), 1e-10)
        premium = (close[-1] - vwap_proxy[-1]) / max(vwap_proxy[-1], 1.0)
        # Scale to realistic funding range [-0.05%, +0.05%]
        funding_rate = float(np.clip(premium * 0.5, -0.0005, 0.0005))
        funding_annualized = funding_rate * 3 * 365  # 3 funding intervals/day

        # Synthetic funding history (last 24 bars as DataFrame)
        funding_hist_vals = []
        lookback = min(n, 96)
        for i in range(max(0, n - lookback), n):
            vw = np.sum(typical_price[max(0, i-20):i+1] * volume[max(0, i-20):i+1]) / max(np.sum(volume[max(0, i-20):i+1]), 1e-10)
            fr = float(np.clip((close[i] - vw) / max(vw, 1.0) * 0.5, -0.0005, 0.0005))
            funding_hist_vals.append({"funding_rate": fr})
        funding_hist = pd.DataFrame(funding_hist_vals) if funding_hist_vals else pd.DataFrame()

        # 2. Synthetic Open Interest: volume-weighted momentum proxy
        #    Rising volume + rising price = rising OI (longs entering)
        #    Rising volume + falling price = rising OI (shorts entering)
        vol_sma = float(np.mean(volume[-20:])) if n >= 20 else float(np.mean(volume))
        current_vol = float(volume[-1]) if n > 0 else vol_sma
        price_now = float(close[-1])
        oi_base = 50000.0 * (price_now / 60000.0)  # Scale OI with price
        vol_ratio = current_vol / max(vol_sma, 1.0)
        oi_contracts = oi_base * max(0.5, min(2.0, vol_ratio))

        # Synthetic OI history
        oi_hist_vals = []
        lookback_oi = min(n, 48)
        for i in range(max(0, n - lookback_oi), n):
            v_sma_local = float(np.mean(volume[max(0, i-20):i+1]))
            v_ratio = float(volume[i]) / max(v_sma_local, 1.0)
            oi_val = oi_base * max(0.5, min(2.0, v_ratio))
            oi_hist_vals.append({"open_interest": oi_val, "timestamp": i})
        oi_hist = pd.DataFrame(oi_hist_vals) if oi_hist_vals else pd.DataFrame()

        # 3. Synthetic Fear & Greed Index from composite indicators
        #    RSI contribution (30=extreme fear, 70=extreme greed)
        if n >= 15:
            deltas = np.diff(close[-(15):])
            gains = np.where(deltas > 0, deltas, 0)
            losses = np.where(deltas < 0, -deltas, 0)
            avg_gain = float(np.mean(gains)) if len(gains) > 0 else 0.0
            avg_loss = float(np.mean(losses)) if len(losses) > 0 else 1e-10
            rs = avg_gain / max(avg_loss, 1e-10)
            rsi = 100 - (100 / (1 + rs))
        else:
            rsi = 50.0

        # Volatility contribution (high vol = fear, low vol = complacency/greed)
        if n >= 20:
            returns = np.diff(np.log(np.maximum(close[-21:], 1e-10)))
            vol_pct = float(np.std(returns) * np.sqrt(24 * 365) * 100)  # Annualized
        else:
            vol_pct = 50.0
        vol_fear = max(0, min(100, 100 - vol_pct))  # Higher vol = lower score (more fear)

        # Price momentum contribution
        if n >= 24:
            mom_24h = (close[-1] - close[-24]) / max(close[-24], 1.0) * 100
        else:
            mom_24h = 0.0
        mom_score = max(0, min(100, 50 + mom_24h * 5))  # ±10% move = ±50 FGI points

        # Composite FGI
        fgi = int(np.clip(rsi * 0.40 + vol_fear * 0.30 + mom_score * 0.30, 1, 99))
        if fgi <= 25:
            fgi_label = "Extreme Fear"
        elif fgi <= 40:
            fgi_label = "Fear"
        elif fgi <= 60:
            fgi_label = "Neutral"
        elif fgi <= 75:
            fgi_label = "Greed"
        else:
            fgi_label = "Extreme Greed"

        # 4. Synthetic Top Trader Long/Short Ratio from buy/sell volume imbalance
        if n >= 10:
            buy_vol = np.sum((close[-10:] - low[-10:]) / np.maximum(high[-10:] - low[-10:], 1e-10) * volume[-10:])
            sell_vol = np.sum((high[-10:] - close[-10:]) / np.maximum(high[-10:] - low[-10:], 1e-10) * volume[-10:])
            top_ratio = float(buy_vol / max(sell_vol, 1e-10))
        else:
            top_ratio = 1.0
        top_trader_df = pd.DataFrame([{"long_short_ratio": round(top_ratio, 3)}])

        return {
            "funding_data": {"funding_rate": funding_rate, "funding_rate_annualized": funding_annualized},
            "funding_hist": funding_hist,
            "oi_data": {"open_interest_contracts": oi_contracts},
            "oi_hist": oi_hist,
            "top_trader_df": top_trader_df,
            "sentiment_data": {"value": fgi, "classification": fgi_label},
        }

    async def analyze_live(self, packet: DataPacket) -> MarketIntelligenceReport:
        """
        Asynchronously fetches live derivatives and sentiment metrics, evaluates positioning,
        and publishes MarketIntelligenceReport.
        """
        symbol = packet.symbol

        # Fetch derivatives and sentiment concurrently
        funding_task = self.derivatives_fetcher.fetch_funding_rate(symbol)
        funding_hist_task = self.derivatives_fetcher.fetch_funding_rate_history(symbol, limit=90)
        oi_task = self.derivatives_fetcher.fetch_open_interest(symbol)
        oi_hist_task = self.derivatives_fetcher.fetch_open_interest_history(symbol, period="1h", limit=48)
        top_trader_task = self.derivatives_fetcher.fetch_top_trader_long_short_ratio(symbol, period="1h", limit=24)
        sentiment_task = self.sentiment_fetcher.fetch_fear_and_greed()

        (
            funding_data,
            funding_hist,
            oi_data,
            oi_hist,
            top_trader_df,
            sentiment_data,
        ) = await asyncio.gather(
            funding_task,
            funding_hist_task,
            oi_task,
            oi_hist_task,
            top_trader_task,
            sentiment_task,
            return_exceptions=False,
        )

        return self.evaluate_market_data(
            packet=packet,
            funding_data=funding_data,
            funding_hist=funding_hist,
            oi_data=oi_data,
            oi_hist=oi_hist,
            top_trader_df=top_trader_df,
            sentiment_data=sentiment_data,
        )

    def evaluate_market_data(
        self,
        packet: DataPacket,
        funding_data: Dict[str, Any],
        funding_hist: Any,
        oi_data: Dict[str, Any],
        oi_hist: Any,
        top_trader_df: Any,
        sentiment_data: Dict[str, Any],
    ) -> MarketIntelligenceReport:
        """
        Synchronously calculates positioning metrics and returns MarketIntelligenceReport.
        """
        symbol = packet.symbol
        rate = float(funding_data.get("funding_rate", 0.0001))
        rate_annualized = float(funding_data.get("funding_rate_annualized", 10.95))

        # 1. Funding Rate Z-Score
        funding_zscore = self.analyzer.calculate_funding_zscore(rate, funding_hist)

        # 2. Open Interest & Velocity
        oi_contracts = float(oi_data.get("open_interest_contracts", 50000.0))
        current_price = packet.latest_price if packet.latest_price > 0 else 60000.0
        oi_usd = oi_contracts * current_price
        oi_chg_4h, oi_chg_24h = self.analyzer.calculate_oi_velocity(oi_hist)

        # 3. 24h Spot Price Change from 1h or 1d candles
        price_chg_24h = 0.0
        if "1h" in packet.timeframes and len(packet.timeframes["1h"]) >= 24:
            df_1h = packet.timeframes["1h"]
            p_now = float(df_1h["close"].iloc[-1])
            p_24h_ago = float(df_1h["close"].iloc[-24])
            price_chg_24h = (p_now - p_24h_ago) / p_24h_ago if p_24h_ago > 0 else 0.0

        # 4. Positioning Quadrant
        quadrant = self.analyzer.classify_positioning_quadrant(price_chg_24h, oi_chg_24h)

        # 5. Top Trader Long/Short Ratio
        top_ratio = 1.0
        if top_trader_df is not None and not top_trader_df.empty and "long_short_ratio" in top_trader_df.columns:
            top_ratio = float(top_trader_df["long_short_ratio"].iloc[-1])

        # 6. Sentiment
        fgi_val = int(sentiment_data.get("value", 50))
        fgi_label = str(sentiment_data.get("classification", "Neutral"))

        # 7. Crowding & Penalty Analysis
        crowding_bias, penalty, squeeze_warn = self.analyzer.calculate_crowding_and_penalty(
            funding_zscore=funding_zscore,
            oi_change_24h_pct=oi_chg_24h,
            top_trader_ls=top_ratio,
            fgi_value=fgi_val,
        )

        report = MarketIntelligenceReport(
            symbol=symbol,
            funding_rate=rate,
            funding_rate_annualized=rate_annualized,
            funding_zscore=funding_zscore,
            open_interest_usd=oi_usd,
            oi_change_4h_pct=oi_chg_4h,
            oi_change_24h_pct=oi_chg_24h,
            positioning_quadrant=quadrant,
            top_trader_long_short_ratio=top_ratio,
            fear_and_greed_index=fgi_val,
            fear_and_greed_label=fgi_label,
            crowding_bias=crowding_bias,
            crowding_penalty=penalty,
            squeeze_warning=squeeze_warn,
            timestamp=datetime.now(timezone.utc),
        )

        self.last_report = report
        event_bus.publish(EVENT_MARKET_INTELLIGENCE_REPORT, report)

        if squeeze_warn or penalty >= 0.25:
            logger.warning(
                f"MARKET INTELLIGENCE ALERT [{symbol}]: Bias={crowding_bias.value} | Penalty={penalty:.2f} | Warning={squeeze_warn}"
            )
            event_bus.publish(EVENT_MARKET_INTELLIGENCE_ALERT, {
                "symbol": symbol,
                "warning": squeeze_warn,
                "penalty": penalty,
                "report": report,
            })

        logger.info(
            f"Market Intelligence [{symbol}]: Funding={rate:.4%} (Z={funding_zscore:+.2f}) | Quadrant={quadrant.value} | FGI={fgi_val} ({fgi_label}) | Penalty={penalty:.2f}"
        )
        return report

    async def close(self) -> None:
        """Gracefully closes underlying network fetchers and sessions."""
        if hasattr(self.derivatives_fetcher, "close"):
            await self.derivatives_fetcher.close()
