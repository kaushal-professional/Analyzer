"""
Order management via Fyers API.

All functions use get_client() from auth for authentication.
Fyers order side: 1 = Buy, -1 = Sell
Fyers order type: 1 = Limit, 2 = Market, 3 = SL-Market, 4 = SL-Limit
Fyers product type: INTRADAY, CNC, MARGIN, CO, BO
"""
import logging
from auth.auth import get_fyers_client

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
