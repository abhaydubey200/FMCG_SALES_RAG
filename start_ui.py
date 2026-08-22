import subprocess
import sys
import time
import webbrowser
import urllib.request

# First check if API is running
try:
    resp = urllib.request.urlopen("http://localhost:8000/health")
    print(f"✓ API is already running: {resp.read().decode()}")
except Exception:
    print("Starting FastAPI backend...")
    api_proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "8000"],
    )
    print(f"   API PID: {api_proc.pid}")
    time.sleep(5)
    try:
        resp = urllib.request.urlopen("http://localhost:8000/health")
        print(f"   API ready: {resp.read().decode()}")
    except Exception as e:
        print(f"   Warning: API may not be fully ready yet: {e}")

# Start Streamlit
print("\nStarting Streamlit UI...")
streamlit_proc = subprocess.Popen(
    [sys.executable, "-m", "streamlit", "run", "ui/streamlit_app.py",
     "--server.port", "8501", "--server.headless", "true"],
)
print(f"   Streamlit PID: {streamlit_proc.pid}")

time.sleep(3)

# Open browser
url = "http://localhost:8501"
print(f"\nOpening browser at {url}...")
webbrowser.open(url)

print("\n✓ Both services are running:")
print("  API:    http://localhost:8000")
print("  UI:     http://localhost:8501")
print("  Docs:   http://localhost:8000/docs")
print("\nPress Ctrl+C to stop all services.")

try:
    streamlit_proc.wait()
except KeyboardInterrupt:
    print("\nStopping services...")
    streamlit_proc.terminate()
    try:
        api_proc.terminate()
    except NameError:
        pass
    print("Done.")
