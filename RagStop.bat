@echo off
echo ============================================
echo  Amazon RAG - Stopping services...
echo ============================================
echo.

:: Kill uvicorn (FastAPI backend)
echo Stopping FastAPI backend...
taskkill /FI "WINDOWTITLE eq RAG-API*" /F >nul 2>&1
taskkill /FI "IMAGENAME eq python.exe" /FI "WINDOWTITLE eq RAG-API*" /F >nul 2>&1

:: Kill streamlit (UI)
echo Stopping Streamlit UI...
taskkill /FI "WINDOWTITLE eq RAG-UI*" /F >nul 2>&1
taskkill /FI "IMAGENAME eq streamlit.exe" /FI "WINDOWTITLE eq RAG-UI*" /F >nul 2>&1

:: Also try to kill by port usage
echo Cleaning up any remaining processes...
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8000 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1
for /f "tokens=5" %%a in ('netstat -aon ^| findstr :8501 ^| findstr LISTENING') do taskkill /PID %%a /F >nul 2>&1

echo.
echo ============================================
echo  All services stopped.
echo ============================================
echo.
pause
