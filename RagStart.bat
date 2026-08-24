@echo off
echo ============================================
echo  Amazon RAG - Sales & Marketing Intelligence
echo  Starting services via Docker Compose...
echo ============================================
echo.

:: Navigate to script directory
cd /d "%~dp0"

:: Check Docker is available
where docker >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker is not installed or not in PATH.
    echo Please install Docker Desktop: https://docs.docker.com/get-docker/
    pause
    exit /b 1
)

:: Check Docker daemon is running
docker info >nul 2>&1
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker daemon is not running.
    echo Please start Docker Desktop and try again.
    pause
    exit /b 1
)

:: Create .env if missing
if not exist ".env" (
    echo [1/4] Creating .env from template...
    copy .env.example .env >nul 2>&1
) else (
    echo [1/4] .env already exists.
)

echo [2/4] Building and starting Docker containers...
docker compose up -d --build
if %ERRORLEVEL% neq 0 (
    echo ERROR: Docker Compose failed to start. Check the output above.
    pause
    exit /b 1
)

echo [3/4] Waiting for services to be healthy...
set /a RETRY=0
:WAIT_LOOP
set /a RETRY+=1
if %RETRY% gtr 30 (
    echo WARNING: Services may not be fully healthy after 60 seconds.
    echo Check: docker compose ps
    goto SHOW_STATUS
)
curl -s http://localhost:8000/health >nul 2>&1
if %ERRORLEVEL% neq 0 (
    timeout /t 2 /nobreak >nul
    goto WAIT_LOOP
)
echo        API is healthy.

:SHOW_STATUS
echo [4/4] Service status:
docker compose ps

echo.
echo ============================================
echo  Services started!
echo    API:      http://localhost:8000
echo    Frontend: http://localhost:3000
echo    Docs:     http://localhost:8000/docs
echo ============================================
echo.
echo Press any key to exit this window (services keep running)...
pause >nul
