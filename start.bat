@echo off
echo ==============================================
echo  Starting Agentic Data Analyst Project
echo ==============================================

cd /d "%~dp0"

echo [1/3] Starting PostgreSQL Server...
"C:\Program Files\PostgreSQL\17\bin\pg_ctl.exe" start -D "%~dp0pgdata" -l "%~dp0pg.log"

timeout /t 2 /nobreak >nul

echo [2/3] Starting FastAPI Backend on http://localhost:8000...
start "FastAPI Backend (Port 8000)" cmd /k ""%~dp0.venv\Scripts\python.exe" -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000"

timeout /t 2 /nobreak >nul

echo [3/3] Starting Streamlit UI on http://localhost:8501...
start "Streamlit Web UI (Port 8501)" cmd /k ""%~dp0.venv\Scripts\python.exe" -m streamlit run ui/streamlit_app.py"

echo.
echo ==============================================
echo Application is up and running!
echo Web UI:      http://localhost:8501
echo API Docs:    http://localhost:8000/docs
echo ==============================================
pause
