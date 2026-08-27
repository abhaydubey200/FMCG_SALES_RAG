@echo off
echo ============================================
echo  Sales & Marketing Intelligence Platform
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
    echo [1/5] Creating .env from template...
    copy .env.example .env >nul 2>&1
) else (
    echo [1/5] .env already exists.
)

echo [2/5] Starting PostgreSQL and Redis...
docker compose up -d postgres redis
if %ERRORLEVEL% neq 0 (
    echo ERROR: Failed to start database services.
    pause
    exit /b 1
)

echo [3/5] Waiting for database health...
set /a RETRY=0
:WAIT_DB
set /a RETRY+=1
if %RETRY% gtr 30 (
    echo WARNING: Database may not be fully healthy.
    goto START_SERVICES
)
docker compose exec -T postgres pg_isready -U ragsql >nul 2>&1
if %ERRORLEVEL% neq 0 (
    timeout /t 2 /nobreak >nul
    goto WAIT_DB
)
echo        Database is healthy.

:START_SERVICES
echo [4/5] Starting API, Worker, Frontend, and Nginx...
docker compose up -d api worker frontend nginx
if %ERRORLEVEL% neq 0 (
    echo WARNING: Some services may have failed to start.
    echo Check: docker compose ps
)

echo [5/5] Waiting for API health...
set /a RETRY=0
:WAIT_API
set /a RETRY+=1
if %RETRY% gtr 20 (
    echo WARNING: API may not be fully healthy after 40 seconds.
    goto SHOW_STATUS
)
curl -s http://localhost:8000/health >nul 2>&1
if %ERRORLEVEL% neq 0 (
    timeout /t 2 /nobreak >nul
    goto WAIT_API
)
echo        API is healthy.

:: Run database migrations (safe to run multiple times)
echo        Running database migrations...
docker compose exec -T api python -m src.database.migrate >nul 2>&1
docker compose exec -T api python -m src.database.migrate_dynamic >nul 2>&1
docker compose exec -T api python -m src.database.migrate_persistence >nul 2>&1
echo        Migrations complete.

:SHOW_STATUS
echo.
echo ============================================
echo  Service Status:
echo ============================================
docker compose ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
echo.
echo ============================================
echo  Application URLs:
echo    Frontend:  http://localhost:3000
echo    API:       http://localhost:8000
echo    API Docs:  http://localhost:8000/docs
echo    Nginx:     http://localhost:80
echo ============================================
echo.
echo Press any key to exit this window (services keep running)...
pause >nul
