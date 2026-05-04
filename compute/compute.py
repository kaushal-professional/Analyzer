"""
Compute analytics from market data.

Consumes data from market, applies thresholds from config.settings,
and produces analysis results.
"""
import logging
from market.market import get_option_chain, get_quotes
import config.settings as settings

logger = logging.getLogger(__name__)


def compute_pcr(symbol: str) -> dict:
    """
    Compute Put-Call Ratio from option chain data.

    PCR = Total Put OI / Total Call OI
    - PCR > 1.3 = extreme bearish (from settings.PCR_EXTREME_BEARISH_ABOVE)
    - PCR < 0.7 = extreme bullish (from settings.PCR_EXTREME_BULLISH_BELOW)

    Args:
        symbol: Fyers index symbol, e.g. "NSE:NIFTY50-INDEX"

    Returns:
        {
            "symbol": "NSE:NIFTY50-INDEX",
            "pcr": 1.15,
            "total_put_oi": 12345678,
            "total_call_oi": 10734502,
            "signal": "neutral" | "extreme_bearish" | "extreme_bullish"
        }
    """
    chain = get_option_chain(symbol)
    oc_data = chain.get("data", {}).get("oc", [])

    total_put_oi = 0
    total_call_oi = 0
    for strike in oc_data:
        if "pe" in strike:
            total_put_oi += strike["pe"].get("oi", 0)
        if "ce" in strike:
            total_call_oi += strike["ce"].get("oi", 0)

    pcr = total_put_oi / total_call_oi if total_call_oi > 0 else 0.0

    if pcr > settings.PCR_EXTREME_BEARISH_ABOVE:
        signal = "extreme_bearish"
    elif pcr < settings.PCR_EXTREME_BULLISH_BELOW:
        signal = "extreme_bullish"
    else:
        signal = "neutral"

    result = {
        "symbol": symbol,
        "pcr": round(pcr, 4),
        "total_put_oi": total_put_oi,
        "total_call_oi": total_call_oi,
        "signal": signal,
    }
    logger.info(f"PCR for {symbol}: {pcr:.4f} ({signal})")
    return result


def compute_max_pain(symbol: str) -> dict:
    """
    Calculate the max pain strike price.

    Max pain is the strike where option writers (sellers) have the least
    total loss. It's the strike where total value of puts + calls expiring
    worthless is maximum.

    Args:
        symbol: Fyers index symbol, e.g. "NSE:NIFTY50-INDEX"

    Returns:
        {
            "symbol": "NSE:NIFTY50-INDEX",
            "max_pain_strike": 24500.0,
            "current_price": 24650.0,
            "deviation_pct": 0.61,
            "within_buffer": True
        }
    """
    chain = get_option_chain(symbol)
    oc_data = chain.get("data", {}).get("oc", [])

    strikes = {}
    for strike_data in oc_data:
        strike_price = strike_data.get("strikePrice", 0)
        if not strike_price:
            continue
        ce_oi = strike_data.get("ce", {}).get("oi", 0)
        pe_oi = strike_data.get("pe", {}).get("oi", 0)
        strikes[strike_price] = {"ce_oi": ce_oi, "pe_oi": pe_oi}

    if not strikes:
        raise RuntimeError(f"No strike data for {symbol}")

    # For each possible expiry price, calculate total pain to option writers
    min_pain = float("inf")
    max_pain_strike = 0
    strike_prices = sorted(strikes.keys())

    for expiry_price in strike_prices:
        total_pain = 0
        for sp, oi in strikes.items():
            # Call writers lose when price > strike
            if expiry_price > sp:
                total_pain += (expiry_price - sp) * oi["ce_oi"]
            # Put writers lose when price < strike
            if expiry_price < sp:
                total_pain += (sp - expiry_price) * oi["pe_oi"]
        if total_pain < min_pain:
            min_pain = total_pain
            max_pain_strike = expiry_price

    # Get current price for deviation calculation
    spot_symbol = symbol.replace("-INDEX", "2") if "-INDEX" in symbol else symbol
    try:
        quotes = get_quotes([spot_symbol])
        current_price = quotes.get("d", [{}])[0].get("v", {}).get("lp", 0)
    except Exception:
        current_price = 0

    deviation_pct = (
        abs(current_price - max_pain_strike) / max_pain_strike * 100
        if max_pain_strike else 0
    )

    result = {
        "symbol": symbol,
        "max_pain_strike": max_pain_strike,
        "current_price": current_price,
        "deviation_pct": round(deviation_pct, 2),
        "within_buffer": deviation_pct <= settings.MAX_PAIN_BUFFER_PCT,
    }
    logger.info(f"Max pain for {symbol}: {max_pain_strike} (deviation {deviation_pct:.2f}%)")
    return result


def compute_delivery(symbol: str) -> dict:
    """
    Compute delivery percentage analysis.

    Delivery % = (delivered qty / traded qty) * 100
    - High delivery (>50%) suggests genuine buying/selling
    - Low delivery (<30%) suggests speculative/intraday activity

    Args:
        symbol: Fyers equity symbol, e.g. "NSE:RELIANCE-EQ"

    Returns:
        {
            "symbol": "NSE:RELIANCE-EQ",
            "delivery_pct": 45.2,
            "signal": "neutral" | "high_delivery" | "low_delivery"
        }

    Note: Fyers API does not directly provide delivery data.
    This is a placeholder that returns the quote volume data.
    Full implementation requires NSE bhavcopy or similar data source.
    """
    quotes = get_quotes([symbol])
    quote_data = quotes.get("d", [{}])[0].get("v", {})

    # Fyers quotes don't include delivery %. This returns volume info.
    # Full delivery analysis requires NSE bhavcopy integration.
    volume = quote_data.get("volume", 0)

    result = {
        "symbol": symbol,
        "volume": volume,
        "delivery_pct": 0.0,
        "signal": "data_unavailable",
    }
    logger.info(f"Delivery for {symbol}: data requires NSE bhavcopy integration")
    return result


def compute_conviction(symbol: str) -> dict:
    """
    Compute conviction score — weighted combination of multiple signals.

    Uses weights from config.settings.CONVICTION_WEIGHTS.
    Each signal contributes a score between -1 (bearish) and +1 (bullish).
    Final score is weighted average.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"

    Returns:
        {
            "symbol": "NSE:RELIANCE-EQ",
            "conviction_score": 0.45,
            "signals": {
                "oi_pcr_extreme": {"score": 0.5, "weight": 0.15},
                ...
            },
            "verdict": "bullish" | "bearish" | "neutral"
        }

    Note: This is a partial implementation. Full conviction scoring
    requires block trade data, FII flow data, sector data, and futures
    basis data which are not yet available through the Fyers API alone.
    Currently computes PCR-based signal only.
    """
    signals = {}
    weights = settings.CONVICTION_WEIGHTS

    # PCR signal
    try:
        index_symbol = _equity_to_index(symbol)
        pcr_data = compute_pcr(index_symbol)
        pcr = pcr_data["pcr"]
        if pcr > settings.PCR_EXTREME_BEARISH_ABOVE:
            pcr_score = -1.0
        elif pcr < settings.PCR_EXTREME_BULLISH_BELOW:
            pcr_score = 1.0
        else:
            pcr_score = 0.0
        signals["oi_pcr_extreme"] = {"score": pcr_score, "weight": weights["oi_pcr_extreme"]}
    except Exception as e:
        logger.debug(f"PCR signal failed: {e}")
        signals["oi_pcr_extreme"] = {"score": 0.0, "weight": weights["oi_pcr_extreme"]}

    # Other signals default to 0 until data sources are integrated
    for key in weights:
        if key not in signals:
            signals[key] = {"score": 0.0, "weight": weights[key]}

    # Weighted average
    total_score = sum(s["score"] * s["weight"] for s in signals.values())

    if total_score > 0.2:
        verdict = "bullish"
    elif total_score < -0.2:
        verdict = "bearish"
    else:
        verdict = "neutral"

    result = {
        "symbol": symbol,
        "conviction_score": round(total_score, 4),
        "signals": signals,
        "verdict": verdict,
    }
    logger.info(f"Conviction for {symbol}: {total_score:.4f} ({verdict})")
    return result


def _equity_to_index(symbol: str) -> str:
    """Map equity symbol to its parent index for OI analysis."""
    # Simple mapping — extend as needed
    nifty_50 = {"NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ", "NSE:HDFCBANK-EQ",
                "NSE:ICICIBANK-EQ", "NSE:HINDUNILVR-EQ", "NSE:ITC-EQ", "NSE:SBIN-EQ",
                "NSE:BHARTIARTL-EQ", "NSE:KOTAKBANK-EQ"}
    if symbol in nifty_50:
        return "NSE:NIFTY50-INDEX"
    return "NSE:NIFTY50-INDEX"  # default fallback
