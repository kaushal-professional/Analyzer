# Analyzer MCP + gRPC Server — Design Spec

**Date:** 2026-04-15
**Scope:** Convert Analyzer into a dual-interface server: gRPC for the frontend server and other backend services, MCP for AI-assisted development/debugging.

---

## System Context

```
End User  →  Frontend Server  →  [gRPC]  →  Analyzer (this project)
                                               ├── core/auth      (Fyers login, token mgmt)
                                               ├── core/market     (quotes, option chain, historical)
                                               ├── core/compute    (PCR, max pain, delivery, conviction)
                                               ├── core/orders     (place, modify, cancel, books)
                                               └── db/             (Supabase for persistence)

Developer →  Claude Code/Desktop  →  [MCP stdio]  →  Analyzer MCP Server
```

- **Analyzer** is a data extraction + computation backend. Not user-facing.
- **Frontend Server** (separate project) connects end users to this backend via gRPC.
- **MCP Server** is for developer/AI interaction — debugging, ad-hoc queries, inspecting state.
- **Data flow is dual-mode:** scheduled jobs run pipelines on a cron (premarket, market hours, EOD, monthly), and gRPC serves both stored results and on-demand queries.

---

## Core Library (`core/`)

All business logic lives here. Both MCP and gRPC are thin wrappers.

### `core/auth.py`

Refactored from `auth/fyers_login.py`. Same logic, same 3-strategy approach. Public API:

| Function | Description |
|----------|-------------|
| `get_token() -> str` | Returns valid access token (cached/refreshed/fresh) |
| `get_client() -> FyersModel` | Returns ready-to-use Fyers SDK client |
| `refresh_token() -> str` | Force refresh, returns new token |
| `get_profile() -> dict` | Get account profile from Fyers |

### `core/market.py`

Market data extraction. Uses `get_client()` from `core/auth`.

| Function | Description |
|----------|-------------|
| `get_quotes(symbols: list[str]) -> dict` | Real-time quotes for given symbols |
| `get_option_chain(symbol: str, strike_count: int) -> dict` | Option chain data |
| `get_market_depth(symbol: str) -> dict` | Level 2 market depth |
| `get_historical_data(symbol: str, resolution: str, from_date: str, to_date: str) -> dict` | OHLCV candle data |

### `core/orders.py`

Order management. Uses `get_client()` from `core/auth`.

| Function | Description |
|----------|-------------|
| `place_order(symbol: str, qty: int, side: int, type: int, price: float, ...) -> dict` | Place new order |
| `modify_order(order_id: str, qty: int, price: float, ...) -> dict` | Modify existing order |
| `cancel_order(order_id: str) -> dict` | Cancel an order |
| `get_order_book() -> dict` | All orders for the day |
| `get_trade_book() -> dict` | All executed trades |
| `get_positions() -> dict` | Open positions |
| `get_holdings() -> dict` | Portfolio holdings |
| `get_funds() -> dict` | Available funds/margins |

### `core/compute.py`

Computation layer. Consumes market data, produces analytics.

| Function | Description |
|----------|-------------|
| `compute_pcr(symbol: str) -> dict` | Put-Call Ratio from option chain |
| `compute_max_pain(symbol: str) -> dict` | Max pain strike calculation |
| `compute_delivery(symbol: str) -> dict` | Delivery percentage analysis |
| `compute_conviction(symbol: str) -> dict` | Conviction score (weighted signals) |

---

## gRPC Service (`grpc_service/`)

### Proto Definition (`grpc_service/fyers.proto`)

Three gRPC services mapping to core modules:

```
service AuthService {
  rpc GetToken(Empty) returns (TokenResponse);
  rpc RefreshToken(Empty) returns (TokenResponse);
  rpc GetProfile(Empty) returns (ProfileResponse);
}

service MarketService {
  rpc GetQuotes(QuotesRequest) returns (QuotesResponse);
  rpc GetOptionChain(OptionChainRequest) returns (OptionChainResponse);
  rpc GetMarketDepth(MarketDepthRequest) returns (MarketDepthResponse);
  rpc GetHistoricalData(HistoricalDataRequest) returns (HistoricalDataResponse);
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

service ComputeService {
  rpc ComputePCR(ComputeRequest) returns (ComputeResponse);
  rpc ComputeMaxPain(ComputeRequest) returns (ComputeResponse);
  rpc ComputeDelivery(ComputeRequest) returns (ComputeResponse);
  rpc ComputeConviction(ComputeRequest) returns (ComputeResponse);
}
```

### Server (`grpc_service/server.py`)

- Thin wrappers calling core functions
- Runs on configurable port (default 50051)
- Reflection enabled for discoverability
- Graceful shutdown on SIGINT/SIGTERM

### Generated Code (`grpc_service/generated/`)

- Auto-generated from `.proto` via `grpc_tools.protoc`
- `fyers_pb2.py` (message classes) and `fyers_pb2_grpc.py` (service stubs)
- Regenerated via a script, never hand-edited

---

## MCP Server (`mcp/server.py`)

For developer/AI interaction via Claude Code or Claude Desktop.

### Tools (same operations as gRPC, exposed as `@mcp.tool()`)

**Auth tools:**
- `get_token()` — get current valid token
- `refresh_token()` — force refresh
- `get_profile()` — account info

**Market tools:**
- `get_quotes(symbols)` — real-time quotes
- `get_option_chain(symbol, strike_count)` — option chain
- `get_market_depth(symbol)` — L2 data
- `get_historical_data(symbol, resolution, from_date, to_date)` — candles

**Order tools:**
- `place_order(symbol, qty, side, type, price)` — place order
- `modify_order(order_id, qty, price)` — modify order
- `cancel_order(order_id)` — cancel order
- `get_order_book()` — all orders
- `get_trade_book()` — all trades
- `get_positions()` — positions
- `get_holdings()` — holdings
- `get_funds()` — funds

**Compute tools:**
- `compute_pcr(symbol)` — put-call ratio
- `compute_max_pain(symbol)` — max pain
- `compute_delivery(symbol)` — delivery analysis
- `compute_conviction(symbol)` — conviction score

### Transport

- stdio (default, for Claude Code)
- SSE (optional, for Claude Desktop remote)

---

## File Structure

```
Analyzer/
├── core/
│   ├── __init__.py
│   ├── auth.py              (refactored from auth/fyers_login.py)
│   ├── market.py            (new)
│   ├── orders.py            (new)
│   └── compute.py           (new)
├── mcp/
│   ├── __init__.py
│   └── server.py            (MCP tools wrapping core/)
├── grpc_service/
│   ├── __init__.py
│   ├── fyers.proto          (protobuf definitions)
│   ├── server.py            (gRPC server wrapping core/)
│   ├── codegen.py           (script to regenerate stubs)
│   └── generated/
│       ├── __init__.py
│       ├── fyers_pb2.py     (auto-generated)
│       └── fyers_pb2_grpc.py (auto-generated)
├── auth/
│   ├── __init__.py          (re-exports from core/auth for backwards compat)
│   └── fyers_login.py       (kept as-is, imports from core/auth)
├── config/
│   └── settings.py          (add GRPC_PORT, MCP_TRANSPORT)
├── jobs/                    (unchanged — scheduled pipelines)
├── db/                      (unchanged — Supabase persistence)
├── run_grpc.py              (entry point: start gRPC server)
├── run_mcp.py               (entry point: start MCP server)
└── requirements.txt         (add grpcio, grpcio-tools, mcp)
```

---

## Config Additions (`config/settings.py`)

```python
GRPC_HOST = os.getenv("GRPC_HOST", "0.0.0.0")
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))
MCP_TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")  # "stdio" or "sse"
```

---

## Dependencies

```
# Existing
fyers-apiv3
pyotp
requests
python-dotenv

# New — gRPC
grpcio>=1.60.0
grpcio-tools>=1.60.0
grpcio-reflection>=1.60.0

# New — MCP
mcp>=1.0.0
```

---

## Non-goals

- No database schema changes (DB layer is separate concern)
- No frontend server (separate project)
- No authentication/authorization on gRPC (trusted internal network for now)
- No streaming RPCs in v1 (can add later for real-time quotes)
- No Docker/deployment config (separate concern)
