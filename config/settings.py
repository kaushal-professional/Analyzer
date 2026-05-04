"""
Central settings — credentials + thresholds + timing.
All magic numbers live here, nowhere else.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ============================================================
# FYERS CREDENTIALS
# ============================================================
FYERS_APP_ID        = os.getenv("FYERS_APP_ID")
FYERS_SECRET_KEY    = os.getenv("FYERS_SECRET_KEY")
FYERS_REDIRECT_URL  = os.getenv("FYERS_REDIRECT_URL")
FYERS_USERNAME      = os.getenv("FYERS_USERNAME")
FYERS_PIN           = os.getenv("FYERS_PIN")
FYERS_TOTP_SECRET   = os.getenv("FYERS_TOTP_SECRET")

# ============================================================
# DATABASE (Supabase Postgres — direct connection)
# ============================================================
DATABASE_URL = os.getenv("DATABASE_URL")

# ============================================================
# BLOCK TRADE THRESHOLDS
# ============================================================
BLOCK_THRESHOLD_LARGE_CAP = 30_000_000 ## 3Crores
BLOCK_THRESHOLD_SMALL_CAP = 5_200_000 ## 52 Lakhs

# ============================================================
# SIGNAL THRESHOLDS
# ============================================================
PCR_EXTREME_BEARISH_ABOVE = 1.3
PCR_EXTREME_BULLISH_BELOW = 0.7
VIX_LOW_BELOW              = 15
VIX_HIGH_ABOVE             = 20
DELIVERY_HIGH_ABOVE        = 50
DELIVERY_LOW_BELOW         = 30
MAX_PAIN_BUFFER_PCT        = 5.0

# ============================================================
# CONVICTION SCORE WEIGHTS (must sum to 1.0)
# ============================================================
CONVICTION_WEIGHTS = {
    "block_direction":  0.20,
    "oi_pcr_extreme":   0.15,
    "oi_direction":     0.15,
    "max_pain_align":   0.10,
    "delivery_pct":     0.10,
    "fii_flow":         0.10,
    "vix_regime":       0.05,
    "volume_spike":     0.05,
    "sector_cluster":   0.05,
    "futures_basis":    0.05,
}

# ============================================================
# TIMING (IST)
# ============================================================
MARKET_OPEN  = "09:15"
MARKET_CLOSE = "15:30"
OPTION_CHAIN_INTERVAL_MIN = 15

# ============================================================
# gRPC SERVER
# ============================================================
GRPC_HOST = os.getenv("GRPC_HOST", "0.0.0.0")
GRPC_PORT = int(os.getenv("GRPC_PORT", "50051"))

# ============================================================
# TELEGRAM BOT (auto-login notifications + /frc command)
# ============================================================
TELEGRAM_BOT_TOKEN      = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID        = os.getenv("TELEGRAM_CHAT_ID")
# Must be HTTPS (Telegram requirement); typically a TLS-terminating proxy in front of TELEGRAM_WEBHOOK_PORT.
TELEGRAM_WEBHOOK_URL    = os.getenv("TELEGRAM_WEBHOOK_URL")
TELEGRAM_WEBHOOK_HOST   = os.getenv("TELEGRAM_WEBHOOK_HOST", "0.0.0.0")
TELEGRAM_WEBHOOK_PORT   = int(os.getenv("TELEGRAM_WEBHOOK_PORT", "8080"))
TELEGRAM_WEBHOOK_SECRET = os.getenv("TELEGRAM_WEBHOOK_SECRET")

# ============================================================
# SCHEDULER
# ============================================================
SCHEDULER_TRIGGER_TIME  = os.getenv("SCHEDULER_TRIGGER_TIME", "09:13")  # HH:MM IST
