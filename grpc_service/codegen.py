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
