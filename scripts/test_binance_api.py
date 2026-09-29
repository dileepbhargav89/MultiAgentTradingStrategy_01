"""Diagnostic test script to verify Binance API credentials, network connectivity, and account permissions.

Loads credentials safely from .env without printing secrets to logs or terminal.
"""

import sys
from pathlib import Path
from loguru import logger

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from config.settings import get_settings
from engine.exchange_client import BinanceExchangeClient


def test_binance_connection() -> bool:
    settings = get_settings()

    logger.info("==================================================================")
    logger.info("🔍 StrategyOne: Binance API Connectivity & Account Validation Test")
    logger.info("==================================================================")

    # 1. Check if keys are present in .env
    has_key = bool(settings.API_KEY and settings.API_KEY.strip())
    has_secret = bool(settings.API_SECRET and settings.API_SECRET.strip())

    if not has_key or not has_secret:
        logger.warning("❌ Binance API Key or Secret is missing in .env!")
        logger.info(f"Target .env file: {PROJECT_ROOT / '.env'}")
        logger.info("Please set BINANCE_API_KEY and BINANCE_API_SECRET in your .env file.")
        return False

    masked_key = settings.API_KEY[:6] + "..." + settings.API_KEY[-4:] if len(settings.API_KEY) > 10 else "***"
    logger.info(f"✓ API Key detected: {masked_key}")
    logger.info(f"✓ Testnet Mode: {settings.TESTNET}")
    logger.info(f"✓ Default Market Type: {settings.DEFAULT_TYPE}")
    logger.info(f"✓ Target Trading Symbol: {settings.SYMBOL}")

    # 2. Initialize exchange client
    logger.info("\n[1/3] Connecting to Binance exchange endpoint...")
    client = BinanceExchangeClient(
        api_key=settings.API_KEY,
        api_secret=settings.API_SECRET,
        testnet=settings.TESTNET,
        default_type=settings.DEFAULT_TYPE,
    )

    if not client.client:
        logger.error("❌ Failed to instantiate CCXT client.")
        return False

    # 3. Test public market rules & price fetch
    logger.info("\n[2/3] Fetching live market rules and ticker for " + settings.SYMBOL + "...")
    try:
        rules = client.load_market_rules(settings.SYMBOL)
        ticker = client.client.fetch_ticker(settings.SYMBOL)
        last_price = ticker.get("last", 0.0)
        logger.info(f"✓ Ticker Price: {settings.SYMBOL} = ${last_price:,.2f}")
        logger.info(f"✓ Market Filters: tickSize={rules.get('tickSize')}, stepSize={rules.get('stepSize')}, minNotional=${rules.get('minNotional')}")
    except Exception as e:
        logger.error(f"❌ Market rules / ticker fetch failed: {e}")
        return False

    # 4. Test authenticated private balance fetch
    logger.info("\n[3/3] Authenticating API key and verifying balance permissions...")
    try:
        balance = client.client.fetch_balance()
        free_usdt = balance.get("USDT", {}).get("free", 0.0)
        total_usdt = balance.get("USDT", {}).get("total", 0.0)
        logger.info(f"✓ Authentication SUCCESSFUL!")
        logger.info(f"✓ Account Balance: {total_usdt:,.2f} USDT (Available: {free_usdt:,.2f} USDT)")
    except Exception as e:
        logger.error(f"❌ Private balance authentication failed: {e}")
        logger.info("Note: Verify that the API Key has Futures/Spot trading permissions enabled and correct IP whitelisting.")
        return False

    logger.info("\n==================================================================")
    logger.info("🎉 ALL BINANCE API TESTS PASSED! Ready for live/testnet daemon.")
    logger.info("==================================================================")
    return True


if __name__ == "__main__":
    success = test_binance_connection()
    sys.exit(0 if success else 1)
