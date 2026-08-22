@echo off
echo ============================================
echo  Amazon RAG - Sales & Marketing Intelligence
echo  Starting services...
echo ============================================
echo.

:: Navigate to script directory
cd /d "%~dp0"

:: Check if data exists, if not generate it
if not exist "data\warehouse.db" (
    echo [1/3] Generating synthetic dataset...
    set PYTHONPATH=.
    python src\ingestion\data_generator.py
) else (
    echo [1/3] Dataset already exists, skipping generation.
)

:: Check if vector store exists, if not build it
if not exist "data\vector_store.pkl" (
    echo [2/3] Building vector store...
    set PYTHONPATH=.
    python -c "from src.retrieval.vector_store import build_and_persist_vector_store; build_and_persist_vector_store()"
) else (
    echo [2/3] Vector store already exists, skipping build.
)

:: Create .env if missing
if not exist ".env" (
    echo [3/3] Creating .env from template...
    copy .env.example .env >nul 2>&1
) else (
    echo [3/3] .env already exists.
)

echo.
echo Starting FastAPI backend on port 8000...
start "RAG-API" cmd /k "set PYTHONPATH=. && python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000"
ping 127.0.0.1 -n 4 >nul

:: Wait for API to be ready
echo Waiting for API to start...
timeout /t 5 /nobreak >nul

echo Starting Streamlit UI on port 8501...
start "RAG-UI" cmd /k "set API_BASE_URL=http://localhost:8000 && python -m streamlit run ui/streamlit_app.py"

echo.
echo ============================================
echo  Services started!
echo    API:    http://localhost:8000
echo    UI:     http://localhost:8501
echo    Docs:   http://localhost:8000/docs
echo ============================================
echo.
echo Press any key to exit this window (services keep running)...
pause >nul
