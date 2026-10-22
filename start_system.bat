@echo off
echo =====================================================================
echo  STARTING MULTI-AGENT HOSPITAL OPERATIONS SYSTEM
echo =====================================================================
echo.

cd /d "%~dp0"

echo [1/2] Starting FastAPI Backend on http://localhost:8000...
start "Hospital Backend (FastAPI)" cmd /k "cd backend && python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload"

echo [2/2] Starting React Vite Frontend on http://localhost:5173...
start "Hospital Frontend (React/Vite)" cmd /k "cd frontend && npm run dev -- --port 5173 --host"

echo.
echo =====================================================================
echo  SYSTEM LAUNCHED SUCCESSFULLY
echo  - Frontend URL: http://localhost:5173
echo  - Backend API:  http://localhost:8000/docs
echo  - Credentials:  ADM-001 / hospital@123 (Administrator)
echo                  DOC-001 / hospital@123 (Doctor)
echo =====================================================================
