@echo off
echo ============================================
echo  Amazon RAG - Stopping services...
echo ============================================
echo.

:: Navigate to script directory
cd /d "%~dp0"

:: Stop Docker Compose services (preserves volumes/data)
echo Stopping Docker Compose services...
docker compose down
if %ERRORLEVEL% neq 0 (
    echo WARNING: docker compose down returned an error.
    echo Attempting to stop containers individually...
    docker compose stop
)

:: Also kill any lingering Streamlit processes (legacy cleanup)
echo Cleaning up any legacy processes...
taskkill /FI "IMAGENAME eq streamlit.exe" /F >nul 2>&1

echo.
echo ============================================
echo  All services stopped.
echo  Data volumes preserved (PostgreSQL, Redis).
echo ============================================
echo.
pause
