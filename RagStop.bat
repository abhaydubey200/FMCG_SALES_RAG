@echo off
echo ============================================
echo  Sales & Marketing Intelligence Platform
echo  Stopping services...
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

echo.
echo ============================================
echo  All services stopped.
echo  Data volumes preserved:
echo    - PostgreSQL data (uploaded datasets, semantic mappings)
echo    - Redis cache
echo    - Knowledge base documents
echo ============================================
echo.
echo To restart: double-click RagStart.bat
echo To remove ALL data: docker compose down -v
echo.
pause
