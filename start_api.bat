@echo off
title RAG-API
set PYTHONPATH=.
cd /d "%~dp0"
python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
pause
