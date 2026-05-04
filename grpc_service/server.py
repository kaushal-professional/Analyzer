"""
gRPC server — thin wrappers around domain modules.

Consumed by the frontend server and other backend services.
"""
import json
import logging
from concurrent import futures

import grpc
from grpc_reflection.v1alpha import reflection

from grpc_service.generated import fyers_pb2, fyers_pb2_grpc
import auth, market, orders, compute

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
