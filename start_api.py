import subprocess
import time
import sys

proc = subprocess.Popen(
    [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    cwd=__import__("os").path.dirname(__import__("os").path.abspath(__file__))
)

print(f"API server started with PID {proc.pid}")
print("Waiting for server to be ready...")
time.sleep(5)

try:
    import urllib.request
    resp = urllib.request.urlopen("http://localhost:8000/health")
    print(f"API health check: {resp.read().decode()}")
except Exception as e:
    print(f"Health check failed: {e}")
    print("Server may still be starting...")

print("\nAPI is running at http://localhost:8000")
print("API docs at http://localhost:8000/docs")
print("Press Ctrl+C to stop")
proc.wait()
