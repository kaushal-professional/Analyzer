# Save this as debug_step4.py and run it
import base64, json, requests, pyotp
from urllib.parse import parse_qs, urlparse

CLIENT_ID     = "OBOYSW9YS8-100"
SECRET_KEY    = "WNRN977P34"
REDIRECT_URI  = "https://v0-fyersanalysis.vercel.app"
FY_ID         = "FAI84781"
PIN           = "3005"
TOTP_SECRET   = "363HLCNHI7RJMTG7RXLEMYCHWPL33ZWZ"

H = {"Accept":"application/json","Content-Type":"application/json",
     "User-Agent":"Mozilla/5.0","Origin":"https://api-t1.fyers.in","Referer":"https://api-t1.fyers.in/"}

# Step 1
r = requests.post("https://api-t2.fyers.in/vagator/v2/send_login_otp", json={"fy_id":FY_ID,"app_id":"2"}, headers=H)
rk = r.json()["request_key"]

# Step 2
otp = pyotp.TOTP(TOTP_SECRET).now()
r = requests.post("https://api-t2.fyers.in/vagator/v2/verify_otp", json={"request_key":rk,"otp":otp}, headers=H)
rk = r.json()["request_key"]

# Step 3
r = requests.post("https://api-t2.fyers.in/vagator/v2/verify_pin", json={"request_key":rk,"identity_type":"pin","identifier":PIN}, headers=H)
access_token = r.json()["data"]["access_token"]

# Step 4 — PRINT FULL RESPONSE
h = {**H, "Authorization": f"Bearer {access_token}"}
payload = {"fyers_id":FY_ID,"app_id":CLIENT_ID.split("-")[0],"redirect_uri":REDIRECT_URI,
           "appType":"100","code_challenge":"","state":"sample_state","scope":"","nonce":"",
           "response_type":"code","create_cookie":True}
r = requests.post("https://api-t1.fyers.in/api/v3/token", json=payload, headers=h)
d = r.json()

print("\n=== FULL STEP 4 RESPONSE ===")
print(json.dumps(d, indent=2))
print("============================\n")