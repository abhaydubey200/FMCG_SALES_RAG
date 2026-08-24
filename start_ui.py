"""
Start the application stack locally (without Docker).
For Docker-based deployment, use docker compose instead.
"""
import subprocess
import sys
import time
import webbrowser
import urllib.request


def check_api():
    try:
        resp = urllib.request.urlopen("http://localhost:8000/health")
        print(f"API is already running: {resp.read().decode()}")
        return True
    except Exception:
        return False


def main():
    api_proc = None

    # Start FastAPI backend
    if not check_api():
        print("Starting FastAPI backend...")
        api_proc = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "src.api.main:app",
             "--host", "0.0.0.0", "--port", "8000"],
        )
        print(f"   API PID: {api_proc.pid}")
        time.sleep(5)
        try:
            resp = urllib.request.urlopen("http://localhost:8000/health")
            print(f"   API ready: {resp.read().decode()}")
        except Exception as e:
            print(f"   Warning: API may not be fully ready yet: {e}")

    # Frontend is now Next.js — open in browser
    url = "http://localhost:3000"
    print(f"\nFrontend URL: {url}")
    print("(For local dev, run: cd frontend && npm run dev)")
    print(f"\nOpening browser at {url}...")
    webbrowser.open(url)

    print("\nServices:")
    print("  API:      http://localhost:8000")
    print("  Frontend: http://localhost:3000")
    print("  Docs:     http://localhost:8000/docs")
    print("\nPress Ctrl+C to stop the API server.")

    if api_proc:
        try:
            api_proc.wait()
        except KeyboardInterrupt:
            print("\nStopping services...")
            api_proc.terminate()
            print("Done.")
    else:
        print("\nAPI was already running — not stopping it.")
        print("To stop: use RagStop.bat or docker compose down")


if __name__ == "__main__":
    main()
