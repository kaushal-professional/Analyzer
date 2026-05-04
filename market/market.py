"""
Market data extraction from Fyers API.

All functions use get_client() from auth for authentication.
"""
import logging
from auth.auth import get_fyers_client

logger = logging.getLogger(__name__)


def get_quotes(symbols: list[str]) -> dict:
    """
    Get real-time quotes for given symbols.

    Args:
        symbols: List of Fyers symbols, e.g. ["NSE:RELIANCE-EQ", "NSE:TCS-EQ"]

    Returns:
        Raw Fyers API response dict with quote data.
        On success: {"s": "ok", "d": [{"n": "NSE:RELIANCE-EQ", "v": {...}}, ...]}

    Raises:
        RuntimeError: If API call fails.
    """
    client = get_fyers_client()
    data = {"symbols": ",".join(symbols)}
    resp = client.quotes(data)
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Quotes failed: {resp}")


def get_option_chain(symbol: str, strike_count: int = 10) -> dict:
    """
    Get option chain data for a symbol.

    Args:
        symbol: Fyers symbol, e.g. "NSE:NIFTY50-INDEX"
        strike_count: Number of strikes above/below ATM to fetch.

    Returns:
        Raw Fyers API response with option chain data.

    Raises:
        RuntimeError: If API call fails.
    """
    client = get_fyers_client()
    data = {"symbol": symbol, "strikecount": strike_count, "timestamp": ""}
    resp = client.optionchain(data)
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Option chain failed: {resp}")


def get_market_depth(symbol: str) -> dict:
    """
    Get Level 2 market depth for a symbol.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"

    Returns:
        Raw Fyers API response with bid/ask depth.

    Raises:
        RuntimeError: If API call fails.
    """
    client = get_fyers_client()
    data = {"symbol": symbol, "ohlcv_flag": 1}
    resp = client.depth(data)
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Market depth failed: {resp}")


def get_historical_data(symbol: str, resolution: str,
                        from_date: str, to_date: str) -> dict:
    """
    Get historical OHLCV candle data.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"
        resolution: Candle resolution — "1", "5", "15", "30", "60", "D", "W", "M"
        from_date: Start date as "YYYY-MM-DD"
        to_date: End date as "YYYY-MM-DD"

    Returns:
        Raw Fyers API response with candle data.

    Raises:
        RuntimeError: If API call fails.
    """
    client = get_fyers_client()
    data = {
        "symbol": symbol,
        "resolution": resolution,
        "date_format": "1",
        "range_from": from_date,
        "range_to": to_date,
        "cont_flag": "1",
    }
    resp = client.history(data)
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Historical data failed: {resp}")
