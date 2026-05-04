# MCP + gRPC Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert Analyzer into a dual-interface server — gRPC for the frontend server, MCP for AI-assisted development — with a shared core library.

**Architecture:** Three layers: `core/` (all business logic), `grpc_service/` (proto + server wrapping core), `mcp/` (MCP tools wrapping core). Both servers are separate processes importing the same core. Existing `auth/fyers_login.py` is refactored into `core/auth.py`.

**Tech Stack:** Python 3.9+, fyers-apiv3, grpcio, grpcio-tools, grpcio-reflection, mcp SDK

---

## Phase 1: Core Library

### Task 1: Create `core/auth.py` — refactor from `auth/fyers_login.py`

**Files:**
- Create: `core/__init__.py`
- Create: `core/auth.py`
- Modify: `auth/fyers_login.py` (make it re-export from core)

- [ ] **Step 1: Create `core/__init__.py`**

```python
# core/__init__.py
```

Empty init file.

- [ ] **Step 2: Create `core/auth.py`**

Copy the entire contents of `auth/fyers_login.py` into `core/auth.py` with these changes:

1. Remove the `sys.path.insert` hack (line 50-52) — core/ is at the project root so `config.settings` is directly importable
2. Update `TOKEN_DIR` to point to `auth/` directory (not `core/`):
   ```python
   TOKEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "auth")
   ```
3. Add a `get_profile()` function at the end (before `if __name__`):
   ```python
   def get_profile() -> dict:
       """Get account profile from Fyers API."""
       client = get_fyers_client()
       resp = client.get_profile()
       if resp.get("s") == "ok":
           return resp.get("data", {})
       raise RuntimeError(f"Profile fetch failed: {resp}")
   ```
4. Remove the `if __name__ == "__main__"` CLI block (that stays in `auth/fyers_login.py`)

- [ ] **Step 3: Update `auth/fyers_login.py` to re-export from core**

Replace the entire file with:

```python
"""
Backwards-compatible wrapper — imports from core/auth.py.
Run this file directly to test login.
"""
import sys
import os
import logging

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core.auth import (
    get_fyers_token,
    get_fyers_client,
    get_profile,
    refresh_access_token,
    full_totp_login,
)

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s"
    )

    print("\n" + "=" * 55)
    print("  FYERS AUTO LOGIN")
    print("=" * 55)

    token = get_fyers_token()

    if token:
        print(f"\n  Token:  {token[:25]}...{token[-10:]}")
        print(f"  Status: LOGIN SUCCESSFUL ✓")
        try:
            profile = get_profile()
            print(f"  Name:   {profile.get('name', '?')}")
            print(f"  ID:     {profile.get('fy_id', '?')}")
        except Exception as e:
            print(f"  Profile check: {e}")
    else:
        print("\n  Status: LOGIN FAILED ✗")

    print("=" * 55 + "\n")
```

- [ ] **Step 4: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('core/auth.py', encoding='utf-8').read()); print('core/auth.py OK')"
python -c "import ast; ast.parse(open('auth/fyers_login.py', encoding='utf-8').read()); print('auth/fyers_login.py OK')"
```
Expected: Both print OK

- [ ] **Step 5: Commit**

```bash
git add core/__init__.py core/auth.py auth/fyers_login.py
git commit -m "refactor: extract core/auth.py from auth/fyers_login.py"
```

---

### Task 2: Create `core/market.py` — market data functions

**Files:**
- Create: `core/market.py`

- [ ] **Step 1: Create `core/market.py`**

```python
"""
Market data extraction from Fyers API.

All functions use get_client() from core.auth for authentication.
"""
import logging
from core.auth import get_fyers_client

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
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('core/market.py', encoding='utf-8').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add core/market.py
git commit -m "feat: add core/market.py — quotes, option chain, depth, historical"
```

---

### Task 3: Create `core/orders.py` — order management functions

**Files:**
- Create: `core/orders.py`

- [ ] **Step 1: Create `core/orders.py`**

```python
"""
Order management via Fyers API.

All functions use get_client() from core.auth for authentication.
Fyers order side: 1 = Buy, -1 = Sell
Fyers order type: 1 = Limit, 2 = Market, 3 = SL-Market, 4 = SL-Limit
Fyers product type: INTRADAY, CNC, MARGIN, CO, BO
"""
import logging
from core.auth import get_fyers_client

logger = logging.getLogger(__name__)


def place_order(symbol: str, qty: int, side: int, order_type: int,
                product_type: str = "INTRADAY", limit_price: float = 0,
                stop_price: float = 0, disclosed_qty: int = 0,
                validity: str = "DAY", offline_order: bool = False) -> dict:
    """
    Place a new order.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"
        qty: Quantity to trade.
        side: 1 = Buy, -1 = Sell.
        order_type: 1 = Limit, 2 = Market, 3 = SL-Market, 4 = SL-Limit.
        product_type: "INTRADAY", "CNC", "MARGIN", "CO", "BO".
        limit_price: Limit price (for Limit/SL-Limit orders).
        stop_price: Stop/trigger price (for SL orders).
        disclosed_qty: Disclosed quantity.
        validity: "DAY" or "IOC".
        offline_order: True for AMO (After Market Order).

    Returns:
        Fyers API response with order_id on success.

    Raises:
        RuntimeError: If order placement fails.
    """
    client = get_fyers_client()
    data = {
        "symbol": symbol,
        "qty": qty,
        "type": order_type,
        "side": side,
        "productType": product_type,
        "limitPrice": limit_price,
        "stopPrice": stop_price,
        "disclosedQty": disclosed_qty,
        "validity": validity,
        "offlineOrder": offline_order,
    }
    resp = client.place_order(data)
    if resp.get("s") == "ok":
        logger.info(f"Order placed: {resp.get('id', '?')}")
        return resp
    raise RuntimeError(f"Place order failed: {resp}")


def modify_order(order_id: str, qty: int = 0, order_type: int = 0,
                 limit_price: float = 0, stop_price: float = 0) -> dict:
    """
    Modify an existing order.

    Args:
        order_id: The order ID to modify.
        qty: New quantity (0 = no change).
        order_type: New order type (0 = no change).
        limit_price: New limit price (0 = no change).
        stop_price: New stop price (0 = no change).

    Returns:
        Fyers API response.

    Raises:
        RuntimeError: If modification fails.
    """
    client = get_fyers_client()
    data = {"id": order_id}
    if qty:
        data["qty"] = qty
    if order_type:
        data["type"] = order_type
    if limit_price:
        data["limitPrice"] = limit_price
    if stop_price:
        data["stopPrice"] = stop_price
    resp = client.modify_order(data)
    if resp.get("s") == "ok":
        logger.info(f"Order modified: {order_id}")
        return resp
    raise RuntimeError(f"Modify order failed: {resp}")


def cancel_order(order_id: str) -> dict:
    """
    Cancel an existing order.

    Args:
        order_id: The order ID to cancel.

    Returns:
        Fyers API response.

    Raises:
        RuntimeError: If cancellation fails.
    """
    client = get_fyers_client()
    data = {"id": order_id}
    resp = client.cancel_order(data)
    if resp.get("s") == "ok":
        logger.info(f"Order cancelled: {order_id}")
        return resp
    raise RuntimeError(f"Cancel order failed: {resp}")


def get_order_book() -> dict:
    """Get all orders for the day."""
    client = get_fyers_client()
    resp = client.orderbook()
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Order book failed: {resp}")


def get_trade_book() -> dict:
    """Get all executed trades for the day."""
    client = get_fyers_client()
    resp = client.tradebook()
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Trade book failed: {resp}")


def get_positions() -> dict:
    """Get open positions."""
    client = get_fyers_client()
    resp = client.positions()
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Positions failed: {resp}")


def get_holdings() -> dict:
    """Get portfolio holdings."""
    client = get_fyers_client()
    resp = client.holdings()
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Holdings failed: {resp}")


def get_funds() -> dict:
    """Get available funds and margins."""
    client = get_fyers_client()
    resp = client.funds()
    if resp.get("s") == "ok":
        return resp
    raise RuntimeError(f"Funds failed: {resp}")
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('core/orders.py', encoding='utf-8').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add core/orders.py
git commit -m "feat: add core/orders.py — place, modify, cancel, books, positions, holdings, funds"
```

---

### Task 4: Create `core/compute.py` — analytics functions

**Files:**
- Create: `core/compute.py`
- Read: `config/settings.py` (uses thresholds from here)

- [ ] **Step 1: Create `core/compute.py`**

```python
"""
Compute analytics from market data.

Consumes data from core.market, applies thresholds from config.settings,
and produces analysis results.
"""
import logging
from core.market import get_option_chain, get_quotes
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
```

- [ ] **Step 2: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('core/compute.py', encoding='utf-8').read()); print('OK')"
```
Expected: OK

- [ ] **Step 3: Commit**

```bash
git add core/compute.py
git commit -m "feat: add core/compute.py — PCR, max pain, delivery, conviction"
```

---

### Task 5: Update `config/settings.py` — add server config

**Files:**
- Modify: `config/settings.py`

- [ ] **Step 1: Add gRPC and MCP config to settings.py**

Append to the end of `config/settings.py`:

```python

# ============================================================
# gRPC SERVER
# ============================================================
GRPC_HOST = os.getenv("GRPC_HOST", "0.0.0.0")
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))

# ============================================================
# MCP SERVER
# ============================================================
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")  # "stdio" or "sse"
```

- [ ] **Step 2: Commit**

```bash
git add config/settings.py
git commit -m "feat: add GRPC_HOST, GRPC_PORT, MCP_TRANSPORT to settings"
```

---

## Phase 2: gRPC Server

### Task 6: Create protobuf definitions

**Files:**
- Create: `grpc_service/__init__.py`
- Create: `grpc_service/fyers.proto`

- [ ] **Step 1: Create `grpc_service/__init__.py`**

Empty init file.

- [ ] **Step 2: Create `grpc_service/fyers.proto`**

```protobuf
syntax = "proto3";

package fyers;

// ============================================================
// Common messages
// ============================================================

message Empty {}

message ErrorResponse {
  string error = 1;
}

// ============================================================
// Auth Service
// ============================================================

message TokenResponse {
  string access_token = 1;
}

message ProfileResponse {
  string name = 1;
  string fy_id = 2;
  string email = 3;
  string pan = 4;
}

service AuthService {
  rpc GetToken(Empty) returns (TokenResponse);
  rpc RefreshToken(Empty) returns (TokenResponse);
  rpc GetProfile(Empty) returns (ProfileResponse);
}

// ============================================================
// Market Service
// ============================================================

message QuotesRequest {
  repeated string symbols = 1;
}

message QuotesResponse {
  string data_json = 1;  // JSON-encoded Fyers response
}

message OptionChainRequest {
  string symbol = 1;
  int32 strike_count = 2;
}

message OptionChainResponse {
  string data_json = 1;
}

message MarketDepthRequest {
  string symbol = 1;
}

message MarketDepthResponse {
  string data_json = 1;
}

message HistoricalDataRequest {
  string symbol = 1;
  string resolution = 2;
  string from_date = 3;
  string to_date = 4;
}

message HistoricalDataResponse {
  string data_json = 1;
}

service MarketService {
  rpc GetQuotes(QuotesRequest) returns (QuotesResponse);
  rpc GetOptionChain(OptionChainRequest) returns (OptionChainResponse);
  rpc GetMarketDepth(MarketDepthRequest) returns (MarketDepthResponse);
  rpc GetHistoricalData(HistoricalDataRequest) returns (HistoricalDataResponse);
}

// ============================================================
// Order Service
// ============================================================

message PlaceOrderRequest {
  string symbol = 1;
  int32 qty = 2;
  int32 side = 3;            // 1 = Buy, -1 = Sell
  int32 order_type = 4;      // 1=Limit, 2=Market, 3=SL-M, 4=SL-L
  string product_type = 5;   // INTRADAY, CNC, MARGIN, CO, BO
  double limit_price = 6;
  double stop_price = 7;
  int32 disclosed_qty = 8;
  string validity = 9;       // DAY, IOC
  bool offline_order = 10;
}

message ModifyOrderRequest {
  string order_id = 1;
  int32 qty = 2;
  int32 order_type = 3;
  double limit_price = 4;
  double stop_price = 5;
}

message CancelOrderRequest {
  string order_id = 1;
}

message OrderResponse {
  string data_json = 1;
}

message OrderBookResponse {
  string data_json = 1;
}

message TradeBookResponse {
  string data_json = 1;
}

message PositionsResponse {
  string data_json = 1;
}

message HoldingsResponse {
  string data_json = 1;
}

message FundsResponse {
  string data_json = 1;
}

service OrderService {
  rpc PlaceOrder(PlaceOrderRequest) returns (OrderResponse);
  rpc ModifyOrder(ModifyOrderRequest) returns (OrderResponse);
  rpc CancelOrder(CancelOrderRequest) returns (OrderResponse);
  rpc GetOrderBook(Empty) returns (OrderBookResponse);
  rpc GetTradeBook(Empty) returns (TradeBookResponse);
  rpc GetPositions(Empty) returns (PositionsResponse);
  rpc GetHoldings(Empty) returns (HoldingsResponse);
  rpc GetFunds(Empty) returns (FundsResponse);
}

// ============================================================
// Compute Service
// ============================================================

message ComputeRequest {
  string symbol = 1;
}

message PCRResponse {
  string symbol = 1;
  double pcr = 2;
  int64 total_put_oi = 3;
  int64 total_call_oi = 4;
  string signal = 5;
}

message MaxPainResponse {
  string symbol = 1;
  double max_pain_strike = 2;
  double current_price = 3;
  double deviation_pct = 4;
  bool within_buffer = 5;
}

message DeliveryResponse {
  string symbol = 1;
  int64 volume = 2;
  double delivery_pct = 3;
  string signal = 4;
}

message ConvictionResponse {
  string symbol = 1;
  double conviction_score = 2;
  string signals_json = 3;  // JSON-encoded signal details
  string verdict = 4;
}

service ComputeService {
  rpc ComputePCR(ComputeRequest) returns (PCRResponse);
  rpc ComputeMaxPain(ComputeRequest) returns (MaxPainResponse);
  rpc ComputeDelivery(ComputeRequest) returns (DeliveryResponse);
  rpc ComputeConviction(ComputeRequest) returns (ConvictionResponse);
}
```

- [ ] **Step 3: Commit**

```bash
git add grpc_service/__init__.py grpc_service/fyers.proto
git commit -m "feat: add gRPC protobuf definitions for all 4 services"
```

---

### Task 7: Generate protobuf stubs and create codegen script

**Files:**
- Create: `grpc_service/codegen.py`
- Create: `grpc_service/generated/__init__.py`
- Generate: `grpc_service/generated/fyers_pb2.py`
- Generate: `grpc_service/generated/fyers_pb2_grpc.py`

- [ ] **Step 1: Create `grpc_service/codegen.py`**

```python
"""
Regenerate gRPC stubs from fyers.proto.

Run: python grpc_service/codegen.py
Output goes to grpc_service/generated/
"""
import os
import subprocess
import sys

PROTO_DIR = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(PROTO_DIR, "generated")
PROTO_FILE = os.path.join(PROTO_DIR, "fyers.proto")

os.makedirs(OUT_DIR, exist_ok=True)

# Create __init__.py in generated/ if missing
init_file = os.path.join(OUT_DIR, "__init__.py")
if not os.path.exists(init_file):
    open(init_file, "w").close()

cmd = [
    sys.executable, "-m", "grpc_tools.protoc",
    f"--proto_path={PROTO_DIR}",
    f"--python_out={OUT_DIR}",
    f"--grpc_python_out={OUT_DIR}",
    PROTO_FILE,
]

print(f"Running: {' '.join(cmd)}")
result = subprocess.run(cmd, capture_output=True, text=True)

if result.returncode == 0:
    print("Codegen OK")
else:
    print(f"Codegen FAILED:\n{result.stderr}")
    sys.exit(1)
```

- [ ] **Step 2: Run codegen**

Run:
```bash
pip install grpcio grpcio-tools grpcio-reflection
python grpc_service/codegen.py
```
Expected: `Codegen OK` and files appear in `grpc_service/generated/`

- [ ] **Step 3: Fix import path in generated grpc file**

The generated `fyers_pb2_grpc.py` will have `import fyers_pb2 as fyers__pb2`. This needs to be a relative import. Run:

```bash
python -c "
path = 'grpc_service/generated/fyers_pb2_grpc.py'
code = open(path, encoding='utf-8').read()
code = code.replace('import fyers_pb2 as fyers__pb2', 'from . import fyers_pb2 as fyers__pb2')
open(path, 'w', encoding='utf-8').write(code)
print('Import fix applied')
"
```

- [ ] **Step 4: Commit**

```bash
git add grpc_service/codegen.py grpc_service/generated/
git commit -m "feat: add gRPC codegen script and generated stubs"
```

---

### Task 8: Create gRPC server implementation

**Files:**
- Create: `grpc_service/server.py`
- Create: `run_grpc.py`

- [ ] **Step 1: Create `grpc_service/server.py`**

```python
"""
gRPC server — thin wrappers around core/ functions.

Consumed by the frontend server and other backend services.
"""
import json
import logging
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

from grpc_service.generated import fyers_pb2, fyers_pb2_grpc
from core import auth, market, orders, compute

logger = logging.getLogger(__name__)


class AuthServicer(fyers_pb2_grpc.AuthServiceServicer):

    def GetToken(self, request, context):
        try:
            token = auth.get_fyers_token()
            if not token:
                context.set_code(grpc.StatusCode.INTERNAL)
                context.set_details("All login strategies failed")
                return fyers_pb2.TokenResponse()
            return fyers_pb2.TokenResponse(access_token=token)
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.TokenResponse()

    def RefreshToken(self, request, context):
        try:
            cached = auth.load_token()
            if not cached.get("refresh_token"):
                context.set_code(grpc.StatusCode.FAILED_PRECONDITION)
                context.set_details("No refresh token available")
                return fyers_pb2.TokenResponse()
            tokens = auth.refresh_access_token(cached["refresh_token"])
            if tokens.get("access_token"):
                auth.save_token(tokens)
                return fyers_pb2.TokenResponse(access_token=tokens["access_token"])
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details("Refresh failed")
            return fyers_pb2.TokenResponse()
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.TokenResponse()

    def GetProfile(self, request, context):
        try:
            profile = auth.get_profile()
            return fyers_pb2.ProfileResponse(
                name=profile.get("name", ""),
                fy_id=profile.get("fy_id", ""),
                email=profile.get("email", ""),
                pan=profile.get("pan", ""),
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.ProfileResponse()


class MarketServicer(fyers_pb2_grpc.MarketServiceServicer):

    def GetQuotes(self, request, context):
        try:
            resp = market.get_quotes(list(request.symbols))
            return fyers_pb2.QuotesResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.QuotesResponse()

    def GetOptionChain(self, request, context):
        try:
            strike_count = request.strike_count if request.strike_count else 10
            resp = market.get_option_chain(request.symbol, strike_count)
            return fyers_pb2.OptionChainResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.OptionChainResponse()

    def GetMarketDepth(self, request, context):
        try:
            resp = market.get_market_depth(request.symbol)
            return fyers_pb2.MarketDepthResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.MarketDepthResponse()

    def GetHistoricalData(self, request, context):
        try:
            resp = market.get_historical_data(
                request.symbol, request.resolution,
                request.from_date, request.to_date
            )
            return fyers_pb2.HistoricalDataResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.HistoricalDataResponse()


class OrderServicer(fyers_pb2_grpc.OrderServiceServicer):

    def PlaceOrder(self, request, context):
        try:
            resp = orders.place_order(
                symbol=request.symbol,
                qty=request.qty,
                side=request.side,
                order_type=request.order_type,
                product_type=request.product_type or "INTRADAY",
                limit_price=request.limit_price,
                stop_price=request.stop_price,
                disclosed_qty=request.disclosed_qty,
                validity=request.validity or "DAY",
                offline_order=request.offline_order,
            )
            return fyers_pb2.OrderResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.OrderResponse()

    def ModifyOrder(self, request, context):
        try:
            resp = orders.modify_order(
                order_id=request.order_id,
                qty=request.qty,
                order_type=request.order_type,
                limit_price=request.limit_price,
                stop_price=request.stop_price,
            )
            return fyers_pb2.OrderResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.OrderResponse()

    def CancelOrder(self, request, context):
        try:
            resp = orders.cancel_order(request.order_id)
            return fyers_pb2.OrderResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.OrderResponse()

    def GetOrderBook(self, request, context):
        try:
            resp = orders.get_order_book()
            return fyers_pb2.OrderBookResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.OrderBookResponse()

    def GetTradeBook(self, request, context):
        try:
            resp = orders.get_trade_book()
            return fyers_pb2.TradeBookResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.TradeBookResponse()

    def GetPositions(self, request, context):
        try:
            resp = orders.get_positions()
            return fyers_pb2.PositionsResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.PositionsResponse()

    def GetHoldings(self, request, context):
        try:
            resp = orders.get_holdings()
            return fyers_pb2.HoldingsResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.HoldingsResponse()

    def GetFunds(self, request, context):
        try:
            resp = orders.get_funds()
            return fyers_pb2.FundsResponse(data_json=json.dumps(resp))
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.FundsResponse()


class ComputeServicer(fyers_pb2_grpc.ComputeServiceServicer):

    def ComputePCR(self, request, context):
        try:
            result = compute.compute_pcr(request.symbol)
            return fyers_pb2.PCRResponse(
                symbol=result["symbol"],
                pcr=result["pcr"],
                total_put_oi=result["total_put_oi"],
                total_call_oi=result["total_call_oi"],
                signal=result["signal"],
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.PCRResponse()

    def ComputeMaxPain(self, request, context):
        try:
            result = compute.compute_max_pain(request.symbol)
            return fyers_pb2.MaxPainResponse(
                symbol=result["symbol"],
                max_pain_strike=result["max_pain_strike"],
                current_price=result["current_price"],
                deviation_pct=result["deviation_pct"],
                within_buffer=result["within_buffer"],
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.MaxPainResponse()

    def ComputeDelivery(self, request, context):
        try:
            result = compute.compute_delivery(request.symbol)
            return fyers_pb2.DeliveryResponse(
                symbol=result["symbol"],
                volume=result["volume"],
                delivery_pct=result["delivery_pct"],
                signal=result["signal"],
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.DeliveryResponse()

    def ComputeConviction(self, request, context):
        try:
            result = compute.compute_conviction(request.symbol)
            return fyers_pb2.ConvictionResponse(
                symbol=result["symbol"],
                conviction_score=result["conviction_score"],
                signals_json=json.dumps(result["signals"]),
                verdict=result["verdict"],
            )
        except Exception as e:
            context.set_code(grpc.StatusCode.INTERNAL)
            context.set_details(str(e))
            return fyers_pb2.ConvictionResponse()


def serve(host: str = "0.0.0.0", port: int = 50051):
    """Start the gRPC server."""
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    fyers_pb2_grpc.add_AuthServiceServicer_to_server(AuthServicer(), server)
    fyers_pb2_grpc.add_MarketServiceServicer_to_server(MarketServicer(), server)
    fyers_pb2_grpc.add_OrderServiceServicer_to_server(OrderServicer(), server)
    fyers_pb2_grpc.add_ComputeServiceServicer_to_server(ComputeServicer(), server)

    # Enable reflection for grpcurl / grpc-web discovery
    service_names = (
        fyers_pb2.DESCRIPTOR.services_by_name["AuthService"].full_name,
        fyers_pb2.DESCRIPTOR.services_by_name["MarketService"].full_name,
        fyers_pb2.DESCRIPTOR.services_by_name["OrderService"].full_name,
        fyers_pb2.DESCRIPTOR.services_by_name["ComputeService"].full_name,
        reflection.SERVICE_NAME,
    )
    reflection.enable_server_reflection(service_names, server)

    addr = f"{host}:{port}"
    server.add_insecure_port(addr)
    server.start()
    logger.info(f"gRPC server listening on {addr}")
    print(f"gRPC server listening on {addr}")
    server.wait_for_termination()
```

- [ ] **Step 2: Create `run_grpc.py` entry point**

```python
"""Entry point: start the gRPC server."""
import logging
import config.settings as settings
from grpc_service.server import serve

if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s [%(name)s]: %(message)s"
    )
    serve(host=settings.GRPC_HOST, port=settings.GRPC_PORT)
```

- [ ] **Step 3: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('grpc_service/server.py', encoding='utf-8').read()); print('server OK')"
python -c "import ast; ast.parse(open('run_grpc.py', encoding='utf-8').read()); print('run_grpc OK')"
```
Expected: Both OK

- [ ] **Step 4: Commit**

```bash
git add grpc_service/server.py run_grpc.py
git commit -m "feat: add gRPC server with all 4 servicers and entry point"
```

---

## Phase 3: MCP Server

### Task 9: Create MCP server with all tools

**Files:**
- Create: `mcp/server.py`
- Create: `run_mcp.py`

- [ ] **Step 1: Create `mcp/server.py`**

```python
"""
MCP server — exposes Fyers operations as tools for Claude Code / Claude Desktop.

Thin wrappers around core/ functions. Run via run_mcp.py.
"""
import json
from mcp.server.fastmcp import FastMCP

from core import auth, market, orders, compute

mcp = FastMCP("Fyers Analyzer")


# ============================================================
# AUTH TOOLS
# ============================================================

@mcp.tool()
def get_token() -> str:
    """Get a valid Fyers API access token. Uses cached/refreshed/fresh login as needed."""
    token = auth.get_fyers_token()
    if not token:
        return "ERROR: All login strategies failed. Check .env credentials."
    return f"Token: {token[:25]}...{token[-10:]}"


@mcp.tool()
def refresh_token() -> str:
    """Force refresh the Fyers access token using the stored refresh token."""
    cached = auth.load_token()
    if not cached.get("refresh_token"):
        return "ERROR: No refresh token available. Need full TOTP login."
    tokens = auth.refresh_access_token(cached["refresh_token"])
    if tokens.get("access_token"):
        auth.save_token(tokens)
        return f"Refreshed. Token: {tokens['access_token'][:25]}..."
    return "ERROR: Refresh failed. Refresh token may be expired."


@mcp.tool()
def get_profile() -> str:
    """Get Fyers account profile (name, ID, email)."""
    try:
        profile = auth.get_profile()
        return json.dumps(profile, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# MARKET TOOLS
# ============================================================

@mcp.tool()
def get_quotes(symbols: str) -> str:
    """
    Get real-time quotes for symbols.

    Args:
        symbols: Comma-separated Fyers symbols, e.g. "NSE:RELIANCE-EQ,NSE:TCS-EQ"
    """
    try:
        symbol_list = [s.strip() for s in symbols.split(",")]
        resp = market.get_quotes(symbol_list)
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_option_chain(symbol: str, strike_count: int = 10) -> str:
    """
    Get option chain data for a symbol.

    Args:
        symbol: Fyers symbol, e.g. "NSE:NIFTY50-INDEX"
        strike_count: Number of strikes above/below ATM (default 10)
    """
    try:
        resp = market.get_option_chain(symbol, strike_count)
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_market_depth(symbol: str) -> str:
    """
    Get Level 2 market depth (bid/ask) for a symbol.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"
    """
    try:
        resp = market.get_market_depth(symbol)
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_historical_data(symbol: str, resolution: str,
                        from_date: str, to_date: str) -> str:
    """
    Get historical OHLCV candle data.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"
        resolution: Candle size — "1", "5", "15", "30", "60", "D", "W", "M"
        from_date: Start date as "YYYY-MM-DD"
        to_date: End date as "YYYY-MM-DD"
    """
    try:
        resp = market.get_historical_data(symbol, resolution, from_date, to_date)
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# ORDER TOOLS
# ============================================================

@mcp.tool()
def place_order(symbol: str, qty: int, side: int, order_type: int,
                product_type: str = "INTRADAY", limit_price: float = 0,
                stop_price: float = 0) -> str:
    """
    Place a new order.

    Args:
        symbol: Fyers symbol, e.g. "NSE:RELIANCE-EQ"
        qty: Quantity to trade
        side: 1 = Buy, -1 = Sell
        order_type: 1=Limit, 2=Market, 3=SL-Market, 4=SL-Limit
        product_type: INTRADAY, CNC, MARGIN, CO, BO
        limit_price: Limit price (for Limit/SL-Limit orders)
        stop_price: Stop/trigger price (for SL orders)
    """
    try:
        resp = orders.place_order(
            symbol=symbol, qty=qty, side=side, order_type=order_type,
            product_type=product_type, limit_price=limit_price,
            stop_price=stop_price,
        )
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def modify_order(order_id: str, qty: int = 0, order_type: int = 0,
                 limit_price: float = 0, stop_price: float = 0) -> str:
    """
    Modify an existing order.

    Args:
        order_id: The order ID to modify
        qty: New quantity (0 = no change)
        order_type: New order type (0 = no change)
        limit_price: New limit price (0 = no change)
        stop_price: New stop price (0 = no change)
    """
    try:
        resp = orders.modify_order(
            order_id=order_id, qty=qty, order_type=order_type,
            limit_price=limit_price, stop_price=stop_price,
        )
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def cancel_order(order_id: str) -> str:
    """
    Cancel an existing order.

    Args:
        order_id: The order ID to cancel
    """
    try:
        resp = orders.cancel_order(order_id)
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_order_book() -> str:
    """Get all orders for the day."""
    try:
        resp = orders.get_order_book()
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_trade_book() -> str:
    """Get all executed trades for the day."""
    try:
        resp = orders.get_trade_book()
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_positions() -> str:
    """Get open positions."""
    try:
        resp = orders.get_positions()
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_holdings() -> str:
    """Get portfolio holdings."""
    try:
        resp = orders.get_holdings()
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def get_funds() -> str:
    """Get available funds and margins."""
    try:
        resp = orders.get_funds()
        return json.dumps(resp, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


# ============================================================
# COMPUTE TOOLS
# ============================================================

@mcp.tool()
def compute_pcr(symbol: str) -> str:
    """
    Compute Put-Call Ratio from option chain.

    Args:
        symbol: Index symbol, e.g. "NSE:NIFTY50-INDEX"
    """
    try:
        result = compute.compute_pcr(symbol)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def compute_max_pain(symbol: str) -> str:
    """
    Calculate max pain strike price from option chain.

    Args:
        symbol: Index symbol, e.g. "NSE:NIFTY50-INDEX"
    """
    try:
        result = compute.compute_max_pain(symbol)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def compute_delivery(symbol: str) -> str:
    """
    Compute delivery percentage analysis.

    Args:
        symbol: Equity symbol, e.g. "NSE:RELIANCE-EQ"
    """
    try:
        result = compute.compute_delivery(symbol)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"ERROR: {e}"


@mcp.tool()
def compute_conviction(symbol: str) -> str:
    """
    Compute conviction score — weighted combination of market signals.

    Args:
        symbol: Equity symbol, e.g. "NSE:RELIANCE-EQ"
    """
    try:
        result = compute.compute_conviction(symbol)
        return json.dumps(result, indent=2)
    except Exception as e:
        return f"ERROR: {e}"
```

- [ ] **Step 2: Create `run_mcp.py` entry point**

```python
"""Entry point: start the MCP server."""
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s [%(name)s]: %(message)s"
)

from mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
```

**IMPORTANT:** The import `from mcp.server import mcp` refers to `mcp/server.py` in our project (the module we created), not the `mcp` pip package. This works because Python resolves local packages first. The `mcp` pip package is imported inside `mcp/server.py` as `from mcp.server.fastmcp import FastMCP`.

- [ ] **Step 3: Verify syntax**

Run:
```bash
python -c "import ast; ast.parse(open('mcp/server.py', encoding='utf-8').read()); print('mcp/server.py OK')"
python -c "import ast; ast.parse(open('run_mcp.py', encoding='utf-8').read()); print('run_mcp.py OK')"
```
Expected: Both OK

- [ ] **Step 4: Commit**

```bash
git add mcp/server.py run_mcp.py
git commit -m "feat: add MCP server with all 19 tools and entry point"
```

---

### Task 10: Update `requirements.txt` and update `mcp/__init__.py`

**Files:**
- Modify: `requirements.txt`
- Modify: `mcp/__init__.py`

- [ ] **Step 1: Write `requirements.txt`**

```
# Fyers API
fyers-apiv3
pyotp
requests
python-dotenv

# gRPC
grpcio>=1.60.0
grpcio-tools>=1.60.0
grpcio-reflection>=1.60.0

# MCP
mcp>=1.0.0
```

- [ ] **Step 2: Ensure `mcp/__init__.py` is empty**

The file must exist but be empty (no imports) to avoid circular import issues with the `mcp` pip package.

- [ ] **Step 3: Commit**

```bash
git add requirements.txt mcp/__init__.py
git commit -m "feat: add dependencies to requirements.txt"
```

---

### Task 11: Final verification

- [ ] **Step 1: Verify all files exist**

Run:
```bash
python -c "
import os
files = [
    'core/__init__.py', 'core/auth.py', 'core/market.py', 'core/orders.py', 'core/compute.py',
    'grpc_service/__init__.py', 'grpc_service/fyers.proto', 'grpc_service/codegen.py',
    'grpc_service/server.py', 'grpc_service/generated/__init__.py',
    'grpc_service/generated/fyers_pb2.py', 'grpc_service/generated/fyers_pb2_grpc.py',
    'mcp/server.py', 'run_grpc.py', 'run_mcp.py', 'requirements.txt',
]
for f in files:
    status = 'OK' if os.path.exists(f) else 'MISSING'
    print(f'  {status}: {f}')
"
```
Expected: All OK

- [ ] **Step 2: Verify all Python files have valid syntax**

Run:
```bash
python -c "
import ast, glob
for f in glob.glob('core/*.py') + glob.glob('grpc_service/*.py') + glob.glob('mcp/server.py') + ['run_grpc.py', 'run_mcp.py']:
    try:
        ast.parse(open(f, encoding='utf-8').read())
        print(f'  OK: {f}')
    except SyntaxError as e:
        print(f'  FAIL: {f} — {e}')
"
```
Expected: All OK

- [ ] **Step 3: Install deps and verify imports**

Run:
```bash
pip install -r requirements.txt
python -c "import grpc; print(f'grpc {grpc.__version__}')"
python -c "from mcp.server.fastmcp import FastMCP; print('MCP SDK OK')"
```

- [ ] **Step 4: Final commit if needed**

```bash
git status
# If any uncommitted changes remain:
git add -A
git commit -m "chore: final cleanup for MCP + gRPC server"
```
