@echo off
echo Starting ClauseGuard Local Analysis Service...
cd /d "%~dp0"
if exist ".venv\Scripts\python.exe" (
    ".venv\Scripts\python.exe" -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
) else (
    uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
)
pause
